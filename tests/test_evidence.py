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

from src.analysis.evidence import evidence_for_officer_ratification, resolve_evidence
from src.models import Base, Council, ExtractionEvidence, Meeting, Motion, MotionOutcome
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
