"""
Tests for the 7 claim-object counterparts built using the new median/
categorical/concentration/overlap/trend inference machinery (docs/uplift/
migration/02-claim-layer.md Step 6, continued): voting_power, tenure,
tender_concentration, procurement_incumbency, engagement,
confidential_tender_size, confidential_topics.

These complete claim-object coverage for 26 of the 29 battery tests. The
remaining 3 (single_source, reserve_trajectory, sponsorship) are not
attempted: the first two have no underlying data on this corpus at all
(already `_nodata` in the legacy TestResult path), and the third's query
(`sponsorship_network()`) emits hardcoded era-by-era prose rather than a
computed statistic — no amount of inference machinery closes either gap.

Hermetic by design (docs/TESTING.md), same `testville` "baseline" fixture
as test_claim_migrations_batch2.py. All 7 were also run by hand against
the real Cambridge corpus (data/council.db) during development — every
one executed without exception; that run caught and fixed two real,
generalizable bugs in claim_linter.py's L-11/L-03 number regex (a hyphen
in a compound word like "top-10" or a range like "41-92%" was misread as
a negative sign; a comma-formatted thousand like "4,993" was split at the
comma into two numbers) rather than any bug in these claims. Remaining
lint failures on the real corpus fall into the same already-documented
systemic categories (L-02: no achieved_power computation anywhere; L-11:
some narrative figures — e.g. a single individual's raw tenure, a firm
count — aren't literally statistic/numerator/denominator fields, the same
class of gap already flagged for the two-group comparison claims).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.claim_linter import lint_claim
from src.analysis.claims import GRADE_CONCERN, GRADE_CRITICAL, GRADE_NEUTRAL, GRADE_SUPPORTIVE
from src.analysis.tests import (
    _t_confidential_tender_size_claim,
    _t_confidential_topics_claim,
    _t_engagement_claim,
    _t_procurement_incumbency_claim,
    _t_tender_concentration_claim,
    _t_tenure_claim,
    _t_voting_power_claim,
)
from src.fixtures.testville import seed_profile
from src.models import Base
from src.storage.database import _enable_wal_and_fk

ALL_CLAIM_FNS = [
    _t_voting_power_claim, _t_tenure_claim, _t_tender_concentration_claim,
    _t_procurement_incumbency_claim, _t_engagement_claim,
    _t_confidential_tender_size_claim, _t_confidential_topics_claim,
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
    claim = fn(session, council_id, {})
    if claim is None:
        return
    assert claim.grade in {GRADE_CRITICAL, GRADE_CONCERN, GRADE_NEUTRAL, GRADE_SUPPORTIVE}
    assert claim.denominator.n > 0
    assert claim.numerator.n >= 0
    results = lint_claim(claim)  # must not raise
    assert results


def test_tenure_claim_is_always_neutral(session, council_id):
    claim = _t_tenure_claim(session, council_id, {})
    assert claim is not None
    assert claim.grade == GRADE_NEUTRAL


def test_tender_concentration_claim_is_always_neutral(session, council_id):
    claim = _t_tender_concentration_claim(session, council_id, {})
    assert claim is not None
    assert claim.grade == GRADE_NEUTRAL


def test_engagement_claim_is_always_neutral(session, council_id):
    claim = _t_engagement_claim(session, council_id, {})
    assert claim is not None
    assert claim.grade == GRADE_NEUTRAL


def test_procurement_incumbency_claim_reflects_configured_overlap():
    """Baseline profile sets incumbency_overlap=False - no firm should be
    both a frequent repeat-winner and a top-10 dollar-recipient. Fresh
    in-memory DB, same reasoning as test_recusal_trend_claim_direction_
    matches_configured_profile in batch2 (independent of fixture order)."""
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, expire_on_commit=False)()
    cid, _ = seed_profile(sess, "baseline")
    claim = _t_procurement_incumbency_claim(sess, cid, {})
    if claim is not None:
        assert claim.numerator.n == 0
        assert claim.grade == GRADE_SUPPORTIVE
