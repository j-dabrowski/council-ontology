"""Tests for src/analysis/record_streets.py -- record_streets.json
(docs/frontend/RECORD_PAGE_PLAN.md Step 3, Part C.2).

Hermetic: sqlite:///:memory: + Base.metadata.create_all, same pattern as
tests/test_evidence.py. No real corpus data here -- the real-corpus
coverage/busiest-streets numbers are reported by hand from a local run
against data/council.db (gitignored, absent from CI), same convention
as tests/test_privacy.py.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.record_streets import build_record_streets, extract_street_name, extract_suburb
from src.models import (
    ApplicationStatus,
    Base,
    CommunitySubmission,
    Council,
    ExtractionEvidence,
    Meeting,
    Motion,
    PlanningApplication,
    Site,
)
from src.storage.database import _enable_wal_and_fk

# ---------------------------------------------------------------------------
# extract_street_name() / extract_suburb() -- pure functions, real address
# shapes from the corpus reproduced with invented street/suburb names.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("address,expected", [
    ("Lot 82 (No. 25) Brighton Street, West Leederville", "Brighton Street"),
    ("111 Harborne Street, Wembley", "Harborne Street"),
    ("Lots 628 and 629 (No.84) The Boulevard, Floreat", "The Boulevard"),
    ("Lot 1 (No. 122A) St Leonards Avenue, West Leederville", "St Leonards Avenue"),
    ("Lot 960 (No.28) Kenmore Crescent, corner Moray Avenue, Floreat", "Kenmore Crescent"),
    ("Lots 1 and 2, 47 Keane Street, Wembley", "Keane Street"),
    ("Subiaco Oval", None),
    ("Floreat Activity Centre", None),
    (None, None),
    ("", None),
])
def test_extract_street_name(address, expected):
    assert extract_street_name(address) == expected


@pytest.mark.parametrize("address,expected", [
    ("Lot 82 (No. 25) Brighton Street, West Leederville", "West Leederville"),
    ("Lot 960 (No.28) Kenmore Crescent, corner Moray Avenue, Floreat", "Floreat"),
    ("Subiaco Oval", None),
    (None, None),
    ("", None),
])
def test_extract_suburb(address, expected):
    assert extract_suburb(address) == expected


# ---------------------------------------------------------------------------
# build_record_streets()
# ---------------------------------------------------------------------------


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
    c = Council(name="Test Council Full Name", short_name="TestCouncil", state="WA")
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, meeting_date_, minutes_text=None,
             minutes_pdf_url=None) -> int:
    m = Meeting(
        council_id=council_id, meeting_date=meeting_date_, document_type="minutes",
        meeting_type="Ordinary Council Meeting", minutes_text=minutes_text,
        minutes_pdf_url=minutes_pdf_url,
    )
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id) -> int:
    mo = Motion(meeting_id=meeting_id, title="A motion", item_number="1")
    session.add(mo)
    session.flush()
    return mo.id


def _site(session, council_id, address, lot_number=None) -> int:
    s = Site(council_id=council_id, address=address, lot_number=lot_number)
    session.add(s)
    session.flush()
    return s.id


def _application(session, motion_id, site_id, **kwargs) -> int:
    pa = PlanningApplication(motion_id=motion_id, site_id=site_id, **kwargs)
    session.add(pa)
    session.flush()
    return pa.id


def _evidence(session, meeting_id, entity_id, quote_text) -> None:
    session.add(ExtractionEvidence(
        meeting_id=meeting_id, entity_table="planning_applications", entity_id=entity_id,
        quote_text=quote_text,
    ))
    session.flush()


def _build_fixture_corpus(session):
    """Two sites on the same street (one with an extractable street name,
    one that isn't -- so coverage numbers are exercisable), a site on a
    different street, one application with real-shaped private-name
    content in its description, one with objectors, and one application
    that carries no site at all."""
    council_id = _council(session)
    meeting_id = _meeting(
        session, council_id, date(2020, 3, 1),
        minutes_text="The council considered the application at Lot 5 Example Street.",
        minutes_pdf_url="https://example.org/minutes/2020-03-01.pdf",
    )

    site_a = _site(session, council_id, "Lot 5 (No. 10) Example Street, Testville", lot_number="5")
    site_b = _site(session, council_id, "Lot 9 (No. 20) Example Street, Testville", lot_number="9")
    site_unparseable = _site(session, council_id, "Testville Community Oval")

    motion1 = _motion(session, meeting_id)
    app1 = _application(
        session, motion1, site_a,
        reference_number="1DA-2020",
        applicant_name="Mr John Smith",  # must never reach the payload
        description="Proposed subdivision of two lots. Landowner: Mr John Smith",
        status=ApplicationStatus.APPROVED,
    )
    _evidence(session, meeting_id, app1, "The council considered the application at Lot 5 Example Street.")

    motion2 = _motion(session, meeting_id)
    app2 = _application(
        session, motion2, site_b,
        reference_number="2DA-2020",
        description="Two storey dwelling addition",
        status=ApplicationStatus.REFUSED,
    )
    for _ in range(3):
        session.add(CommunitySubmission(application_id=app2, position="object"))
    session.flush()

    motion3 = _motion(session, meeting_id)
    _application(
        session, motion3, None,  # no site
        reference_number="3DA-2020",
        description="Application with no linked site",
        status=ApplicationStatus.PENDING,
    )

    motion4 = _motion(session, meeting_id)
    _application(
        session, motion4, site_unparseable,
        reference_number="4DA-2020",
        description="Signage for the oval clubrooms",
        status=ApplicationStatus.APPROVED,
    )

    return council_id


def test_coverage_counts(session):
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")

    assert payload["coverage"]["sites"] == 3
    assert payload["coverage"]["sites_with_street"] == 2  # the oval doesn't parse
    assert payload["coverage"]["applications"] == 4
    assert payload["coverage"]["applications_with_site"] == 3  # app3 has no site
    assert "3" in payload["coverage"]["note"] or "1" in payload["coverage"]["note"]


def test_street_grouping_and_counts(session):
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")

    names = {s["name"] for s in payload["streets"]}
    assert names == {"Example Street"}  # the oval yields no street name

    street = payload["streets"][0]
    assert street["n_sites"] == 2
    assert street["n_applications"] == 2  # apps 1 and 2; app3 has no site, app4 is on the oval
    assert street["suburbs"] == ["Testville"]


def test_objector_count_and_outcome(session):
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")

    street = payload["streets"][0]
    apps_by_ref = {
        app["reference"]: app
        for site in street["sites"]
        for app in site["applications"]
    }
    assert apps_by_ref["1DA-2020"]["n_objectors"] == 0
    assert apps_by_ref["1DA-2020"]["outcome"] == "approved"
    assert apps_by_ref["2DA-2020"]["n_objectors"] == 3
    assert apps_by_ref["2DA-2020"]["outcome"] == "refused"


def test_evidence_document_reference_is_populated(session):
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")

    street = payload["streets"][0]
    apps_by_ref = {
        app["reference"]: app
        for site in street["sites"]
        for app in site["applications"]
    }
    ev = apps_by_ref["1DA-2020"]["evidence"]
    assert ev["meeting_date"] == "2020-03-01"
    assert ev["url"] == "https://example.org/minutes/2020-03-01.pdf"
    assert apps_by_ref["1DA-2020"]["date"] == "2020-03-01"

    # The one with no evidence row at all still gets a well-shaped entry.
    ev2 = apps_by_ref["2DA-2020"]["evidence"]
    assert set(ev2) == {"filename", "url", "meeting_date", "page"}


def test_no_applicant_name_or_owner_applicant_string_anywhere_in_payload(session):
    """The literal RECORD_PAGE_PLAN.md Step 3 acceptance check: no
    applicant_name field, and no "Owner:"/"Applicant:" string, anywhere
    in the serialised payload."""
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")
    payload_json = json.dumps(payload)

    assert "applicant_name" not in payload_json
    assert "John Smith" not in payload_json
    assert "Owner:" not in payload_json
    assert "Applicant:" not in payload_json
    assert "Landowner:" not in payload_json


def test_description_is_redacted_in_place(session):
    council_id = _build_fixture_corpus(session)
    payload = build_record_streets(session, council_id, generated_at="2026-09-11T00:00:00Z")

    street = payload["streets"][0]
    apps_by_ref = {
        app["reference"]: app
        for site in street["sites"]
        for app in site["applications"]
    }
    desc = apps_by_ref["1DA-2020"]["description"]
    assert "Smith" not in desc
    assert "private individual" in desc  # the placeholder survived
