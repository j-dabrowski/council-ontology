"""
Unit tests for src/analysis/evidence.py (docs/frontend/EVIDENCE_CHAIN_PLAN.md
Step 1) — resolve_evidence()'s four match tiers plus the no-evidence case,
and evidence_for_officer_ratification()'s both-sides pairing.

sqlite:///:memory: engine + Base.metadata.create_all, same pattern as
test_digest.py / test_method.py.
"""
from datetime import date
from pathlib import Path

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.evidence import (
    evidence_for_chair_capture,
    evidence_for_objection_responsiveness,
    evidence_for_officer_ratification,
    evidence_for_threshold_gaming,
    evidence_for_transparency,
    resolve_evidence,
)
from src.models import (
    ApplicationStatus,
    Base,
    BudgetItem,
    CommunitySubmission,
    Council,
    Councillor,
    CouncillorTerm,
    ExtractionEvidence,
    Meeting,
    Motion,
    MotionOutcome,
    PlanningApplication,
    Tender,
)
from src.storage.database import _enable_wal_and_fk


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


def _council(session, short_name="TestCouncil") -> int:
    c = Council(name=f"{short_name} Full Name", short_name=short_name, state="WA")
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, meeting_date, document_type="minutes",
             minutes_text=None, minutes_pdf_path=None, minutes_pdf_url=None) -> int:
    m = Meeting(
        council_id=council_id, meeting_date=meeting_date, document_type=document_type,
        meeting_type="Ordinary Council Meeting", minutes_text=minutes_text,
        minutes_pdf_path=minutes_pdf_path, minutes_pdf_url=minutes_pdf_url,
    )
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id, title="A motion", item_number="1",
            officer_recommendation=None, outcome=None, motion_text=None) -> int:
    mo = Motion(
        meeting_id=meeting_id, title=title, item_number=item_number,
        officer_recommendation=officer_recommendation, outcome=outcome,
        motion_text=motion_text,
    )
    session.add(mo)
    session.flush()
    return mo.id


def _evidence(session, meeting_id, entity_table, entity_id, quote_text, char_offset=None) -> None:
    session.add(ExtractionEvidence(
        meeting_id=meeting_id, entity_table=entity_table, entity_id=entity_id,
        quote_text=quote_text, char_offset=char_offset,
    ))
    session.flush()


# ---------------------------------------------------------------------------
# resolve_evidence(): the four tiers, against minutes_text (no PDF on disk)
# ---------------------------------------------------------------------------

def test_exact_tier_when_quote_found_verbatim(session):
    council_id = _council(session)
    text = "The council considered item 1. MOVED that the tender be accepted. CARRIED."
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text=text)
    motion_id = _motion(session, meeting_id)
    _evidence(session, meeting_id, "motions", motion_id, "MOVED that the tender be accepted.")

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    assert len(entries) == 1
    entry = entries[0]
    assert "tier" not in entry  # only set for no_evidence
    assert len(entry["quotes"]) == 1
    q = entry["quotes"][0]
    assert q["tier"] == "exact"
    assert q["text"] == "MOVED that the tender be accepted."
    assert q["resolved_against"] == "minutes_text"
    assert q["resolved_offset"] == text.find("MOVED that the tender be accepted.")


def test_normalised_tier_when_only_whitespace_differs(session):
    council_id = _council(session)
    text = "MOVED that the\ntender   be accepted. CARRIED."
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text=text)
    motion_id = _motion(session, meeting_id)
    # Same content, ordinary single-spaced quote — differs from the source's
    # line-wrap and double space, so an exact substring search misses.
    _evidence(session, meeting_id, "motions", motion_id, "MOVED that the tender be accepted.")

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    q = entries[0]["quotes"][0]
    assert q["tier"] == "normalised"


def test_stripped_tier_when_only_punctuation_or_symbols_differ(session):
    council_id = _council(session)
    # A pypdf-style word-split artefact: hyphen injected mid-word.
    text = "That the ten-der from Aussie Concreting be accepted for the works program."
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text=text)
    motion_id = _motion(session, meeting_id)
    _evidence(session, meeting_id, "motions", motion_id,
              "That the tender from Aussie Concreting be accepted for the works program.")

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    q = entries[0]["quotes"][0]
    assert q["tier"] == "stripped"


def test_paraphrase_tier_when_content_genuinely_differs(session):
    council_id = _council(session)
    text = "The council resolved to defer the matter pending further advice."
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text=text)
    motion_id = _motion(session, meeting_id)
    quote = "Council unanimously rejected the proposal outright."
    _evidence(session, meeting_id, "motions", motion_id, quote)

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    q = entries[0]["quotes"][0]
    assert q["tier"] == "paraphrase"
    assert q["resolved_offset"] is None
    # B.6: never synthesised or tidied, even when unmatched.
    assert q["text"] == quote


def test_entity_with_no_evidence_is_rendered_not_dropped(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text="some text")
    motion_id = _motion(session, meeting_id)
    # deliberately no ExtractionEvidence row for this motion

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["tier"] == "no_evidence"
    assert entry["quotes"] == []
    assert entry["meeting_id"] == meeting_id
    assert entry["meeting_date"] == "2024-01-01"


def test_unrequested_entities_are_not_returned(session):
    """resolve_evidence only ever returns one entry per requested ref."""
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text="text")
    m1 = _motion(session, meeting_id, title="One")
    _motion(session, meeting_id, title="Two", item_number="2")

    entries = resolve_evidence(session, [("motions", m1, "minutes_motion")], council_id)
    assert [e["entity_id"] for e in entries] == [m1]


# ---------------------------------------------------------------------------
# resolve_evidence(): resolving against a real PDF, including page number
# ---------------------------------------------------------------------------

def _write_pdf(path: Path, page_texts: list[str]) -> None:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_pdf_tier_and_page_when_pdf_is_on_disk(tmp_path, monkeypatch, session):
    import src.analysis.evidence as evidence_mod

    monkeypatch.setattr(evidence_mod, "_REPO_ROOT", tmp_path)
    raw_dir = tmp_path / "data" / "raw" / "testcouncil"
    raw_dir.mkdir(parents=True)
    pdf_path = raw_dir / "minutes.pdf"
    _write_pdf(pdf_path, ["Cover page, nothing relevant here.",
                          "MOVED that the tender be accepted. CARRIED."])

    council_id = _council(session)
    meeting_id = _meeting(
        session, council_id, date(2024, 1, 1),
        minutes_pdf_path="data/raw/testcouncil/minutes.pdf",
        minutes_pdf_url="https://example.test/minutes.pdf",
    )
    motion_id = _motion(session, meeting_id)
    _evidence(session, meeting_id, "motions", motion_id, "MOVED that the tender be accepted.")

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    entry = entries[0]
    q = entry["quotes"][0]
    assert q["tier"] == "exact"
    assert q["resolved_against"] == "pdf"
    assert entry["document"] == {
        "filename": "minutes.pdf",
        "url": "https://example.test/minutes.pdf",
        "page": 2,
    }


def test_falls_back_to_minutes_text_when_pdf_missing_from_disk(session):
    council_id = _council(session)
    meeting_id = _meeting(
        session, council_id, date(2024, 1, 1),
        minutes_text="MOVED that the tender be accepted. CARRIED.",
        minutes_pdf_path="data/raw/testcouncil/does-not-exist.pdf",
    )
    motion_id = _motion(session, meeting_id)
    _evidence(session, meeting_id, "motions", motion_id, "MOVED that the tender be accepted.")

    entries = resolve_evidence(session, [("motions", motion_id, "minutes_motion")], council_id)
    q = entries[0]["quotes"][0]
    assert q["resolved_against"] == "minutes_text"
    assert entry_page_is_none(entries[0])


def entry_page_is_none(entry: dict) -> bool:
    return entry["document"]["page"] is None


# ---------------------------------------------------------------------------
# evidence_for_officer_ratification(): both sides of a pair
# ---------------------------------------------------------------------------

def test_both_sides_of_a_diverged_pair_are_resolved(session):
    council_id = _council(session)
    agenda_meeting_id = _meeting(session, council_id, date(2024, 2, 1), document_type="agenda",
                                  minutes_text="RECOMMENDED THAT the application be approved.")
    minutes_meeting_id = _meeting(session, council_id, date(2024, 2, 1), document_type="minutes",
                                   minutes_text="MOVED that the application be refused. LOST.")

    agenda_motion_id = _motion(
        session, agenda_meeting_id, item_number="7", title="Application X",
        officer_recommendation="the application be approved",
    )
    minutes_motion_id = _motion(
        session, minutes_meeting_id, item_number="7", title="Application X",
        outcome=MotionOutcome.LOST, motion_text="the application be refused",
    )
    _evidence(session, agenda_meeting_id, "motions", agenda_motion_id,
              "RECOMMENDED THAT the application be approved.")
    _evidence(session, minutes_meeting_id, "motions", minutes_motion_id,
              "MOVED that the application be refused.")

    result = evidence_for_officer_ratification(session, council_id)
    assert len(result["pairs"]) == 1
    pair = result["pairs"][0]
    assert pair["diverged"] is True
    assert pair["council_outcome"] == "lost"
    assert pair["agenda_motion"]["entity_id"] == agenda_motion_id
    assert pair["agenda_motion"]["quotes"][0]["tier"] == "exact"
    assert pair["minutes_motion"]["entity_id"] == minutes_motion_id
    assert pair["minutes_motion"]["quotes"][0]["tier"] == "exact"


def test_pair_with_no_evidence_on_either_side_still_reports_the_pair(session):
    council_id = _council(session)
    agenda_meeting_id = _meeting(session, council_id, date(2024, 3, 1), document_type="agenda",
                                  minutes_text="text")
    minutes_meeting_id = _meeting(session, council_id, date(2024, 3, 1), document_type="minutes",
                                   minutes_text="text")
    _motion(
        session, agenda_meeting_id, item_number="9", title="Application Y",
        officer_recommendation="the application be approved",
    )
    _motion(
        session, minutes_meeting_id, item_number="9", title="Application Y",
        outcome=MotionOutcome.CARRIED,
    )
    # No ExtractionEvidence rows on either side.

    result = evidence_for_officer_ratification(session, council_id)
    pair = result["pairs"][0]
    assert pair["diverged"] is False
    assert pair["council_outcome"] == "carried"
    assert pair["agenda_motion"]["tier"] == "no_evidence"
    assert pair["minutes_motion"]["tier"] == "no_evidence"


# ---------------------------------------------------------------------------
# resolve_evidence(): _MEETING_ID_VIA (an entity table with no direct
# meeting_id column — planning_applications links via motion_id)
# ---------------------------------------------------------------------------

def _planning_app(session, motion_id, status=ApplicationStatus.APPROVED) -> int:
    pa = PlanningApplication(motion_id=motion_id, status=status)
    session.add(pa)
    session.flush()
    return pa.id


def test_resolve_evidence_joins_through_motion_id_for_planning_applications(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1),
                           minutes_text="The application at Lot 1 was approved.")
    motion_id = _motion(session, meeting_id)
    app_id = _planning_app(session, motion_id)
    _evidence(session, meeting_id, "planning_applications", app_id,
              "The application at Lot 1 was approved.")

    entries = resolve_evidence(session, [("planning_applications", app_id, "application")], council_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["meeting_id"] == meeting_id
    assert entry["meeting_date"] == "2024-01-01"
    assert entry["quotes"][0]["tier"] == "exact"


# ---------------------------------------------------------------------------
# evidence_for_objection_responsiveness()
# ---------------------------------------------------------------------------

def test_objection_responsiveness_buckets_and_caps_by_objector_count(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text="text")

    # Two "5+" applications so the cap can be exercised with cap=1.
    for n_obj in (7, 6):
        motion_id = _motion(session, meeting_id, title=f"App with {n_obj} objectors")
        app_id = _planning_app(session, motion_id, status=ApplicationStatus.REFUSED)
        for i in range(n_obj):
            session.add(CommunitySubmission(application_id=app_id, position="object"))
        session.flush()

    # One "0" application, no evidence at all.
    motion_id0 = _motion(session, meeting_id, title="Uncontested app")
    _planning_app(session, motion_id0, status=ApplicationStatus.APPROVED)

    result = evidence_for_objection_responsiveness(session, council_id, cap=1)
    by_label = {b["label"]: b for b in result["buckets"]}

    assert len(by_label["5+"]["applications"]) == 1  # capped from 2 down to 1
    assert by_label["5+"]["applications"][0]["entity_table"] == "planning_applications"
    assert len(by_label["0"]["applications"]) == 1
    assert by_label["0"]["applications"][0]["tier"] == "no_evidence"
    assert by_label["1"]["applications"] == []
    assert by_label["2-4"]["applications"] == []


# ---------------------------------------------------------------------------
# evidence_for_transparency()
# ---------------------------------------------------------------------------

def test_transparency_groups_confidential_items_by_year_across_tables(session):
    council_id = _council(session)
    m2022 = _meeting(session, council_id, date(2022, 6, 1),
                      minutes_text="Road works contract awarded confidentially.")
    m2023 = _meeting(session, council_id, date(2023, 6, 1), minutes_text="text")

    tender = Tender(meeting_id=m2022, description="Road works contract", is_confidential=True)
    session.add(tender)
    session.flush()
    tender_id = tender.id
    _evidence(session, m2022, "tenders", tender_id, "Road works contract awarded confidentially.")

    budget = BudgetItem(meeting_id=m2023, description="Reserve transfer", is_confidential=True)
    session.add(budget)
    session.flush()
    # No ExtractionEvidence row for this one — must still appear, no_evidence.

    # A non-confidential tender must never appear.
    session.add(Tender(meeting_id=m2022, description="Public tender", is_confidential=False))
    session.flush()

    result = evidence_for_transparency(session, council_id)
    by_year = {y["year"]: y for y in result["years"]}

    assert set(by_year) == {2022, 2023}
    assert len(by_year[2022]["items"]) == 1
    item_2022 = by_year[2022]["items"][0]
    assert item_2022["entity_table"] == "tenders"
    assert item_2022["entity_id"] == tender_id
    assert item_2022["quotes"][0]["tier"] == "exact"

    assert len(by_year[2023]["items"]) == 1
    assert by_year[2023]["items"][0]["entity_table"] == "budget_items"
    assert by_year[2023]["items"][0]["tier"] == "no_evidence"


def test_transparency_caps_per_table_per_year_not_combined(session):
    """The cap is per (year, table) — each UNION ALL branch's own
    ROW_NUMBER() restarts at 1, so 3 confidential tenders + 3 confidential
    budget items in the same year, capped at 2, yields 2 + 2 = 4, not 2."""
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 6, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, description=f"Tender {i}", is_confidential=True))
    for i in range(3):
        session.add(BudgetItem(meeting_id=meeting_id, description=f"Budget {i}", is_confidential=True))
    session.flush()

    result = evidence_for_transparency(session, council_id, cap=2)
    by_year = {y["year"]: y for y in result["years"]}
    tables_seen = [item["entity_table"] for item in by_year[2022]["items"]]
    assert len(by_year[2022]["items"]) == 4
    assert tables_seen.count("tenders") == 2
    assert tables_seen.count("budget_items") == 2


# ---------------------------------------------------------------------------
# evidence_for_chair_capture()
# ---------------------------------------------------------------------------

def _mayor(session, council_id, given, family, term_start=None, term_end=None) -> int:
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    session.add(CouncillorTerm(
        councillor_id=c.id, council_id=council_id, role="Mayor",
        term_start=term_start, term_end=term_end,
    ))
    session.flush()
    return c.id


def test_chair_capture_caps_per_mayor_and_excludes_non_mayor_movers(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1),
                           minutes_text="MOVED that the budget be adopted. CARRIED (3/1).")
    mayor_id = _mayor(session, council_id, "Jane", "Shannon",
                       term_start=date(2020, 1, 1), term_end=None)
    backbench = Councillor(given_name="Back", family_name="Bencher", slug="back-bencher")
    session.add(backbench)
    session.flush()
    backbench_id = backbench.id  # no CouncillorTerm at all — never a mayor

    mayor_motion_id = _motion(
        session, meeting_id, title="Budget motion", item_number="1",
        outcome=MotionOutcome.CARRIED,
    )
    session.query(Motion).filter_by(id=mayor_motion_id).update({
        "moved_by_id": mayor_id, "votes_against": 1,
    })
    other_motion_id = _motion(
        session, meeting_id, title="Backbench motion", item_number="2",
        outcome=MotionOutcome.CARRIED,
    )
    session.query(Motion).filter_by(id=other_motion_id).update({
        "moved_by_id": backbench_id, "votes_against": 1,
    })
    session.flush()
    _evidence(session, meeting_id, "motions", mayor_motion_id,
              "MOVED that the budget be adopted.")

    result = evidence_for_chair_capture(session, council_id)
    assert len(result["mayors"]) == 1
    m = result["mayors"][0]
    assert m["name"] == "Jane Shannon"
    assert len(m["motions"]) == 1  # the backbench-moved motion never enters any mayor's list
    assert m["motions"][0]["entity_id"] == mayor_motion_id
    assert m["motions"][0]["quotes"][0]["tier"] == "exact"


def test_chair_capture_excludes_motions_moved_before_the_term_started(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2010, 1, 1), minutes_text="text")
    mayor_id = _mayor(session, council_id, "Old", "Mayor",
                       term_start=date(2020, 1, 1), term_end=None)  # term starts after this meeting

    motion_id = _motion(session, meeting_id, title="Pre-term motion", outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_id).update({
        "moved_by_id": mayor_id, "votes_against": 1,
    })
    session.flush()

    result = evidence_for_chair_capture(session, council_id)
    # A mayor with zero qualifying motions doesn't appear at all — unlike
    # mayoral.json's own per_mayor list (which enumerates every mayor via
    # its own aggregate query and defaults an absent drill-down to []),
    # this file is entity-driven: nothing to resolve means no entry. The
    # frontend joins by entity_id across all mayors, not by mayor name, so
    # this doesn't affect anything the panel actually looks up.
    assert result["mayors"] == []


# ---------------------------------------------------------------------------
# evidence_for_threshold_gaming() — first of the tests.<generator> group:
# no existing snapshot/drill-down to reuse, entity population built from
# scratch, generic {"buckets": [{"label", "entries"}]} shape.
# ---------------------------------------------------------------------------

def test_threshold_gaming_buckets_by_dollar_bin_and_excludes_pre_2015(session):
    council_id = _council(session)
    meeting_2022 = _meeting(session, council_id, date(2022, 1, 1),
                             minutes_text="Tender for road works awarded, amount $220,000.")
    meeting_2010 = _meeting(session, council_id, date(2010, 1, 1), minutes_text="text")

    tender_in_bin = Tender(meeting_id=meeting_2022, amount=220_000,
                            description="Road works")
    session.add(tender_in_bin)
    session.flush()
    _evidence(session, meeting_2022, "tenders", tender_in_bin.id,
              "Tender for road works awarded, amount $220,000.")

    # Same $-range but before 2015 — must be excluded entirely.
    pre_2015 = Tender(meeting_id=meeting_2010, amount=220_000, description="Old tender")
    session.add(pre_2015)
    session.flush()

    result = evidence_for_threshold_gaming(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    assert len(by_label["200–250k"]["entries"]) == 1
    entry = by_label["200–250k"]["entries"][0]
    assert entry["entity_table"] == "tenders"
    assert entry["entity_id"] == tender_in_bin.id
    assert entry["quotes"][0]["tier"] == "exact"
    # No other bin picked up either tender.
    assert all(len(b["entries"]) == 0 for label, b in by_label.items() if label != "200–250k")


def test_threshold_gaming_caps_per_bin(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, amount=220_000, description=f"Tender {i}"))
    session.flush()

    result = evidence_for_threshold_gaming(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["200–250k"]["entries"]) == 2
