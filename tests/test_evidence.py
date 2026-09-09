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
    evidence_for_attendance,
    evidence_for_big_dollar_leniency,
    evidence_for_chair_capture,
    evidence_for_confidential_tender_size,
    evidence_for_confidential_topics,
    evidence_for_decider_supplier_conflict,
    evidence_for_delegate_body_conflict,
    evidence_for_deputation_dissent,
    evidence_for_election_cycle,
    evidence_for_eoy_spending,
    evidence_for_freshman_effect,
    evidence_for_incumbency,
    evidence_for_objection_responsiveness,
    evidence_for_officer_ratification,
    evidence_for_oversight_body_capture,
    evidence_for_power_spread,
    evidence_for_question_responsiveness,
    evidence_for_recusal_management,
    evidence_for_recusal_trend,
    evidence_for_repeat_applicant,
    evidence_for_threshold_gaming,
    evidence_for_transparency,
    evidence_for_unanimity_trend,
    resolve_evidence,
)
from src.models import (
    ApplicationStatus,
    Appointment,
    Base,
    BudgetItem,
    CommunitySubmission,
    Council,
    Councillor,
    CouncillorTerm,
    DelegatedDecision,
    Deputation,
    ExtractionEvidence,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    Motion,
    MotionOutcome,
    OtherItem,
    PlanningApplication,
    PublicQuestion,
    Tender,
    Vote,
    VoteChoice,
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


# ---------------------------------------------------------------------------
# resolve_evidence(): shared source_cache across calls (the fix for
# `council draft` re-parsing the same meeting's PDF once per test)
# ---------------------------------------------------------------------------

def test_shared_source_cache_parses_a_meeting_once_across_two_calls(session, monkeypatch):
    import src.analysis.evidence as evidence_mod

    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2024, 1, 1), minutes_text="MOVED that X. CARRIED.")
    m1 = _motion(session, meeting_id, title="One")
    m2 = _motion(session, meeting_id, title="Two", item_number="2")
    _evidence(session, meeting_id, "motions", m1, "MOVED that X.")
    _evidence(session, meeting_id, "motions", m2, "MOVED that X.")

    calls = {"n": 0}
    real_build = evidence_mod._build_meeting_source

    def counting_build(meeting):
        calls["n"] += 1
        return real_build(meeting)

    monkeypatch.setattr(evidence_mod, "_build_meeting_source", counting_build)

    cache: dict = {}
    resolve_evidence(session, [("motions", m1, "minutes_motion")], council_id, cache)
    resolve_evidence(session, [("motions", m2, "minutes_motion")], council_id, cache)
    assert calls["n"] == 1  # same meeting, second call reused the shared cache

    calls["n"] = 0
    resolve_evidence(session, [("motions", m1, "minutes_motion")], council_id)
    resolve_evidence(session, [("motions", m2, "minutes_motion")], council_id)
    assert calls["n"] == 2  # no cache passed — each call builds its own, as before


# ---------------------------------------------------------------------------
# evidence_for_eoy_spending()
# ---------------------------------------------------------------------------

def test_eoy_spending_buckets_by_calendar_month_across_years(session):
    council_id = _council(session)
    meeting_dec_2022 = _meeting(session, council_id, date(2022, 12, 15),
                                 minutes_text="Tender for landscaping awarded, $80,000.")
    meeting_dec_2019 = _meeting(session, council_id, date(2019, 12, 3), minutes_text="text")
    meeting_jun = _meeting(session, council_id, date(2021, 6, 1), minutes_text="text")

    t1 = Tender(meeting_id=meeting_dec_2022, amount=80_000, description="Landscaping")
    session.add(t1)
    session.flush()
    _evidence(session, meeting_dec_2022, "tenders", t1.id,
              "Tender for landscaping awarded, $80,000.")

    t2 = Tender(meeting_id=meeting_dec_2019, amount=50_000, description="Other Dec tender")
    session.add(t2)

    t3 = Tender(meeting_id=meeting_jun, amount=30_000, description="June tender")
    session.add(t3)

    # Zero-amount tender must be excluded (matches tests._t_eoy_spending's `if a` check).
    session.add(Tender(meeting_id=meeting_jun, amount=0, description="Zero-amount"))
    session.flush()

    result = evidence_for_eoy_spending(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    assert len(by_label["Dec"]["entries"]) == 2
    assert len(by_label["Jun"]["entries"]) == 1
    assert all(len(b["entries"]) == 0 for label, b in by_label.items() if label not in ("Dec", "Jun"))

    dec_entry = next(e for e in by_label["Dec"]["entries"] if e["entity_id"] == t1.id)
    assert dec_entry["quotes"][0]["tier"] == "exact"


def test_eoy_spending_caps_per_month(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 12, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, amount=10_000 + i, description=f"Tender {i}"))
    session.flush()

    result = evidence_for_eoy_spending(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Dec"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_big_dollar_leniency()
# ---------------------------------------------------------------------------

def test_big_dollar_leniency_splits_into_equal_count_quartiles(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    app_ids = []
    for i in range(1, 21):  # 20 applications, values $10k..$200k
        motion_id = _motion(session, meeting_id, title=f"App {i}", item_number=str(i))
        app_id = _planning_app(session, motion_id, status=ApplicationStatus.APPROVED)
        session.query(PlanningApplication).filter_by(id=app_id).update(
            {"estimated_value": i * 10_000}
        )
        app_ids.append(app_id)
    session.flush()

    result = evidence_for_big_dollar_leniency(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    q1_ids = {e["entity_id"] for e in by_label["Q1 (lowest $)"]["entries"]}
    q4_ids = {e["entity_id"] for e in by_label["Q4 (highest $)"]["entries"]}
    assert q1_ids == set(app_ids[0:5])
    assert q4_ids == set(app_ids[15:20])
    # Highest value first within a bucket.
    q4_ordered = [e["entity_id"] for e in by_label["Q4 (highest $)"]["entries"]]
    assert q4_ordered == list(reversed(app_ids[15:20]))


def test_big_dollar_leniency_below_n20_floor_returns_empty_buckets(session):
    """Matches tests._t_big_dollar_leniency's own len(vals) < 20 floor — the
    real chart reports "not computable" below it, so there's nothing a
    click could ever reach; empty buckets, not a guessed quartile split."""
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(5):
        motion_id = _motion(session, meeting_id, title=f"App {i}", item_number=str(i))
        app_id = _planning_app(session, motion_id, status=ApplicationStatus.APPROVED)
        session.query(PlanningApplication).filter_by(id=app_id).update({"estimated_value": 50_000})
    session.flush()

    result = evidence_for_big_dollar_leniency(session, council_id)
    assert all(len(b["entries"]) == 0 for b in result["buckets"])


# ---------------------------------------------------------------------------
# evidence_for_repeat_applicant()
# ---------------------------------------------------------------------------

def _applicant_apps(session, meeting_id, name, n, status=ApplicationStatus.APPROVED, start_item=1):
    ids = []
    for i in range(n):
        motion_id = _motion(session, meeting_id, title=f"{name} app {i}", item_number=str(start_item + i))
        app_id = _planning_app(session, motion_id, status=status)
        session.query(PlanningApplication).filter_by(id=app_id).update({"applicant_name": name})
        ids.append(app_id)
    session.flush()
    return ids


def test_repeat_applicant_buckets_by_normalised_name_frequency(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")

    # "Alice Smith" once, but with different case/whitespace — must count as
    # the same applicant (normalised: strip + lowercase).
    one = _applicant_apps(session, meeting_id, "Alice Smith", 1)
    two_three = _applicant_apps(session, meeting_id, "  BOB jones ", 3, start_item=10)
    four_six = _applicant_apps(session, meeting_id, "carol white", 5, start_item=20)
    seven_plus = _applicant_apps(session, meeting_id, "Dave Black", 8, start_item=30)

    result = evidence_for_repeat_applicant(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    assert {e["entity_id"] for e in by_label["1 app"]["entries"]} == set(one)
    assert {e["entity_id"] for e in by_label["2–3"]["entries"]} == set(two_three)
    assert {e["entity_id"] for e in by_label["4–6"]["entries"]} == set(four_six)
    assert {e["entity_id"] for e in by_label["7+"]["entries"]} == set(seven_plus)


def test_repeat_applicant_caps_per_bucket(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    # Two different one-shot applicants — both land in "1 app", exercising
    # the cap across applicants within the same bucket, not within one name.
    _applicant_apps(session, meeting_id, "Applicant A", 1, start_item=1)
    _applicant_apps(session, meeting_id, "Applicant B", 1, start_item=2)

    result = evidence_for_repeat_applicant(session, council_id, cap=1)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["1 app"]["entries"]) == 1


# ---------------------------------------------------------------------------
# evidence_for_unanimity_trend() — first line-chart test in this group:
# bucket label is a year string (String(p.payload.x) on the frontend), not
# a chart bar label.
# ---------------------------------------------------------------------------

def _carried_motions_in_year(session, council_id, year, n, contested_n=0):
    """n CARRIED motions dated within `year`; the first contested_n have
    votes_against=1, the rest 0. Returns the contested motions' ids."""
    meeting_id = _meeting(session, council_id, date(year, 6, 1), minutes_text="text")
    contested_ids = []
    for i in range(n):
        motion_id = _motion(
            session, meeting_id, title=f"Motion {year}-{i}", item_number=str(i),
            outcome=MotionOutcome.CARRIED,
        )
        va = 1 if i < contested_n else 0
        session.query(Motion).filter_by(id=motion_id).update({"votes_against": va})
        if va:
            contested_ids.append(motion_id)
    session.flush()
    return contested_ids


def test_unanimity_trend_only_plots_years_with_at_least_30_carried_motions(session):
    council_id = _council(session)
    contested_2020 = _carried_motions_in_year(session, council_id, 2020, n=35, contested_n=3)
    _carried_motions_in_year(session, council_id, 2010, n=10, contested_n=2)  # below the 30 floor

    result = evidence_for_unanimity_trend(session, council_id)
    labels = [b["label"] for b in result["buckets"]]
    assert labels == ["2020"]  # 2010 excluded entirely, not even an empty bucket

    by_label = {b["label"]: b for b in result["buckets"]}
    assert {e["entity_id"] for e in by_label["2020"]["entries"]} == set(contested_2020)


def test_unanimity_trend_plotted_year_with_no_contested_motions_gets_empty_bucket(session):
    council_id = _council(session)
    _carried_motions_in_year(session, council_id, 2021, n=30, contested_n=0)

    result = evidence_for_unanimity_trend(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert by_label["2021"]["entries"] == []


def test_unanimity_trend_caps_contested_motions_per_year(session):
    council_id = _council(session)
    _carried_motions_in_year(session, council_id, 2022, n=30, contested_n=5)

    result = evidence_for_unanimity_trend(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["2022"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_confidential_tender_size()
# ---------------------------------------------------------------------------

def test_confidential_tender_size_splits_by_flag_not_missingness(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1),
                           minutes_text="Confidential tender awarded, value $500,000.")

    conf = Tender(meeting_id=meeting_id, amount=500_000, is_confidential=True,
                  description="Confidential tender")
    session.add(conf)
    session.flush()
    _evidence(session, meeting_id, "tenders", conf.id,
              "Confidential tender awarded, value $500,000.")

    opn = Tender(meeting_id=meeting_id, amount=100_000, is_confidential=False,
                 description="Open tender")
    session.add(opn)

    # A confidential tender with NO amount must be excluded entirely — the
    # test's own docstring calls out amount-missingness as a trap to avoid,
    # never a bucket to sort into.
    session.add(Tender(meeting_id=meeting_id, amount=None, is_confidential=True,
                        description="No amount recorded"))
    session.flush()

    result = evidence_for_confidential_tender_size(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    assert {e["entity_id"] for e in by_label["Confidential"]["entries"]} == {conf.id}
    assert {e["entity_id"] for e in by_label["Open"]["entries"]} == {opn.id}
    conf_entry = by_label["Confidential"]["entries"][0]
    assert conf_entry["quotes"][0]["tier"] == "exact"


def test_confidential_tender_size_caps_per_bucket(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, amount=10_000 + i, is_confidential=True))
    session.flush()

    result = evidence_for_confidential_tender_size(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Confidential"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_confidential_topics()
# ---------------------------------------------------------------------------

def test_confidential_topics_matches_multiple_themes_and_excludes_open_items(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1),
                           minutes_text="Confidential tender for legal advice awarded.")

    multi = Tender(meeting_id=meeting_id, is_confidential=True,
                    description="Confidential tender for legal advice")
    session.add(multi)
    session.flush()
    _evidence(session, meeting_id, "tenders", multi.id,
              "Confidential tender for legal advice awarded.")

    # Open item matching "Tender/procurement" — must never appear anywhere.
    open_tender = Tender(meeting_id=meeting_id, is_confidential=False,
                          description="Open tender for road works")
    session.add(open_tender)
    session.flush()

    result = evidence_for_confidential_topics(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    # "Confidential tender for legal advice" matches Commercial-in-conf
    # ("confidential"), Tender/procurement ("tender") and Legal/litigation
    # ("legal") — appears in all three, not just one.
    for label in ("Commercial-in-conf", "Tender/procurement", "Legal/litigation"):
        ids = {e["entity_id"] for e in by_label[label]["entries"]}
        assert multi.id in ids, f"{label} missing multi.id"

    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert open_tender.id not in all_ids


def test_confidential_topics_excludes_nil_placeholder_heading(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    session.add(Tender(meeting_id=meeting_id, is_confidential=True,
                        description="Confidential Reports - Nil"))
    session.flush()

    result = evidence_for_confidential_topics(session, council_id)
    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert all_ids == set()


def test_confidential_topics_spans_three_tables(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")

    other = OtherItem(meeting_id=meeting_id, is_confidential=True,
                       item_type="Report", description="Staff recruitment matter")
    session.add(other)
    dd = DelegatedDecision(meeting_id=meeting_id, is_confidential=True,
                            description="Land acquisition settlement")
    session.add(dd)
    session.flush()

    result = evidence_for_confidential_topics(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    other_ids = {e["entity_id"] for e in by_label["Personnel/HR"]["entries"]
                 if e["entity_table"] == "other_items"}
    assert other.id in other_ids
    dd_ids = {e["entity_id"] for e in by_label["Land/property deal"]["entries"]
              if e["entity_table"] == "delegated_decisions"}
    assert dd.id in dd_ids


def test_confidential_topics_caps_per_theme(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, is_confidential=True,
                            description=f"Confidential tender {i}"))
    session.flush()

    result = evidence_for_confidential_topics(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Commercial-in-conf"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_incumbency()
# ---------------------------------------------------------------------------

def _tenders_for_firm(session, council_id, name, n_years):
    """n_years tenders for `name`, one per distinct year starting 2000."""
    ids = []
    for j in range(n_years):
        meeting_id = _meeting(session, council_id, date(2000 + j, 1, 1), minutes_text="text")
        t = Tender(meeting_id=meeting_id, awarded_to=name, amount=1000)
        session.add(t)
        session.flush()
        ids.append(t.id)
    return ids


def test_incumbency_normalises_name_variants_into_one_firm(session):
    council_id = _council(session)
    meeting_2020 = _meeting(session, council_id, date(2020, 1, 1),
                             minutes_text="Awarded to R J Vincent Pty Ltd.")
    meeting_2021 = _meeting(session, council_id, date(2021, 1, 1), minutes_text="text")

    t1 = Tender(meeting_id=meeting_2020, awarded_to="R J Vincent Pty Ltd")
    session.add(t1)
    session.flush()
    _evidence(session, meeting_2020, "tenders", t1.id, "Awarded to R J Vincent Pty Ltd.")

    t2 = Tender(meeting_id=meeting_2021, awarded_to="RJ Vincent")
    session.add(t2)
    session.flush()

    result = evidence_for_incumbency(session, council_id)
    # Both variants normalise to the same firm key "rjvincent" -> label "Rjvincent".
    by_label = {b["label"]: b for b in result["buckets"]}
    assert "Rjvincent" in by_label
    ids = {e["entity_id"] for e in by_label["Rjvincent"]["entries"]}
    assert ids == {t1.id, t2.id}
    exact_entry = next(e for e in by_label["Rjvincent"]["entries"] if e["entity_id"] == t1.id)
    assert exact_entry["quotes"][0]["tier"] == "exact"


def test_incumbency_excludes_names_containing_respondent(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    session.add(Tender(meeting_id=meeting_id, awarded_to="Respondent A"))
    session.flush()

    result = evidence_for_incumbency(session, council_id)
    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert all_ids == set()


def test_incumbency_keeps_only_top_10_by_distinct_years(session):
    council_id = _council(session)
    for i in range(1, 12):  # 11 firms, 1..11 distinct years each
        _tenders_for_firm(session, council_id, f"Firm{i}", i)

    result = evidence_for_incumbency(session, council_id)
    labels = [b["label"] for b in result["buckets"]]
    assert len(labels) == 10
    assert "Firm1" not in labels  # the least-recurring firm, excluded
    assert "Firm11" in labels    # the most-recurring, definitely included


def test_incumbency_caps_tenders_per_firm(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    for i in range(3):
        session.add(Tender(meeting_id=meeting_id, awarded_to="Acme Co"))
    session.flush()

    result = evidence_for_incumbency(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Acmeco"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_deputation_dissent() — both buckets show the same entity type
# (contested motions), split by whether the motion's meeting had a
# deputation at all, per the agreed design (avoids putting deputations on
# one side and motions on the other for the same statistic).
# ---------------------------------------------------------------------------

def test_deputation_dissent_splits_contested_motions_by_meeting_deputation(session):
    council_id = _council(session)
    meeting_with = _meeting(session, council_id, date(2022, 1, 1),
                             minutes_text="MOVED the levy be adopted. CARRIED (3/2).")
    meeting_without = _meeting(session, council_id, date(2021, 1, 1), minutes_text="text")

    session.add(Deputation(meeting_id=meeting_with, presenter_name="A Resident", topic="Traffic"))
    session.flush()

    contested_with = _motion(session, meeting_with, title="Levy motion", outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=contested_with).update({"votes_against": 2})
    _evidence(session, meeting_with, "motions", contested_with,
              "MOVED the levy be adopted.")

    contested_without = _motion(session, meeting_without, title="Other motion",
                                 outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=contested_without).update({"votes_against": 1})

    # An uncontested carried motion in the deputation meeting — must be
    # excluded from both buckets entirely, not just the "without" one.
    uncontested = _motion(session, meeting_with, title="Uncontested", item_number="2",
                           outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=uncontested).update({"votes_against": 0})
    session.flush()

    result = evidence_for_deputation_dissent(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    with_ids = {e["entity_id"] for e in by_label["With a deputation"]["entries"]}
    without_ids = {e["entity_id"] for e in by_label["Without"]["entries"]}
    assert with_ids == {contested_with}
    assert without_ids == {contested_without}
    assert uncontested not in with_ids | without_ids

    with_entry = by_label["With a deputation"]["entries"][0]
    assert with_entry["quotes"][0]["tier"] == "exact"


def test_deputation_dissent_caps_per_bucket(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        motion_id = _motion(session, meeting_id, title=f"Motion {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.query(Motion).filter_by(id=motion_id).update({"votes_against": 1})
    session.flush()

    result = evidence_for_deputation_dissent(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Without"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_freshman_effect() — votes have no quote of their own; the
# receipt is always the parent motion (same design PowerPanel already uses).
# ---------------------------------------------------------------------------

def _councillor(session, given, family) -> int:
    p = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(p)
    session.flush()
    return p.id


def test_freshman_effect_allows_the_same_motion_in_both_buckets(session):
    council_id = _council(session)
    freshman_id = _councillor(session, "New", "Member")
    veteran_id = _councillor(session, "Old", "Hand")

    # New Member's first-ever vote is this one -> days=0 -> "First 12 months".
    meeting_shared = _meeting(session, council_id, date(2020, 1, 1),
                               minutes_text="MOVED the budget be adopted. CARRIED (3/2).")
    motion_shared = _motion(session, meeting_shared, title="Budget motion",
                             outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_shared, councillor_id=freshman_id, choice=VoteChoice.AGAINST))
    _evidence(session, meeting_shared, "motions", motion_shared, "MOVED the budget be adopted.")

    # Old Hand's first vote was a decade earlier (FOR, on an unrelated
    # motion) — this AGAINST vote is >365 days later -> "Later service".
    meeting_old_first = _meeting(session, council_id, date(2010, 1, 1), minutes_text="text")
    old_first_motion = _motion(session, meeting_old_first, title="Old first motion",
                                item_number="99", outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=old_first_motion, councillor_id=veteran_id, choice=VoteChoice.FOR))
    session.add(Vote(motion_id=motion_shared, councillor_id=veteran_id, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_freshman_effect(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    early_ids = {e["entity_id"] for e in by_label["First 12 months"]["entries"]}
    late_ids = {e["entity_id"] for e in by_label["Later service"]["entries"]}
    # Dissented on by both a freshman and a veteran -> genuinely in both.
    assert motion_shared in early_ids
    assert motion_shared in late_ids
    # Only a FOR vote was ever cast on this one -> never appears anywhere.
    assert old_first_motion not in early_ids | late_ids

    early_entry = next(e for e in by_label["First 12 months"]["entries"] if e["entity_id"] == motion_shared)
    assert early_entry["quotes"][0]["tier"] == "exact"


def test_freshman_effect_dedupes_same_motion_within_one_bucket(session):
    council_id = _council(session)
    cllr_a = _councillor(session, "A", "Freshman")
    cllr_b = _councillor(session, "B", "Freshman")
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_a, choice=VoteChoice.AGAINST))
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_b, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_freshman_effect(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    early_ids = [e["entity_id"] for e in by_label["First 12 months"]["entries"]]
    assert early_ids.count(motion_id) == 1


def test_freshman_effect_ignores_for_votes(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "New", "Member")
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_freshman_effect(session, council_id)
    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert all_ids == set()


def test_freshman_effect_caps_per_bucket(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "New", "Member")
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        motion_id = _motion(session, meeting_id, title=f"Motion {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_freshman_effect(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["First 12 months"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_election_cycle() — same votes-have-no-quote design as
# freshman_effect, but the window is a pure function of the meeting date,
# so a motion can only ever land in one bucket.
# ---------------------------------------------------------------------------

def test_election_cycle_classifies_by_pre_election_window(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "A", "Councillor")

    # 2023 (odd year), June (in Apr-Oct) -> pre-election window.
    meeting_in_window = _meeting(session, council_id, date(2023, 6, 1),
                                  minutes_text="MOVED the plan be adopted. CARRIED (3/2).")
    motion_in_window = _motion(session, meeting_in_window, title="Plan motion",
                                outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_in_window, councillor_id=cllr_id, choice=VoteChoice.AGAINST))
    _evidence(session, meeting_in_window, "motions", motion_in_window,
              "MOVED the plan be adopted.")

    # 2022 (even year) -> outside the window regardless of month.
    meeting_even_year = _meeting(session, council_id, date(2022, 6, 1), minutes_text="text")
    motion_even_year = _motion(session, meeting_even_year, title="Even year motion",
                                item_number="2", outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_even_year, councillor_id=cllr_id, choice=VoteChoice.AGAINST))

    # 2023 (odd year) but December -> outside Apr-Oct, so outside the window.
    meeting_odd_dec = _meeting(session, council_id, date(2023, 12, 1), minutes_text="text")
    motion_odd_dec = _motion(session, meeting_odd_dec, title="December motion",
                              item_number="3", outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_odd_dec, councillor_id=cllr_id, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_election_cycle(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    window_ids = {e["entity_id"] for e in by_label["Pre-election (Apr–Oct odd yr)"]["entries"]}
    rest_ids = {e["entity_id"] for e in by_label["Rest of cycle"]["entries"]}
    assert window_ids == {motion_in_window}
    assert rest_ids == {motion_even_year, motion_odd_dec}

    window_entry = by_label["Pre-election (Apr–Oct odd yr)"]["entries"][0]
    assert window_entry["quotes"][0]["tier"] == "exact"


def test_election_cycle_ignores_for_votes(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "A", "Councillor")
    meeting_id = _meeting(session, council_id, date(2023, 6, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_election_cycle(session, council_id)
    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert all_ids == set()


def test_election_cycle_dedupes_same_motion_within_one_bucket(session):
    council_id = _council(session)
    cllr_a = _councillor(session, "A", "One")
    cllr_b = _councillor(session, "B", "Two")
    meeting_id = _meeting(session, council_id, date(2023, 6, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_a, choice=VoteChoice.AGAINST))
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_b, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_election_cycle(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    window_ids = [e["entity_id"] for e in by_label["Pre-election (Apr–Oct odd yr)"]["entries"]]
    assert window_ids.count(motion_id) == 1


def test_election_cycle_caps_per_bucket(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "A", "Councillor")
    meeting_id = _meeting(session, council_id, date(2023, 6, 1), minutes_text="text")
    for i in range(3):
        motion_id = _motion(session, meeting_id, title=f"Motion {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.AGAINST))
    session.flush()

    result = evidence_for_election_cycle(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Pre-election (Apr–Oct odd yr)"]["entries"]) == 2


# ---------------------------------------------------------------------------
# evidence_for_attendance() — last of the tests.<generator> batch. Same
# motion-as-receipt design; no CARRIED-only filter (the real test has none);
# ABSENT rows split by declared_interest, not a time-based bucket.
# ---------------------------------------------------------------------------

def test_attendance_splits_absent_votes_by_declared_interest(session):
    council_id = _council(session)
    recused_cllr = _councillor(session, "Recused", "Councillor")
    absent_cllr = _councillor(session, "Genuinely", "Absent")

    # LOST outcome (not CARRIED) — the real test has no outcome filter at
    # all, so this must still count.
    meeting_id = _meeting(session, council_id, date(2022, 1, 1),
                           minutes_text="MOVED the rezoning be approved. LOST.")
    motion_recusal = _motion(session, meeting_id, title="Rezoning motion",
                              outcome=MotionOutcome.LOST)
    session.add(Vote(motion_id=motion_recusal, councillor_id=recused_cllr,
                      choice=VoteChoice.ABSENT, declared_interest=True))
    _evidence(session, meeting_id, "motions", motion_recusal, "MOVED the rezoning be approved.")

    motion_genuine = _motion(session, meeting_id, title="Other motion", item_number="2",
                              outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_genuine, councillor_id=absent_cllr,
                      choice=VoteChoice.ABSENT, declared_interest=False))

    # A FOR vote must never appear in either bucket.
    for_only_motion = _motion(session, meeting_id, title="For only", item_number="3",
                               outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=for_only_motion, councillor_id=recused_cllr, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_attendance(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}

    recusal_ids = {e["entity_id"] for e in by_label["Recusal (declared)"]["entries"]}
    genuine_ids = {e["entity_id"] for e in by_label["Genuine absence"]["entries"]}
    assert recusal_ids == {motion_recusal}
    assert genuine_ids == {motion_genuine}
    assert for_only_motion not in recusal_ids | genuine_ids

    recusal_entry = by_label["Recusal (declared)"]["entries"][0]
    assert recusal_entry["quotes"][0]["tier"] == "exact"


def test_attendance_allows_the_same_motion_in_both_buckets(session):
    council_id = _council(session)
    recused_cllr = _councillor(session, "Recused", "One")
    absent_cllr = _councillor(session, "Genuine", "Two")
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=recused_cllr,
                      choice=VoteChoice.ABSENT, declared_interest=True))
    session.add(Vote(motion_id=motion_id, councillor_id=absent_cllr,
                      choice=VoteChoice.ABSENT, declared_interest=False))
    session.flush()

    result = evidence_for_attendance(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id in {e["entity_id"] for e in by_label["Recusal (declared)"]["entries"]}
    assert motion_id in {e["entity_id"] for e in by_label["Genuine absence"]["entries"]}


def test_attendance_caps_per_bucket(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Genuine", "Absent")
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    for i in range(3):
        motion_id = _motion(session, meeting_id, title=f"Motion {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id,
                          choice=VoteChoice.ABSENT, declared_interest=False))
    session.flush()

    result = evidence_for_attendance(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert len(by_label["Genuine absence"]["entries"]) == 2


def test_decider_supplier_conflict_matches_tender_title_keyword(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    tender_motion = _motion(session, meeting_id, title="Tender for road works")
    _evidence(session, meeting_id, "motions", tender_motion, "text")
    other_motion = _motion(session, meeting_id, title="Approve the minutes", item_number="2")
    session.flush()

    result = evidence_for_decider_supplier_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    ids = {e["entity_id"] for e in by_label["Tender-award votes"]["entries"]}
    assert ids == {tender_motion}
    assert other_motion not in ids
    # No natural "notable subset" of the whole-corpus baseline — left empty
    # rather than fabricated, see evidence_for_decider_supplier_conflict().
    assert by_label["Chamber base rate"]["entries"] == []


def test_decider_supplier_conflict_matches_motion_text_keyword_too(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1), minutes_text="text")
    motion_id = _motion(
        session, meeting_id, title="Item 4",
        motion_text="Council awards the contract to Acme Pty Ltd",
    )
    session.flush()

    result = evidence_for_decider_supplier_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id in {e["entity_id"] for e in by_label["Tender-award votes"]["entries"]}


def test_decider_supplier_conflict_excludes_agenda_documents(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2022, 1, 1),
                           document_type="agenda", minutes_text="text")
    motion_id = _motion(session, meeting_id, title="Tender for cleaning services")
    session.flush()

    result = evidence_for_decider_supplier_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id not in {e["entity_id"] for e in by_label["Tender-award votes"]["entries"]}


def test_decider_supplier_conflict_caps_and_orders_newest_first(session):
    council_id = _council(session)
    ids_by_year = {}
    for i, yr in enumerate([2019, 2021, 2020]):
        meeting_id = _meeting(session, council_id, date(yr, 1, 1), minutes_text="text")
        motion_id = _motion(session, meeting_id, title=f"Tender {i}", item_number=str(i))
        ids_by_year[yr] = motion_id
    session.flush()

    result = evidence_for_decider_supplier_conflict(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    entries = by_label["Tender-award votes"]["entries"]
    assert len(entries) == 2
    expected_newest_two = {ids_by_year[2021], ids_by_year[2020]}
    assert {e["entity_id"] for e in entries} == expected_newest_two


def test_delegate_body_conflict_only_affiliated_votes_included(session):
    council_id = _council(session)
    cllr_aff = _councillor(session, "Aff", "Iliate")
    cllr_other = _councillor(session, "Other", "Councillor")

    meeting_appt = _meeting(session, council_id, date(2019, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=cllr_aff,
                             body_name="Mindarie Regional Council"))

    meeting_vote = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_vote, title="Mindarie Regional Council Annual Report",
                         outcome=MotionOutcome.CARRIED)
    _evidence(session, meeting_vote, "motions", motion_id, "text")
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_aff,
                      choice=VoteChoice.FOR, declared_interest=True))
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_other,
                      choice=VoteChoice.FOR, declared_interest=False))
    session.flush()

    result = evidence_for_delegate_body_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert {e["entity_id"] for e in by_label["Mindarie Regional Council"]["entries"]} == {motion_id}
    # Buckets for un-triggered bodies still appear, just empty.
    assert by_label["Tamala Park Regional Council"]["entries"] == []
    assert by_label["Ocean Gardens (Inc) Board of Management"]["entries"] == []


def test_delegate_body_conflict_excludes_votes_outside_the_tenure_window(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Later", "Appointee")

    # Vote cast BEFORE the appointment even happened -> outside any window.
    meeting_vote = _meeting(session, council_id, date(2015, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_vote, title="Mindarie Regional Council matter")
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))

    meeting_appt = _meeting(session, council_id, date(2019, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=cllr_id,
                             body_name="Mindarie Regional Council"))
    session.flush()

    result = evidence_for_delegate_body_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id not in {e["entity_id"] for e in by_label["Mindarie Regional Council"]["entries"]}


def test_delegate_body_conflict_appt_exclude_keyword_is_honoured(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Working", "Group")

    # "Working Group" is a distinct sub-body per _DELEGATE_BODIES' own
    # appt_exclude — must not count as a Mindarie plenary appointment.
    meeting_appt = _meeting(session, council_id, date(2018, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=cllr_id,
                             body_name="Mindarie Regional Council Working Group"))

    meeting_vote = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_vote, title="Mindarie Regional Council report")
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_delegate_body_conflict(session, council_id)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id not in {e["entity_id"] for e in by_label["Mindarie Regional Council"]["entries"]}


def test_delegate_body_conflict_caps_and_orders_newest_first(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Repeat", "Appointee")
    meeting_appt = _meeting(session, council_id, date(2018, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=cllr_id,
                             body_name="Tamala Park Regional Council"))

    ids_by_year = {}
    for yr in (2019, 2021, 2020):
        meeting_vote = _meeting(session, council_id, date(yr, 1, 1), minutes_text="text")
        motion_id = _motion(session, meeting_vote, title=f"Tamala Park Regional Council item {yr}")
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
        ids_by_year[yr] = motion_id
    session.flush()

    result = evidence_for_delegate_body_conflict(session, council_id, cap=2)
    by_label = {b["label"]: b for b in result["buckets"]}
    entries = by_label["Tamala Park Regional Council"]["entries"]
    assert len(entries) == 2
    expected_newest_two = {ids_by_year[2021], ids_by_year[2020]}
    assert {e["entity_id"] for e in entries} == expected_newest_two


def test_oversight_body_capture_splits_by_audit_appointment(session):
    council_id = _council(session)
    appointee_cllr = _councillor(session, "Audit", "Member")
    other_cllr = _councillor(session, "Regular", "Member")

    meeting_appt = _meeting(session, council_id, date(2019, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=appointee_cllr,
                             body_name="Audit Committee"))

    meeting_vote = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    motion_app = _motion(session, meeting_vote, title="Contested motion A",
                          outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_app).update({"votes_against": 1})
    session.add(Vote(motion_id=motion_app, councillor_id=appointee_cllr, choice=VoteChoice.FOR))
    _evidence(session, meeting_vote, "motions", motion_app, "text")

    motion_non = _motion(session, meeting_vote, title="Contested motion B", item_number="2",
                          outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_non).update({"votes_against": 1})
    session.add(Vote(motion_id=motion_non, councillor_id=other_cllr, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_oversight_body_capture(session, council_id, min_votes=1)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert {e["entity_id"] for e in by_label["Appointees"]["entries"]} == {motion_app}
    assert {e["entity_id"] for e in by_label["Non-appointees"]["entries"]} == {motion_non}


def test_oversight_body_capture_ceo_keyword_requires_performance_too(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Partial", "Match")

    # "ceo" alone (no "performance") must NOT count as an appointee match.
    meeting_appt = _meeting(session, council_id, date(2019, 1, 1), minutes_text="text")
    session.add(Appointment(meeting_id=meeting_appt, councillor_id=cllr_id,
                             body_name="CEO Recruitment Panel"))

    meeting_vote = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_vote, title="Contested", outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_id).update({"votes_against": 1})
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_oversight_body_capture(session, council_id, min_votes=1)
    by_label = {b["label"]: b for b in result["buckets"]}
    assert motion_id in {e["entity_id"] for e in by_label["Non-appointees"]["entries"]}
    assert motion_id not in {e["entity_id"] for e in by_label["Appointees"]["entries"]}


def test_oversight_body_capture_excludes_below_cohort_floor_and_uncontested(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Contested", "Only")
    meeting_vote = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")

    # No votes_against set (None) -> uncontested -> excluded regardless of cohort.
    uncontested = _motion(session, meeting_vote, title="Uncontested", outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=uncontested, councillor_id=cllr_id, choice=VoteChoice.FOR))

    contested = _motion(session, meeting_vote, title="Contested", item_number="2",
                         outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=contested).update({"votes_against": 1})
    session.add(Vote(motion_id=contested, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    # min_votes=2 but this councillor only has 1 contested vote -> below cohort floor.
    result = evidence_for_oversight_body_capture(session, council_id, min_votes=2)
    all_ids = {e["entity_id"] for b in result["buckets"] for e in b["entries"]}
    assert uncontested not in all_ids
    assert contested not in all_ids


def test_oversight_body_capture_caps_and_orders_newest_first(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Prolific", "Voter")
    ids_by_year = {}
    for yr in (2019, 2021, 2020):
        meeting_vote = _meeting(session, council_id, date(yr, 1, 1), minutes_text="text")
        motion_id = _motion(session, meeting_vote, title=f"Contested {yr}", outcome=MotionOutcome.CARRIED)
        session.query(Motion).filter_by(id=motion_id).update({"votes_against": 1})
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
        ids_by_year[yr] = motion_id
    session.flush()

    result = evidence_for_oversight_body_capture(session, council_id, cap=2, min_votes=1)
    by_label = {b["label"]: b for b in result["buckets"]}
    entries = by_label["Non-appointees"]["entries"]
    assert len(entries) == 2
    expected_newest_two = {ids_by_year[2021], ids_by_year[2020]}
    assert {e["entity_id"] for e in entries} == expected_newest_two


def test_recusal_management_resolves_matched_declarations(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Declares", "Often")
    decl_ids = []
    # conflict_recusal_stats()'s own min_declared=8 cohort floor (matching
    # declared.json's call in src/cli.py) -> need >= 8 declared votes.
    for i in range(8):
        text = "Cr Declares Often declared a financial interest in Item 0." if i == 0 else "text"
        meeting_id = _meeting(session, council_id, date(2020, 1, i + 1), minutes_text=text)
        motion_id = _motion(session, meeting_id, title=f"Item {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id,
                          choice=VoteChoice.FOR, declared_interest=True))
        decl = InterestDeclaration(meeting_id=meeting_id, councillor_id=cllr_id,
                                    interest_type=InterestDeclarationType.FINANCIAL,
                                    description="Owns property nearby", item_reference=str(i))
        session.add(decl)
        session.flush()
        decl_ids.append(decl.id)
        if i == 0:
            _evidence(session, meeting_id, "interest_declarations", decl.id,
                      "Cr Declares Often declared a financial interest in Item 0.")
    session.flush()

    result = evidence_for_recusal_management(session, council_id)
    ids = {e["entity_id"] for e in result["entries"]}
    # Every declared vote here has a matched declaration -> all resolve, even
    # the 7 with zero ExtractionEvidence rows (never dropped, B.5).
    assert set(decl_ids) == ids
    entry0 = next(e for e in result["entries"] if e["entity_id"] == decl_ids[0])
    assert entry0["quotes"][0]["tier"] == "exact"


def test_recusal_management_skips_votes_with_no_matched_declaration(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Partial", "Match")
    for i in range(7):
        meeting_id = _meeting(session, council_id, date(2020, 1, i + 1), minutes_text="text")
        motion_id = _motion(session, meeting_id, title=f"Item {i}", item_number=str(i),
                             outcome=MotionOutcome.CARRIED)
        session.add(Vote(motion_id=motion_id, councillor_id=cllr_id,
                          choice=VoteChoice.FOR, declared_interest=True))
        session.add(InterestDeclaration(meeting_id=meeting_id, councillor_id=cllr_id,
                                         interest_type=InterestDeclarationType.FINANCIAL,
                                         description="d", item_reference=str(i)))
    # 8th declared vote has no InterestDeclaration whose item_reference
    # matches this motion's item_number -> DeclarationDetail.entity_id is
    # None -> nothing for this mechanism to resolve (panel falls back to
    # the vote's own interest_description, not an ExtractionEvidence quote).
    meeting_id = _meeting(session, council_id, date(2020, 2, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, title="Unmatched item", item_number="unmatched",
                         outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR,
                      declared_interest=True, interest_description="Some interest"))
    session.flush()

    result = evidence_for_recusal_management(session, council_id)
    assert len(result["entries"]) == 7


def test_recusal_trend_resolves_matched_declarations(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Financial", "Interest")
    quote_text = "Cr Financial Interest declared a financial interest and left the meeting."
    meeting_id = _meeting(session, council_id, date(2020, 3, 1), minutes_text=quote_text)
    motion_id = _motion(session, meeting_id, title="Item 1", item_number="1",
                         outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id,
                      choice=VoteChoice.ABSENT, declared_interest=True))
    decl = InterestDeclaration(meeting_id=meeting_id, councillor_id=cllr_id,
                                interest_type=InterestDeclarationType.FINANCIAL,
                                description="Owns nearby land", item_reference="1")
    session.add(decl)
    session.flush()
    _evidence(session, meeting_id, "interest_declarations", decl.id, quote_text)
    session.flush()

    result = evidence_for_recusal_trend(session, council_id)
    ids = {e["entity_id"] for e in result["entries"]}
    assert decl.id in ids
    entry = next(e for e in result["entries"] if e["entity_id"] == decl.id)
    assert entry["quotes"][0]["tier"] == "exact"


def test_recusal_trend_skips_votes_with_no_matched_declaration(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "No", "Match")
    meeting_id = _meeting(session, council_id, date(2020, 3, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, title="Unmatched item", item_number="unmatched",
                         outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR,
                      declared_interest=True, interest_description="Some interest"))
    session.flush()

    result = evidence_for_recusal_trend(session, council_id)
    assert result["entries"] == []


def test_power_spread_resolves_matched_motions(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Contested", "Voter")
    quote_text = "MOVED that the application be approved. CARRIED (5/2)."
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text=quote_text)
    motion_id = _motion(session, meeting_id, title="Item 1", outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_id).update({"votes_against": 2, "votes_for": 5})
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    _evidence(session, meeting_id, "motions", motion_id, quote_text)
    session.flush()

    result = evidence_for_power_spread(session, council_id, min_votes=1, min_dissents=1)
    ids = {e["entity_id"] for e in result["entries"]}
    assert motion_id in ids
    entry = next(e for e in result["entries"] if e["entity_id"] == motion_id)
    assert entry["quotes"][0]["tier"] == "exact"


def test_power_spread_excludes_below_cohort_floor(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Below", "Floor")
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    motion_id = _motion(session, meeting_id, title="Item 1", outcome=MotionOutcome.CARRIED)
    session.query(Motion).filter_by(id=motion_id).update({"votes_against": 1})
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    # min_votes=2 but this councillor only has 1 contested vote -> excluded
    # from `profiles` entirely (voting_power()'s own cohort floor), so its
    # motion never reaches this builder's resolve at all.
    result = evidence_for_power_spread(session, council_id, min_votes=2, min_dissents=1)
    assert result["entries"] == []


def test_power_spread_excludes_uncontested_motions(session):
    council_id = _council(session)
    cllr_id = _councillor(session, "Uncontested", "Voter")
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    # votes_against left unset (None) -> uncontested, per voting_power()'s
    # own Motion.votes_against > 0 filter.
    motion_id = _motion(session, meeting_id, title="Item 1", outcome=MotionOutcome.CARRIED)
    session.add(Vote(motion_id=motion_id, councillor_id=cllr_id, choice=VoteChoice.FOR))
    session.flush()

    result = evidence_for_power_spread(session, council_id, min_votes=1, min_dissents=1)
    assert result["entries"] == []


def test_question_responsiveness_resolves_on_notice_and_answered(session):
    council_id = _council(session)
    on_notice_text = "This question has been taken on notice."
    meeting_on = _meeting(session, council_id, date(2020, 1, 1), minutes_text=on_notice_text)
    pq_on = PublicQuestion(meeting_id=meeting_on, questioner_name="A Resident",
                            question_summary="When will the road be fixed?",
                            response_summary=on_notice_text)
    session.add(pq_on)

    answered_text = "The Manager advised the works are complete."
    meeting_ans = _meeting(session, council_id, date(2020, 2, 1), minutes_text=answered_text)
    pq_ans = PublicQuestion(meeting_id=meeting_ans, questioner_name="Another Resident",
                             question_summary="Is the park open?",
                             response_summary=answered_text)
    session.add(pq_ans)
    session.flush()
    _evidence(session, meeting_on, "public_questions", pq_on.id, on_notice_text)
    _evidence(session, meeting_ans, "public_questions", pq_ans.id, answered_text)
    session.flush()

    result = evidence_for_question_responsiveness(session, council_id)
    ids = {e["entity_id"] for e in result["entries"]}
    assert {pq_on.id, pq_ans.id} <= ids
    on_entry = next(e for e in result["entries"] if e["entity_id"] == pq_on.id)
    assert on_entry["quotes"][0]["tier"] == "exact"


def test_question_responsiveness_excludes_blank_responses(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2020, 1, 1), minutes_text="text")
    pq_blank = PublicQuestion(meeting_id=meeting_id, questioner_name="Resident",
                               question_summary="Unanswered?", response_summary="")
    session.add(pq_blank)
    session.flush()

    result = evidence_for_question_responsiveness(session, council_id)
    assert pq_blank.id not in {e["entity_id"] for e in result["entries"]}
