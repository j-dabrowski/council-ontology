"""
Loader for config/frameworks.json (docs/uplift/migration/04-jurisdiction.md
Steps 1-2) — the WA statutory instrument table this council is actually
assessed against, plus Nolan/CIPFA demoted to a secondary mapping.

Modelled on src/council_eras.py: plain `json.load`, `DEFAULT_PATH` beside
the module. The future `framework_refs` claim-object field
(`02-claim-layer.md`) will resolve `{instrument, section}` pairs against
`primary_instruments()`'s keys — this loader is the first real consumer-
facing surface for that config, ahead of that field existing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "frameworks.json"


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    relevance: str


def _load(path: Path = DEFAULT_PATH) -> dict:
    if not path.exists():
        return {"primary_instruments": {}, "secondary_mapping": {}}
    return json.loads(path.read_text())


def primary_instruments(path: Path = DEFAULT_PATH) -> dict[str, Instrument]:
    """The seven WA instruments, keyed as `framework_refs` will key them
    (`LGA_1995`, `ADMIN_REGS`, `FG_REGS`, `CONDUCT_REGS`, `MODEL_CODE_2021`,
    `DLGSC`, `SAT`)."""
    data = _load(path)
    return {
        key: Instrument(key=key, name=v["name"], relevance=v["relevance"])
        for key, v in data.get("primary_instruments", {}).items()
    }


def instrument(key: str, path: Path = DEFAULT_PATH) -> Instrument | None:
    return primary_instruments(path).get(key)


def secondary_mapping(path: Path = DEFAULT_PATH) -> dict:
    """Nolan/CIPFA definitions, demoted but not deleted — `{"nolan": {...},
    "cipfa": {...}}`, each a flat `{key: definition}` dict."""
    return _load(path).get("secondary_mapping", {})
