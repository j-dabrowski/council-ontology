"""
Shared validation logic for Level 3c and Level 4.

Provides:
  - Quote classification (three-tier: full match, stripped match, paraphrase)
  - Five per-document metrics: quote completeness, paraphrase rate, coverage ratio,
    inventory agreement, keyword gap rate
  - determine_status() → PASS / REVIEW / FAIL
  - validate_doc() — assembles all five metrics for one document
  - DB helpers and data loaders

Imported by scripts/validate_sample.py (Level 3c) and
scripts/validate_extraction.py (Level 4).
"""

import json
import re
import sqlite3
from pathlib import Path

from pypdf import PdfReader

_REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = _REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# High-signal keywords: uncovered occurrences suggest a missed entity.
GAP_KEYWORDS: dict[str, str] = {
    "MOVED":                   r"\bMOVED\b",
    "CARRIED":                 r"\bCARRIED\b",
    "LOST":                    r"\bLOST\b",
    "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
    "DECLARATION OF INTEREST": r"DECLARATION OF INTEREST",
    "DEPUTATION":              r"\bDEPUTATION\b",
    "PETITION":                r"\bPETITION\b",
}

# (inventory_field, db_table, WHERE clause using ? for meeting_id)
INVENTORY_FIELDS: list[tuple[str, str, str]] = [
    ("motion_count",             "motions",               "meeting_id = ?"),
    ("planning_count",           "planning_applications", "motion_id IN (SELECT id FROM motions WHERE meeting_id = ?)"),
    ("interest_count",           "interest_declarations", "meeting_id = ?"),
    ("public_question_count",    "public_questions",      "meeting_id = ?"),
    ("deputation_count",         "deputations",           "meeting_id = ?"),
    ("petition_count",           "petitions",             "meeting_id = ?"),
    ("appointment_count",        "appointments",          "meeting_id = ?"),
    ("tender_count",             "tenders",               "meeting_id = ?"),
    ("budget_item_count",        "budget_items",          "meeting_id = ?"),
    ("committee_report_count",   "committee_reports",     "meeting_id = ?"),
    ("delegated_decision_count", "delegated_decisions",   "meeting_id = ?"),
    ("building_permit_count",    "building_permits",      "meeting_id = ?"),
]

# (db_table, WHERE clause using ? for meeting_id) — entity types that must have source quotes.
ENTITY_QUOTE_TABLES: list[tuple[str, str]] = [
    ("motions",               "meeting_id = ?"),
    ("planning_applications", "motion_id IN (SELECT id FROM motions WHERE meeting_id = ?)"),
    ("public_questions",      "meeting_id = ?"),
    ("deputations",           "meeting_id = ?"),
    ("petitions",             "meeting_id = ?"),
    ("appointments",          "meeting_id = ?"),
    ("committee_reports",     "meeting_id = ?"),
    ("budget_items",          "meeting_id = ?"),
    ("interest_declarations", "meeting_id = ?"),
    ("tenders",               "meeting_id = ?"),
    ("delegated_decisions",   "meeting_id = ?"),
    ("building_permits",      "meeting_id = ?"),
    ("other_items",           "meeting_id = ?"),
]

_MIN_STRIPPED_LEN = 15  # skip stripped matching for very short quotes (false positive risk)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_census() -> dict[str, dict]:
    path = DATA_DIR / "census.json"
    if not path.exists():
        raise FileNotFoundError(f"Census not found at {path}. Run 'council census' first.")
    return {d["filename"]: d for d in json.loads(path.read_text())["documents"]}


def load_inventory(stem: str) -> dict | None:
    path = DATA_DIR / "inventories" / f"{stem}.json"
    return json.loads(path.read_text()) if path.exists() else None


def extract_pdf_text(council: str, filename: str) -> str:
    path = RAW_DIR / council / filename
    if not path.exists():
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# DB helpers (raw sqlite3)
# ---------------------------------------------------------------------------

def find_meeting(conn: sqlite3.Connection, filename: str) -> dict | None:
    rows = conn.execute(
        "SELECT id, meeting_date, meeting_type FROM meetings WHERE minutes_pdf_path LIKE ?",
        (f"%{filename}",),
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    return {"id": r[0], "meeting_date": r[1], "meeting_type": r[2]}


def get_quotes(conn: sqlite3.Connection, meeting_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT entity_table, quote_text FROM extraction_evidence WHERE meeting_id = ?",
        (meeting_id,),
    ).fetchall()
    return [{"entity_table": r[0], "quote_text": r[1]} for r in rows if r[1]]


def get_entity_counts(conn: sqlite3.Connection, meeting_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for inv_field, table, where in INVENTORY_FIELDS:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {where}", (meeting_id,)
        ).fetchone()[0]
        counts[inv_field] = n
    return counts


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _norm_stripped(s: str) -> str:
    """Remove everything except letters and digits (handles pypdf word-split artefacts)."""
    return re.sub(r"[^a-zA-Z0-9]", "", s)


def _strip_page_headers(text: str) -> str:
    """Remove pypdf page header lines that embed Windows file paths (H:\\...).

    Council minutes PDFs repeat a header on every page; pypdf extracts these
    inline between content, breaking verbatim quote matching across page breaks.
    """
    cleaned = [
        line for line in text.split("\n")
        if "H:\\" not in line and "H:/" not in line
    ]
    return "\n".join(cleaned)


def _find_partial_match(norm_quote: str, norm_source: str, min_words: int = 4) -> dict | None:
    words = norm_quote.split()
    for n in range(len(words), min_words - 1, -1):
        prefix = " ".join(words[:n])
        idx = norm_source.find(prefix)
        if idx >= 0:
            end = min(idx + len(norm_quote) + 40, len(norm_source))
            return {
                "matched_words": n,
                "total_words": len(words),
                "source_context": norm_source[idx:end].strip(),
            }
    return None


# ---------------------------------------------------------------------------
# Quote classification — three tiers, single pass
# ---------------------------------------------------------------------------

def _classify_quotes(quotes: list[dict], source_text: str) -> list[dict]:
    """Classify each quote as full match, stripped match, or paraphrase.

    Tier 1: whitespace-normalised verbatim match.
    Tier 2: stripped alphanumeric match (handles pypdf word-split artefacts).
             Span recovered via position-mapping array for coverage computation.
    Tier 3: paraphrase — content genuinely differs.
    """
    norm_source = _norm(source_text)
    strip_to_norm: list[int] = [i for i, ch in enumerate(norm_source) if ch.isalnum()]
    stripped_source = _norm_stripped(norm_source)

    classified: list[dict] = []
    for q in quotes:
        nq = _norm(q["quote_text"])
        base = {"entity_table": q["entity_table"], "quote_text": q["quote_text"]}

        idx = norm_source.find(nq)
        if idx >= 0:
            classified.append({**base, "match_type": "full",
                                "norm_start": idx, "norm_end": idx + len(nq)})
            continue

        snq = _norm_stripped(nq)
        if len(snq) >= _MIN_STRIPPED_LEN:
            sidx = stripped_source.find(snq)
            if sidx >= 0:
                send = sidx + len(snq) - 1
                norm_start = strip_to_norm[sidx] if sidx < len(strip_to_norm) else None
                norm_end = (strip_to_norm[send] + 1) if send < len(strip_to_norm) else None
                classified.append({**base, "match_type": "stripped",
                                   "norm_start": norm_start, "norm_end": norm_end})
                continue

        partial = _find_partial_match(nq, norm_source)
        classified.append({**base, "match_type": "paraphrase",
                           "norm_start": None, "norm_end": None,
                           "partial_match": partial})

    return classified


# ---------------------------------------------------------------------------
# Metric computations
# ---------------------------------------------------------------------------

def compute_paraphrase_rate(
    classified: list[dict],
) -> tuple[int, int, int, float, list[dict]]:
    """Return (paraphrased, stripped_matched, total, rate, paraphrase_examples)."""
    total = len(classified)
    paraphrased = 0
    stripped_matched = 0
    examples: list[dict] = []
    for c in classified:
        if c["match_type"] == "paraphrase":
            paraphrased += 1
            examples.append({
                "entity_table": c["entity_table"],
                "quote": c["quote_text"],
                "partial_match": c.get("partial_match"),
            })
        elif c["match_type"] == "stripped":
            stripped_matched += 1
    rate = paraphrased / total if total else 0.0
    return paraphrased, stripped_matched, total, rate, examples


def compute_coverage(classified: list[dict], source_text: str, max_chars: int | None = None) -> float:
    """Fraction of the extraction window covered by matched quotes (full + stripped)."""
    if max_chars is not None and max_chars < len(source_text):
        window = len(_norm(source_text[:max_chars]))
    else:
        window = len(_norm(source_text))
    if window == 0:
        return 0.0
    covered: set[int] = set()
    for c in classified:
        if c["norm_start"] is not None and c["norm_end"] is not None:
            covered.update(range(c["norm_start"], c["norm_end"]))
    return len(covered) / window


def compute_inventory_agreement(l1_inventory: dict, extracted_counts: dict) -> dict[str, dict]:
    inv = l1_inventory.get("inventory", {})
    result: dict[str, dict] = {}
    for inv_field, _table, _where in INVENTORY_FIELDS:
        l1_val = inv.get(inv_field) or 0
        ext_val = extracted_counts.get(inv_field, 0)
        if l1_val == 0 and ext_val == 0:
            ratio: float = 1.0
            flag = False
        elif l1_val == 0:
            ratio = float("inf")
            flag = True
        else:
            ratio = ext_val / l1_val
            flag = ratio < 0.4 or ratio > 2.5
        result[inv_field] = {"l1": l1_val, "extracted": ext_val, "ratio": round(ratio, 3), "flag": flag}
    return result


def compute_keyword_gaps(classified: list[dict], source_text: str) -> dict:
    """Keyword hits in normalised source text not covered by any matched quote span."""
    norm_source = _norm(source_text)
    spans: list[tuple[int, int]] = [
        (c["norm_start"], c["norm_end"])
        for c in classified
        if c["norm_start"] is not None and c["norm_end"] is not None
    ]

    total_hits = 0
    uncovered_hits = 0
    gap_examples: list[dict] = []

    for kw, pattern in GAP_KEYWORDS.items():
        for m in re.finditer(pattern, norm_source):
            pos = m.start()
            total_hits += 1
            if not any(s <= pos < e for s, e in spans):
                uncovered_hits += 1
                if len(gap_examples) < 5:
                    snippet = norm_source[max(0, pos - 30): pos + 60].strip()
                    gap_examples.append({"keyword": kw, "pos": pos, "snippet": snippet})

    gap_rate = uncovered_hits / total_hits if total_hits > 0 else 0.0
    return {
        "total_hits": total_hits,
        "uncovered_hits": uncovered_hits,
        "gap_rate": round(gap_rate, 4),
        "gap_examples": gap_examples,
    }


def compute_quote_completeness(conn: sqlite3.Connection, meeting_id: int) -> dict:
    """Fraction of extracted entities that have at least one source quote."""
    total_entities = 0
    entities_with_quotes = 0
    missing_by_table: dict[str, int] = {}

    for table, where in ENTITY_QUOTE_TABLES:
        n_total = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {where}", (meeting_id,)
        ).fetchone()[0]
        n_with = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) FROM extraction_evidence "
            "WHERE meeting_id = ? AND entity_table = ?",
            (meeting_id, table),
        ).fetchone()[0]
        total_entities += n_total
        entities_with_quotes += n_with
        missing = n_total - n_with
        if missing > 0:
            missing_by_table[table] = missing

    rate = entities_with_quotes / total_entities if total_entities > 0 else 1.0
    return {
        "total_entities": total_entities,
        "entities_with_quotes": entities_with_quotes,
        "completeness_rate": round(rate, 4),
        "missing_by_table": missing_by_table,
    }


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------

def determine_status(
    para_rate: float,
    cov_ratio: float,
    gap_rate: float,
    quote_count: int,
    completeness_rate: float = 1.0,
) -> str:
    if quote_count == 0:
        return "FAIL"
    if para_rate >= 0.80 and cov_ratio < 0.02:
        return "FAIL"
    if completeness_rate < 0.50:
        return "FAIL"
    if para_rate >= 0.50 or cov_ratio < 0.03 or gap_rate >= 0.40 or completeness_rate < 0.80:
        return "REVIEW"
    return "PASS"


# ---------------------------------------------------------------------------
# Per-document validation
# ---------------------------------------------------------------------------

def validate_doc(
    conn: sqlite3.Connection,
    council: str,
    filename: str,
    census: dict,
    max_chars: int | None = None,
) -> dict:
    """Run all five metrics for one document. Returns a result dict.

    On error (meeting not in DB, empty PDF) returns a minimal dict with
    an 'error' key and status='FAIL'.
    """
    stem = Path(filename).stem

    meeting = find_meeting(conn, filename)
    if meeting is None:
        return {"filename": filename, "error": "meeting not found in DB", "status": "FAIL"}

    meeting_id = meeting["id"]
    quotes = get_quotes(conn, meeting_id)
    entity_counts = get_entity_counts(conn, meeting_id)
    l1_inventory = load_inventory(stem)

    source_text = _strip_page_headers(extract_pdf_text(council, filename))
    classified = _classify_quotes(quotes, source_text)

    para_n, stripped_n, para_total, para_rate, para_examples = compute_paraphrase_rate(classified)
    cov_ratio = compute_coverage(classified, source_text, max_chars=max_chars)
    inv_agreement = compute_inventory_agreement(l1_inventory, entity_counts) if l1_inventory else None
    kw_gap = compute_keyword_gaps(classified, source_text)
    completeness = compute_quote_completeness(conn, meeting_id)

    status = determine_status(
        para_rate, cov_ratio, kw_gap["gap_rate"], para_total,
        completeness_rate=completeness["completeness_rate"],
    )

    return {
        "filename": filename,
        "meeting_id": meeting_id,
        "meeting_date": meeting["meeting_date"],
        "meeting_type": meeting["meeting_type"],
        "total_chars": census.get(filename, {}).get("char_count", 0),
        "quotes": {
            "total": para_total,
            "paraphrased": para_n,
            "stripped_matched": stripped_n,
            "paraphrase_rate": round(para_rate, 4),
            "paraphrase_examples": para_examples,
        },
        "coverage_ratio": round(cov_ratio, 4),
        "entity_counts": entity_counts,
        "inventory_agreement": inv_agreement,
        "keyword_gap": kw_gap,
        "quote_completeness": completeness,
        "status": status,
    }
