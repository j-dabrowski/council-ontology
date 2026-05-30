"""
Level 3c: Validate sample extractions.

Reads data/{council}_sample.json, then for each doc computes:
  - Paraphrase rate: quotes that cannot be matched in the normalised source text.
    Both the PDF source text and each quote are whitespace-normalised before
    comparison, so pypdf line-break artefacts and minor spacing differences do
    not produce false positives. Only genuine content differences count.
  - Coverage ratio: chars of normalised source text covered by matched quotes.
  - Inventory agreement: extracted entity counts vs L1 inventory counts.
  - Keyword gap rate: high-signal keywords in normalised source text not covered
    by any matched quote span (potential missed entities).

All matching is done at query time against the live PDF text — the DB column
char_offset is not used here (it is a best-effort convenience for UI only).

Writes:
  data/sample_validation/{stem}.json  per-doc JSON report
  data/sample_validation/report.txt   human-readable summary + interpretation

Prints a rich table to stdout. This report is the human gate before Level 4:
  - High paraphrase rate  → strengthen PROVENANCE RULE in system_prompt.txt
  - High keyword gap rate → widen text window or fix extraction rules
  - Poor inventory agreement → check entity-specific extraction instructions

Usage:
    council validate-sample cambridge
    python scripts/validate_sample.py cambridge
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv()

from pypdf import PdfReader
from rich.console import Console
from rich.table import Table

console = Console()

DATA_DIR = _REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
VALIDATION_DIR = DATA_DIR / "sample_validation"

# High-signal keywords: uncovered occurrences suggest a missed entity.
GAP_KEYWORDS: dict[str, str] = {
    "MOVED":                 r"\bMOVED\b",
    "CARRIED":               r"\bCARRIED\b",
    "LOST":                  r"\bLOST\b",
    "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
    "DECLARATION OF INTEREST": r"DECLARATION OF INTEREST",
    "DEPUTATION":            r"\bDEPUTATION\b",
    "PETITION":              r"\bPETITION\b",
}

# (inventory_field, db_table, WHERE clause using ? for meeting_id)
INVENTORY_FIELDS: list[tuple[str, str, str]] = [
    ("motion_count",             "motions",              "meeting_id = ?"),
    ("planning_count",           "planning_applications", "motion_id IN (SELECT id FROM motions WHERE meeting_id = ?)"),
    ("interest_count",           "interest_declarations", "meeting_id = ?"),
    ("public_question_count",    "public_questions",     "meeting_id = ?"),
    ("deputation_count",         "deputations",          "meeting_id = ?"),
    ("petition_count",           "petitions",            "meeting_id = ?"),
    ("appointment_count",        "appointments",         "meeting_id = ?"),
    ("tender_count",             "tenders",              "meeting_id = ?"),
    ("budget_item_count",        "budget_items",         "meeting_id = ?"),
    ("committee_report_count",   "committee_reports",    "meeting_id = ?"),
    ("delegated_decision_count", "delegated_decisions",  "meeting_id = ?"),
    ("building_permit_count",    "building_permits",     "meeting_id = ?"),
]

# (db_table, WHERE clause using ? for meeting_id) — entity types that must have source quotes.
# Used to compute quote_completeness_rate: fraction of extracted entities that have ≥1 evidence row.
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
# DB helpers (raw sqlite3 — no SQLAlchemy session needed)
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
    """Return all source quotes the model produced for this meeting, with entity context."""
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
    """Collapse all whitespace runs to a single space and strip."""
    return re.sub(r"\s+", " ", s).strip()


def _norm_stripped(s: str) -> str:
    """Remove everything except letters and digits.

    Used as the last-resort match tier to handle PDF word-split artefacts where
    pypdf inserts spaces inside words ('no ise', 'provisi ons', 'sub- clause').
    The model reconstructs the correct word in its quote; stripping both sides
    makes them comparable.  Only attempted when the whitespace-normalised match fails,
    and only when the stripped quote is long enough to avoid false positives.
    """
    return re.sub(r"[^a-zA-Z0-9]", "", s)


def _strip_page_headers(text: str) -> str:
    """Remove pypdf page header lines that embed Windows file paths.

    Council minutes PDFs (originally Word documents) repeat a header on every
    page containing the meeting title, date, and a Windows file path such as:
      COUNCIL 22 SEPTEMBER 2009 H:\\CEO\\GOV\\COUNCIL MINUTES\\...\\B DV.DOC 34
    pypdf extracts these between page content, so after whitespace normalisation
    they appear inline and prevent verbatim quote matching.

    The H:\\ anchor is unambiguous — it cannot appear in legitimate meeting text.
    Stripping whole lines that contain it is safe and sufficient.
    """
    cleaned = [
        line for line in text.split("\n")
        if "H:\\" not in line and "H:/" not in line
    ]
    return "\n".join(cleaned)


def _find_partial_match(norm_quote: str, norm_source: str, min_words: int = 4) -> dict | None:
    """Find the longest prefix of norm_quote that appears in norm_source.

    Returns a dict with the source context at the match position, the number of
    words matched, and the total words in the quote — or None if even the minimum
    prefix is not found.  Used to distinguish near-misses (normalisation gap) from
    genuine paraphrases (no foothold in source at all).
    """
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
# Quote classification  (single pass, three tiers)
# ---------------------------------------------------------------------------

_MIN_STRIPPED_LEN = 15  # skip stripped matching for very short quotes (false positive risk)


def _classify_quotes(quotes: list[dict], source_text: str) -> list[dict]:
    """Classify each quote as full match, stripped match, or paraphrase.

    Three tiers, in order:
      1. Normalised match  — whitespace collapsed, verbatim content.
      2. Stripped match    — all non-alphanumeric chars removed from both sides.
                            Handles pypdf word-split artefacts ('no ise' → 'noise').
                            Span in normalised source is recovered via a position
                            mapping so coverage can be computed correctly.
      3. Paraphrase        — content genuinely differs; collected for the report.

    Each returned dict has:
      entity_table, quote_text,
      match_type   : "full" | "stripped" | "paraphrase"
      norm_start   : int | None  — start of match in _norm(source_text)
      norm_end     : int | None  — end   of match in _norm(source_text)
      partial_match: dict | None — only present for "paraphrase"
    """
    norm_source = _norm(source_text)

    # Build a map from stripped-source index → norm_source index.
    # strip_to_norm[i] = position of the i-th alphanumeric char in norm_source.
    strip_to_norm: list[int] = [i for i, ch in enumerate(norm_source) if ch.isalnum()]
    stripped_source = _norm_stripped(norm_source)

    classified: list[dict] = []
    for q in quotes:
        nq = _norm(q["quote_text"])
        base = {"entity_table": q["entity_table"], "quote_text": q["quote_text"]}

        # Tier 1: normalised (whitespace-collapsed) match
        idx = norm_source.find(nq)
        if idx >= 0:
            classified.append({**base, "match_type": "full",
                                "norm_start": idx, "norm_end": idx + len(nq)})
            continue

        # Tier 2: stripped match — recover span via position mapping
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

        # Tier 3: genuine paraphrase
        partial = _find_partial_match(nq, norm_source)
        classified.append({**base, "match_type": "paraphrase",
                           "norm_start": None, "norm_end": None,
                           "partial_match": partial})

    return classified


# ---------------------------------------------------------------------------
# Metric computations  (consume pre-classified quotes)
# ---------------------------------------------------------------------------

def compute_paraphrase_rate(
    classified: list[dict],
) -> tuple[int, int, int, float, list[dict]]:
    """Summarise match results.

    Returns (paraphrased, stripped_matched, total, paraphrase_rate, paraphrase_examples).
    Only tier-3 (paraphrase) quotes appear in examples; tier-2 (stripped) are matches.
    """
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
    """Fraction of the extraction window covered by matched quotes (full + stripped).

    max_chars: when given, the denominator is the normalised length of source_text[:max_chars]
               rather than the full document, matching the extractor's truncation window.
    """
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

    # Both full and stripped matches have recoverable spans and count as coverage.
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
    """Fraction of extracted entities that have at least one source quote in extraction_evidence.

    Paraphrase rate only measures quality of quotes that were produced — it cannot see
    entities where source_quotes=[] was returned (zero evidence rows).  This metric
    directly counts how many extracted entities have any provenance at all.

    Returns total_entities, entities_with_quotes, completeness_rate, missing_by_table.
    If no entities were extracted the rate is 1.0 (nothing to flag; other metrics catch that).
    """
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

def validate_doc(conn: sqlite3.Connection, council: str, filename: str, census: dict, max_chars: int | None = None) -> dict:
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


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_table(results: list[dict]) -> None:
    table = Table(title="Level 3c Sample Validation", show_lines=True)
    table.add_column("File", style="dim", width=14)
    table.add_column("Date", width=10)
    table.add_column("Type", width=20)
    table.add_column("Quot", justify="right", width=5)
    table.add_column("Cmpl%", justify="right", width=6)
    table.add_column("Para%", justify="right", width=6)
    table.add_column("Cov%", justify="right", width=6)
    table.add_column("InvAgr", justify="right", width=7)
    table.add_column("KwGap%", justify="right", width=7)
    table.add_column("Status", width=7)

    STATUS_STYLE = {"PASS": "green", "REVIEW": "yellow", "FAIL": "red"}

    for r in results:
        if "error" in r:
            table.add_row(r["filename"][:14], "—", r["error"], "—", "—", "—", "—", "—", "—", "[red]FAIL[/red]")
            continue

        q = r["quotes"]
        para_rate = q["paraphrase_rate"]
        cov = r["coverage_ratio"]
        gap_rate = r["keyword_gap"]["gap_rate"]
        cmpl = r.get("quote_completeness", {}).get("completeness_rate", 1.0)

        # Average inventory agreement ratio across fields with non-zero l1 or extracted
        inv = r.get("inventory_agreement") or {}
        meaningful = [
            min(v["ratio"], 2.5)
            for v in inv.values()
            if v["ratio"] != float("inf") and (v["l1"] > 0 or v["extracted"] > 0)
        ]
        avg_inv = sum(meaningful) / len(meaningful) if meaningful else None

        para_style = "red" if para_rate >= 0.70 else ("yellow" if para_rate >= 0.40 else "green")
        cov_style = "red" if cov < 0.02 else ("yellow" if cov < 0.05 else "green")
        gap_style = "red" if gap_rate >= 0.50 else ("yellow" if gap_rate >= 0.25 else "green")
        cmpl_style = "red" if cmpl < 0.50 else ("yellow" if cmpl < 0.80 else "green")

        mtype = r.get("meeting_type", "")[:20]
        status = r.get("status", "?")

        table.add_row(
            r["filename"][:14],
            str(r.get("meeting_date", ""))[:10],
            mtype,
            str(q["total"]),
            f"[{cmpl_style}]{cmpl*100:.0f}%[/{cmpl_style}]",
            f"[{para_style}]{para_rate*100:.0f}%[/{para_style}]",
            f"[{cov_style}]{cov*100:.1f}%[/{cov_style}]",
            f"{avg_inv:.2f}" if avg_inv is not None else "—",
            f"[{gap_style}]{gap_rate*100:.0f}%[/{gap_style}]",
            f"[{STATUS_STYLE.get(status, 'white')}]{status}[/{STATUS_STYLE.get(status, 'white')}]",
        )

    console.print(table)

    valid = [r for r in results if "error" not in r]
    if not valid:
        return

    avg_para = sum(r["quotes"]["paraphrase_rate"] for r in valid) / len(valid)
    avg_cov = sum(r["coverage_ratio"] for r in valid) / len(valid)
    avg_gap = sum(r["keyword_gap"]["gap_rate"] for r in valid) / len(valid)
    avg_cmpl = sum(r.get("quote_completeness", {}).get("completeness_rate", 1.0) for r in valid) / len(valid)
    passes = sum(1 for r in valid if r["status"] == "PASS")
    reviews = sum(1 for r in valid if r["status"] == "REVIEW")
    fails = sum(1 for r in valid if r["status"] == "FAIL")

    console.print(f"\n[bold]Aggregate (n={len(valid)}):[/bold]")
    cmpl_col = "red" if avg_cmpl < 0.50 else ("yellow" if avg_cmpl < 0.80 else "green")
    para_col = "red" if avg_para >= 0.50 else "green"
    cov_col = "red" if avg_cov < 0.03 else "green"
    gap_col = "red" if avg_gap >= 0.40 else "green"
    console.print(f"  Quote completeness: [{cmpl_col}]{avg_cmpl*100:.1f}%[/{cmpl_col}]  (target >80%)")
    console.print(f"  Paraphrase rate:    [{para_col}]{avg_para*100:.1f}%[/{para_col}]  (target <30%)")
    console.print(f"  Coverage ratio:     [{cov_col}]{avg_cov*100:.2f}%[/{cov_col}]  (target >5%)")
    console.print(f"  Keyword gap rate:   [{gap_col}]{avg_gap*100:.1f}%[/{gap_col}]  (target <25%)")
    console.print(f"  Status: [green]{passes} PASS[/green]  [yellow]{reviews} REVIEW[/yellow]  [red]{fails} FAIL[/red]")


def _write_report(results: list[dict], council: str, sample: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "Level 3c Sample Validation Report",
        f"Council: {council}  |  Sample: {sample['count']} docs  |  Generated: {ts}",
        "",
        "METRICS",
        "-------",
        "  Quote completeness  — fraction of extracted entities that have ≥1 source quote in",
        "                        extraction_evidence. Paraphrase rate only measures quality of",
        "                        quotes that were produced; this metric catches entities where",
        "                        source_quotes=[] was returned (no evidence rows at all).",
        "                        Target: >80%. FAIL if <50%.",
        "  Paraphrase rate     — quotes not found in whitespace-normalised source text.",
        "                        Both PDF text and quote are normalised before matching.",
        "                        Only genuine content differences count. Target: <30%.",
        "  Coverage ratio      — fraction of the extraction window (first max_chars chars) covered",
        "                        by matched quotes. Denominator is capped at the extraction window",
        "                        so large documents are not penalised for truncated content.",
        "                        Target: >5%.",
        "  Inventory agreement — average of (extracted count / L1 count) across entity types.",
        "                        Values near 1.0 = good. Flagged if <0.4 or >2.5.",
        "  Keyword gap rate    — MOVED/CARRIED/DA/DECLARATION etc. in normalised source text",
        "                        not covered by any matched quote span. Target: <25%.",
        "",
        "RESULTS",
        "-------",
    ]

    hdr = f"{'File':<16} {'Date':<12} {'Para%':>5} {'Cov%':>5} {'KwGap%':>7} {'Status'}"
    lines.append(hdr)
    lines.append("-" * (len(hdr) + 4))

    for r in results:
        if "error" in r:
            lines.append(f"{r['filename']:<16} {'—':<12} {'—':>5} {'—':>5} {'—':>7} FAIL  ({r['error']})")
            continue
        q = r["quotes"]
        lines.append(
            f"{r['filename']:<16} {str(r['meeting_date']):<12}"
            f" {q['paraphrase_rate']*100:>4.0f}%"
            f" {r['coverage_ratio']*100:>4.1f}%"
            f" {r['keyword_gap']['gap_rate']*100:>6.0f}%"
            f" {r['status']}"
        )

    lines.append("")

    valid = [r for r in results if "error" not in r]
    if valid:
        avg_para = sum(r["quotes"]["paraphrase_rate"] for r in valid) / len(valid)
        avg_cov = sum(r["coverage_ratio"] for r in valid) / len(valid)
        avg_gap = sum(r["keyword_gap"]["gap_rate"] for r in valid) / len(valid)
        avg_cmpl = sum(r.get("quote_completeness", {}).get("completeness_rate", 1.0) for r in valid) / len(valid)
        passes = sum(1 for r in valid if r["status"] == "PASS")
        reviews = sum(1 for r in valid if r["status"] == "REVIEW")
        fails = sum(1 for r in valid if r["status"] == "FAIL")

        lines += [
            f"AGGREGATE (n={len(valid)})",
            "---------",
            f"  Quote completeness: {avg_cmpl*100:.1f}%  (target >80%)",
            f"  Paraphrase rate:    {avg_para*100:.1f}%  (target <30%)",
            f"  Coverage ratio:     {avg_cov*100:.2f}%  (target >5%)",
            f"  Keyword gap rate:   {avg_gap*100:.1f}%  (target <25%)",
            f"  Status:             {passes} PASS / {reviews} REVIEW / {fails} FAIL",
            "",
        ]

        # Interpretation
        issues: list[str] = []
        if avg_cmpl < 0.50:
            issues.append(
                f"LOW QUOTE COMPLETENESS ({avg_cmpl*100:.0f}%)\n"
                "  More than half the extracted entities have no source quote in extraction_evidence.\n"
                "  This means the model is extracting content but silently dropping the PROVENANCE RULE.\n"
                "  Check missing_by_table in per-doc JSON to see which entity types are worst.\n"
                "  Fix: strengthen the PROVENANCE RULE in system_prompt.txt; ensure source_quotes\n"
                "  appears in the OUTPUT SCHEMA block for every entity type."
            )
        elif avg_cmpl < 0.80:
            issues.append(
                f"MODERATE QUOTE COMPLETENESS ({avg_cmpl*100:.0f}%)\n"
                "  Some extracted entities have no source quote. Check missing_by_table in per-doc\n"
                "  JSON to identify which entity types are missing provenance most often."
            )
        if avg_para >= 0.50:
            issues.append(
                f"HIGH PARAPHRASE RATE ({avg_para*100:.0f}%)\n"
                "  More than half the model's source quotes cannot be found in the source text\n"
                "  even after whitespace normalisation. The model is paraphrasing or condensing\n"
                "  rather than quoting. Fix: strengthen the PROVENANCE RULE in system_prompt.txt.\n"
                "  Quotes must reproduce the source wording closely enough that normalised matching\n"
                "  succeeds. Consider adding a worked example of an acceptable vs unacceptable quote."
            )
        if avg_cov < 0.03:
            issues.append(
                f"LOW COVERAGE RATIO ({avg_cov*100:.2f}%)\n"
                "  Very little of the source text is spanned by matched quotes. This is usually\n"
                "  a downstream effect of a high paraphrase rate: unmatched quotes contribute\n"
                "  nothing to coverage. Reducing the paraphrase rate should raise coverage."
            )
        if avg_gap >= 0.40:
            issues.append(
                f"HIGH KEYWORD GAP RATE ({avg_gap*100:.0f}%)\n"
                "  Many entity-signalling keywords (MOVED, CARRIED, DA, etc.) appear in source\n"
                "  text but are not spanned by any matched quote. This means either:\n"
                "  (a) entities are being missed entirely (extraction gap), or\n"
                "  (b) they are extracted but with paraphrased quotes (covered by paraphrase fix).\n"
                "  Check per-doc gap_examples in sample_validation/*.json to distinguish."
            )

        if issues:
            lines.append("INTERPRETATION")
            lines.append("--------------")
            for issue in issues:
                lines.append(issue)
                lines.append("")
            lines.append("NEXT STEPS")
            lines.append("----------")
            lines.append("  1. Fix the identified issues in system_prompt.txt (and/or schemas.py).")
            lines.append("  2. Re-run: council extract-sample cambridge")
            lines.append("  3. Re-run: council validate-sample cambridge")
            lines.append("  Repeat until paraphrase <30%, coverage >5%, keyword gap <25%.")
            lines.append("  Then proceed to Level 4: confidence metrics and full batch extraction.")
        else:
            lines += [
                "NEXT STEPS",
                "----------",
                "  Metrics are within targets. Proceed to Level 4:",
                "  Implement scripts/validate_extraction.py (per-doc confidence scorer).",
                "  Then run: council batch cambridge --limit 20",
            ]

        # Inventory agreement flags
        flagged_fields: dict[str, list[str]] = {}
        for r in valid:
            if not r.get("inventory_agreement"):
                continue
            for field, info in r["inventory_agreement"].items():
                if info.get("flag"):
                    flagged_fields.setdefault(field, []).append(
                        f"  {r['filename']} (L1={info['l1']}, extracted={info['extracted']}, ratio={info['ratio']})"
                    )
        if flagged_fields:
            lines += ["", "INVENTORY AGREEMENT FLAGS", "-------------------------"]
            for field, cases in sorted(flagged_fields.items()):
                lines.append(f"  {field}: {len(cases)} doc(s) flagged")
                for case in cases[:5]:
                    lines.append(case)

    (VALIDATION_DIR / "report.txt").write_text("\n".join(lines) + "\n")


def _write_paraphrase_report(results: list[dict], council: str, sample: dict) -> None:
    """Write a detailed per-quote paraphrase analysis for human or AI inspection.

    For each unmatched quote, shows:
      - The entity table it came from
      - The quote as the model produced it
      - The best partial match found in the source (longest prefix of the normalised
        quote that appears in the normalised source text), with surrounding context
      - Whether no foothold at all was found (likely a fabrication or heavy rewrite)

    Use this to:
      - Distinguish normalisation gaps (source_context ≈ quote) from genuine paraphrases
      - Spot systematic patterns (e.g. model always adds "." between mover and motion text)
      - Feed examples directly to Claude when revising the extraction prompt
    """
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "Paraphrase Analysis Report",
        f"Council: {council}  |  Sample: {sample['count']} docs  |  Generated: {ts}",
        "",
        "HOW TO READ THIS REPORT",
        "-----------------------",
        "Each entry is a quote the model produced that could not be matched in the",
        "normalised source text (whitespace collapsed to single spaces).",
        "",
        "  partial_match: longest prefix of the quote found verbatim in the source.",
        "    matched_words/total_words — how much of the quote's start was found.",
        "    source_context — what the source text actually says from that position.",
        "    If source_context ≈ quote: the normaliser needs improvement (e.g. handle",
        "      punctuation differences). The extraction itself is fine.",
        "    If source_context diverges early: the model paraphrased the content.",
        "  no_partial_match: even the first 4 words weren't found — likely fabricated",
        "    structure (e.g. 'PUBLIC QUESTION TIME: Nil' as a synthetic heading) or a",
        "    heavily reworded passage.",
        "",
        "=" * 72,
        "",
    ]

    valid = [r for r in results if "error" not in r]
    for r in valid:
        examples = r.get("quotes", {}).get("paraphrase_examples", [])
        if not examples:
            continue

        q_info = r["quotes"]
        header = (
            f"{r['filename']}  |  {r['meeting_type']}  |  {r['meeting_date']}"
            f"  |  {q_info['paraphrased']}/{q_info['total']} quotes paraphrased"
            f"  ({q_info['paraphrase_rate']*100:.0f}%)"
        )
        lines.append(header)
        lines.append("-" * min(len(header), 72))

        for ex in examples:
            lines.append(f"  [{ex['entity_table']}]")
            # Wrap the quote at 68 chars with indentation
            quote_lines = _wrap(ex["quote"], 68)
            lines.append(f"    QUOTE:  {quote_lines[0]}")
            for ql in quote_lines[1:]:
                lines.append(f"            {ql}")

            pm = ex.get("partial_match")
            if pm:
                matched = pm["matched_words"]
                total = pm["total_words"]
                ctx_lines = _wrap(pm["source_context"], 68)
                lines.append(f"    SOURCE: {ctx_lines[0]}  [{matched}/{total} words matched]")
                for cl in ctx_lines[1:]:
                    lines.append(f"            {cl}")
            else:
                lines.append("    SOURCE: [no partial match — first 4 words not found in source]")
            lines.append("")

        lines.append("")

    (VALIDATION_DIR / "paraphrase_report.txt").write_text("\n".join(lines) + "\n")


def _wrap(text: str, width: int) -> list[str]:
    """Simple word-wrap returning a list of lines."""
    words = text.split()
    out: list[str] = []
    line = ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip() if line else w
    if line:
        out.append(line)
    return out or [""]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(args) -> None:
    from src.extraction.extractor import DEFAULT_MAX_CHARS
    council = args.council
    max_chars: int | None = getattr(args, "max_chars", DEFAULT_MAX_CHARS)

    sample_path = DATA_DIR / f"{council}_sample.json"
    if not sample_path.exists():
        console.print(f"[red]No sample file at {sample_path}. Run 'council sample {council}' first.[/red]")
        sys.exit(1)

    sample = json.loads(sample_path.read_text())
    files: list[str] = sample["files"]

    console.print(f"\n[bold]Level 3c: validating {len(files)} sample docs for council '{council}'[/bold]")

    census = load_census()
    conn = sqlite3.connect(str(DATA_DIR / "council.db"))
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for filename in files:
        console.print(f"  {filename} ...", end="", highlight=False)
        result = validate_doc(conn, council, filename, census, max_chars=max_chars)
        results.append(result)
        stem = Path(filename).stem
        (VALIDATION_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2))
        status = result.get("status", "?")
        style = {"PASS": "green", "REVIEW": "yellow", "FAIL": "red"}.get(status, "white")
        console.print(f" [{style}]{status}[/{style}]")

    conn.close()

    console.print()
    _print_table(results)
    _write_report(results, council, sample)
    _write_paraphrase_report(results, council, sample)

    console.print(f"\n[dim]Per-doc JSON:       {VALIDATION_DIR}/*.json[/dim]")
    console.print(f"[dim]Summary:            {VALIDATION_DIR}/report.txt[/dim]")
    console.print(f"[dim]Paraphrase detail: {VALIDATION_DIR}/paraphrase_report.txt[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
