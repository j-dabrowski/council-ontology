"""
Loader for config/test_registry.json — the canonical, council-agnostic list
of tests the Standard Council Test Battery runs (docs/frontend/
TEST_REGISTRY_PLAN.md Part B). One row per test: `id` is the join key back
to `src.analysis.tests._GENERATORS` and to a snapshot's `test_id`; every
other field is either static copy (title/question/principles/method/
caveats/objection/response) or routing (category, order, has_deep_dive,
meeting_scope, detail_panel, evidence_query, evidence_snapshot). Never a
computed number — those live in scorecard.json/digest.json, not here.

Modelled on src/agent_config.py: plain `json.load`, a frozen dataclass per
row, `DEFAULT_PATH` beside the module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "test_registry.json"

_VALID_CATEGORIES = (
    "integrity_procurement",
    "governance_culture",
    "transparency_engagement",
    "financial",
)


@dataclass(frozen=True)
class RegistryRow:
    id: str
    order: int
    category: str
    question_technical: str
    question_public: str
    title_technical: str
    title_public: str
    principles: list[str]
    method: str
    caveats: list[str]
    objection: str | None
    response: str | None
    evidence_query: str
    evidence_snapshot: str | None
    has_deep_dive: bool
    public_interest: bool
    meeting_scope: bool
    detail_panel: str
    code: str | None = None


def load_test_registry(path: Path = DEFAULT_PATH) -> list[RegistryRow]:
    if not path.exists():
        raise FileNotFoundError(f"No test registry at {path}")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of rows")

    registry = [RegistryRow(**row) for row in rows]

    for row in registry:
        if row.category not in _VALID_CATEGORIES:
            raise ValueError(
                f"{row.id}: category must be one of {_VALID_CATEGORIES}, got {row.category!r}"
            )
    return registry
