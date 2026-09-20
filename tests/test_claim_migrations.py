"""
Tests for the three claim-object counterparts built in Step 6
(docs/uplift/migration/02-claim-layer.md) — _t_eoy_spending_claim,
_t_repeat_applicant_claim, _t_recusal_overall_claim (src/analysis/tests.py).
Synthetic in-memory data, same pattern as test_gold.py/test_evidence.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.claim_linter import LintContext, LintStatus, lint_claim
from src.analysis.claims import GRADE_CRITICAL, GRADE_NEUTRAL, GRADE_SUPPORTIVE
from src.analysis.tests import (
    _t_eoy_spending_claim,
    _t_recusal_overall_claim,
    _t_repeat_applicant_claim,
)
from src.models import (
    ApplicationStatus,
    Base,
    Council,
    Councillor,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    Motion,
    PlanningApplication,
    Tender,
    Vote,
    VoteChoice,
)
from src.storage.database import _enable_wal_and_fk


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, expire_on_commit=False)()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture
def council_id(session):
    c = Council(name="Test Council", short_name="TestCouncil", state="WA")
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, d=date(2024, 1, 1)):
    m = Meeting(council_id=council_id, meeting_date=d, document_type="minutes")
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id, item_number="1"):
    m = Motion(meeting_id=meeting_id, item_number=item_number, title="A motion")
    session.add(m)
    session.flush()
    return m.id


def _councillor(session, given, family):
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    return c.id


# ── _t_eoy_spending_claim ────────────────────────────────────────────────

def test_eoy_spending_claim_none_without_tenders(session, council_id):
    assert _t_eoy_spending_claim(session, council_id, {}) is None


def test_eoy_spending_claim_flags_end_of_year_concentration(session, council_id):
    # Fiscal year defaults to Jul-start (no config/fiscal_year.json in test
    # env) -> EOY months are May, Jun. Put 18/20 awards in May/June.
    for i in range(18):
        may_meeting = _meeting(session, council_id, d=date(2024, 5, i % 27 + 1))
        session.add(Tender(meeting_id=may_meeting, awarded_to=f"Firm {i}", amount=1000.0))
    for i in range(2):
        other_meeting = _meeting(session, council_id, d=date(2024, 1, i + 1))
        session.add(Tender(meeting_id=other_meeting, awarded_to=f"OtherFirm {i}", amount=1000.0))
    session.flush()

    claim = _t_eoy_spending_claim(session, council_id, {})
    assert claim is not None
    assert claim.numerator.n == 18
    assert claim.denominator.n == 20
    assert claim.grade == GRADE_CRITICAL
    assert "config/fiscal_year.json" in claim.narrative.body
    # The invalid-comparison-style ratio never appears in this claim.
    assert "×" not in claim.narrative.headline

    results = lint_claim(claim, LintContext(null_value=2 / 12))
    by_rule = {r.rule_id: r for r in results}
    assert by_rule["L-01"].status == LintStatus.PASS
    assert by_rule["L-16"].status == LintStatus.PASS
    assert by_rule["L-11"].status == LintStatus.PASS


def test_eoy_spending_claim_neutral_when_evenly_spread(session, council_id):
    for month in range(1, 13):
        m = _meeting(session, council_id, d=date(2024, month, 1))
        session.add(Tender(meeting_id=m, awarded_to=f"Firm {month}", amount=1000.0))
    session.flush()

    claim = _t_eoy_spending_claim(session, council_id, {})
    assert claim is not None
    assert claim.grade == GRADE_NEUTRAL


# ── _t_repeat_applicant_claim ────────────────────────────────────────────

def test_repeat_applicant_claim_none_without_both_extremes(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    session.add(PlanningApplication(motion_id=motion_id, applicant_name="Solo Applicant",
                                     status=ApplicationStatus.APPROVED))
    session.flush()
    assert _t_repeat_applicant_claim(session, council_id, {}) is None


def test_repeat_applicant_claim_detects_a_real_difference(session, council_id):
    mid = _meeting(session, council_id)
    # 10 one-shot applicants, all refused.
    for i in range(10):
        motion_id = _motion(session, mid, item_number=f"one-{i}")
        session.add(PlanningApplication(motion_id=motion_id, applicant_name=f"OneShot {i}",
                                         status=ApplicationStatus.REFUSED))
    # 1 frequent applicant (7 applications), all approved.
    for i in range(7):
        motion_id = _motion(session, mid, item_number=f"freq-{i}")
        session.add(PlanningApplication(motion_id=motion_id, applicant_name="Frequent Flyer",
                                         status=ApplicationStatus.APPROVED))
    session.flush()

    claim = _t_repeat_applicant_claim(session, council_id, {})
    assert claim is not None
    assert claim.statistic.ci_low > 0  # a real, positive difference
    assert claim.grade != GRADE_SUPPORTIVE

    results = lint_claim(claim)
    by_rule = {r.rule_id: r for r in results}
    assert by_rule["L-13"].status == LintStatus.NOT_APPLICABLE  # no flat/no-difference wording used


def test_repeat_applicant_claim_flat_result_fails_l13_on_missing_power(session, council_id):
    mid = _meeting(session, council_id)
    # Both groups approved at ~50%, roughly equal n -> CI should contain 0.
    for i in range(10):
        motion_id = _motion(session, mid, item_number=f"one-{i}")
        status = ApplicationStatus.APPROVED if i % 2 == 0 else ApplicationStatus.REFUSED
        session.add(PlanningApplication(motion_id=motion_id, applicant_name=f"OneShot {i}", status=status))
    for i in range(7):
        motion_id = _motion(session, mid, item_number=f"freq-{i}")
        status = ApplicationStatus.APPROVED if i % 2 == 0 else ApplicationStatus.REFUSED
        session.add(PlanningApplication(motion_id=motion_id, applicant_name="Frequent Flyer", status=status))
    session.flush()

    claim = _t_repeat_applicant_claim(session, council_id, {})
    assert claim is not None
    if claim.statistic.ci_low <= 0 <= claim.statistic.ci_high:
        assert "No difference" in claim.narrative.body
        results = lint_claim(claim)
        by_rule = {r.rule_id: r for r in results}
        # Expected, documented gap: no achieved_power computation exists yet
        # for a two-proportion difference test.
        assert by_rule["L-13"].status == LintStatus.FAIL


# ── _t_recusal_overall_claim ─────────────────────────────────────────────

def _declare_and_vote(session, meeting_id, council_id, cllr_id, item_number, choice):
    motion_id = _motion(session, meeting_id, item_number=item_number)
    session.add(InterestDeclaration(
        meeting_id=meeting_id, councillor_id=cllr_id, item_reference=item_number,
        interest_type=InterestDeclarationType.FINANCIAL,
    ))
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=choice, declared_interest=True))


def test_recusal_overall_claim_none_without_declarations(session, council_id):
    assert _t_recusal_overall_claim(session, council_id, {}) is None


def test_recusal_overall_claim_flags_baseline_as_different_event(session, council_id):
    mid = _meeting(session, council_id)
    a, b, c = (_councillor(session, "A", "One"), _councillor(session, "B", "Two"),
               _councillor(session, "C", "Three"))
    _declare_and_vote(session, mid, council_id, a, "1", VoteChoice.ABSENT)
    _declare_and_vote(session, mid, council_id, b, "2", VoteChoice.ABSENT)
    _declare_and_vote(session, mid, council_id, c, "3", VoteChoice.FOR)
    # A baseline (non-declared) vote for the ordinary-vote comparator.
    baseline_motion = _motion(session, mid, item_number="baseline")
    session.add(Vote(motion_id=baseline_motion, councillor_id=c, choice=VoteChoice.FOR,
                      declared_interest=False))
    session.flush()

    claim = _t_recusal_overall_claim(session, council_id, {})
    assert claim is not None
    assert claim.denominator.n == 3
    assert claim.numerator.n == 2
    assert claim.grade == GRADE_SUPPORTIVE
    assert claim.comparison.reference_is_same_event is False
    assert claim.narrative.caveats  # L-07's requirement: surfaced as a caveat
    # The legacy TestResult's invalid "×" multiplier never appears here.
    assert "×" not in claim.narrative.headline
    assert "×" not in claim.narrative.body

    results = lint_claim(claim)
    by_rule = {r.rule_id: r for r in results}
    assert by_rule["L-07"].status == LintStatus.PASS
    assert by_rule["L-11"].status == LintStatus.PASS
    assert by_rule["L-12"].status == LintStatus.PASS
