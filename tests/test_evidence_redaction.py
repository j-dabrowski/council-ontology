"""Tests for src.privacy.redact_evidence_quotes() (docs/frontend/
RECORD_PAGE_PLAN.md Step 8) -- the export-time redaction step for
evidence/*.json files about to publish at public tier for the first
time.

Hermetic: no DB, synthetic entries in the exact shape
src.analysis.evidence.resolve_evidence() returns. The real-corpus
percentages (38/223 planning, 3/129 tenure, 3/636 transparency) were
measured directly against data/council.db and are reported by hand, not
committed here, same convention as tests/test_privacy.py and
tests/test_record_streets.py -- committing the real flagged quotes
would recreate the exact leak this step fixes.
"""
from __future__ import annotations

from src.privacy import PLACEHOLDER, redact_evidence_quotes


def _entry(quotes: list[str]) -> dict:
    return {
        "entity_table": "planning_applications",
        "entity_id": 1,
        "role": "application",
        "meeting_id": 1,
        "meeting_date": "2020-01-01",
        "document": {"filename": "x.pdf", "url": None, "page": 1},
        "quotes": [
            {"text": q, "tier": "exact", "char_offset": None,
             "resolved_offset": None, "resolved_against": "minutes_text"}
            for q in quotes
        ],
    }


def test_redacts_quote_text_in_place():
    entries = [_entry(["Application: 1DA-2020\nOwner: Mr John Smith\nApplicant: Mr John Smith"])]
    redact_evidence_quotes(entries)
    text = entries[0]["quotes"][0]["text"]
    assert "Smith" not in text
    assert "Owner:" not in text
    assert "Applicant:" not in text
    assert PLACEHOLDER in text


def test_leaves_ordinary_quote_text_untouched():
    original = "That Council APPROVES the tender for road resurfacing works."
    entries = [_entry([original])]
    redact_evidence_quotes(entries)
    assert entries[0]["quotes"][0]["text"] == original


def test_multiple_quotes_per_entry_all_redacted():
    entries = [_entry([
        "Owner: Jane Doe",
        "an ordinary sentence with no names",
        "Applicant: Richard Roe",
    ])]
    redact_evidence_quotes(entries)
    texts = [q["text"] for q in entries[0]["quotes"]]
    assert "Jane Doe" not in texts[0]
    assert texts[1] == "an ordinary sentence with no names"
    assert "Richard Roe" not in texts[2]


def test_entry_with_no_quotes_is_a_no_op():
    entry = {"entity_table": "motions", "entity_id": 1, "quotes": []}
    redact_evidence_quotes([entry])
    assert entry["quotes"] == []


def test_entry_missing_quotes_key_does_not_raise():
    entry = {"entity_table": "motions", "entity_id": 1, "tier": "no_evidence"}
    redact_evidence_quotes([entry])  # must not raise


def test_flattening_nested_bucket_shape():
    """evidence/planning.objection_responsiveness.json's real shape --
    buckets[].applications[] -- flattened by the caller before this
    function ever sees it, per redact_evidence_quotes()'s own contract."""
    buckets_shaped_payload = {
        "buckets": [
            {"label": "0", "applications": [_entry(["Owner: A B"])]},
            {"label": "5+", "applications": [_entry(["Owner: C D"]), _entry(["no name here"])]},
        ]
    }
    flat = [app for b in buckets_shaped_payload["buckets"] for app in b["applications"]]
    redact_evidence_quotes(flat)
    assert "A B" not in buckets_shaped_payload["buckets"][0]["applications"][0]["quotes"][0]["text"]
    assert "C D" not in buckets_shaped_payload["buckets"][1]["applications"][0]["quotes"][0]["text"]
    assert buckets_shaped_payload["buckets"][1]["applications"][1]["quotes"][0]["text"] == "no name here"
