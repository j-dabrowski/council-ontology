"""
Loader for config/council_eras.json — per-council external-scrutiny window
(docs/SECOND_COUNCIL_PLAN.md Phase 1.2).

Replaces the hardcoded 2018-2021 "Authorised Inquiry" window that used to
sit directly in `src/analysis/queries.py`'s `_recusal_era()` — real for
Cambridge, meaningless for any other council. A council with no entry here
has no configured window at all: `conflict.recusal_trend` and
`engagement.question_responsiveness` (`src/analysis/tests.py`) degrade to
an era-neutral computation rather than inventing a split with no basis.

Modelled on src/test_registry.py: plain `json.load`, a frozen dataclass per
row, `DEFAULT_PATH` beside the module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "council_eras.json"


@dataclass(frozen=True)
class EraWindow:
    label: str
    from_year: int
    to_year: int


def load_council_eras(path: Path = DEFAULT_PATH) -> dict[str, EraWindow]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {
        key.lower(): EraWindow(label=v["label"], from_year=v["from"], to_year=v["to"])
        for key, v in data.items()
    }


def era_window_for(council_short_name: str, path: Path = DEFAULT_PATH) -> EraWindow | None:
    """`council_short_name` is `Council.short_name` (e.g. "Cambridge",
    "Testville") — matched case-insensitively against the config's keys."""
    return load_council_eras(path).get(council_short_name.lower())
