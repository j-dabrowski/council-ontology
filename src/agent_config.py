"""
Switches that gate agent behavior across the investigator, research, and
review tracks — not general project constants, just the small set of
toggles that decide whether/how an LLM-driven session acts:

- `data_enrichment_status` (OPEN | FROZEN) — gates Explorer's write to
  `docs/pipeline/DATA_ENRICHMENT.md` (see `Explorer_prompt.txt` Phase 3
  step 0).
- `researcher_gate_mode` (file-review | auto-merge) — default gate mode
  for a Researcher session when not explicitly overridden at session
  start (see `docs/research/RESEARCH_PROTOCOL.md`).
- `conductor_max_passes` — how many Editor/Fixer rounds the Conductor
  attempts before escalating a draft to a human (see
  `docs/review/CONDUCTOR.md`).

Plain JSON, read directly — not parsed out of a doc's prose. An earlier
design read the OPEN/FROZEN value out of a Status line in
`DATA_ENRICHMENT.md`'s markdown, which breaks the moment that doc's
wording changes underneath it. This file is the one place — for code and
for LLM sessions reading it directly — that actually holds the value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_switches.json"

_VALID_DATA_ENRICHMENT_STATUS = ("OPEN", "FROZEN")
_VALID_RESEARCHER_GATE_MODE = ("file-review", "auto-merge")


@dataclass
class AgentSwitches:
    data_enrichment_status: str
    researcher_gate_mode: str
    conductor_max_passes: int


def load_agent_switches(path: Path = DEFAULT_PATH) -> AgentSwitches:
    if not path.exists():
        raise FileNotFoundError(f"No agent switches config at {path}")
    data = json.loads(path.read_text())

    status = data.get("data_enrichment_status")
    if status not in _VALID_DATA_ENRICHMENT_STATUS:
        raise ValueError(
            f"data_enrichment_status must be one of {_VALID_DATA_ENRICHMENT_STATUS}, got {status!r}"
        )

    gate_mode = data.get("researcher_gate_mode")
    if gate_mode not in _VALID_RESEARCHER_GATE_MODE:
        raise ValueError(
            f"researcher_gate_mode must be one of {_VALID_RESEARCHER_GATE_MODE}, got {gate_mode!r}"
        )

    max_passes = data.get("conductor_max_passes")
    if not isinstance(max_passes, int) or max_passes < 1:
        raise ValueError(f"conductor_max_passes must be a positive integer, got {max_passes!r}")

    return AgentSwitches(
        data_enrichment_status=status,
        researcher_gate_mode=gate_mode,
        conductor_max_passes=max_passes,
    )
