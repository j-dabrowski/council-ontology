"""One-off measurement script, not part of any pipeline — never scheduled,
never imported by anything else. Re-measures docs/frontend/
RECORD_PAGE_PLAN.md A.1's coverage figures (12% Owner:/Applicant: label,
3% personal title, on a 3,000-quote sample, dated 2026-09-11) against the
live corpus, and reports what src/privacy.py's redactor actually catches
of each on real data.

Needs a populated data/council.db (gitignored, local-only — nothing in
tests/ depends on this, docs/TESTING.md "Why no LLM calls in CI").

Usage: python scripts/measure_private_name_patterns.py
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from src.privacy import PLACEHOLDER, contains_private_name_pattern, redact_private_names

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "council.db"
SAMPLE_SIZE = 3000
SEED = 20260911  # date this measurement was first taken (A.1)


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"No database at {DB_PATH} — this script needs a local data/council.db")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT quote_text FROM extraction_evidence WHERE entity_table = 'planning_applications'"
    )
    all_quotes = [row[0] for row in cur.fetchall() if row[0]]
    conn.close()

    total = len(all_quotes)
    rng = random.Random(SEED)
    sample = rng.sample(all_quotes, min(SAMPLE_SIZE, total))

    def _measure(quotes: list[str]) -> dict:
        n = len(quotes)
        has_label = sum(1 for q in quotes if _has_owner_applicant_label(q))
        has_title = sum(1 for q in quotes if _has_personal_title(q))
        has_either = sum(1 for q in quotes if contains_private_name_pattern(q))
        caught_of_labelled = sum(
            1 for q in quotes if _has_owner_applicant_label(q) and _label_fully_redacted(q)
        )
        return {
            "n": n,
            "pct_label": 100 * has_label / n,
            "pct_title": 100 * has_title / n,
            "pct_either": 100 * has_either / n,
            "labelled": has_label,
            "labelled_fully_redacted": caught_of_labelled,
        }

    sample_stats = _measure(sample)
    full_stats = _measure(all_quotes)

    print(f"Total planning_applications evidence quotes in corpus: {total}")
    print()
    print(f"Sample (n={sample_stats['n']}, seed={SEED}) — mirrors A.1's methodology:")
    print(f"  Owner:/Applicant:/Landowner: label present: {sample_stats['pct_label']:.1f}%")
    print(f"  Personal title (Mr/Mrs/Ms/Miss/Dr) present: {sample_stats['pct_title']:.1f}%")
    print(f"  Either pattern present (redactor would touch this quote): {sample_stats['pct_either']:.1f}%")
    print(
        f"  Of {sample_stats['labelled']} labelled quotes, the label's whole value is fully "
        f"redacted (no residual after the label) in {sample_stats['labelled_fully_redacted']} "
        f"({100 * sample_stats['labelled_fully_redacted'] / max(sample_stats['labelled'], 1):.1f}%)"
    )
    print()
    print(f"Full population (n={full_stats['n']}):")
    print(f"  Owner:/Applicant:/Landowner: label present: {full_stats['pct_label']:.1f}%")
    print(f"  Personal title (Mr/Mrs/Ms/Miss/Dr) present: {full_stats['pct_title']:.1f}%")
    print(f"  Either pattern present: {full_stats['pct_either']:.1f}%")


def _has_owner_applicant_label(text: str) -> bool:
    import re

    return bool(re.search(r"\b(OWNER|LANDOWNER|APPLICANT)S?:", text, re.IGNORECASE))


def _has_personal_title(text: str) -> bool:
    import re

    return bool(re.search(r"\b(Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z]", text))


def _label_fully_redacted(text: str) -> bool:
    # The label itself ("Owner:") is deliberately kept; only its value is
    # replaced. "Redacted" here means the placeholder shows up at all --
    # the value's original content is gone, not that the label vanished.
    redacted = redact_private_names(text)
    return PLACEHOLDER in redacted if redacted else True


if __name__ == "__main__":
    main()
