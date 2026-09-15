"""
Tests for src/analysis/rating.py against the eight scenarios simulated in
docs/frontend/MAP_PAGE_PLAN.md B.2 — those scenarios are what the rating
rule (config/rating.json) was designed against, so they're the fixtures
here rather than Cambridge's live battery, which drifts as Refiner codifies
new tests and as SECOND_COUNCIL_PLAN's Phase 1.1 rewrites existing ones.

Hermetic throughout: synthetic TestResult lists for the eight scenarios and
the crash/floor invariants; the valence/grade consistency check is the one
test here that needs a real battery, and gets it from Testville's baseline
profile (src/fixtures/testville.py) rather than data/council.db, so it
can't silently break because someone's corpus changed underneath it.
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.rating import BASE_REASON, compute_rating
from src.analysis.tests import (
    CRITICAL,
    G_COMMEND,
    G_CONCERN,
    G_INTEGRITY,
    G_NODATA,
    G_OBSERVATION,
    G_SOUND,
    G_STRENGTH,
    NEUTRAL,
    SUPPORTIVE,
    TestResult,
    run_test_battery,
)
from src.fixtures.testville import seed_profile
from src.models import Base
from src.rating_config import load_rating_config
from src.storage.database import _enable_wal_and_fk
from src.test_registry import load_test_registry

_SUPPORTIVE_GRADES = {G_SOUND, G_STRENGTH, G_COMMEND}
_CRITICAL_GRADES = {G_CONCERN, G_INTEGRITY}


def _tr(test_id: str, valence: str, grade: str, data_ok: bool = True) -> TestResult:
    return TestResult(
        test_id=test_id, title=test_id, genre="test", principle="test",
        question="test?", valence=valence, grade=grade,
        headline="test" if data_ok else "Not computable on this corpus",
        verdict="test", data_ok=data_ok,
    )


@pytest.fixture(scope="module")
def config():
    return load_rating_config()


@pytest.fixture
def categories() -> dict[str, str]:
    return {row.id: row.category for row in load_test_registry()}


# ── B.2's eight scenarios ───────────────────────────────────────────────


def test_cambridge_shaped(config, categories):
    battery = (
        [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(10)]
        + [_tr(f"n{i}", NEUTRAL, G_OBSERVATION) for i in range(10)]
        + [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(7)]
        + [_tr(f"x{i}", NEUTRAL, G_NODATA, data_ok=False) for i in range(2)]
    )
    r = compute_rating(battery, categories, config)
    assert r.band == "yellow"
    assert r.band_reason == BASE_REASON
    assert r.n_decisive == 17
    assert r.critical_share == pytest.approx(7 / 17)
    assert r.computable_share == pytest.approx(27 / 29)


def test_one_integrity_flag_all_else_strength(config, categories):
    battery = [_tr("integrity0", CRITICAL, G_INTEGRITY)] + [
        _tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(9)
    ]
    r = compute_rating(battery, categories, config)
    assert r.band == "red"
    assert r.band_reason == "one integrity flag"


def test_integrity_flag_plus_extra_mild_concerns(config, categories):
    battery = (
        [_tr("integrity0", CRITICAL, G_INTEGRITY)]
        + [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(9)]
        + [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(10)]
    )
    r = compute_rating(battery, categories, config)
    # base share alone (10/20 = 0.50) already lands in red — the floor
    # fires too, but doesn't change the band, so the reason stays "base".
    assert r.critical_share == pytest.approx(0.5)
    assert r.band == "red"
    assert r.band_reason == BASE_REASON


def test_sparse_corpus_coverage_gate(config, categories):
    battery = (
        [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(5)]
        + [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(4)]
        + [_tr(f"x{i}", NEUTRAL, G_NODATA, data_ok=False) for i in range(11)]
    )
    r = compute_rating(battery, categories, config)
    assert r.band == "insufficient"
    assert r.critical_share is None
    assert "9 of 20" in r.band_reason


def test_ten_new_observation_tests_dont_move_the_band(config, categories):
    """The drift test: neutrals are excluded from the decisive denominator,
    so growing the battery with descriptive tests must not re-colour a
    council whose conduct hasn't changed."""
    base = (
        [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(10)]
        + [_tr(f"n{i}", NEUTRAL, G_OBSERVATION) for i in range(10)]
        + [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(7)]
        + [_tr(f"x{i}", NEUTRAL, G_NODATA, data_ok=False) for i in range(2)]
    )
    grown = base + [_tr(f"n_new{i}", NEUTRAL, G_OBSERVATION) for i in range(10)]
    r_base = compute_rating(base, categories, config)
    r_grown = compute_rating(grown, categories, config)
    assert r_grown.band == r_base.band == "yellow"
    assert r_grown.band_reason == r_base.band_reason == BASE_REASON
    assert r_grown.n_decisive == r_base.n_decisive == 17
    assert r_grown.critical_share == r_base.critical_share


def test_six_new_supportive_integrity_tests(config, categories):
    base = (
        [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(10)]
        + [_tr(f"n{i}", NEUTRAL, G_OBSERVATION) for i in range(10)]
        + [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(7)]
        + [_tr(f"x{i}", NEUTRAL, G_NODATA, data_ok=False) for i in range(2)]
    )
    grown = base + [_tr(f"s_new{i}", SUPPORTIVE, G_STRENGTH) for i in range(6)]
    r = compute_rating(grown, categories, config)
    assert r.band == "yellow"
    assert r.band_reason == BASE_REASON


def test_everything_clean(config, categories):
    battery = [_tr(f"s{i}", SUPPORTIVE, G_STRENGTH) for i in range(20)]
    r = compute_rating(battery, categories, config)
    assert r.band == "green"
    assert r.band_reason == BASE_REASON
    assert r.critical_share == 0.0


def test_everything_a_concern(config, categories):
    battery = [_tr(f"c{i}", CRITICAL, G_CONCERN) for i in range(20)]
    r = compute_rating(battery, categories, config)
    assert r.band == "red"
    assert r.band_reason == BASE_REASON
    assert r.critical_share == 1.0


# ── invariants ────────────────────────────────────────────────────────────


def test_floor_never_improves_a_band(config, categories):
    """Property check over many random batteries: compute_rating() asserts
    internally if a floor would move a band upward, so simply running it
    against a wide spread of random compositions (including ones that
    trigger both floors) is enough to catch a config/rating.py disagreement
    — no AssertionError should ever escape."""
    rng = random.Random(20260915)
    cats = list({*categories.values(), "integrity_procurement"})
    for _ in range(200):
        n = rng.randint(0, 30)
        battery = []
        for i in range(n):
            data_ok = rng.random() > 0.1
            if not data_ok:
                battery.append(_tr(f"t{i}", NEUTRAL, G_NODATA, data_ok=False))
                continue
            valence = rng.choice([SUPPORTIVE, NEUTRAL, CRITICAL])
            if valence == SUPPORTIVE:
                grade = rng.choice([G_SOUND, G_STRENGTH, G_COMMEND])
            elif valence == CRITICAL:
                grade = rng.choice([G_CONCERN, G_INTEGRITY])
            else:
                grade = G_OBSERVATION
            battery.append(_tr(f"t{i}", valence, grade))
        cats_for_battery = {r.test_id: rng.choice(cats) for r in battery}
        compute_rating(battery, cats_for_battery, config)  # must not raise


def test_zero_computable_tests_is_insufficient_not_a_crash(config, categories):
    battery = [_tr(f"x{i}", NEUTRAL, G_NODATA, data_ok=False) for i in range(15)]
    r = compute_rating(battery, categories, config)
    assert r.band == "insufficient"
    assert r.critical_share is None


@pytest.fixture(scope="module")
def _baseline_battery():
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    council_id, _ = seed_profile(session, "baseline")
    battery = run_test_battery(session, council_id)
    session.close()
    return battery


def test_valence_grade_consistency_against_real_registry(_baseline_battery):
    """No named exceptions: governance.power_spread used to be the one test
    where valence and grade disagreed on purpose (MAP_PAGE_PLAN.md B.2), but
    commit 906f343 made its valence derive from real term-to-term turnover
    instead of being asserted — its grade now always agrees with its
    valence. If a future test introduces a real, deliberate mismatch, name
    it explicitly here rather than weakening this assertion."""
    bad = []
    for r in _baseline_battery:
        if not r.data_ok:
            continue
        if r.valence == SUPPORTIVE and r.grade not in _SUPPORTIVE_GRADES:
            bad.append((r.test_id, r.valence, r.grade))
        elif r.valence == CRITICAL and r.grade not in _CRITICAL_GRADES:
            bad.append((r.test_id, r.valence, r.grade))
    assert not bad, f"valence/grade disagree for: {bad}"
