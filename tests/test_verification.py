"""
Tests for src/analysis/verification.py (docs/uplift/migration/
05-verification.md Steps 1-2, V-1/V-2): document-derived, zero-model
reconciliation and contradiction-sweep checks. Synthetic in-memory data,
same pattern as test_extractor.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.verification import (
    reconcile_cross_document,
    reconcile_stated_tallies,
    sweep_contradictions,
)
from src.models import (
    AttendanceStatus,
    Base,
    Council,
    Councillor,
    CouncillorTerm,
    InterestDeclaration,
    Meeting,
    MeetingAttendance,
    Motion,
    OtherItem,
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


def _meeting(session, council_id, d, doc_type="minutes"):
    m = Meeting(council_id=council_id, meeting_date=d, meeting_type="Ordinary Council Meeting",
                document_type=doc_type)
    session.add(m)
    session.flush()
    return m.id


def _councillor(session, given, family):
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    return c.id


# ---------------------------------------------------------------------------
# V-1: reconcile_stated_tallies
# ---------------------------------------------------------------------------

def test_matching_tally_counts_as_matched(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    c2 = _councillor(session, "B", "Two")
    motion = Motion(meeting_id=mid, title="X", votes_for=1, votes_against=1)
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion.id, councillor_id=c2, choice=VoteChoice.AGAINST))
    session.flush()

    r = reconcile_stated_tallies(session, council_id)
    assert r.total_with_stated_tally == 1
    assert r.checkable == 1
    assert r.matched == 1
    assert r.mismatched == 0
    assert r.match_rate == 100.0


def test_mismatched_tally_is_flagged_with_both_sides(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    motion = Motion(meeting_id=mid, title="X", item_number="4.1", votes_for=5, votes_against=1)
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.flush()

    r = reconcile_stated_tallies(session, council_id)
    assert r.matched == 0
    assert r.mismatched == 1
    assert len(r.mismatches) == 1
    m = r.mismatches[0]
    assert m.stated_for == 5 and m.counted_for == 1
    assert m.stated_against == 1 and m.counted_against == 0


def test_stated_tally_with_no_individual_votes_is_uncheckable_not_matched(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    session.add(Motion(meeting_id=mid, title="X", votes_for=5, votes_against=1))
    session.flush()

    r = reconcile_stated_tallies(session, council_id)
    assert r.total_with_stated_tally == 1
    assert r.checkable == 0
    assert r.matched == 0
    assert r.mismatched == 0
    assert r.match_rate is None


def test_null_stated_field_is_not_compared(session, council_id):
    """votes_abstain is never stated (None) — an unrelated abstain vote row
    existing shouldn't make this a mismatch."""
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    c2 = _councillor(session, "B", "Two")
    motion = Motion(meeting_id=mid, title="X", votes_for=1, votes_against=None, votes_abstain=None)
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion.id, councillor_id=c2, choice=VoteChoice.ABSTAIN))
    session.flush()

    r = reconcile_stated_tallies(session, council_id)
    assert r.matched == 1
    assert r.mismatched == 0


# ---------------------------------------------------------------------------
# V-2: sweep_contradictions
# ---------------------------------------------------------------------------

def test_absent_and_voted_detected(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=c1, status=AttendanceStatus.APOLOGY))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "absent_and_voted")
    assert stat.count == 1
    assert stat.coverage_denominator == 1


def test_orphan_declaration_detected(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    session.add(Motion(meeting_id=mid, title="X", item_number="4.1"))
    session.add(InterestDeclaration(meeting_id=mid, councillor_id=c1, item_reference="9.9"))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "orphan_declaration")
    assert stat.count == 1

    # A declaration matching a real item is not flagged.
    session.add(InterestDeclaration(meeting_id=mid, councillor_id=c1, item_reference="4.1"))
    session.flush()
    r2 = sweep_contradictions(session, council_id, persist=False)
    stat2 = next(s for s in r2.by_class if s.contradiction_class == "orphan_declaration")
    assert stat2.count == 1  # still just the one orphan, not two


def test_out_of_term_vote_detected_and_excludes_councillors_with_no_term_data(session, council_id):
    mid = _meeting(session, council_id, date(2020, 6, 1))
    c1 = _councillor(session, "A", "One")  # has term data, vote falls outside it
    c2 = _councillor(session, "B", "Two")  # no term data at all — excluded from denominator
    session.add(CouncillorTerm(councillor_id=c1, council_id=council_id,
                                term_start=date(2015, 1, 1), term_end=date(2018, 1, 1)))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion.id, councillor_id=c2, choice=VoteChoice.FOR))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "out_of_term_vote")
    assert stat.count == 1  # only c1's vote is checkable and out of term
    assert stat.coverage_denominator == 1  # c2's vote never enters the denominator


def test_mover_seconder_absent_detected(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    present = _councillor(session, "A", "One")
    mover = _councillor(session, "B", "Two")
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=present, status=AttendanceStatus.PRESENT))
    session.add(Motion(meeting_id=mid, title="X", moved_by_id=mover))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "mover_seconder_absent")
    assert stat.count == 1


def test_mover_seconder_check_excludes_meetings_with_no_attendance_data(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    mover = _councillor(session, "B", "Two")
    session.add(Motion(meeting_id=mid, title="X", moved_by_id=mover))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "mover_seconder_absent")
    assert stat.count == 0
    assert stat.coverage_denominator == 0


def test_tally_exceeds_chamber_detected(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    c2 = _councillor(session, "B", "Two")
    m1 = Motion(meeting_id=mid, title="X", votes_for=10, votes_against=0)  # only 2 ever voted this meeting
    session.add(m1)
    session.flush()
    session.add(Vote(motion_id=m1.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=m1.id, councillor_id=c2, choice=VoteChoice.FOR))
    session.flush()

    r = sweep_contradictions(session, council_id, persist=False)
    stat = next(s for s in r.by_class if s.contradiction_class == "tally_exceeds_chamber")
    assert stat.count == 1


def test_sweep_persist_replaces_prior_run_for_the_council(session, council_id):
    from src.models import Contradiction

    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=c1, status=AttendanceStatus.APOLOGY))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.flush()

    sweep_contradictions(session, council_id, persist=True)
    first_count = session.query(Contradiction).filter(Contradiction.council_id == council_id).count()
    assert first_count > 0

    # Re-running with no new data must not double the rows.
    sweep_contradictions(session, council_id, persist=True)
    second_count = session.query(Contradiction).filter(Contradiction.council_id == council_id).count()
    assert second_count == first_count


# ---------------------------------------------------------------------------
# V-3: reconcile_cross_document
# ---------------------------------------------------------------------------

def _check(r, name):
    return next(c for c in r.checks if c.name == name)


def test_attendance_vs_votes_reconciles_when_voters_within_present_count(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1, c2 = _councillor(session, "A", "One"), _councillor(session, "B", "Two")
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=c1, status=AttendanceStatus.PRESENT))
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=c2, status=AttendanceStatus.PRESENT))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.flush()

    r = reconcile_cross_document(session, council_id)
    c = _check(r, "attendance_vs_votes")
    assert c.checked == 1
    assert c.reconciled == 1


def test_attendance_vs_votes_flags_more_voters_than_present(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    c2 = _councillor(session, "B", "Two")  # votes but isn't in the present list
    session.add(MeetingAttendance(meeting_id=mid, councillor_id=c1, status=AttendanceStatus.PRESENT))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion.id, councillor_id=c2, choice=VoteChoice.AGAINST))
    session.flush()

    r = reconcile_cross_document(session, council_id)
    c = _check(r, "attendance_vs_votes")
    assert c.checked == 1
    assert c.reconciled == 0


def test_tender_aggregate_reconciles_within_5pct(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    session.add(OtherItem(meeting_id=mid, item_type="finance",
                          description="Total tender payments this quarter: $1,000"))
    session.add(Tender(meeting_id=mid, amount=1000.0, awarded_to="Firm A"))
    session.flush()

    r = reconcile_cross_document(session, council_id)
    c = _check(r, "tender_value_vs_aggregate")
    assert c.checked == 1
    assert c.reconciled == 1


def test_councillor_terms_coverage_counts_only_voting_councillors(session, council_id):
    mid = _meeting(session, council_id, date(2020, 1, 1))
    c1 = _councillor(session, "A", "One")
    c2 = _councillor(session, "B", "Two")
    session.add(CouncillorTerm(councillor_id=c1, council_id=council_id,
                                term_start=date(2018, 1, 1), term_end=None))
    motion = Motion(meeting_id=mid, title="X")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=c1, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion.id, councillor_id=c2, choice=VoteChoice.AGAINST))
    session.flush()

    r = reconcile_cross_document(session, council_id)
    c = _check(r, "councillor_names_vs_terms")
    assert c.checked == 2
    assert c.reconciled == 1
