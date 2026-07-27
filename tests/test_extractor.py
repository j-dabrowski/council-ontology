"""
Tests for Level 2 plumbing:
  - _resolve_offset (unit)
  - DB schema smoke test (all expected tables exist after init_db)
  - save_extraction integration: evidence rows, hallucination flagging, new entity types
"""
import pytest
from datetime import date

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.extraction.extractor import _resolve_offset, save_extraction
from src.extraction.schemas import (
    ExtractedAppointment,
    ExtractedBudgetItem,
    ExtractedBuildingPermit,
    ExtractedCouncillor,
    ExtractedCommitteeReport,
    ExtractedDelegatedDecision,
    ExtractedDeputation,
    ExtractedInterestDeclaration,
    ExtractedMeeting,
    ExtractedMotion,
    ExtractedOtherItem,
    ExtractedPetition,
    ExtractedPublicQuestion,
    ExtractedTender,
)
from src.models import Base, Council, ExtractionEvidence
from src.storage.database import _enable_wal_and_fk


# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture
def council_id(session):
    council = Council(name="Test Council", short_name="TestCouncil", state="WA")
    session.add(council)
    session.flush()
    return council.id


# ---------------------------------------------------------------------------
# _resolve_offset — unit tests
# ---------------------------------------------------------------------------


def test_resolve_offset_found():
    text = "The council RESOLVED to approve the budget for the year."
    quote = "RESOLVED to approve"
    offset, length = _resolve_offset(text, quote)
    assert offset == text.index(quote)
    assert length == len(quote)


def test_resolve_offset_not_found():
    offset, length = _resolve_offset("Some meeting text", "phrase not in text")
    assert offset is None
    assert length is None


def test_resolve_offset_empty_text():
    assert _resolve_offset("", "quote") == (None, None)


def test_resolve_offset_empty_quote():
    assert _resolve_offset("some text", "") == (None, None)


def test_resolve_offset_both_empty():
    assert _resolve_offset("", "") == (None, None)


def test_resolve_offset_first_occurrence():
    text = "MOVED by Smith. MOVED by Jones."
    quote = "MOVED"
    offset, length = _resolve_offset(text, quote)
    assert offset == 0
    assert length == 5


def test_resolve_offset_at_start():
    text = "Start of document something else"
    offset, length = _resolve_offset(text, "Start of document")
    assert offset == 0
    assert length == len("Start of document")


def test_resolve_offset_at_end():
    text = "Some text then CARRIED"
    offset, length = _resolve_offset(text, "CARRIED")
    assert offset == len("Some text then ")
    assert length == len("CARRIED")


# ---------------------------------------------------------------------------
# DB schema smoke test
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "councils", "councillors", "councillor_terms", "sites",
    "meetings", "motions", "votes", "planning_applications", "community_submissions",
    "public_questions", "deputations", "petitions", "appointments",
    "committee_reports", "budget_items", "interest_declarations",
    "tenders", "delegated_decisions", "building_permits",
    "other_items", "extraction_evidence", "relationships",
}


def test_all_tables_created(engine):
    insp = inspect(engine)
    actual = set(insp.get_table_names())
    missing = EXPECTED_TABLES - actual
    assert not missing, f"Tables not created: {sorted(missing)}"


# ---------------------------------------------------------------------------
# save_extraction — integration tests
# ---------------------------------------------------------------------------

# Source text that contains all quotes used in _make_meeting() verbatim.
SOURCE_TEXT = (
    "MINUTES OF THE ORDINARY COUNCIL MEETING held on 15 March 2023.\n"
    "MOVED by Cr Smith, SECONDED by Cr Jones that the budget be approved. CARRIED.\n"
    "Public question from Jane Doe regarding parking meters.\n"
    "Deputation by Mr Brown on the proposed development at 42 Main St.\n"
    "Petition tabled: Stop the roundabout, 150 signatures.\n"
    "Cr Alice Green appointed to the Tourism Advisory Board.\n"
    "Finance Committee report tabled covering 5 items.\n"
    "Budget item: Parks maintenance allocation $120,000.\n"
    "Cr Bob White declared a financial interest in Item 7.\n"
    "Tender RFT-2023-001 awarded to ABC Contractors for $85,000.\n"
    "Delegated decision: CEO approved permit extension.\n"
    "Building permit BP-001 at 10 Elm St approved.\n"
    "Other: Verbal thanks to retiring officer.\n"
)


def _make_meeting() -> ExtractedMeeting:
    return ExtractedMeeting(
        council_name="Test Council",
        meeting_type="Ordinary Council Meeting",
        meeting_date=date(2023, 3, 15),
        motions=[
            ExtractedMotion(
                item_number="1",
                title="Budget Approval",
                motion_text="that the budget be approved",
                outcome="carried",
                source_quotes=[
                    "MOVED by Cr Smith, SECONDED by Cr Jones that the budget be approved. CARRIED."
                ],
            )
        ],
        public_questions=[
            ExtractedPublicQuestion(
                questioner_name="Jane Doe",
                question_summary="parking meters",
                source_quotes=["Public question from Jane Doe regarding parking meters."],
            )
        ],
        deputations=[
            ExtractedDeputation(
                presenter_name="Mr Brown",
                topic="42 Main St development",
                source_quotes=[
                    "Deputation by Mr Brown on the proposed development at 42 Main St."
                ],
            )
        ],
        petitions=[
            ExtractedPetition(
                subject="Stop the roundabout",
                signatory_count=150,
                source_quotes=["Petition tabled: Stop the roundabout, 150 signatures."],
            )
        ],
        appointments=[
            ExtractedAppointment(
                councillor=ExtractedCouncillor(given_name="Alice", family_name="Green"),
                role="Member",
                body_name="Tourism Advisory Board",
                source_quotes=["Cr Alice Green appointed to the Tourism Advisory Board."],
            )
        ],
        committee_reports=[
            ExtractedCommitteeReport(
                committee_name="Finance Committee",
                item_count=5,
                source_quotes=["Finance Committee report tabled covering 5 items."],
            )
        ],
        budget_items=[
            ExtractedBudgetItem(
                description="Parks maintenance allocation",
                amount=120000.0,
                source_quotes=["Budget item: Parks maintenance allocation $120,000."],
            )
        ],
        interest_declarations=[
            ExtractedInterestDeclaration(
                councillor=ExtractedCouncillor(given_name="Bob", family_name="White"),
                interest_type="financial",
                item_reference="Item 7",
                source_quotes=["Cr Bob White declared a financial interest in Item 7."],
            )
        ],
        tenders=[
            ExtractedTender(
                reference_number="RFT-2023-001",
                awarded_to="ABC Contractors",
                amount=85000.0,
                source_quotes=["Tender RFT-2023-001 awarded to ABC Contractors for $85,000."],
            )
        ],
        delegated_decisions=[
            ExtractedDelegatedDecision(
                description="permit extension",
                officer_title="CEO",
                source_quotes=["Delegated decision: CEO approved permit extension."],
            )
        ],
        building_permits=[
            ExtractedBuildingPermit(
                reference_number="BP-001",
                site_address="10 Elm St",
                status="approved",
                source_quotes=["Building permit BP-001 at 10 Elm St approved."],
            )
        ],
        other_items=[
            ExtractedOtherItem(
                item_type="acknowledgement",
                description="Verbal thanks to retiring officer",
                source_quotes=["Other: Verbal thanks to retiring officer."],
            )
        ],
    )


def test_save_extraction_returns_meeting_id(session, council_id):
    meeting_id = save_extraction(session, council_id, _make_meeting(), text=SOURCE_TEXT)
    assert isinstance(meeting_id, int)
    assert meeting_id > 0


def test_save_extraction_evidence_row_count(session, council_id):
    save_extraction(session, council_id, _make_meeting(), text=SOURCE_TEXT)
    # One source_quote per entity type × 12 entity types = 12 rows
    count = session.query(ExtractionEvidence).count()
    assert count == 12


def test_save_extraction_offsets_all_resolved(session, council_id):
    save_extraction(session, council_id, _make_meeting(), text=SOURCE_TEXT)
    rows = session.query(ExtractionEvidence).all()
    for row in rows:
        assert row.char_offset is not None, f"Unresolved: {row.quote_text!r}"
        assert row.char_length == len(row.quote_text)
        assert row.char_offset + row.char_length <= len(SOURCE_TEXT)
        # Verify the offset actually points to the quote in SOURCE_TEXT
        assert SOURCE_TEXT[row.char_offset:row.char_offset + row.char_length] == row.quote_text


def test_save_extraction_hallucination_flagged(session, council_id):
    extracted = ExtractedMeeting(
        meeting_type="Ordinary Council Meeting",
        meeting_date=date(2023, 4, 1),
        motions=[
            ExtractedMotion(
                title="Test",
                source_quotes=["this phrase does not appear in the source text XYZ-HALLUCINATED"],
            )
        ],
    )
    save_extraction(session, council_id, extracted, text=SOURCE_TEXT)
    rows = session.query(ExtractionEvidence).filter_by(
        quote_text="this phrase does not appear in the source text XYZ-HALLUCINATED"
    ).all()
    assert len(rows) == 1
    assert rows[0].char_offset is None
    assert rows[0].char_length is None


def test_save_extraction_no_text_all_offsets_null(session, council_id):
    extracted = ExtractedMeeting(
        meeting_type="Ordinary Council Meeting",
        meeting_date=date(2023, 5, 1),
        motions=[
            ExtractedMotion(
                title="Test",
                source_quotes=["MOVED by Cr Smith"],
            )
        ],
    )
    save_extraction(session, council_id, extracted, text=None)
    rows = session.query(ExtractionEvidence).filter_by(quote_text="MOVED by Cr Smith").all()
    assert len(rows) == 1
    assert rows[0].char_offset is None


def test_save_extraction_all_new_entity_types_persisted(session, council_id):
    from src.models import (
        Appointment, BudgetItem, BuildingPermit, CommitteeReport,
        DelegatedDecision, Deputation, InterestDeclaration,
        OtherItem, Petition, PublicQuestion, Tender,
    )
    save_extraction(session, council_id, _make_meeting(), text=SOURCE_TEXT)
    assert session.query(PublicQuestion).count() == 1
    assert session.query(Deputation).count() == 1
    assert session.query(Petition).count() == 1
    assert session.query(Appointment).count() == 1
    assert session.query(CommitteeReport).count() == 1
    assert session.query(BudgetItem).count() == 1
    assert session.query(InterestDeclaration).count() == 1
    assert session.query(Tender).count() == 1
    assert session.query(DelegatedDecision).count() == 1
    assert session.query(BuildingPermit).count() == 1
    assert session.query(OtherItem).count() == 1


def test_save_extraction_evidence_covers_all_entity_tables(session, council_id):
    save_extraction(session, council_id, _make_meeting(), text=SOURCE_TEXT)
    tables = {
        row.entity_table
        for row in session.query(ExtractionEvidence).all()
    }
    expected = {
        "motions", "public_questions", "deputations", "petitions",
        "appointments", "committee_reports", "budget_items",
        "interest_declarations", "tenders", "delegated_decisions",
        "building_permits", "other_items",
    }
    assert tables == expected


def test_save_extraction_meeting_upsert(session, council_id):
    """Same council + date returns the same meeting_id (upsert, not duplicate)."""
    extracted = ExtractedMeeting(
        meeting_type="Ordinary Council Meeting",
        meeting_date=date(2023, 6, 1),
    )
    id1 = save_extraction(session, council_id, extracted)
    id2 = save_extraction(session, council_id, extracted)
    assert id1 == id2
