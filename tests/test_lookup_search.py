"""Tests for src/analysis/lookup_search.py -- lookup_search.json
(RECORD_PAGE_PLAN.md follow-on, 2026-09-15): the keyword-searchable
motions/other_items/tenders index behind /record's "Search council
records" feature.

Hermetic: sqlite:///:memory: + Base.metadata.create_all, same pattern as
tests/test_record_streets.py/tests/test_watch_feed.py. No real corpus data
here -- the real-corpus redaction counts (9/14,013 motion titles, 218/
13,682 motion descriptions, 4/840 tender awarded_to, 0/840 tender
descriptions flagged) are reported by hand from a local run against
data/council.db, same convention as tests/test_privacy.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.lookup_search import build_lookup_search
from src.models import Base, Council, Meeting, Motion, OtherItem, Tender
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


def _council(session) -> int:
    c = Council(name="Test Council Full Name", short_name="TestCouncil", state="WA")
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, document_type="minutes") -> int:
    m = Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type=document_type,
    )
    session.add(m)
    session.flush()
    return m.id


def test_motions_other_items_and_tenders_all_present(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id)
    session.add(Motion(meeting_id=meeting_id, item_number="1", title="A motion",
                       description="A motion's reasoning.", outcome="carried"))
    session.add(OtherItem(meeting_id=meeting_id, item_number="2", item_type="officer_report",
                          description="An officer report.", is_confidential=False))
    session.add(Tender(meeting_id=meeting_id, description="A tender", amount=50000,
                       awarded_to="Acme Constructions", is_confidential=False))
    session.flush()

    data = build_lookup_search(session, council_id, "2026-09-15T00:00:00+00:00")
    assert data["n_motions"] == 1
    assert data["n_other_items"] == 1
    assert data["n_tenders"] == 1
    assert data["motions"][0]["kind"] == "motion"
    assert data["other_items"][0]["kind"] == "other_item"
    assert data["tenders"][0]["kind"] == "tender"


def test_agenda_document_meetings_are_excluded(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, document_type="agenda")
    session.add(Motion(meeting_id=meeting_id, item_number="1", title="Agenda-only motion"))
    session.flush()

    data = build_lookup_search(session, council_id, "2026-09-15T00:00:00+00:00")
    assert data["n_motions"] == 0


def test_nil_placeholder_other_items_are_excluded(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id)
    session.add(OtherItem(meeting_id=meeting_id, item_number="1", item_type="confidential",
                          description="Confidential Reports - Nil", is_confidential=False))
    session.flush()

    data = build_lookup_search(session, council_id, "2026-09-15T00:00:00+00:00")
    assert data["n_other_items"] == 0


def test_private_names_are_redacted_across_all_three_kinds(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id)
    session.add(Motion(
        meeting_id=meeting_id, item_number="1",
        title="Legal Proceedings - Mr M Congerton",
        description="Application submitted by Mr M Congerton.",
    ))
    session.add(OtherItem(
        meeting_id=meeting_id, item_number="2", item_type="officer_report",
        description="Letter from Ms Sam Boucher requesting an extension.",
        is_confidential=False,
    ))
    session.add(Tender(
        meeting_id=meeting_id, description="A tender", amount=1000,
        awarded_to="Starlight Theatre Lighting (Mr Ian Ashton)", is_confidential=False,
    ))
    session.flush()

    data = build_lookup_search(session, council_id, "2026-09-15T00:00:00+00:00")
    m = data["motions"][0]
    assert "Congerton" not in m["title"] and "[private individual" in m["title"]
    assert "Congerton" not in m["description"] and "[private individual" in m["description"]
    oi = data["other_items"][0]
    assert "Boucher" not in oi["description"] and "[private individual" in oi["description"]
    t = data["tenders"][0]
    assert "Ashton" not in t["awarded_to"] and "[private individual" in t["awarded_to"]
    assert "Starlight Theatre Lighting" in t["awarded_to"]  # business name untouched


def test_confidential_tender_with_a_named_business_is_not_redacted(session):
    # A confidential tender's awarded_to, when present, is a real business
    # in this corpus (never a private individual) -- see this module's own
    # docstring. Business names are never redacted anywhere on this site.
    council_id = _council(session)
    meeting_id = _meeting(session, council_id)
    session.add(Tender(
        meeting_id=meeting_id, description="A confidential tender", amount=250000,
        awarded_to="Albarossa Pty Ltd ACN 131 350 340", is_confidential=True,
    ))
    session.flush()

    data = build_lookup_search(session, council_id, "2026-09-15T00:00:00+00:00")
    t = data["tenders"][0]
    assert t["awarded_to"] == "Albarossa Pty Ltd ACN 131 350 340"
    assert t["is_confidential"] is True
