"""
Loader for config/rating.json — the rule behind the overall governance
rating (docs/frontend/MAP_PAGE_PLAN.md Phase 1): the bands, the floors that
can push a band down, and the coverage gate that withholds a rating from a
too-thinly-recorded corpus. Plain data, not code, because none of it can be
calibrated until a second council's battery exists to check it against — see
the file's own `note` field.

Modelled on src/agent_config.py: plain `json.load`, a dataclass per shape, a
clear error on a malformed file rather than a silent default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "rating.json"

_VALID_FLOOR_WHEN = ("any_grade", "grade_count_in_category")


@dataclass(frozen=True)
class Band:
    id: str
    label: str
    max_critical_share: float


@dataclass(frozen=True)
class Floor:
    when: str
    grade: str
    force_band: str
    reason: str
    min: int | None = None


@dataclass(frozen=True)
class CoverageGate:
    min_computable_share: float
    min_decisive_tests: int
    band_id: str
    label: str


@dataclass(frozen=True)
class RatingConfig:
    version: int
    provisional: bool
    bands: list[Band]
    floors: list[Floor]
    coverage_gate: CoverageGate


def load_rating_config(path: Path = DEFAULT_PATH) -> RatingConfig:
    if not path.exists():
        raise FileNotFoundError(f"No rating config at {path}")
    data = json.loads(path.read_text())

    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"version must be a positive integer, got {version!r}")

    provisional = data.get("provisional")
    if not isinstance(provisional, bool):
        raise ValueError(f"provisional must be a bool, got {provisional!r}")

    raw_bands = data.get("bands")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise ValueError("bands must be a non-empty list")
    bands: list[Band] = []
    for b in raw_bands:
        try:
            bands.append(Band(id=b["id"], label=b["label"],
                               max_critical_share=float(b["max_critical_share"])))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"malformed band entry {b!r}: {e}") from e
    band_ids = [b.id for b in bands]
    if len(band_ids) != len(set(band_ids)):
        raise ValueError(f"band ids must be unique, got {band_ids}")
    thresholds = [b.max_critical_share for b in bands]
    if thresholds != sorted(thresholds):
        raise ValueError(f"bands must be listed in increasing max_critical_share order, got {thresholds}")
    if thresholds[-1] != 1.0:
        raise ValueError(f"the last band's max_critical_share must be 1.0 (covers every share), got {thresholds[-1]}")
    if any(t < 0 or t > 1 for t in thresholds):
        raise ValueError(f"max_critical_share values must be in [0, 1], got {thresholds}")

    raw_floors = data.get("floors")
    if not isinstance(raw_floors, list):
        raise ValueError("floors must be a list")
    floors: list[Floor] = []
    for f in raw_floors:
        when = f.get("when")
        if when not in _VALID_FLOOR_WHEN:
            raise ValueError(f"floor 'when' must be one of {_VALID_FLOOR_WHEN}, got {when!r}")
        force_band = f.get("force_band")
        if force_band not in band_ids:
            raise ValueError(f"floor force_band {force_band!r} is not a known band id {band_ids}")
        reason = f.get("reason")
        if not reason or not isinstance(reason, str):
            raise ValueError(f"floor reason must be a non-empty string, got {reason!r}")
        grade = f.get("grade")
        if not grade or not isinstance(grade, str):
            raise ValueError(f"floor grade must be a non-empty string, got {grade!r}")
        min_ = f.get("min")
        if when == "grade_count_in_category":
            if not isinstance(min_, int) or min_ < 1:
                raise ValueError(f"floor with when=grade_count_in_category needs an integer min >= 1, got {min_!r}")
        floors.append(Floor(when=when, grade=grade, force_band=force_band, reason=reason, min=min_))

    raw_gate = data.get("coverage_gate")
    if not isinstance(raw_gate, dict):
        raise ValueError("coverage_gate must be an object")
    try:
        coverage_gate = CoverageGate(
            min_computable_share=float(raw_gate["min_computable_share"]),
            min_decisive_tests=int(raw_gate["min_decisive_tests"]),
            band_id=raw_gate["band_id"],
            label=raw_gate["label"],
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"malformed coverage_gate {raw_gate!r}: {e}") from e
    if not (0 <= coverage_gate.min_computable_share <= 1):
        raise ValueError(f"coverage_gate.min_computable_share must be in [0, 1], got {coverage_gate.min_computable_share}")
    if coverage_gate.min_decisive_tests < 0:
        raise ValueError(f"coverage_gate.min_decisive_tests must be >= 0, got {coverage_gate.min_decisive_tests}")
    if coverage_gate.band_id in band_ids:
        raise ValueError(f"coverage_gate.band_id {coverage_gate.band_id!r} must not collide with a real band id")

    return RatingConfig(version=version, provisional=provisional, bands=bands,
                         floors=floors, coverage_gate=coverage_gate)
