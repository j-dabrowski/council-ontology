"""
One-off backfill (docs/uplift/migration/02-claim-layer.md Step 8): parses
docs/investigator/INVESTIGATIONS.md's existing `## [N] ...` entries into
docs/investigator/hypothesis_registry.json's structured form.

Best-effort, per that step's own instruction: `pre_registered_at` for
every backfilled entry is the date THIS SCRIPT RUNS, not the original
investigation date — a hypothesis registry entry's whole point is proving
the question predated the result, which a retrospective parse of an
already-written document cannot honestly claim. The real session date
INVESTIGATIONS.md records is kept in `investigation_session_label`
instead, for context, never as a substitute.

Only genuine hypothesis headings are backfilled. INVESTIGATIONS.md's `##
[tag] ...` headings were enumerated by hand before writing this script
(72 total) — most are a leading integer, optionally with a suffix
("35 REFINED", "48 REFINEMENT ATTEMPT"), each kept as its own registry
entry (one row per dated log event, not collapsed into one row per
hypothesis number — simpler, and erring toward a larger family_size is
the safer direction for a multiple-comparison correction). A fixed,
explicit denylist below (`_NON_HYPOTHESIS_TAGS`) skips the small number of
purely administrative headings (a data-quality fix note, stage/phase
progress markers) that were never actually hypotheses — checked against
that enumeration, not inferred by a heuristic that could silently miss a
new shape in a future edit of the file.

Run with: python scripts/backfill_hypothesis_registry.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

from src.hypothesis_registry import (
    DEFAULT_PATH,
    OUTCOME_DROPPED,
    OUTCOME_NULL,
    OUTCOME_REPORTED,
    HypothesisEntry,
    save_registry,
)

console = Console()

INVESTIGATIONS_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "investigator" / "INVESTIGATIONS.md"
)

# Enumerated by hand (grep -oP '(?<=^## \[)[^\]]+' docs/investigator/
# INVESTIGATIONS.md) against the file as it stood 2026-09-20 — administrative
# headings that were never a testable hypothesis. Not a heuristic: a future
# edit adding a genuinely new administrative-note shape needs this list
# updated by hand too, which is the point (silently mis-skipping a real
# hypothesis is worse than this script needing a small edit).
_NON_HYPOTHESIS_TAGS = frozenset({
    "data-quality", "note", "SYNTHESIS", "PROMOTER PASS", "BATTERY",
    "INTERACT", "INTERACT cont'd", "PANELS", "INTERACT tenders",
    "INTERACT power", "INTERACT recusal", "STAGE-3 BATTERY", "SYNTHESIS v2",
    "STAGE 9", "RUNNER",
})

# Raw table names (as INVESTIGATIONS.md's own "Tables:" lines name them,
# predating the gold-table layer) mapped onto the 7 target gold tables
# (docs/uplift/02-claim-layer.md) where a direct equivalent exists.
# Anything not in this map is kept as its own raw name rather than
# guessing — several ("community_submissions", "councillors") have no
# gold-table equivalent at all.
_RAW_TO_GOLD = {
    "votes": "vote_fact", "vote": "vote_fact",
    "interest_declarations": "declaration_fact",
    "tenders": "tender_fact", "tender": "tender_fact",
    "planning_applications": "application_fact",
    "public_questions": "question_fact",
    "appointments": "membership_fact",
    "motions": "motion_fact", "motion": "motion_fact",
}

_HEADING_RE = re.compile(r"^## \[(?P<tag>[^\]]+)\]\s*(?P<rest>.*)$", re.MULTILINE)
_SESSION_HEADER_RE = re.compile(r"^#\s+(Phase\s+\S+.*)$", re.MULTILINE)
_CODIFIED_RE = re.compile(r"codified as `([\w.]+)`")
_TABLES_RE = re.compile(r"^\s*Tables:\s*(.+?)(?=\n\s*\n|\n {2}[A-Z][a-z]+:|\Z)", re.MULTILINE | re.DOTALL)
_FINDING_RE = re.compile(r"^\s*Finding:\s*(.+?)(?=\n\s*\n|\n {2}[A-Z][a-z]+:|\Z)", re.MULTILINE | re.DOTALL)
_REASON_RE = re.compile(r"(?:Reason|Why infeasible)(?: \(.*?\))?:\s*(.+?)(?=\n\s*\n|\Z)", re.DOTALL)


def _clean_question(rest: str) -> str:
    """Strip trailing outcome markers (✓/✗ and whatever words follow) from
    a heading's text, leaving just the question as posed."""
    return re.split(r"\s*[✓✗]", rest, maxsplit=1)[0].strip()


def _classify_outcome(tag: str, rest: str, body: str) -> tuple[str, str | None]:
    if "INFEASIBLE" in body or "pre-killed" in tag.lower():
        reason = _REASON_RE.search(body)
        return OUTCOME_DROPPED, (
            reason.group(1).strip().replace("\n", " ")[:300] if reason else "marked infeasible/pre-killed"
        )
    if "✓" in rest:
        return OUTCOME_REPORTED, None
    if "✗" in rest:
        finding = _FINDING_RE.search(body)
        reason = finding.group(1).strip().replace("\n", " ")[:300] if finding else None
        return OUTCOME_NULL, (reason or "null result — see INVESTIGATIONS.md for detail")
    if "Already built" in body or "confirmed live" in body:
        return OUTCOME_REPORTED, None
    return OUTCOME_NULL, None


def _gold_tables(body: str) -> tuple[str, ...]:
    match = _TABLES_RE.search(body)
    if not match:
        return ()
    # Strip parenthetical field lists ("votes (declared_interest, choice)")
    # before splitting on comma/x/× — otherwise a field name inside the
    # parens gets split out as if it were its own table.
    without_parens = re.sub(r"\([^)]*\)", "", match.group(1))
    raw = [t.strip() for t in re.split(r"[,×x]", without_parens) if t.strip()]
    return tuple(_RAW_TO_GOLD.get(t, t) for t in raw if t)


def _session_label(pos: int, text: str) -> str | None:
    headers = list(_SESSION_HEADER_RE.finditer(text[:pos]))
    return headers[-1].group(1).strip() if headers else None


def backfill() -> tuple[list[HypothesisEntry], list[str]]:
    text = INVESTIGATIONS_PATH.read_text()
    headings = list(_HEADING_RE.finditer(text))
    today = datetime.now(timezone.utc).date().isoformat()
    entries: list[HypothesisEntry] = []
    skipped: list[str] = []
    for i, m in enumerate(headings):
        tag, rest = m.group("tag"), m.group("rest")
        if tag in _NON_HYPOTHESIS_TAGS:
            skipped.append(tag)
            continue
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end]
        outcome, drop_reason = _classify_outcome(tag, rest, body)
        codified = _CODIFIED_RE.search(rest) or _CODIFIED_RE.search(body)
        entry_id = "inv-" + re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
        entries.append(HypothesisEntry(
            id=entry_id,
            question=_clean_question(rest),
            pre_registered_at=today,
            gold_tables_used=_gold_tables(body),
            outcome=outcome,
            claim_id=codified.group(1) if codified else None,
            drop_reason=drop_reason,
            backfilled=True,
            investigation_session_label=_session_label(m.start(), text),
            source_heading=f"## [{tag}] {rest}".strip(),
        ))
    return entries, skipped


if __name__ == "__main__":
    entries, skipped = backfill()
    save_registry(entries, DEFAULT_PATH)
    console.print(f"Parsed {len(entries) + len(skipped)} headings from {INVESTIGATIONS_PATH}")
    console.print(f"  [green]{len(entries)}[/green] backfilled as hypotheses -> {DEFAULT_PATH}")
    console.print(f"  [dim]{len(skipped)} skipped as non-hypothesis administrative headings: {skipped}[/dim]")
    n_reported = sum(1 for e in entries if e.outcome == OUTCOME_REPORTED)
    n_null = sum(1 for e in entries if e.outcome == OUTCOME_NULL)
    n_dropped = sum(1 for e in entries if e.outcome == OUTCOME_DROPPED)
    n_linked = sum(1 for e in entries if e.claim_id)
    console.print(
        f"  outcomes: {n_reported} reported, {n_null} null, {n_dropped} dropped; "
        f"{n_linked} linked to a claim_id via an explicit \"codified as\" reference"
    )
