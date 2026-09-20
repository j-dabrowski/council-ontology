"""
The structured hypothesis registry (docs/uplift/migration/02-claim-layer.md
Step 8; target schema docs/uplift/02-claim-layer.md "Hypothesis registry").

Purposes, per the target spec:
1. Gives a claim's `statistic.multiple_comparison.family_size`
   (`src/analysis/claims.py`) a real value instead of the schema's default
   of 1.
2. Enables publishing "we tested N hypotheses; M reached the reporting
   threshold" — the difference between an analysis and a highlight reel.
3. Prevents silent hypothesis-shopping across regeneration runs.

Schema per the target spec (`id, question, pre_registered_at,
gold_tables_used, outcome, claim_id, drop_reason`), plus two additive
provenance fields the target spec doesn't ask for but a backfilled entry
needs to stay honest about: `backfilled` (True for every entry
`scripts/backfill_hypothesis_registry.py` produced) and
`investigation_session_label` (the real session/date
`docs/investigator/INVESTIGATIONS.md` recorded — kept for context, never a
substitute for `pre_registered_at`, which for a backfilled entry is
necessarily the backfill run's own date: proving a hypothesis predated its
result is exactly what a retrospective parse of an already-written
document cannot honestly claim).

File location: `docs/investigator/hypothesis_registry.json`, not the
migration plan's literal `investigator/hypothesis_registry.json` — this
project's top-level `investigator/` track directory was folded into
`docs/investigator/` in the 2026-06-27 doc reorg, before that plan was
written.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "docs" / "investigator" / "hypothesis_registry.json"

OUTCOME_REPORTED = "reported"
OUTCOME_NULL = "null"
OUTCOME_DROPPED = "dropped"
_OUTCOMES = frozenset({OUTCOME_REPORTED, OUTCOME_NULL, OUTCOME_DROPPED})


@dataclass(frozen=True)
class HypothesisEntry:
    id: str
    question: str
    pre_registered_at: str  # ISO date - the date this ENTRY was added to the registry
    gold_tables_used: tuple[str, ...]
    outcome: str  # reported | null | dropped
    claim_id: str | None = None
    drop_reason: str | None = None
    backfilled: bool = False
    investigation_session_label: str | None = None
    source_heading: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in _OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(_OUTCOMES)}, got {self.outcome!r}")


def load_registry(path: Path = DEFAULT_PATH) -> list[HypothesisEntry]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [
        HypothesisEntry(**{**e, "gold_tables_used": tuple(e.get("gold_tables_used", ()))})
        for e in data
    ]


def save_registry(entries: list[HypothesisEntry], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(e) for e in entries], indent=2) + "\n")


def append_entry(entry: HypothesisEntry, path: Path = DEFAULT_PATH) -> None:
    """For a future `council explore` session: append one structured entry
    alongside `INVESTIGATIONS.md`'s own prose (both kept — the prose
    remains the human-readable notebook; this is what `family_size`
    actually counts). Raises `ValueError` on a duplicate id rather than
    silently overwriting."""
    entries = load_registry(path)
    if any(e.id == entry.id for e in entries):
        raise ValueError(f"hypothesis id {entry.id!r} already registered")
    entries.append(entry)
    save_registry(entries, path)


def family_size(entries: list[HypothesisEntry] | None = None, path: Path = DEFAULT_PATH) -> int:
    """The whole registry, by default — the most conservative (largest)
    family a multiple-comparison correction could use. The target schema
    doesn't define a finer-grained "family" grouping (e.g. by test_id
    prefix or shared `gold_tables_used`), so this doesn't invent one; a
    caller needing a narrower family should filter `entries` itself before
    passing them in. Erring toward a larger count is also the safer
    direction here: undercounting understates the correction a claim's
    `survives_correction` needs, overcounting only makes it more
    conservative."""
    if entries is None:
        entries = load_registry(path)
    return len(entries)
