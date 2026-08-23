"""
Unit tests for src/analysis/profile.py — the S2 corpus profile:
  - span (document counts, date range, zero-meeting-month detection)
  - entity_counts (council-scoped row counts across meeting/motion joins)
  - record_quality (NULL rates, vote choice distribution, coverage rates)
  - identity_resolution (with_terms/with_votes/with_neither, duplicate
    family names)
  - two councils sharing one DB never leak into each other's profile

sqlite:///:memory: engine + Base.metadata.create_all, same pattern as
test_extractor.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.profile import compute_corpus_profile
from src.models import (
    Base,
    Council,
    Councillor,
    CouncillorTerm,
    Meeting,
    Motion,
    MotionOutcome,
    PlanningApplication,
    Tender,
    Vote,
    VoteChoice,
)
from src.storage.database import _enable_wal_and_fk


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(eng)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.rollback()
    sess.close()


def _council(session, short_name="TestCouncil") -> int:
    c = Council(name=f"{short_name} Full Name", short_name=short_name, state="WA")
    session.add(c)
    session.flush()
    return c.id


def _councillor(session, given, family) -> int:
    slug = f"{given}-{family}".lower()
    p = Councillor(given_name=given, family_name=family, slug=slug)
    session.add(p)
    session.flush()
    return p.id


def _meeting(session, council_id, meeting_date, document_type="minutes") -> int:
    m = Meeting(council_id=council_id, meeting_date=meeting_date, document_type=document_type)
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id, outcome=MotionOutcome.CARRIED) -> int:
    mo = Motion(meeting_id=meeting_id, title="A motion", outcome=outcome)
    session.add(mo)
    session.flush()
    return mo.id


def _vote(session, motion_id, councillor_id, choice=VoteChoice.FOR, declared=False) -> None:
    session.add(Vote(motion_id=motion_id, councillor_id=councillor_id, choice=choice,
                      declared_interest=declared))
    session.flush()


# ---------------------------------------------------------------------------
# span
# ---------------------------------------------------------------------------

def test_span_counts_documents_by_type_and_date_range(session):
    council_id = _council(session)
    _meeting(session, council_id, date(2020, 1, 15), document_type="minutes")
    _meeting(session, council_id, date(2020, 3, 20), document_type="agenda")

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.span.total_documents == 2
    assert profile.span.by_document_type == {"minutes": 1, "agenda": 1}
    assert profile.span.date_min == "2020-01-15"
    assert profile.span.date_max == "2020-03-20"


def test_span_detects_zero_meeting_month_between_two_meetings(session):
    council_id = _council(session)
    _meeting(session, council_id, date(2020, 1, 10))
    _meeting(session, council_id, date(2020, 3, 5))

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    zero_months = [m.split(" ")[0] for m in profile.span.zero_meeting_months_in_span]
    assert zero_months == ["2020-02"]


def test_span_no_gap_when_meetings_are_consecutive_months(session):
    council_id = _council(session)
    _meeting(session, council_id, date(2020, 1, 10))
    _meeting(session, council_id, date(2020, 2, 5))

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.span.zero_meeting_months_in_span == []


# ---------------------------------------------------------------------------
# entity_counts + council isolation
# ---------------------------------------------------------------------------

def test_entity_counts_scoped_to_council_only(session):
    council_a = _council(session, "A")
    council_b = _council(session, "B")

    m_a = _meeting(session, council_a, date(2020, 1, 1))
    _motion(session, m_a)
    _motion(session, m_a)

    m_b = _meeting(session, council_b, date(2020, 1, 1))
    _motion(session, m_b)

    profile_a = compute_corpus_profile(session, council_a, "a", "2026-08-23T00:00:00Z")
    profile_b = compute_corpus_profile(session, council_b, "b", "2026-08-23T00:00:00Z")

    assert profile_a.entity_counts.motions == 2
    assert profile_a.entity_counts.meetings == 1
    assert profile_b.entity_counts.motions == 1
    assert profile_b.entity_counts.meetings == 1


def test_entity_counts_votes_via_motion_join(session):
    council_id = _council(session)
    cid = _councillor(session, "Jane", "Citizen")
    m = _meeting(session, council_id, date(2020, 1, 1))
    mo = _motion(session, m)
    _vote(session, mo, cid)

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.entity_counts.votes == 1


# ---------------------------------------------------------------------------
# record_quality
# ---------------------------------------------------------------------------

def test_planning_application_date_null_rate(session):
    council_id = _council(session)
    m = _meeting(session, council_id, date(2020, 1, 1))
    mo1 = _motion(session, m)
    mo2 = _motion(session, m)
    session.add(PlanningApplication(motion_id=mo1, application_date=None))
    session.add(PlanningApplication(motion_id=mo2, application_date=date(2020, 1, 1)))
    session.flush()

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.record_quality.planning_application_date_null_rate == 0.5


def test_motion_outcome_null_rate(session):
    council_id = _council(session)
    m = _meeting(session, council_id, date(2020, 1, 1))
    _motion(session, m, outcome=MotionOutcome.CARRIED)
    _motion(session, m, outcome=None)
    _motion(session, m, outcome=None)

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.record_quality.motion_outcome_null_rate == pytest.approx(2 / 3, abs=1e-3)


def test_vote_choice_distribution_and_declared_interest_rate(session):
    council_id = _council(session)
    cid = _councillor(session, "Jane", "Citizen")
    m = _meeting(session, council_id, date(2020, 1, 1))
    mo = _motion(session, m)
    _vote(session, mo, cid, choice=VoteChoice.FOR, declared=True)

    cid2 = _councillor(session, "John", "Resident")
    _vote(session, mo, cid2, choice=VoteChoice.AGAINST, declared=False)

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.record_quality.vote_choice_distribution == {"for": 1, "against": 1}
    assert profile.record_quality.vote_declared_interest_rate == 0.5


def test_tender_confidential_and_amount_null_rates(session):
    council_id = _council(session)
    m = _meeting(session, council_id, date(2020, 1, 1))
    session.add(Tender(meeting_id=m, is_confidential=True, amount=None))
    session.add(Tender(meeting_id=m, is_confidential=False, amount=100.0))
    session.flush()

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.record_quality.tender_confidential_rate == 0.5
    assert profile.record_quality.tender_amount_null_rate == 0.5


def test_no_rows_gives_none_rates_not_zero_division(session):
    council_id = _council(session)
    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.record_quality.planning_application_date_null_rate is None
    assert profile.record_quality.motion_outcome_null_rate is None
    assert profile.record_quality.tender_confidential_rate is None


# ---------------------------------------------------------------------------
# identity_resolution
# ---------------------------------------------------------------------------

def test_identity_resolution_with_terms_with_votes_with_neither(session):
    council_id = _council(session)
    with_votes_only = _councillor(session, "Jane", "Citizen")
    with_terms_only = _councillor(session, "John", "Resident")
    with_both = _councillor(session, "Kim", "Local")

    m = _meeting(session, council_id, date(2020, 1, 1))
    mo = _motion(session, m)
    _vote(session, mo, with_votes_only)
    _vote(session, mo, with_both)

    session.add(CouncillorTerm(councillor_id=with_terms_only, council_id=council_id))
    session.add(CouncillorTerm(councillor_id=with_both, council_id=council_id))
    session.flush()

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    ir = profile.identity_resolution
    assert ir.councillor_count == 3
    assert ir.with_votes == 2
    assert ir.with_terms == 2
    assert ir.with_neither == 0


def test_identity_resolution_ignores_councillor_with_no_activity_on_this_council(session):
    council_id = _council(session)
    _councillor(session, "Ghost", "Nobody")  # never voted or termed on this council

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.identity_resolution.councillor_count == 0
    assert profile.identity_resolution.with_neither == 0


def test_identity_resolution_flags_shared_family_name(session):
    council_id = _council(session)
    a = _councillor(session, "Jamie", "Fixture")
    b = _councillor(session, "James", "Fixture")
    c = _councillor(session, "Jane", "Citizen")

    m = _meeting(session, council_id, date(2020, 1, 1))
    mo = _motion(session, m)
    _vote(session, mo, a)
    _vote(session, mo, b)
    _vote(session, mo, c)

    profile = compute_corpus_profile(session, council_id, "test", "2026-08-23T00:00:00Z")
    assert profile.identity_resolution.duplicate_family_name_groups == 1
