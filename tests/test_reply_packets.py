"""
Unit tests for src/reply_packets.py — S9 right-of-reply packet assembly:
  - assemble_reply_packets() grouping by named person, scoping to
    unit=individual claims with no reply on file, one claim naming two
    people appearing in both packets
  - render_packet_template() content
  - attach_reply() / non_response_text()
  - load_response_window_days() reading the real config

All plain TestResult objects and plain data — no DB, no CLI invocation.
"""
import json

import pytest

from src.analysis.tests import (
    ENTITY_RESOLUTION_CLEAN,
    SUPPORTIVE,
    G_SOUND,
    TestResult,
    UNIT_INDIVIDUAL,
    UNIT_INDIVIDUAL_IMPLICATING,
    UNIT_INSTITUTIONAL,
)
from src.reply_packets import (
    DECLINED_TEXT,
    NO_RESPONSE_TEXT,
    assemble_reply_packets,
    attach_reply,
    load_response_window_days,
    load_sent_ledger,
    non_response_text,
    person_slug,
    render_packet_template,
    update_sent_ledger,
)


def _claim(**overrides) -> TestResult:
    fields = dict(
        test_id="fixture.claim",
        title="Fixture claim",
        genre="Fixture",
        principle="—",
        question="—",
        valence=SUPPORTIVE,
        grade=G_SOUND,
        headline="headline",
        verdict="verdict",
        n=25,
        base_rate="10% baseline",
        era="2020-2026",
    )
    fields.update(overrides)
    return TestResult(**fields)


# ---------------------------------------------------------------------------
# assemble_reply_packets
# ---------------------------------------------------------------------------

def test_no_individual_claims_gives_zero_packets():
    battery = [_claim(unit_of_analysis=UNIT_INSTITUTIONAL)]
    assert assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z") == []


def test_individual_claim_produces_one_packet_for_its_named_person():
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    packets = assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z")
    assert len(packets) == 1
    assert packets[0].person == "Jane Citizen"
    assert len(packets[0].claims) == 1


def test_claim_naming_two_people_appears_in_both_packets():
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen", "John Resident"],
    )]
    packets = assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z")
    people = {p.person for p in packets}
    assert people == {"Jane Citizen", "John Resident"}
    assert all(len(p.claims) == 1 for p in packets)


def test_individual_implicating_claim_is_out_of_scope():
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING,
        named_entities=["Jane Citizen"],
    )]
    assert assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z") == []


def test_claim_with_reply_already_on_file_is_excluded():
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        reply={"sent_at": "2026-08-01T00:00:00Z", "response": None, "declined": False},
    )]
    assert assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z") == []


def test_two_qualifying_claims_for_the_same_person_share_one_packet():
    battery = [
        _claim(test_id="a", unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Jane Citizen"]),
        _claim(test_id="b", unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Jane Citizen"]),
    ]
    packets = assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z")
    assert len(packets) == 1
    assert len(packets[0].claims) == 2


def test_packets_sorted_by_person_name():
    battery = [
        _claim(test_id="a", unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Zoe Zephyr"]),
        _claim(test_id="b", unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Amy Alpha"]),
    ]
    packets = assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z")
    assert [p.person for p in packets] == ["Amy Alpha", "Zoe Zephyr"]


# ---------------------------------------------------------------------------
# render_packet_template
# ---------------------------------------------------------------------------

def test_render_packet_template_includes_person_claims_and_window():
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        title="A named claim",
        headline="the headline",
    )]
    packet = assemble_reply_packets(battery, 14, "2026-08-23T00:00:00Z")[0]
    text = render_packet_template(packet)
    assert "Jane Citizen" in text
    assert "14 days" in text
    assert "A named claim" in text
    assert "the headline" in text
    assert NO_RESPONSE_TEXT in text


# ---------------------------------------------------------------------------
# attach_reply / non_response_text
# ---------------------------------------------------------------------------

def test_attach_reply_returns_new_claim_without_mutating_original():
    original = _claim(unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Jane Citizen"])
    updated = attach_reply(original, sent_at="2026-08-23T00:00:00Z", declined=True)
    assert original.reply is None
    assert updated.reply == {"sent_at": "2026-08-23T00:00:00Z", "response": None, "declined": True}


def test_non_response_text_none_before_packet_sent():
    claim = _claim(unit_of_analysis=UNIT_INDIVIDUAL, named_entities=["Jane Citizen"])
    assert non_response_text(claim) is None


def test_non_response_text_declined():
    claim = attach_reply(
        _claim(unit_of_analysis=UNIT_INDIVIDUAL), sent_at="2026-08-23T00:00:00Z", declined=True,
    )
    assert non_response_text(claim) == DECLINED_TEXT


def test_non_response_text_no_response():
    claim = attach_reply(_claim(unit_of_analysis=UNIT_INDIVIDUAL), sent_at="2026-08-23T00:00:00Z")
    assert non_response_text(claim) == NO_RESPONSE_TEXT


def test_non_response_text_none_when_response_given():
    claim = attach_reply(
        _claim(unit_of_analysis=UNIT_INDIVIDUAL), sent_at="2026-08-23T00:00:00Z",
        response="This is inaccurate because...",
    )
    assert non_response_text(claim) is None


# ---------------------------------------------------------------------------
# load_response_window_days
# ---------------------------------------------------------------------------

def test_load_response_window_days_reads_real_config():
    assert load_response_window_days() == 14


def test_load_response_window_days_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_response_window_days(tmp_path / "does_not_exist.json")


def test_load_response_window_days_rejects_non_positive(tmp_path):
    path = tmp_path / "reply_policy.json"
    path.write_text(json.dumps({"response_window_days": 0}))
    with pytest.raises(ValueError):
        load_response_window_days(path)


# ---------------------------------------------------------------------------
# the sent ledger — dedup across runs (the filter that could never fire)
# ---------------------------------------------------------------------------

def test_ledger_suppresses_a_claim_the_person_was_already_approached_about():
    battery = [_claim(
        test_id="conflict.recusal",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Ada Fixture"],
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    ledger = {"Ada Fixture": ["conflict.recusal"]}
    assert assemble_reply_packets(battery, 14, "2026-08-24T00:00:00Z", ledger) == []


def test_ledger_still_emits_a_claim_that_person_has_not_seen():
    battery = [_claim(
        test_id="procurement.concentration",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Ada Fixture"],
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    ledger = {"Ada Fixture": ["conflict.recusal"]}
    packets = assemble_reply_packets(battery, 14, "2026-08-24T00:00:00Z", ledger)
    assert [p.person for p in packets] == ["Ada Fixture"]


def test_update_sent_ledger_accumulates_without_duplicating():
    battery = [_claim(
        test_id="conflict.recusal",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Ada Fixture"],
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    packets = assemble_reply_packets(battery, 14, "2026-08-24T00:00:00Z")
    first = update_sent_ledger({}, packets)
    assert first == {"Ada Fixture": ["conflict.recusal"]}
    # Folding the same packets in again must not double up.
    assert update_sent_ledger(first, packets) == first


def test_load_sent_ledger_missing_file_is_empty(tmp_path):
    assert load_sent_ledger(tmp_path / "sent_ledger.json") == {}


# ---------------------------------------------------------------------------
# person_slug — a collision silently destroys one person's packet
# ---------------------------------------------------------------------------

def test_person_slug_strips_path_separators_and_punctuation():
    assert person_slug("O'Connor, Pauline").startswith("o-connor-pauline-")
    assert "/" not in person_slug("Smith / Jones")


def test_person_slug_never_produces_a_hidden_or_empty_filename():
    for name in ("...", "   ", "/"):
        slug = person_slug(name)
        assert slug.startswith("person-")
        assert "/" not in slug


def test_person_slug_distinguishes_the_split_identity_shape():
    # "O'Connor, Pauline" vs "O'Connor Pauline" fold to the same readable
    # stem; the digest is what stops one packet overwriting the other.
    assert person_slug("O'Connor, Pauline") != person_slug("O'Connor Pauline")


def test_person_slug_is_stable_for_the_same_name():
    assert person_slug("Ada Fixture") == person_slug("Ada Fixture")
