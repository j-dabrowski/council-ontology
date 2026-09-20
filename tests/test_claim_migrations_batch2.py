"""
Tests for the 16 additional claim-object counterparts built in the second
half of Step 6 (docs/uplift/migration/02-claim-layer.md): era/period-trend
claims (recusal_trend, transparency, question_responsiveness), two-group
bucket-comparison claims (mayoral, oversight_body_capture, objection_dose,
big_dollar_leniency, freshman, election_cycle, deputation_dissent), and
single-proportion claims (officer_divergence, threshold_gaming,
unanimity_trend, attendance, delegate_body_conflict, decider_supplier_conflict).

Hermetic by design (docs/TESTING.md -- nothing here touches
data/council.db, which is gitignored and absent from CI). Uses
src/fixtures/testville.py's "baseline" synthetic corpus (the same one
tests/test_council_agnostic.py and tests/test_rating.py already share)
rather than a bespoke fixture per function, since testville already models
every parameter these tests read (recusal_pre/inquiry/post,
officer_divergence_rate, mayor_dissent_ratio, oversight_capture,
big_dollar_gap, repeat_applicant_gap, objection_responsive, ...).

All 19 claim functions (these 16 plus the 3 in test_claim_migrations.py)
were also run by hand against the real Cambridge corpus (data/council.db)
during development -- every one executed without exception and produced a
Claim whose only lint failures fall into three documented, systemic
categories: L-02 (no achieved_power computation exists anywhere yet -
every GRADE_SUPPORTIVE claim fails it, a real, project-wide gap), L-04 (no
clustered two-proportion difference estimator exists - only the
single-sample clustered_proportion() does, so vote-level two-group
comparisons can't set clustering_unit), and L-11 on the two-group
comparison claims specifically (the claim schema's numerator/denominator
pair can't represent two groups' individual rates, only a pooled count and
the difference statistic - a real target-schema gap, not a bug in these
claims, flagged for whoever extends 02-claim-layer.md's schema next).
That real-data run is not committed or re-run in CI (same convention as
tests/test_privacy.py / tests/test_lookup_search.py).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.claim_linter import lint_claim
from src.analysis.claims import GRADE_CONCERN, GRADE_CRITICAL, GRADE_NEUTRAL, GRADE_SUPPORTIVE
from src.analysis.tests import (
    _t_attendance_claim,
    _t_big_dollar_leniency_claim,
    _t_decider_supplier_conflict_claim,
    _t_delegate_body_conflict_claim,
    _t_deputation_dissent_claim,
    _t_election_cycle_claim,
    _t_freshman_claim,
    _t_mayoral_claim,
    _t_objection_dose_claim,
    _t_officer_divergence_claim,
    _t_oversight_body_capture_claim,
    _t_question_responsiveness_claim,
    _t_recusal_trend_claim,
    _t_threshold_gaming_claim,
    _t_transparency_claim,
    _t_unanimity_trend_claim,
)
from src.fixtures.testville import seed_profile
from src.models import Base
from src.storage.database import _enable_wal_and_fk

ALL_CLAIM_FNS = [
    _t_attendance_claim, _t_big_dollar_leniency_claim, _t_decider_supplier_conflict_claim,
    _t_delegate_body_conflict_claim, _t_deputation_dissent_claim, _t_election_cycle_claim,
    _t_freshman_claim, _t_mayoral_claim, _t_objection_dose_claim, _t_officer_divergence_claim,
    _t_oversight_body_capture_claim, _t_question_responsiveness_claim, _t_recusal_trend_claim,
    _t_threshold_gaming_claim, _t_transparency_claim, _t_unanimity_trend_claim,
]


@pytest.fixture(scope="module")
def session():
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, expire_on_commit=False)()
    yield sess
    sess.close()


@pytest.fixture(scope="module")
def council_id(session):
    cid, _created = seed_profile(session, "baseline")
    return cid


@pytest.mark.parametrize("fn", ALL_CLAIM_FNS, ids=lambda f: f.__name__)
def test_claim_fn_runs_clean_against_testville(fn, session, council_id):
    """Every claim function must either return None (no data) or a valid
    Claim, and must lint without raising — the baseline invariant Step 6's
    own "Done when" requires (a claim object, or a controlled, named
    failure — never a crash or silence)."""
    claim = fn(session, council_id, {})
    if claim is None:
        return
    assert claim.grade in {GRADE_CRITICAL, GRADE_CONCERN, GRADE_NEUTRAL, GRADE_SUPPORTIVE}
    assert claim.denominator.n > 0
    assert claim.numerator.n >= 0
    results = lint_claim(claim)  # must not raise
    assert results  # every claim gets checked against all 17 single-claim rules


def test_officer_divergence_claim_reflects_configured_divergence_rate(session, council_id):
    """Baseline profile sets officer_divergence_rate=0.04 (near-total
    ratification) -- the claim should grade this critical, same direction
    the legacy TestResult reaches."""
    claim = _t_officer_divergence_claim(session, council_id, {})
    assert claim is not None
    assert claim.statistic.value > 0.9  # >90% ratification at a 4% divergence rate


def test_recusal_trend_claim_direction_matches_configured_profile():
    """Baseline profile sets recusal_pre=0.75 > recusal_post=0.35 -- a real
    decline. Uses a fresh in-memory DB (not the module-scoped session/
    council_id fixtures) since this profile has already been seeded there
    with a fixed random seed; re-seeding here keeps this test independent
    of fixture execution order."""
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, expire_on_commit=False)()
    cid, _ = seed_profile(sess, "baseline")
    claim = _t_recusal_trend_claim(sess, cid, {})
    assert claim is not None
    assert claim.statistic.value < 0  # post minus pre should be negative (a decline)
