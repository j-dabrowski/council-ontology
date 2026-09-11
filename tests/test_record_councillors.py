"""Tests for src/analysis/record_councillors.py (docs/frontend/
RECORD_PAGE_PLAN.md Step 6, Part B.3) -- the reduced councillor-card
projection.

Hermetic: sqlite:///:memory: + Base.metadata.create_all, same pattern as
tests/test_record_streets.py and tests/test_evidence.py.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.record_councillors import build_record_councillors
from src.models import Base, Councillor, Meeting, Motion, MotionOutcome, Vote, VoteChoice
from src.storage.database import _enable_wal_and_fk

BANNED_FIELDS = [
    "win_rate", "dissent_rate", "dissent_n", "dissent_effectiveness",
    "recusal_rate", "declarations", "n_declarations", "n_recused",
    "applicant_name",
]


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


def _council(session) -> int:
    from src.models import Council
    c = Council(name="Test Council Full Name", short_name="TestCouncil", state="WA")
    session.add(c)
    session.flush()
    return c.id


def _councillor(session, given, family) -> int:
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, meeting_date) -> int:
    m = Meeting(
        council_id=council_id, meeting_date=meeting_date, document_type="minutes",
        meeting_type="Ordinary Council Meeting",
    )
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id, moved_by_id, seconded_by_id, outcome, votes_against) -> int:
    m = Motion(
        meeting_id=meeting_id, title="A motion", item_number="1",
        moved_by_id=moved_by_id, seconded_by_id=seconded_by_id,
        outcome=outcome, votes_for=3, votes_against=votes_against,
    )
    session.add(m)
    session.flush()
    return m.id


def _vote(session, councillor_id, motion_id, choice) -> None:
    session.add(Vote(councillor_id=councillor_id, motion_id=motion_id, choice=choice))


def _build_fixture_corpus(session):
    """Alice moves 15 motions seconded by Bob, 5 more seconded by Carol
    (so Bob is Alice's most frequent seconder, not Carol). Alice also
    seconds 5 of Bob's motions. Every councillor casts >=20 votes (the
    min_votes floor in councillor_tenure()) across every motion, so all
    three qualify for a card. Alice's contested-vote record is built to
    an exact, checkable split: 10 won, 15 lost."""
    council_id = _council(session)
    alice = _councillor(session, "Alice", "Adams")
    bob = _councillor(session, "Bob", "Bradley")
    carol = _councillor(session, "Carol", "Carter")

    base_day = date(2020, 1, 1)
    motion_ids = []
    for i in range(25):
        meeting_id = _meeting(session, council_id, base_day + timedelta(days=7 * i))
        if i < 15:
            moved_by, seconded_by = alice, bob
        elif i < 20:
            moved_by, seconded_by = alice, carol
        else:
            moved_by, seconded_by = bob, alice

        # Alice: FOR on a CARRIED motion or AGAINST on a LOST motion = won.
        # First 10 motions: Alice votes FOR and it CARRIES (won).
        # Next 15 motions: Alice votes FOR but it's LOST (lost).
        if i < 10:
            outcome, alice_choice = MotionOutcome.CARRIED, VoteChoice.FOR
        else:
            outcome, alice_choice = MotionOutcome.LOST, VoteChoice.FOR

        motion_id = _motion(session, meeting_id, moved_by, seconded_by, outcome, votes_against=1)
        motion_ids.append(motion_id)

        _vote(session, alice, motion_id, alice_choice)
        _vote(session, bob, motion_id, VoteChoice.AGAINST)
        _vote(session, carol, motion_id, VoteChoice.FOR)
    session.flush()

    return council_id, {"alice": alice, "bob": bob, "carol": carol}


def test_five_fields_only_no_performance_fields(session):
    council_id, _ = _build_fixture_corpus(session)
    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    payload_json = json.dumps(payload)
    for field in BANNED_FIELDS:
        assert field not in payload_json, f"banned field {field!r} leaked into the payload"

    alice = next(c for c in payload["councillors"] if c["name"] == "Alice Adams")
    assert set(alice) == {
        "name", "given_name", "family_name", "slug",
        "years_served", "first_vote", "motions_moved", "votes_cast",
        "most_frequent_seconder", "contested_votes",
    }


def test_motions_moved_and_most_frequent_seconder(session):
    council_id, _ = _build_fixture_corpus(session)
    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    by_name = {c["name"]: c for c in payload["councillors"]}

    assert by_name["Alice Adams"]["motions_moved"] == 20
    assert by_name["Alice Adams"]["most_frequent_seconder"] == {"name": "Bob Bradley", "count": 15}
    assert by_name["Bob Bradley"]["motions_moved"] == 5
    assert by_name["Bob Bradley"]["most_frequent_seconder"] == {"name": "Alice Adams", "count": 5}


def test_contested_votes_are_raw_counts_not_a_rate(session):
    council_id, _ = _build_fixture_corpus(session)
    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    by_name = {c["name"]: c for c in payload["councillors"]}

    alice_cv = by_name["Alice Adams"]["contested_votes"]
    assert alice_cv == {"total": 25, "won": 10, "lost": 15}
    assert set(alice_cv) == {"total", "won", "lost"}


def test_votes_cast_and_years_served_come_from_councillor_tenure(session):
    council_id, _ = _build_fixture_corpus(session)
    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    by_name = {c["name"]: c for c in payload["councillors"]}

    assert by_name["Alice Adams"]["votes_cast"] == 25
    assert by_name["Alice Adams"]["first_vote"] == "2020-01"
    assert by_name["Alice Adams"]["years_served"] > 0


def test_cards_sorted_alphabetically_by_surname(session):
    council_id, _ = _build_fixture_corpus(session)
    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    names = [(c["family_name"], c["given_name"]) for c in payload["councillors"]]
    assert names == sorted(names)


def test_councillor_below_min_votes_threshold_is_excluded(session):
    """councillor_tenure()'s min_votes=20 floor: a councillor with fewer
    than 20 recorded votes gets no card at all, same as TenurePanel's own
    leaderboard -- not a bug, the inherited threshold of the function this
    module reuses for years_served/votes_cast."""
    council_id, ids = _build_fixture_corpus(session)
    quiet = _councillor(session, "Quiet", "Quinn")
    meeting_id = _meeting(session, council_id, date(2021, 1, 1))
    motion_id = _motion(
        session, meeting_id, ids["alice"], ids["bob"], MotionOutcome.CARRIED, votes_against=0
    )
    _vote(session, quiet, motion_id, VoteChoice.FOR)
    session.flush()

    payload = build_record_councillors(session, council_id, generated_at="2026-09-12T00:00:00Z")
    names = {c["name"] for c in payload["councillors"]}
    assert "Quiet Quinn" not in names
