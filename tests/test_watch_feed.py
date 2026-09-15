"""
Unit tests for compute_watch_feed() (src/analysis/meeting_baselines.py,
docs/frontend/WATCH_FEED_PLAN.md Step 4) — the corpus-wide per-meeting watch
record: one row per minutes meeting (content-bearing or not, B.4), each
exception carrying both a deep and a public view (B.3), tests.{run,
exceptions,within_baseline} always summing to 14, and provenance joined in.

Uses the real config/test_registry.json (via load_test_registry()'s default,
same as run_meeting_digest()) — same pattern test_digest.py's
compose_period_digest tests already rely on for procurement.concentration.
"""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.meeting_baselines import (
    MeetingBaselines,
    TestBaseline,
    compute_watch_feed,
    project_watch_feed_to_public,
)
from src.models import Base, Council, Meeting, Motion, Tender
from src.storage.database import _enable_wal_and_fk

# A fixture meeting id (SQLite auto-increment starting at 1) can collide with
# a real meeting_id in data/validation/data/batch_jobs — point provenance at
# a directory that can't possibly exist, so every test here is hermetic.
_NO_SUCH_DIR = Path("/no/such/watch-feed-fixture-dir")


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


def _baselines(entries: dict | None = None) -> MeetingBaselines:
    return MeetingBaselines(
        council="test", generated_at="x", n_meetings_considered=0, baselines=entries or {},
    )


def test_row_count_equals_minutes_meeting_count(session):
    council_id = _council(session)
    for i in range(3):
        session.add(Meeting(
            council_id=council_id, meeting_date=date(2026, 1, i + 1),
            meeting_type="Ordinary Council Meeting", document_type="minutes",
        ))
    # An agenda document must not be counted as a minutes meeting.
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2026, 2, 1),
        meeting_type="Ordinary Council Meeting", document_type="agenda",
    ))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    assert feed["n_meetings"] == 3
    assert len(feed["meetings"]) == 3


def test_meeting_with_no_motions_still_gets_a_row(session):
    # B.4: a stub/placeholder minutes meeting (no content) is still one of
    # the 506 rows — unlike compute_meeting_baselines()'s content-bearing
    # filter, which exists only to protect the baseline distributions.
    council_id = _council(session)
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2026, 1, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    ))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    assert feed["n_meetings"] == 1
    row = feed["meetings"][0]
    assert row["counts"] == {"items": 0, "motions": 0, "other_items": 0}
    assert row["tests"]["run"] == 14


def test_motions_are_present_and_name_free_and_redacted(session):
    # WATCH_FEED_PLAN.md follow-on (2026-09-15): the feed now carries what
    # a meeting actually decided, not just counts. moved_by/seconded_by
    # must never appear (public_inventory_projection() strips them before
    # this even reaches redact_private_names()); a real private-individual
    # shape in the title itself must come back redacted, matching
    # record_streets.py's own treatment of free text.
    council_id = _council(session)
    meeting = Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    )
    session.add(meeting)
    session.flush()
    session.add(Motion(
        meeting_id=meeting.id, item_number="9.1", title="Adoption of Annual Budget",
        description="Adopts the budget as tabled, per s6.2 of the Local Government Act.",
        outcome="carried",
    ))
    session.add(Motion(
        meeting_id=meeting.id, item_number="9.2",
        title="Legal Proceedings - Mr M Congerton, 18 Joseph Street",
        description="Application submitted by Mr M Congerton for legal costs recovery.",
        outcome="carried",
    ))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    row = feed["meetings"][0]
    assert len(row["motions"]) == 2
    plain = next(m for m in row["motions"] if m["item_number"] == "9.1")
    assert plain == {
        "item_number": "9.1", "title": "Adoption of Annual Budget", "outcome": "carried",
        "description": "Adopts the budget as tabled, per s6.2 of the Local Government Act.",
    }
    flagged = next(m for m in row["motions"] if m["item_number"] == "9.2")
    assert "Congerton" not in flagged["title"]
    assert "[private individual" in flagged["title"]
    assert "Congerton" not in flagged["description"]
    assert "[private individual" in flagged["description"]
    for m in row["motions"]:
        assert "moved_by" not in m and "seconded_by" not in m


def test_tests_run_exceptions_and_within_baseline_always_sum_to_run(session):
    council_id = _council(session)
    meeting_id = Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    )
    session.add(meeting_id)
    session.flush()
    session.add(Motion(meeting_id=meeting_id.id, title="A motion", item_number="1"))
    session.add(Tender(meeting_id=meeting_id.id, description="Playground upgrade", amount=50000,
                       awarded_to="Acme Constructions", is_confidential=False))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    row = feed["meetings"][0]
    assert row["tests"]["run"] == 14
    assert row["tests"]["exceptions"] + row["tests"]["within_baseline"] == row["tests"]["run"]
    assert row["tests"]["exceptions"] == len(row["exceptions"])


def test_any_occurrence_tender_award_is_an_exception_with_both_views(session):
    council_id = _council(session)
    meeting = Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    )
    session.add(meeting)
    session.flush()
    session.add(Motion(meeting_id=meeting.id, title="A motion", item_number="1"))
    session.add(Tender(meeting_id=meeting.id, description="Playground upgrade", amount=50000,
                       awarded_to="Acme Constructions", is_confidential=False))
    session.flush()

    tb = TestBaseline(n_meetings=20, values=[0.0] * 20)
    feed = compute_watch_feed(
        session, council_id, "test", "2026-09-06T00:00:00+00:00",
        _baselines({"procurement.concentration": {"full_council": tb}}), min_n=3,
        validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR,
    )
    row = feed["meetings"][0]
    exc = next(e for e in row["exceptions"] if e["test_id"] == "procurement.concentration")
    assert exc["threshold_kind"] == "any_occurrence"
    assert exc["baseline_median"] == 0.0
    # An institutional-unit test's claim needs no redaction — public mirrors deep.
    assert exc["deep"]["finding"]
    assert exc["public"] is not None
    assert exc["public"]["finding"] == exc["deep"]["finding"]


def test_quiet_meeting_has_no_exceptions(session):
    council_id = _council(session)
    meeting = Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    )
    session.add(meeting)
    session.flush()
    session.add(Motion(meeting_id=meeting.id, title="A motion", item_number="1"))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    row = feed["meetings"][0]
    assert row["exceptions"] == []
    assert row["tests"]["exceptions"] == 0
    assert row["tests"]["within_baseline"] == 14


def test_provenance_is_null_for_a_meeting_with_no_recorded_pdf(session):
    council_id = _council(session)
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2026, 5, 12),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
        minutes_pdf_path=None,
    ))
    session.flush()

    feed = compute_watch_feed(session, council_id, "test", "2026-09-06T00:00:00+00:00",
                              _baselines(), min_n=3,
                              validation_dir=_NO_SUCH_DIR, batch_jobs_dir=_NO_SUCH_DIR)
    prov = feed["meetings"][0]["provenance"]
    assert prov["pdf_filename"] is None
    assert prov["run_id"] is None
    assert prov["run_id_count"] == 0
    assert prov["validation_status"] is None


# ---------------------------------------------------------------------------
# project_watch_feed_to_public (Step 5 — the B.3 filter + re-verification)
# ---------------------------------------------------------------------------

def _exc(test_id="a.test", public=True, finding="A finding", verdict="A verdict") -> dict:
    return {
        "test_id": test_id, "threshold_kind": "any_occurrence", "baseline_median": 0.0,
        "why": "value 1", "stat": {"value": 1, "denominator": None, "unit": "count"},
        "deep": {"finding": finding, "verdict": verdict, "valence": "critical", "severity": "Integrity flag"},
        "public": (
            {"finding": finding, "verdict": verdict, "valence": "critical", "severity": "Integrity flag"}
            if public else None
        ),
    }


def _row(meeting_id=1, exceptions=None) -> dict:
    exceptions = exceptions if exceptions is not None else [_exc()]
    return {
        "meeting_id": meeting_id, "meeting_date": "2026-01-01", "meeting_type": "Ordinary Council Meeting",
        "body_class": "full_council", "counts": {"items": 1, "motions": 1, "other_items": 0},
        "tests": {"run": 14, "exceptions": len(exceptions), "within_baseline": 14 - len(exceptions)},
        "exceptions": exceptions,
        "provenance": {"pdf_filename": None, "pdf_url": None, "extracted_at": None,
                       "run_id": None, "run_id_count": 0, "model": None,
                       "validation_status": None, "coverage_ratio": None},
    }


def test_a_withheld_exception_is_dropped_and_counted():
    feed = {"council": "test", "generated_at": "x", "n_meetings": 1,
            "meetings": [_row(exceptions=[_exc(public=True), _exc(test_id="b.test", public=False)])]}
    published, gate = project_watch_feed_to_public(feed, min_n=3)
    row = published["meetings"][0]
    assert [e["test_id"] for e in row["exceptions"]] == ["a.test"]
    assert row["exceptions_withheld"] == 1
    assert gate.passed


def test_published_exception_carries_the_public_fields_flattened():
    feed = {"council": "test", "generated_at": "x", "n_meetings": 1,
            "meetings": [_row(exceptions=[_exc(finding="A public finding", verdict="A public verdict")])]}
    published, _gate = project_watch_feed_to_public(feed, min_n=3)
    exc = published["meetings"][0]["exceptions"][0]
    assert exc["finding"] == "A public finding"
    assert exc["verdict"] == "A public verdict"
    assert exc["valence"] == "critical"
    assert exc["severity"] == "Integrity flag"
    assert exc["threshold_kind"] == "any_occurrence"
    assert exc["baseline_median"] == 0.0


def test_a_row_with_nothing_withheld_reports_zero():
    feed = {"council": "test", "generated_at": "x", "n_meetings": 1,
            "meetings": [_row(exceptions=[_exc()])]}
    published, _gate = project_watch_feed_to_public(feed, min_n=3)
    assert published["meetings"][0]["exceptions_withheld"] == 0


def test_reverification_catches_a_leaked_name_in_what_survived():
    # Simulates a bug in the filter itself: a "public" view that still names
    # someone. This must fail even though it already carries a "public"
    # marker — the re-check operates on the actual shipped text, independent
    # of the tier bookkeeping that put it there.
    known_names = {("Jane", "Citizen")}
    feed = {"council": "test", "generated_at": "x", "n_meetings": 1,
            "meetings": [_row(exceptions=[
                _exc(finding="Jane Citizen had an unexplained absence", verdict="Jane Citizen was absent."),
            ])]}
    _published, gate = project_watch_feed_to_public(feed, min_n=3, known_names=known_names)
    assert not gate.passed
    assert gate.violations[0].check == "name-free-text"
