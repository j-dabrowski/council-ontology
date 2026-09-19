"""
Loader for config/council_eras.json — per-council named era boundaries
(docs/SECOND_COUNCIL_PLAN.md Phase 1.2; docs/uplift/migration/
04-jurisdiction.md Step 3 extended this to multiple named windows per
council, not just the one external-scrutiny window).

Originally replaced the hardcoded 2018-2021 "Authorised Inquiry" window
that used to sit directly in `src/analysis/queries.py`'s `_recusal_era()`
— real for Cambridge, meaningless for any other council. A council with no
"inquiry" entry has no configured scrutiny window at all: `conflict.
recusal_trend` and `engagement.question_responsiveness` (`src/analysis/
tests.py`) degrade to an era-neutral computation rather than inventing a
split with no basis.

Step 3 added three more named windows any council can define alongside
"inquiry" — `model_code_2021`, `conduct_regs_2007`, `covid_2020` — each a
real WA statutory/pandemic boundary, not council-specific. `to_year` may be
`None` for a window still in force (e.g. the 2021 Model Code hasn't been
superseded). `era_window_for()`'s signature is unchanged for its one
existing caller (`queries.py`'s `_council_era_window()`): a bare
`era_window_for(short_name)` still returns the "inquiry" window exactly as
before — `window_name` is new and optional, additive to every existing
call site.

Modelled on src/test_registry.py: plain `json.load`, a frozen dataclass per
row, `DEFAULT_PATH` beside the module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "council_eras.json"
FISCAL_YEAR_PATH = Path(__file__).resolve().parent.parent / "config" / "fiscal_year.json"


@dataclass(frozen=True)
class EraWindow:
    label: str
    from_year: int
    to_year: int | None  # None: still in force, no end year yet


def load_council_eras(path: Path = DEFAULT_PATH) -> dict[str, dict[str, EraWindow]]:
    """`{council_short_name_lower: {window_name: EraWindow}}` — every named
    window for every council, e.g. `{"cambridge": {"inquiry": ...,
    "model_code_2021": ..., "conduct_regs_2007": ..., "covid_2020": ...}}`.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {
        council_key.lower(): {
            window_name: EraWindow(label=v["label"], from_year=v["from"], to_year=v.get("to"))
            for window_name, v in windows.items()
        }
        for council_key, windows in data.items()
    }


def era_window_for(
    council_short_name: str, window_name: str = "inquiry", path: Path = DEFAULT_PATH,
) -> EraWindow | None:
    """`council_short_name` is `Council.short_name` (e.g. "Cambridge",
    "Testville") — matched case-insensitively against the config's keys.
    `window_name` defaults to "inquiry" (the original single-window
    meaning) so every existing call site is unaffected; pass
    "model_code_2021" / "conduct_regs_2007" / "covid_2020" for the other
    three era boundaries.
    """
    return load_council_eras(path).get(council_short_name.lower(), {}).get(window_name)


def fiscal_year_start_month(council_short_name: str, path: Path = FISCAL_YEAR_PATH) -> int:
    """The calendar month (1-12) this council's fiscal year starts on
    (docs/uplift/migration/01-known-defects.md Step 2). Defaults to 7 (WA's
    1 Jul-30 Jun local-government year, LGA 1995 s6.2) if the config is
    missing or the council has no override — every council in this project
    is WA-jurisdiction today, so `overrides` is empty until that changes."""
    if not path.exists():
        return 7
    data = json.loads(path.read_text())
    overrides = {k.lower(): v for k, v in data.get("overrides", {}).items()}
    return overrides.get(council_short_name.lower(), data.get("default_start_month", 7))
