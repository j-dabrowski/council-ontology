"""Builds lookup_search.json -- a corpus-wide, keyword-searchable index of
motions, other agenda items, and tenders/contractor awards, for /record's
"Search council records" feature (RECORD_PAGE_PLAN.md follow-on,
2026-09-15: users should be able to search for a specific matter, e.g.
"st john of god hospital", or a contractor's name and see their full
tender history, not just look up by street).

Deliberately a lightweight direct-query module, not a reuse of
`compute_watch_feed()` -- that function runs the full per-meeting test
battery (src/analysis/meeting_baselines.py), a cost this snapshot has no
reason to pay just to list agenda items. Mirrors record_streets.py's own
style: one flat query per entity table, joined to `meetings`, redacted at
construction time.

Privacy: every free-text field (`title`, `description`, `awarded_to`)
passes through `src.privacy.redact_private_names()` before being written,
same discipline as record_streets.py/dose.json/watch.json's motions.
Checked directly against the live corpus (not assumed) -- see this
module's own tests and the redaction re-check `src/cli.py`'s draft run
prints. `other_items` additionally drops standing "Confidential Reports -
Nil"-shaped placeholder rows via `_is_nil_placeholder`, the same filter
`meeting_inventory()` (src/analysis/digest.py) already applies -- those
aren't decided/discussed items, just an empty section heading.

Confidential tenders are NOT specially suppressed beyond the standard
redaction pass: a named `awarded_to` on a confidential tender is, in this
corpus, always a real business (e.g. "Albarossa Pty Ltd"), never a
private individual -- this project's existing convention (record_streets,
dose, everywhere else) redacts private individuals, not businesses.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.analysis.tests import _is_nil_placeholder
from src.models import Meeting, Motion, OtherItem, Tender
from src.privacy import redact_private_names


def build_lookup_search(session: Session, council_id: int, generated_at: str) -> dict:
    motion_rows = (
        session.query(Motion, Meeting)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )
    motions = [
        {
            "kind": "motion",
            "meeting_id": meeting.id,
            "meeting_date": meeting.meeting_date.isoformat(),
            "meeting_type": meeting.meeting_type,
            "item_number": m.item_number,
            "title": redact_private_names(m.title),
            "description": redact_private_names(m.description),
            "outcome": m.outcome.value if m.outcome else None,
        }
        for m, meeting in motion_rows
    ]

    other_rows = (
        session.query(OtherItem, Meeting)
        .join(Meeting, OtherItem.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )
    other_items = [
        {
            "kind": "other_item",
            "meeting_id": meeting.id,
            "meeting_date": meeting.meeting_date.isoformat(),
            "meeting_type": meeting.meeting_type,
            "item_number": oi.item_number,
            "item_type": oi.item_type,
            "description": redact_private_names(oi.description),
            "is_confidential": oi.is_confidential,
        }
        for oi, meeting in other_rows
        if not _is_nil_placeholder(oi.description)
    ]

    tender_rows = (
        session.query(Tender, Meeting)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )
    tenders = [
        {
            "kind": "tender",
            "meeting_id": meeting.id,
            "meeting_date": meeting.meeting_date.isoformat(),
            "meeting_type": meeting.meeting_type,
            "reference_number": t.reference_number,
            "awarded_to": redact_private_names(t.awarded_to),
            "description": redact_private_names(t.description),
            "amount": t.amount,
            "is_confidential": t.is_confidential,
        }
        for t, meeting in tender_rows
    ]

    return {
        "generated_at": generated_at,
        "source": "data/council.db",
        "n_motions": len(motions),
        "n_other_items": len(other_items),
        "n_tenders": len(tenders),
        "motions": motions,
        "other_items": other_items,
        "tenders": tenders,
    }
