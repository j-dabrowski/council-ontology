"""
Unit tests for build_method_record() (src/analysis/method.py,
docs/frontend/METHOD_PAGE_PLAN.md Step 1) — every metric traces to a fixture
file and carries that file's own generated_at, and a missing or malformed
source file degrades to an explicit `source_missing` gap rather than a zero
or a crash.
"""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.method import build_method_record
from src.models import Base, Council, Meeting
from src.storage.database import _enable_wal_and_fk

FIXTURES = Path(__file__).parent / "fixtures"
FULL_FIXTURE = FIXTURES / "method"
MALFORMED_FIXTURE = FIXTURES / "method_malformed"


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


def _seed_meetings(session, council_id: int) -> None:
    # 2020: one minutes meeting, matching the fixture census (1 censused
    # in 2020). 2021: one minutes + one agenda, so documents_in_db (2)
    # diverges from minutes_in_db (1) — the same shape as the real corpus's
    # 2022-2026 divergence (METHOD_PAGE_PLAN.md A.6).
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2020, 3, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    ))
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2021, 5, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    ))
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2021, 6, 1),
        meeting_type="Ordinary Council Meeting", document_type="agenda",
    ))
    session.flush()


def test_every_populated_metric_carries_its_own_source_and_generated_at(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)

    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )

    assert record["coverage"]["census_total"] == {
        "value": 2, "source": "data/census.json",
        "generated_at": "2020-01-01T00:00:00+00:00", "n": 2,
    }
    metrics = record["validation"]["metrics"]
    assert metrics["quote_completeness"]["full_corpus"] == {
        "value": 0.85, "source": "data/validation/summary.json",
        "generated_at": "2020-01-04T00:00:00+00:00", "n": 2,
    }
    assert metrics["quote_completeness"]["sample"] == {
        "value": 0.9, "source": "data/sample_validation/summary.json",
        "generated_at": "2020-01-03T00:00:00+00:00", "n": 2,
    }
    # Definition/target are report.txt's own words, parsed not retyped.
    assert "at least one" in metrics["quote_completeness"]["definition"]
    assert metrics["quote_completeness"]["target"] == "Target: >80%. FAIL if <50%."
    assert metrics["quote_completeness"]["means_if_failed"]  # non-empty, written once


def test_no_number_is_written_in_jsx_every_figure_traces_to_a_file(session):
    """A spot-check across sections that every rendered figure is the
    fixture's own value, not a default baked into the generator."""
    council_id = _council(session)
    _seed_meetings(session, council_id)
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )

    assert record["coverage"]["document_flags"]["value"] == {"large_document": 1}
    assert record["coverage"]["type_mix"]["value"] == {"Ordinary Council Meeting": 2}
    assert record["validation"]["full_corpus_split"] == {
        "pass": 1, "review": 1, "fail": 0, "errors": 0,
        "source": "data/validation/summary.json",
        "generated_at": "2020-01-04T00:00:00+00:00", "n": 2,
    }
    assert record["validation"]["sample_split"] == {
        "pass": 2, "review": 0, "fail": 0, "converged": True,
        "source": "data/sample_validation/summary.json",
        "generated_at": "2020-01-03T00:00:00+00:00", "n": 2,
    }
    assert record["validation"]["schema_flags"]["value"] == 1
    assert record["validation"]["schema_flags"]["flagged_files"] == ["a.pdf"]

    per_file = record["validation"]["sample_per_file"]["value"]
    assert per_file == [
        {"filename": "a.pdf", "meeting_date": "2020-03-01",
         "paraphrase_pct": 0, "coverage_pct": 30.0, "keyword_gap_pct": 0, "status": "PASS"},
        {"filename": "b.pdf", "meeting_date": "2021-05-01",
         "paraphrase_pct": 5, "coverage_pct": 25.0, "keyword_gap_pct": 0, "status": "PASS"},
    ]

    flags = record["validation"]["metrics"]["inventory_agreement"]["sample"]["flagged_entity_types"]
    assert flags == {
        "motion_count": {
            "flagged_count": 1,
            "docs": [{"filename": "a.pdf", "l1": "1", "extracted": "3", "ratio": "3.0"}],
        },
    }
    # Inventory agreement has no aggregate in either summary file — null with
    # a reason, never a zero.
    inv = record["validation"]["metrics"]["inventory_agreement"]
    assert inv["full_corpus"]["value"] is None
    assert inv["full_corpus"]["reason"] == "no_aggregate_in_source"
    assert inv["sample"]["value"] is None
    assert inv["sample"]["reason"] == "no_aggregate_in_source"


def test_live_per_year_coverage_columns_come_from_the_database(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )

    by_year = {row["year"]: row for row in record["coverage"]["by_year"]}
    assert by_year[2020] == {
        "year": 2020, "censused": 1, "documents_in_db": 1, "minutes_in_db": 1,
    }
    # 2021: census shows 1, database (scraped later) shows 2 documents but
    # only 1 minutes — the divergence the real corpus shows for 2022-2026
    # (METHOD_PAGE_PLAN.md A.6), not an error state.
    assert by_year[2021] == {
        "year": 2021, "censused": 1, "documents_in_db": 2, "minutes_in_db": 1,
    }


def test_missing_source_file_is_null_with_reason_not_a_zero(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)

    # FULL_FIXTURE deliberately has no extraction_errors.json.
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )

    assert record["extraction_batch"] == {
        "value": None, "source": "data/extraction_errors.json",
        "generated_at": None, "n": None, "reason": "source_missing",
    }


def test_malformed_source_file_degrades_without_crashing_other_sections(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)

    # MALFORMED_FIXTURE's validation/summary.json is not valid JSON, but
    # every other file (including extraction_errors.json) is present and
    # valid.
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=MALFORMED_FIXTURE,
    )

    assert record["validation"]["full_corpus_split"]["value"] is None
    assert record["validation"]["full_corpus_split"]["reason"] == "source_missing"
    assert record["validation"]["metrics"]["quote_completeness"]["full_corpus"]["reason"] == \
        "source_missing"
    # The sample side reads a different file and must be unaffected.
    assert record["validation"]["metrics"]["quote_completeness"]["sample"]["value"] == 0.9
    # extraction_errors.json is valid in this fixture and must still load.
    assert record["extraction_batch"]["batch_id"] == "msgbatch_fixture01"
    assert record["extraction_batch"]["attempted"] == 2
