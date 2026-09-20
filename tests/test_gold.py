"""
Tests for src/analysis/gold.py (docs/uplift/migration/02-claim-layer.md
Step 2): gold-fact-table views over the existing raw tables. Synthetic
in-memory data, same pattern as test_verification.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.gold import (
    GOLD_GRAINS,
    POSITION_ABSENT_NON_ATTENDANCE,
    POSITION_ABSENT_RECUSAL,
    POSITION_ABSENT_UNKNOWN,
    application_fact,
    declaration_fact,
    membership_fact,
    motion_fact,
    question_fact,
    tender_fact,
    vote_fact,
)
from src.models import (
    Appointment,
    AttendanceStatus,
    Base,
    CommunitySubmission,
    Council,
    Councillor,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    MeetingAttendance,
    Motion,
    MotionOutcome,
    PlanningApplication,
    PublicQuestion,
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
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
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


def _councillor(session, given, family):
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    return c.id


def _motion(session, meeting_id, item_number="1", **kw):
    m = Motion(meeting_id=meeting_id, item_number=item_number, title="A motion", **kw)
    session.add(m)
    session.flush()
    return m.id


def test_grains_are_declared_and_parse():
    assert set(GOLD_GRAINS) == {
        "vote_fact", "declaration_fact", "tender_fact", "application_fact",
        "question_fact", "membership_fact", "motion_fact",
    }


# ── vote_fact ────────────────────────────────────────────────────────────

def test_vote_fact_ordinary_votes_pass_through(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    cid = _councillor(session, "A", "B")
    session.add(Vote(motion_id=motion_id, councillor_id=cid, choice=VoteChoice.FOR))
    session.flush()

    rows = vote_fact(session, council_id)
    assert len(rows) == 1
    assert rows[0].position == "for"
    assert rows[0].meeting_id == mid
    assert rows[0].motion_id == motion_id


def test_vote_fact_absent_with_apology_is_non_attendance(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    cid = _councillor(session, "A", "B")
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=cid, status=AttendanceStatus.APOLOGY))
    session.add(Vote(motion_id=motion_id, councillor_id=cid, choice=VoteChoice.ABSENT,
                      declared_interest=True))  # apology wins even if also declared
    session.flush()

    rows = vote_fact(session, council_id)
    assert rows[0].position == POSITION_ABSENT_NON_ATTENDANCE


def test_vote_fact_absent_with_declared_interest_is_recusal(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    cid = _councillor(session, "A", "B")
    session.add(Vote(motion_id=motion_id, councillor_id=cid, choice=VoteChoice.ABSENT,
                      declared_interest=True))
    session.flush()

    rows = vote_fact(session, council_id)
    assert rows[0].position == POSITION_ABSENT_RECUSAL


def test_vote_fact_absent_with_neither_signal_is_unknown(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    cid = _councillor(session, "A", "B")
    session.add(Vote(motion_id=motion_id, councillor_id=cid, choice=VoteChoice.ABSENT))
    session.flush()

    rows = vote_fact(session, council_id)
    assert rows[0].position == POSITION_ABSENT_UNKNOWN


# ── declaration_fact ─────────────────────────────────────────────────────

def test_declaration_fact_exposes_raw_rows(session, council_id):
    mid = _meeting(session, council_id)
    cid = _councillor(session, "A", "B")
    session.add(InterestDeclaration(
        meeting_id=mid, councillor_id=cid, item_reference="3",
        interest_type=InterestDeclarationType.FINANCIAL,
    ))
    session.flush()

    rows = declaration_fact(session, council_id)
    assert len(rows) == 1
    assert rows[0].interest_type == "financial"
    assert rows[0].s5_68_permission_granted is None


# ── tender_fact ──────────────────────────────────────────────────────────

def test_tender_fact_normalises_contractor_and_flags_value_recorded(session, council_id):
    mid = _meeting(session, council_id)
    session.add(Tender(meeting_id=mid, awarded_to="ACME Pty Ltd", amount=50000.0))
    session.add(Tender(meeting_id=mid, awarded_to=None, amount=None, is_confidential=True))
    session.flush()

    rows = tender_fact(session, council_id)
    named = next(r for r in rows if r.amount == 50000.0)
    unnamed = next(r for r in rows if r.amount is None)
    assert named.contractor_key is not None
    assert named.value_recorded is True
    assert unnamed.contractor_key is None
    assert unnamed.value_recorded is False
    assert unnamed.confidential is True


# ── application_fact ─────────────────────────────────────────────────────

def test_application_fact_counts_objectors(session, council_id):
    mid = _meeting(session, council_id)
    motion_id = _motion(session, mid)
    app = PlanningApplication(motion_id=motion_id, applicant_name="Jane Doe", estimated_value=1_000_000.0)
    session.add(app)
    session.flush()
    session.add(CommunitySubmission(application_id=app.id, position="object", count=3))
    session.add(CommunitySubmission(application_id=app.id, position="support"))
    session.flush()

    rows = application_fact(session, council_id)
    assert len(rows) == 1
    assert rows[0].objector_count == 3
    assert rows[0].value_recorded is True


# ── question_fact ────────────────────────────────────────────────────────

def test_question_fact_status_from_response_presence(session, council_id):
    mid = _meeting(session, council_id)
    session.add(PublicQuestion(meeting_id=mid, questioner_name="X", response_summary="Answered fully."))
    session.add(PublicQuestion(meeting_id=mid, questioner_name="Y", response_summary=None))
    session.flush()

    rows = question_fact(session, council_id)
    statuses = sorted(r.status for r in rows)
    assert statuses == ["answered", "unknown"]


# ── membership_fact ──────────────────────────────────────────────────────

def test_membership_fact_reads_appointments(session, council_id):
    mid = _meeting(session, council_id)
    cid = _councillor(session, "A", "B")
    session.add(Appointment(meeting_id=mid, councillor_id=cid, role="Delegate", body_name="Regional Council"))
    session.flush()

    rows = membership_fact(session, council_id)
    assert len(rows) == 1
    assert rows[0].body_name == "Regional Council"


# ── motion_fact ──────────────────────────────────────────────────────────

def test_motion_fact_reads_mover_seconder_outcome(session, council_id):
    mid = _meeting(session, council_id)
    m1 = _councillor(session, "A", "B")
    m2 = _councillor(session, "C", "D")
    _motion(session, mid, moved_by_id=m1, seconded_by_id=m2, outcome=MotionOutcome.CARRIED)

    rows = motion_fact(session, council_id)
    assert len(rows) == 1
    assert rows[0].mover_id == m1
    assert rows[0].seconder_id == m2
    assert rows[0].outcome == "carried"
    assert rows[0].amendment_flag is None
