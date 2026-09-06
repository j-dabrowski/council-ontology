"""
Unit tests for src/provenance.py (docs/frontend/WATCH_FEED_PLAN.md Step 3) —
the meetings.minutes_pdf_path -> data/validation/<hash>.json ->
data/batch_jobs/*.json join, over a small fixture directory covering the
three cases the plan's acceptance check names: full provenance, no batch
record, and a document resubmitted in a second, later batch.
"""
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Council, Meeting
from src.provenance import meeting_provenance
from src.storage.database import _enable_wal_and_fk

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "provenance"
VALIDATION_DIR = FIXTURES / "validation"
BATCH_JOBS_DIR = FIXTURES / "batch_jobs"


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


def _seed(session):
    council = Council(name="Test Council Full Name", short_name="TestCouncil", state="WA")
    session.add(council)
    session.flush()

    # 101: full provenance — a validation record and exactly one batch match.
    session.add(Meeting(
        id=101, council_id=council.id, meeting_date=datetime(2026, 1, 1).date(),
        document_type="minutes", minutes_pdf_path="data/raw/testcouncil/aaa11111.pdf",
        minutes_pdf_url="https://example.org/aaa11111.pdf",
        extracted_at=datetime(2026, 1, 2, 3, 4, 5),
    ))
    # 102: no batch record at all — extracted by some earlier, non-batch path.
    session.add(Meeting(
        id=102, council_id=council.id, meeting_date=datetime(2026, 1, 8).date(),
        document_type="minutes", minutes_pdf_path="data/raw/testcouncil/bbb22222.pdf",
        minutes_pdf_url="https://example.org/bbb22222.pdf",
        extracted_at=None,
    ))
    # 103: appears in two separate batch jobs (a later resubmission).
    session.add(Meeting(
        id=103, council_id=council.id, meeting_date=datetime(2026, 1, 15).date(),
        document_type="minutes", minutes_pdf_path="data/raw/testcouncil/ccc33333.pdf",
        minutes_pdf_url="https://example.org/ccc33333.pdf",
        extracted_at=datetime(2026, 3, 2, 0, 0, 0),
    ))
    session.flush()


def test_full_provenance_meeting_has_every_field(session):
    _seed(session)
    result = meeting_provenance(session, [101], VALIDATION_DIR, BATCH_JOBS_DIR)
    p = result[101]
    assert p["pdf_filename"] == "aaa11111.pdf"
    assert p["pdf_url"] == "https://example.org/aaa11111.pdf"
    assert p["extracted_at"] == "2026-01-02T03:04:05"
    assert p["run_id"] == "msgbatch_older"
    assert p["run_id_count"] == 1
    assert p["model"] == "claude-haiku-4-5-20251001"
    assert p["validation_status"] == "PASS"
    assert p["coverage_ratio"] == 0.91


def test_no_batch_record_renders_null_run_fields(session):
    _seed(session)
    result = meeting_provenance(session, [102], VALIDATION_DIR, BATCH_JOBS_DIR)
    p = result[102]
    assert p["extracted_at"] is None
    assert p["run_id"] is None
    assert p["run_id_count"] == 0
    assert p["model"] is None
    # Validation still recorded independently of batch presence.
    assert p["validation_status"] == "REVIEW"
    assert p["coverage_ratio"] == 0.54


def test_multi_batch_meeting_picks_the_most_recent_by_submitted_at(session):
    _seed(session)
    result = meeting_provenance(session, [103], VALIDATION_DIR, BATCH_JOBS_DIR)
    p = result[103]
    assert p["run_id"] == "msgbatch_newer"
    assert p["run_id_count"] == 2


def test_meeting_with_no_pdf_path_gets_null_provenance(session):
    council = Council(name="Test Council Full Name", short_name="TestCouncil", state="WA")
    session.add(council)
    session.flush()
    session.add(Meeting(
        id=104, council_id=council.id, meeting_date=datetime(2026, 1, 22).date(),
        document_type="minutes", minutes_pdf_path=None, minutes_pdf_url=None,
    ))
    session.flush()

    result = meeting_provenance(session, [104], VALIDATION_DIR, BATCH_JOBS_DIR)
    p = result[104]
    assert p["pdf_filename"] is None
    assert p["run_id"] is None
    assert p["run_id_count"] == 0
    assert p["validation_status"] is None
    assert p["coverage_ratio"] is None


def test_missing_directories_do_not_raise(session):
    _seed(session)
    result = meeting_provenance(session, [101], Path("/no/such/dir"), Path("/no/such/dir/either"))
    p = result[101]
    assert p["validation_status"] is None
    assert p["run_id"] is None
