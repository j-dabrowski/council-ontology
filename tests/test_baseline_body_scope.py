"""Meeting-scoped tests must quote a body-matched baseline.

Regression cover for the 2026-08-31 Editor advisory: the digest's salience
layer keys its baselines on `(test_id, body_class)`, but the baselines
rendered into the digest's own prose pooled every minutes meeting. A
committee meeting was therefore compared against a corpus ~90% composed of
full-council meetings.

sqlite:///:memory: engine, same pattern as test_digest.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.queries import transparency_by_year
from src.analysis.tests import _comparable_label, _same_body_meeting_types
from src.models import Base, Council, Meeting, OtherItem
from src.storage.database import _enable_wal_and_fk

FULL = "Ordinary Council Meeting"
COMMITTEE = "Audit and Risk Committee Meeting"


@pytest.fixture
def session():
    eng = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(eng)
    Base.metadata.create_all(eng)
    sess = sessionmaker(bind=eng, expire_on_commit=False)()
    yield sess
    sess.rollback()
    sess.close()


def _meeting(session, council_id, d, meeting_type, items, confidential):
    m = Meeting(council_id=council_id, meeting_date=d, meeting_type=meeting_type,
                document_type="minutes")
    session.add(m)
    session.flush()
    for i in range(items):
        session.add(OtherItem(meeting_id=m.id, item_type="report", description=f"Item {i}",
                              is_confidential=i < confidential))
    session.flush()
    return m.id


@pytest.fixture
def corpus(session):
    c = Council(name="Test", short_name="Test", state="WA")
    session.add(c)
    session.flush()
    # Full council: 10 meetings, 10 items each, none confidential.
    for i in range(10):
        _meeting(session, c.id, date(2026, 1, i + 1), FULL, 10, 0)
    # Committee: 2 meetings, 10 items each, half confidential.
    cm = _meeting(session, c.id, date(2026, 2, 1), COMMITTEE, 10, 5)
    _meeting(session, c.id, date(2026, 2, 2), COMMITTEE, 10, 5)
    session.flush()
    return c.id, cm


def test_peers_are_the_same_body_class_only(session, corpus):
    _cid, committee_meeting = corpus
    peers = _same_body_meeting_types(session, committee_meeting)
    assert "Audit, Risk and Improvement Committee Meeting" in peers  # same class
    assert FULL not in peers


def test_body_matched_baseline_differs_from_the_all_meetings_pool(session, corpus):
    cid, committee_meeting = corpus

    def share(**kw):
        t = transparency_by_year(session, cid, **kw)
        total = sum(y.total for y in t.years)
        return round(100 * sum(y.confidential for y in t.years) / total, 1)

    # Unfiltered, the committee is drowned out by full council: 10 of 120.
    assert share() == 8.3
    # Against its own body class it is exactly the 50% its two meetings run at
    # — the comparison that means something.
    assert share(meeting_types=_same_body_meeting_types(session, committee_meeting)) == 50.0


def test_comparable_label_states_the_pool_size(session, corpus):
    _cid, committee_meeting = corpus
    types = _same_body_meeting_types(session, committee_meeting)
    # Thin pools are the reason the label names N rather than saying "corpus-wide".
    assert _comparable_label(session, committee_meeting, types) == "across 2 comparable meetings"
