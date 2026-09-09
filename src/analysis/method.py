"""
The extraction-quality record behind `/method`
(docs/frontend/METHOD_PAGE_PLAN.md), replacing the old Evidence page's
promises with what the pipeline's own audit files actually say.

`build_method_record()` reads five files under `data/` — `census.json`,
`inventories/summary.json`, `sample_validation/summary.json` +
`report.txt`, `validation/summary.json`, `extraction_errors.json` — plus the
database for the live per-year coverage columns, and returns the
`method.json` shape the plan's B.6 settles: every metric is an object
carrying its own `source` and `generated_at`, never a bare number, so a
stale figure is stale on its face rather than hidden in a footnote.

Per B.1, the five files do not share a generation date, and that spread is
the page's normal condition, not a defect to hide — this module makes no
attempt to reconcile it. A missing or unparseable source file yields
`{"value": None, "reason": "source_missing", ...}` rather than a zero;
Step 3 of the plan renders that as an explicit gap.

`entity_resolution` (docs/frontend/ENTITY_RESOLUTION_SECTION_PLAN.md) is the
one block computed entirely from the live database rather than a `data/`
file: supplier-name normalisation across every named tender award, and the
two raw surname collisions `decider_supplier_conflict()` finds between a
tender winner and a voting councillor. It reuses that function and
`_normalise_contractor()` / `_is_redacted_recipient()` from
`src/analysis/queries.py` directly rather than re-deriving them, and drops
`councillor_name` / `councillor_id` at the boundary — no councillor's name
reaches this module's return value.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.analysis.queries import (
    _is_redacted_recipient,
    _normalise_contractor,
    _normalise_tender_ref,
    decider_supplier_conflict,
)
from src.models import Meeting, Tender

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = _REPO_ROOT / "data"

CENSUS_REL = "data/census.json"
INVENTORIES_SUMMARY_REL = "data/inventories/summary.json"
SAMPLE_VALIDATION_SUMMARY_REL = "data/sample_validation/summary.json"
SAMPLE_VALIDATION_REPORT_REL = "data/sample_validation/report.txt"
VALIDATION_SUMMARY_REL = "data/validation/summary.json"
EXTRACTION_ERRORS_REL = "data/extraction_errors.json"

# Written once, here, per B.6 — the "what failure of this metric would mean"
# sentence report.txt's own METRICS block doesn't carry.
_MEANS_IF_FAILED = {
    "quote_completeness": (
        "A low completeness means entities were extracted with no supporting "
        "quote at all — the record exists in the database but nothing in the "
        "source document backs it. That is a missing-evidence failure, not a "
        "wrong-evidence one."
    ),
    "paraphrase_rate": (
        "A high paraphrase rate means the quotes attached to entities are not "
        "verbatim from the source document — the extraction may be rewording "
        "or inventing text rather than citing it."
    ),
    "coverage_ratio": (
        "Low coverage means most of the document's text was never touched by "
        "any extracted quote — content could be missing from the extraction "
        "even where every individual quote checks out."
    ),
    "inventory_agreement": (
        "A flagged ratio (far below or above 1.0) means the LLM extraction "
        "found a very different number of entities than the cheaper Level 1 "
        "inventory pass counted for the same document — either pass could be "
        "wrong, but the two should track each other."
    ),
    "keyword_gap_rate": (
        "A high gap rate means the source text contains motion, planning or "
        "declaration language that never made it into any extracted quote — "
        "a sign of entities missed entirely, not just a citation problem."
    ),
}

_METRIC_KEYS = list(_MEANS_IF_FAILED)


def _missing(source: str) -> dict:
    return {"value": None, "source": source, "generated_at": None, "n": None,
            "reason": "source_missing"}


def _no_aggregate(source: str, generated_at: str | None, n: int | None) -> dict:
    """The source file exists but does not compute an aggregate for this
    metric (inventory agreement has no corpus-wide or sample-wide average in
    either summary file — only per-document, per-entity-type flags)."""
    return {"value": None, "source": source, "generated_at": generated_at, "n": n,
            "reason": "no_aggregate_in_source"}


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text()
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------------------
# report.txt parsing — definitions/targets stay the file's own words (Step 1
# brief: "parse rather than retype").
# ---------------------------------------------------------------------------

_METRIC_NAME_TO_KEY = {
    "Quote completeness": "quote_completeness",
    "Paraphrase rate": "paraphrase_rate",
    "Coverage ratio": "coverage_ratio",
    "Inventory agreement": "inventory_agreement",
    "Keyword gap rate": "keyword_gap_rate",
}

_METRICS_BLOCK_RE = re.compile(r"METRICS\n-+\n(.*?)\nRESULTS", re.DOTALL)
_METRIC_ENTRY_RE = re.compile(
    r"^  ([A-Za-z][A-Za-z ]*?)\s+— (.*?)(?=^  [A-Za-z][A-Za-z ]*?\s+— |\Z)",
    re.DOTALL | re.MULTILINE,
)
_GENERATED_RE = re.compile(r"Generated:\s*(\S+)")
_SAMPLE_N_RE = re.compile(r"Sample:\s*(\d+)\s*docs")
_RESULTS_ROW_RE = re.compile(
    r"^(\S+\.pdf)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)%\s+([\d.]+)%\s+(\d+)%\s+(PASS|REVIEW|FAIL)\s*$",
    re.MULTILINE,
)
_FLAG_GROUP_HEADER_RE = re.compile(r"^  (\w+):\s*(\d+)\s*doc\(s\) flagged$", re.MULTILINE)
_FLAG_DOC_RE = re.compile(
    r"^  (\S+\.pdf)\s+\(L1=(-?\d+|\S+),\s*extracted=(-?\d+|\S+),\s*ratio=([\w.]+)\)$",
    re.MULTILINE,
)


def _parse_report_txt(text: str) -> dict:
    """Everything method.py needs out of `sample_validation/report.txt`:
    generated_at, sample n, per-metric definition/target, the 18-row
    per-file table, and the inventory-agreement flag list."""
    out: dict = {
        "generated_at": None, "n": None, "metrics": {}, "per_file": [],
        "inventory_agreement_flags": {},
    }

    m = _GENERATED_RE.search(text)
    if m:
        out["generated_at"] = m.group(1)
    m = _SAMPLE_N_RE.search(text)
    if m:
        out["n"] = int(m.group(1))

    block_match = _METRICS_BLOCK_RE.search(text)
    if block_match:
        for entry in _METRIC_ENTRY_RE.finditer(block_match.group(1)):
            name = entry.group(1).strip()
            key = _METRIC_NAME_TO_KEY.get(name)
            if key is None:
                continue
            desc = " ".join(line.strip() for line in entry.group(2).strip().splitlines())
            definition, target = _split_definition_target(desc)
            out["metrics"][key] = {"definition": definition, "target": target}

    for row in _RESULTS_ROW_RE.finditer(text):
        filename, meeting_date, para_pct, cov_pct, gap_pct, status = row.groups()
        out["per_file"].append({
            "filename": filename, "meeting_date": meeting_date,
            "paraphrase_pct": int(para_pct), "coverage_pct": float(cov_pct),
            "keyword_gap_pct": int(gap_pct), "status": status,
        })

    # INVENTORY AGREEMENT FLAGS section: a run of "<entity>_count: N doc(s)
    # flagged" headers, each followed by that many "<file> (L1=.., extracted=..,
    # ratio=..)" lines — group by scanning header positions.
    headers = list(_FLAG_GROUP_HEADER_RE.finditer(text))
    docs = list(_FLAG_DOC_RE.finditer(text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        entity, flagged_count = h.group(1), int(h.group(2))
        rows_in_range = [d for d in docs if start <= d.start() < end]
        out["inventory_agreement_flags"][entity] = {
            "flagged_count": flagged_count,
            "docs": [
                {"filename": d.group(1), "l1": d.group(2), "extracted": d.group(3),
                 "ratio": d.group(4)}
                for d in rows_in_range
            ],
        }

    return out


def _split_definition_target(desc: str) -> tuple[str, str | None]:
    for marker in ("Target:", "Flagged if"):
        idx = desc.find(marker)
        if idx != -1:
            return desc[:idx].strip(), desc[idx:].strip()
    return desc, None


# ---------------------------------------------------------------------------
# Live per-year coverage — the only part of this record computed from the
# database rather than a snapshot file (B.1: what can be recomputed live, is).
# ---------------------------------------------------------------------------

def _live_year_counts(session: Session, council_id: int) -> dict[int, dict[str, int]]:
    meetings = (
        session.query(Meeting.meeting_date, Meeting.document_type)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    by_year: dict[int, dict[str, int]] = {}
    for meeting_date, document_type in meetings:
        if meeting_date is None:
            continue
        row = by_year.setdefault(meeting_date.year, {"documents": 0, "minutes": 0})
        row["documents"] += 1
        if document_type == "minutes":
            row["minutes"] += 1
    return by_year


def _census_year_counts(census: dict | None) -> dict[int, int]:
    counts: dict[int, int] = {}
    if not census:
        return counts
    for doc in census.get("documents", []):
        meeting_date = doc.get("meeting_date")
        if not meeting_date:
            continue
        try:
            year = int(str(meeting_date)[:4])
        except ValueError:
            continue
        counts[year] = counts.get(year, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_method_record(
    session: Session,
    council_id: int,
    council_key: str,
    generated_at: str,
    *,
    data_dir: Path | None = None,
) -> dict:
    data_dir = data_dir if data_dir is not None else DEFAULT_DATA_DIR

    census = _load_json(data_dir / "census.json")
    inventories_summary = _load_json(data_dir / "inventories" / "summary.json")
    sample_summary = _load_json(data_dir / "sample_validation" / "summary.json")
    report_text = _load_text(data_dir / "sample_validation" / "report.txt")
    report = _parse_report_txt(report_text) if report_text is not None else None
    validation_summary = _load_json(data_dir / "validation" / "summary.json")
    extraction_errors = _load_json(data_dir / "extraction_errors.json")

    return {
        "council": council_key,
        "generated_at": generated_at,
        "coverage": _build_coverage(session, council_id, census, inventories_summary),
        "validation": _build_validation(sample_summary, report, validation_summary),
        "extraction_batch": _build_extraction_batch(extraction_errors),
        "entity_resolution": _build_entity_resolution(session, council_id, generated_at),
    }


def _build_coverage(
    session: Session, council_id: int, census: dict | None, inventories_summary: dict | None,
) -> dict:
    census_generated_at = census.get("generated_at") if census else None
    census_by_year = _census_year_counts(census)
    live_by_year = _live_year_counts(session, council_id)

    years = sorted(set(census_by_year) | set(live_by_year))
    by_year = [
        {
            "year": year,
            "censused": census_by_year.get(year),
            "documents_in_db": live_by_year.get(year, {}).get("documents", 0),
            "minutes_in_db": live_by_year.get(year, {}).get("minutes", 0),
        }
        for year in years
    ]

    census_total = (
        {"value": census.get("total"), "source": CENSUS_REL,
         "generated_at": census_generated_at, "n": census.get("total")}
        if census else _missing(CENSUS_REL)
    )

    if inventories_summary:
        type_mix = {
            "value": inventories_summary.get("meeting_type_distribution"),
            "source": INVENTORIES_SUMMARY_REL,
            "generated_at": inventories_summary.get("generated_at"),
            "n": inventories_summary.get("total_inventoried"),
        }
    else:
        type_mix = _missing(INVENTORIES_SUMMARY_REL)

    if census:
        flag_tallies: dict[str, int] = {}
        for doc in census.get("documents", []):
            for flag in doc.get("flags", []):
                flag_tallies[flag] = flag_tallies.get(flag, 0) + 1
        document_flags = {
            "value": flag_tallies, "source": CENSUS_REL,
            "generated_at": census_generated_at, "n": census.get("total"),
        }
    else:
        document_flags = _missing(CENSUS_REL)

    return {
        "census_total": census_total,
        "by_year": by_year,
        "type_mix": type_mix,
        "document_flags": document_flags,
    }


def _metric_value(source_dict: dict | None, field: str, source: str,
                   n_value: int | None, generated_at: str | None) -> dict:
    if source_dict is None or source_dict.get(field) is None:
        return _missing(source)
    return {
        "value": source_dict[field], "source": source, "generated_at": generated_at,
        "n": n_value,
    }


def _build_validation(
    sample_summary: dict | None, report: dict | None, validation_summary: dict | None,
) -> dict:
    validation_generated_at = validation_summary.get("generated_at") if validation_summary else None
    validation_n = validation_summary.get("total_validated") if validation_summary else None
    sample_generated_at = report.get("generated_at") if report else None
    sample_n = sample_summary.get("n") if sample_summary else (report.get("n") if report else None)

    report_metrics = report.get("metrics", {}) if report else {}

    full_corpus_field = {
        "quote_completeness": "avg_quote_completeness",
        "paraphrase_rate": "avg_paraphrase_rate",
        "coverage_ratio": "avg_coverage_ratio",
        "keyword_gap_rate": "avg_keyword_gap_rate",
    }
    sample_field = {
        "quote_completeness": "avg_completeness",
        "paraphrase_rate": "avg_paraphrase",
        "coverage_ratio": "avg_coverage",
        "keyword_gap_rate": "avg_keyword_gap",
    }

    metrics: dict[str, dict] = {}
    for key in _METRIC_KEYS:
        defn = report_metrics.get(key, {})
        entry: dict = {
            "definition": defn.get("definition"),
            "target": defn.get("target"),
            "means_if_failed": _MEANS_IF_FAILED[key],
        }
        if key == "inventory_agreement":
            entry["full_corpus"] = (
                _no_aggregate(VALIDATION_SUMMARY_REL, validation_generated_at, validation_n)
                if validation_summary else _missing(VALIDATION_SUMMARY_REL)
            )
            if report:
                entry["sample"] = {
                    **_no_aggregate(SAMPLE_VALIDATION_REPORT_REL, sample_generated_at, sample_n),
                    "flagged_entity_types": report.get("inventory_agreement_flags", {}),
                }
            else:
                entry["sample"] = _missing(SAMPLE_VALIDATION_REPORT_REL)
        else:
            entry["full_corpus"] = _metric_value(
                validation_summary, full_corpus_field[key], VALIDATION_SUMMARY_REL,
                validation_n, validation_generated_at,
            )
            entry["sample"] = _metric_value(
                sample_summary, sample_field[key], SAMPLE_VALIDATION_SUMMARY_REL,
                sample_n, sample_generated_at,
            )
        metrics[key] = entry

    if validation_summary:
        full_corpus_split = {
            "pass": validation_summary.get("pass"), "review": validation_summary.get("review"),
            "fail": validation_summary.get("fail"), "errors": validation_summary.get("errors"),
            "source": VALIDATION_SUMMARY_REL, "generated_at": validation_generated_at,
            "n": validation_n,
        }
        schema_flags = {
            "value": validation_summary.get("schema_flags_count"),
            "flagged_files": validation_summary.get("schema_flagged_files"),
            "source": VALIDATION_SUMMARY_REL, "generated_at": validation_generated_at,
            "n": validation_n,
        }
    else:
        full_corpus_split = _missing(VALIDATION_SUMMARY_REL)
        schema_flags = _missing(VALIDATION_SUMMARY_REL)

    if sample_summary:
        sample_split = {
            "pass": sample_summary.get("passes"), "review": sample_summary.get("reviews"),
            "fail": sample_summary.get("fails"), "converged": sample_summary.get("converged"),
            "source": SAMPLE_VALIDATION_SUMMARY_REL, "generated_at": sample_generated_at,
            "n": sample_n,
        }
    else:
        sample_split = _missing(SAMPLE_VALIDATION_SUMMARY_REL)

    return {
        "metrics": metrics,
        "full_corpus_split": full_corpus_split,
        "sample_split": sample_split,
        "sample_per_file": {
            "value": report.get("per_file") if report else None,
            "source": SAMPLE_VALIDATION_REPORT_REL, "generated_at": sample_generated_at,
            "n": sample_n,
        } if report else _missing(SAMPLE_VALIDATION_REPORT_REL),
        "schema_flags": schema_flags,
    }


def _build_extraction_batch(extraction_errors: dict | None) -> dict:
    if not extraction_errors:
        return _missing(EXTRACTION_ERRORS_REL)
    return {
        "batch_id": extraction_errors.get("batch_id"),
        "attempted": extraction_errors.get("attempted"),
        "succeeded": extraction_errors.get("succeeded"),
        "failed": extraction_errors.get("failed"),
        "errors_by_class": extraction_errors.get("errors_by_class"),
        "source": EXTRACTION_ERRORS_REL,
        "generated_at": extraction_errors.get("generated_at"),
        "n": extraction_errors.get("attempted"),
        "note": (
            "the last recorded extraction batch, not a corpus-wide rate — "
            "attempted against however many documents are in the database now"
        ),
    }


# ---------------------------------------------------------------------------
# Entity resolution — two live demonstrations of the join discipline the
# analysis already applies (ENTITY_RESOLUTION_SECTION_PLAN.md Part C).
# Computed from the database, not from a `data/` file (B.3 of that plan).
# ---------------------------------------------------------------------------

_ENTITY_RESOLUTION_SOURCE = "data/council.db"

# The one piece of authored prose in this module (ENTITY_RESOLUTION_SECTION_
# PLAN.md Part C): a plain-English statement of what a firm actually is,
# checked against its tender's own `description` and `extraction_evidence`
# quote rather than against its name. Reuses, unchanged, the wording
# `tests.py`'s `_t_decider_supplier_conflict` verdict already publishes on
# the live scorecard for these same two firms (checked here, not retyped
# from there):
#   - G T Evans Weed Spraying Service (TEN0008, $70,000): description
#     "Chemical control of weeds"; quote "...the chemical control of weeds
#     within the Town of Cambridge..." — fully supports "weed-spraying
#     contractor".
#   - MacDonald Johnston (TEN0010, $217,154): description "Supply and
#     delivery of one road sweeper..."; quote "...a MacDonald Johnston road
#     sweeper on a 600 Hino series FE truck..." — the quote names the
#     product after the firm rather than using the word "manufacturer", the
#     ordinary way a piece of branded plant is described; it does not use
#     the firm's name for anything else, so the characterisation is kept.
# A firm not listed here is a collision this module has not been checked
# against yet, and is reported as such rather than resolved by guess.
_COLLISION_WHAT_IT_IS = {
    "gtevansweedsprayingservice": "a weed-spraying contractor",
    "macdonaldjohnston": "a street-sweeper manufacturer",
}

_UNRELATED_BUSINESS_RESOLUTION = (
    "resolves on provenance to an unrelated business, not the councillor "
    "who shares the surname"
)


def _named_tender_rows(session: Session, council_id: int) -> list[tuple]:
    """Every minutes tender award with a non-blank `awarded_to` — the
    population both entity-resolution cases group, before any placeholder
    exclusion or dedup."""
    return (
        session.query(
            Tender.id, Tender.awarded_to, Tender.amount,
            Tender.reference_number, Meeting.meeting_date,
        )
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Tender.awarded_to.isnot(None),
            func.trim(Tender.awarded_to) != "",
        )
        .order_by(Tender.id)
        .all()
    )


def _build_entity_resolution(session: Session, council_id: int, generated_at: str) -> dict:
    return {
        "supplier_normalisation": _build_supplier_normalisation(session, council_id, generated_at),
        "surname_collision": _build_surname_collision(session, council_id, generated_at),
    }


def _build_supplier_normalisation(session: Session, council_id: int, generated_at: str) -> dict:
    rows = _named_tender_rows(session, council_id)
    named_award_rows = len(rows)

    all_keys: set[str] = set()
    real_groups: dict[str, list[tuple[str, float | None]]] = defaultdict(list)
    placeholder_rows = 0
    for _tid, awarded_to, amount, _ref, _mdate in rows:
        name = awarded_to.strip()
        all_keys.add(_normalise_contractor(name))
        if _is_redacted_recipient(name):
            placeholder_rows += 1
            continue
        real_groups[_normalise_contractor(name)].append((name, amount))

    examples = []
    for key, entries in real_groups.items():
        raw_counts = Counter(name for name, _amount in entries)
        if len(raw_counts) <= 1:
            continue
        examples.append({
            "merged_key": key,
            "raw": [{"string": s, "n": n} for s, n in raw_counts.items()],
            "n_awards": len(entries),
            "total_amount": sum(amount or 0.0 for _name, amount in entries),
        })
    examples.sort(key=lambda e: (-e["n_awards"], e["merged_key"]))

    return {
        "source": _ENTITY_RESOLUTION_SOURCE,
        "generated_at": generated_at,
        "named_award_rows": named_award_rows,
        "distinct_firms": len(all_keys),
        "multi_variant_firms": len(examples),
        "rule": "lowercase; strip company suffixes; drop . and ,; remove internal whitespace",
        "examples": examples,
        "excluded_placeholders": {
            "n_awards": placeholder_rows,
            "note": (
                "de-identification placeholders such as 'Respondent 1' or "
                "'Tenderer 3' are excluded from the grouping above — grouped "
                "in as if they were suppliers, a placeholder can out-rank "
                "every real contractor by value"
            ),
        },
    }


def _duplicate_extraction_note(
    dup_groups: dict[tuple[str, str, float], list[tuple[int, object]]],
    firm: str,
    amount: float,
) -> str | None:
    ck = _normalise_contractor(firm)
    for (group_key, _ref_key, group_amount), members in dup_groups.items():
        if group_key != ck or group_amount != amount or len(members) < 2:
            continue
        dates = sorted(m[1] for m in members if m[1] is not None)
        ids = sorted(m[0] for m in members)
        gap = f"{(dates[-1] - dates[0]).days} days apart" if len(dates) >= 2 else "on separate rows"
        return (
            f"this award is itself extracted as {len(members)} minutes rows "
            f"{gap} (ids {', '.join(str(i) for i in ids)}) — one real award, "
            f"not {len(members)}; decider_supplier_conflict() counts it once"
        )
    return None


def _build_surname_collision(session: Session, council_id: int, generated_at: str) -> dict:
    dsc = decider_supplier_conflict(session, council_id)

    rows = _named_tender_rows(session, council_id)
    dup_groups: dict[tuple[str, str, float], list[tuple[int, object]]] = defaultdict(list)
    for tid, awarded_to, amount, ref, mdate in rows:
        name = awarded_to.strip()
        if _is_redacted_recipient(name):
            continue
        ck = _normalise_contractor(name)
        rk = _normalise_tender_ref(ref)
        if ck and rk:
            dup_groups[(ck, rk, float(amount or 0.0))].append((tid, mdate))

    resolved = []
    unresolved_matches = 0
    confirmed_unrelated = 0
    dedup_note = None
    for c in dsc.collisions:
        key = _normalise_contractor(c.firm)
        what_it_is = _COLLISION_WHAT_IT_IS.get(key)
        entry = {
            "firm": c.firm,
            "amount": c.amount,
            "what_it_is": what_it_is,
            "resolution": _UNRELATED_BUSINESS_RESOLUTION if what_it_is else None,
        }
        if what_it_is is None:
            entry["reason"] = "needs_manual_resolution"
            unresolved_matches += 1
        else:
            confirmed_unrelated += 1
        resolved.append(entry)

        if dedup_note is None:
            dedup_note = _duplicate_extraction_note(dup_groups, c.firm, c.amount)

    # A genuine match is a collision resolved to an actual relationship — one
    # this module has no curated case of yet. Every collision is accounted
    # for in exactly one bucket, so this is never a bare constant: it is
    # whatever's left once the confirmed-unrelated and still-open ones are
    # subtracted.
    genuine_matches = len(dsc.collisions) - confirmed_unrelated - unresolved_matches

    return {
        "source": _ENTITY_RESOLUTION_SOURCE,
        "generated_at": generated_at,
        "named_awards": dsc.named_awards,
        "surnames_tested": dsc.surnames_tested,
        "naive_matches": len(dsc.collisions),
        "resolved": resolved,
        "genuine_matches": genuine_matches,
        "unresolved_matches": unresolved_matches,
        "dedup_note": dedup_note,
        "limits": [
            "Surname matching cannot detect a connection through a "
            "differently-named entity — a councillor with an interest in a "
            "firm trading under any other name is invisible to this test.",
            "This is a null within a stated coverage boundary, not proof "
            "of absence.",
            f"Only separately-moved tender-award motions are visible, not "
            f"consent-agenda'd awards — {dsc.named_awards} named awards were "
            f"tested against {dsc.tender_motions} tender-award motions.",
        ],
    }
