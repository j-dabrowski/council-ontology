"""
Unit tests for build_method_record() (src/analysis/method.py,
docs/frontend/METHOD_PAGE_PLAN.md Step 1) — every metric traces to a fixture
file and carries that file's own generated_at, and a missing or malformed
source file degrades to an explicit `source_missing` gap rather than a zero
or a crash.

The entity-resolution tests (ENTITY_RESOLUTION_SECTION_PLAN.md Step 1) cover
the one block computed from the database rather than a fixture file.
"""
import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.method import build_method_record
from src.invariant_gate import usable_roster_names
from src.models import Base, Council, Councillor, Meeting, Motion, Tender, Vote
from src.models.ontology import VoteChoice
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
        "value": 2, "source": str(FULL_FIXTURE / "census.json"),
        "generated_at": "2020-01-01T00:00:00+00:00", "n": 2,
    }
    metrics = record["validation"]["metrics"]
    assert metrics["quote_completeness"]["full_corpus"] == {
        "value": 0.85, "source": str(FULL_FIXTURE / "validation" / "summary.json"),
        "generated_at": "2020-01-04T00:00:00+00:00", "n": 2,
    }
    assert metrics["quote_completeness"]["sample"] == {
        "value": 0.9, "source": str(FULL_FIXTURE / "sample_validation" / "summary.json"),
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
        "source": str(FULL_FIXTURE / "validation" / "summary.json"),
        "generated_at": "2020-01-04T00:00:00+00:00", "n": 2,
    }
    assert record["validation"]["sample_split"] == {
        "pass": 2, "review": 0, "fail": 0, "converged": True,
        "source": str(FULL_FIXTURE / "sample_validation" / "summary.json"),
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
        "value": None, "source": str(FULL_FIXTURE / "extraction_errors.json"),
        "generated_at": None, "n": None, "reason": "source_missing",
    }


def test_model_version_reports_recoverable_and_unrecoverable_documents(session):
    """FULL_FIXTURE's llm_archive covers one meeting (a.pdf); a second,
    otherwise-identical meeting with no archived chunk is the unrecoverable
    case (docs/uplift/migration/01-known-defects.md G-33)."""
    council_id = _council(session)
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2020, 3, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
        minutes_pdf_path="data/raw/fixture/a.pdf",
        extracted_at=datetime(2020, 1, 5),
    ))
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2021, 5, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
        minutes_pdf_path="data/raw/fixture/b.pdf",
        extracted_at=datetime(2021, 1, 1),
    ))
    session.add(Meeting(
        council_id=council_id, meeting_date=date(2019, 1, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    ))  # no extracted_at at all — a different, older gap
    session.flush()

    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )
    mv = record["model_version"]
    assert mv["value"] == {"models": ["claude-haiku-4-5-20251001"]}
    assert mv["n"] == 2
    assert mv["documents_with_recoverable_model"] == 1
    assert mv["documents_without_recoverable_model"] == 1
    assert mv["documents_missing_extraction_timestamp"] == 1


def test_model_version_missing_index_is_null_with_reason(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=MALFORMED_FIXTURE,
    )
    assert record["model_version"]["value"] is None
    assert record["model_version"]["reason"] == "source_missing"


def test_human_audit_counts_filled_and_unfilled_markers(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )
    audit = record["human_audit"]
    assert audit["n"] == 2  # total markers in the fixture (1 filled, 1 unfilled)
    assert audit["value"] == {
        "reviewed": 1, "total_markers": 2, "correct": 1, "correct_pct": 100.0,
    }
    assert audit["generated_at"] == "2020-01-06"


def test_human_audit_all_unfilled_reports_pending_not_a_fabricated_rate(session):
    council_id = _council(session)
    _seed_meetings(session, council_id)
    record = build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=MALFORMED_FIXTURE,
    )
    # MALFORMED_FIXTURE has no audit_report.md at all.
    assert record["human_audit"]["value"] is None
    assert record["human_audit"]["reason"] == "source_missing"


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


# ---------------------------------------------------------------------------
# entity_resolution (docs/frontend/ENTITY_RESOLUTION_SECTION_PLAN.md Step 1)
# ---------------------------------------------------------------------------

def _seed_entity_resolution(session, council_id: int) -> Councillor:
    """A minutes meeting carrying: one multi-spelling firm (Acme Concrete,
    two raw strings), one single-spelling firm, one redaction placeholder,
    and one firm whose name contains a real voting councillor's surname —
    the shapes both entity-resolution cases group."""
    meeting = Meeting(
        council_id=council_id, meeting_date=date(2022, 1, 1),
        meeting_type="Ordinary Council Meeting", document_type="minutes",
    )
    session.add(meeting)
    session.flush()

    for name, amount in [
        ("Acme Concrete Pty Ltd", 1000.0),
        ("Acme Concrete Pty Ltd", 2000.0),
        ("Acme Concrete", 500.0),
        ("Bailey Roofing", 3000.0),
        ("Respondent 1", 4000.0),
        ("Baxter Roofing Supplies", 9000.0),
    ]:
        session.add(Tender(meeting_id=meeting.id, awarded_to=name, amount=amount))

    councillor = Councillor(given_name="Sam", family_name="Baxter", slug="sam-baxter")
    session.add(councillor)
    session.flush()

    # A vote (on an ordinary, non-tender motion) is what makes this
    # councillor eligible for the surname test at all — surnames_tested is
    # restricted to councillors who cast >=1 vote.
    motion = Motion(meeting_id=meeting.id, title="Confirmation of minutes")
    session.add(motion)
    session.flush()
    session.add(Vote(motion_id=motion.id, councillor_id=councillor.id, choice=VoteChoice.FOR))
    session.flush()
    return councillor


def _entity_resolution_record(session, council_id: int) -> dict:
    return build_method_record(
        session, council_id, "fixture", "2020-06-01T00:00:00+00:00",
        data_dir=FULL_FIXTURE,
    )["entity_resolution"]


def test_supplier_normalisation_groups_variants_and_excludes_placeholders(session):
    council_id = _council(session)
    _seed_entity_resolution(session, council_id)

    sn = _entity_resolution_record(session, council_id)["supplier_normalisation"]

    assert sn["named_award_rows"] == 6
    # acmeconcrete, baileyroofing, respondent1, baxterroofingsupplies
    assert sn["distinct_firms"] == 4
    assert sn["multi_variant_firms"] == 1
    assert len(sn["examples"]) == 1

    example = sn["examples"][0]
    assert example["merged_key"] == "acmeconcrete"
    assert example["n_awards"] == 3
    assert example["total_amount"] == 3500.0
    assert {r["string"]: r["n"] for r in example["raw"]} == {
        "Acme Concrete Pty Ltd": 2, "Acme Concrete": 1,
    }
    # "Respondent 1" is excluded from the grouping, not counted as a firm.
    assert sn["excluded_placeholders"]["n_awards"] == 1
    assert "Baxter Roofing Supplies" not in [e["merged_key"] for e in sn["examples"]]


def test_surname_collision_reuses_decider_supplier_conflict_and_drops_councillor_identity(session):
    council_id = _council(session)
    _seed_entity_resolution(session, council_id)

    sc = _entity_resolution_record(session, council_id)["surname_collision"]

    assert sc["named_awards"] == 5  # excludes the "Respondent 1" placeholder
    assert sc["surnames_tested"] == 1
    assert sc["naive_matches"] == 1
    assert sc["resolved"] == [{
        "firm": "Baxter Roofing Supplies", "amount": 9000.0,
        "what_it_is": None, "resolution": None,
        "reason": "needs_manual_resolution",
    }]
    assert sc["unresolved_matches"] == 1
    assert sc["genuine_matches"] == 0

    blob = json.dumps(sc)
    assert "councillor_name" not in blob
    assert "councillor_id" not in blob
    assert "Sam" not in blob  # the councillor's given name never appears


def _full_name_hits(blob: str, councillors: list[Councillor]) -> list[str]:
    known = {(c.given_name, c.family_name) for c in councillors}
    hits = []
    for given, family in usable_roster_names(known):
        pattern = rf"\b{re.escape(given)}\s+{re.escape(family)}\b"
        if re.search(pattern, blob, re.IGNORECASE):
            hits.append(f"{given} {family}")
    return sorted(hits)


def test_entity_resolution_payload_contains_no_councillor_full_name(session):
    council_id = _council(session)
    _seed_entity_resolution(session, council_id)
    session.add(Councillor(given_name="Peter", family_name="Evans", slug="peter-evans"))
    session.flush()

    entity_resolution = _entity_resolution_record(session, council_id)
    blob = json.dumps(entity_resolution)

    councillors = session.query(Councillor).all()
    assert _full_name_hits(blob, councillors) == []


def test_name_scan_fails_when_a_councillor_name_is_injected(session):
    """Proves the check in the previous test actually catches a leak,
    rather than passing vacuously — inject a real councillor's full name
    into a copy of the built block and confirm the scan flags it."""
    council_id = _council(session)
    _seed_entity_resolution(session, council_id)

    entity_resolution = _entity_resolution_record(session, council_id)
    tampered = json.loads(json.dumps(entity_resolution))
    tampered["surname_collision"]["resolved"][0]["what_it_is"] = (
        "a business associated with Sam Baxter"
    )
    blob = json.dumps(tampered)

    councillors = session.query(Councillor).all()
    assert _full_name_hits(blob, councillors) == ["Sam Baxter"]
