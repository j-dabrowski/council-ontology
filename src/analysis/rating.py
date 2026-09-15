"""
The overall governance rating (docs/frontend/MAP_PAGE_PLAN.md Phase 1) — one
scripted band (green / yellow / red / insufficient) per council, derived from
the standard test battery's own `valence`/`grade`/`data_ok` fields and
nothing else.

Deliberately reads claim *metadata* only — never `headline`, `verdict`,
`named_entities` or any other prose field on a `TestResult`. That is what
lets `rating.json` ship at public tier regardless of what tier the battery's
own claims derive (src/cli.py's SNAPSHOT_TIER comment on "rating" explains
why that matters).

`band_reason` is scripted, never authored: it is always either the literal
sentinel "base" or one `reason` string lifted verbatim from
config/rating.json — the same convention watch.json's `why` field uses,
and for the same reason: it is a sentence about a named council that ships
verbatim to the public, so no one gets to write it by hand.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.analysis.tests import CRITICAL, SUPPORTIVE, TestResult, battery_summary
from src.rating_config import Floor, RatingConfig

BASE_REASON = "base"


@dataclass(frozen=True)
class Rating:
    band: str
    band_label: str
    band_reason: str
    critical_share: float | None
    n_supportive: int
    n_neutral: int
    n_critical: int
    n_not_computable: int
    n_decisive: int
    computable_share: float
    config_version: int


def _band_index(config: RatingConfig, band_id: str) -> int:
    for i, b in enumerate(config.bands):
        if b.id == band_id:
            return i
    raise ValueError(f"unknown band id {band_id!r}")


def _floor_fires(floor: Floor, computable: list[TestResult], categories: dict[str, str]) -> bool:
    if floor.when == "any_grade":
        return any(r.grade == floor.grade for r in computable)
    if floor.when == "grade_count_in_category":
        counts: Counter[str] = Counter()
        for r in computable:
            if r.grade == floor.grade:
                counts[categories.get(r.test_id, "")] += 1
        return any(n >= (floor.min or 1) for n in counts.values())
    raise ValueError(f"unknown floor 'when' {floor.when!r}")


def compute_rating(
    battery: list[TestResult], categories: dict[str, str], config: RatingConfig,
) -> Rating:
    summary = battery_summary(battery)
    n_total = len(battery)
    computable = [r for r in battery if r.data_ok]
    n_computable = len(computable)
    computable_share = n_computable / n_total if n_total else 0.0

    decisive = [r for r in computable if r.valence in (SUPPORTIVE, CRITICAL)]
    n_decisive = len(decisive)

    gate = config.coverage_gate
    coverage_fails = computable_share < gate.min_computable_share
    decisive_fails = n_decisive < gate.min_decisive_tests
    if coverage_fails or decisive_fails:
        if coverage_fails and decisive_fails:
            reason = (
                f"only {n_computable} of {n_total} tests could be run on this corpus, "
                f"leaving only {n_decisive} decisive result(s)"
            )
        elif coverage_fails:
            reason = f"only {n_computable} of {n_total} tests could be run on this corpus"
        else:
            reason = f"only {n_decisive} decisive test result(s) on this corpus"
        return Rating(
            band=gate.band_id, band_label=gate.label, band_reason=reason,
            critical_share=None,
            n_supportive=summary["n_supportive"], n_neutral=summary["n_neutral"],
            n_critical=summary["n_critical"], n_not_computable=summary["n_not_computable"],
            n_decisive=n_decisive, computable_share=computable_share,
            config_version=config.version,
        )

    n_critical_decisive = sum(1 for r in decisive if r.valence == CRITICAL)
    critical_share = n_critical_decisive / n_decisive if n_decisive else 0.0

    band = next(b for b in config.bands if critical_share <= b.max_critical_share)
    band_reason = BASE_REASON

    for floor in config.floors:
        if not _floor_fires(floor, computable, categories):
            continue
        current_idx = _band_index(config, band.id)
        floor_idx = _band_index(config, floor.force_band)
        # A floor names a *minimum* severity, not an exact assignment: it
        # only ever applies when it is strictly worse than where the band
        # already stands (from the base share or an earlier floor). This
        # guard is what makes "a floor may only move a band downward" true
        # by construction — a floor whose target is milder than the
        # current band (e.g. this floor fires but the base share already
        # put the council in a worse band) is a no-op, not a bug: nothing
        # ever gets reassigned to a milder band here.
        if floor_idx > current_idx:
            band = next(b for b in config.bands if b.id == floor.force_band)
            band_reason = floor.reason

    return Rating(
        band=band.id, band_label=band.label, band_reason=band_reason,
        critical_share=critical_share,
        n_supportive=summary["n_supportive"], n_neutral=summary["n_neutral"],
        n_critical=summary["n_critical"], n_not_computable=summary["n_not_computable"],
        n_decisive=n_decisive, computable_share=computable_share,
        config_version=config.version,
    )
