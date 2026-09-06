"""
The provenance join (docs/frontend/WATCH_FEED_PLAN.md Step 3): five fields
about *how a meeting's data got here* that live outside the database, in two
kinds of loose files written by the extraction pipeline —

    meetings.minutes_pdf_path  (DB)
        → data/validation/<hash>.json   (per-document validation report)
        → data/batch_jobs/<batch_id>.json  (per-batch submission record)

`meeting_provenance()` is the join. It belongs here, not in a query module
(B.5): the two file kinds are read fresh off disk, never persisted into the
schema — that would be a pipeline change, out of scope for this plan (see
this module's own recommendation at the bottom, and B.5).

Never invents a value: a field with nothing recorded for a meeting is
`None`, which every consumer renders as "not recorded" — the same rule the
rest of this plan applies to a meeting's exceptions.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.models import Meeting

DEFAULT_VALIDATION_DIR = Path(__file__).resolve().parent.parent / "data" / "validation"
DEFAULT_BATCH_JOBS_DIR = Path(__file__).resolve().parent.parent / "data" / "batch_jobs"


def _load_validation_by_meeting_id(validation_dir: Path) -> dict[int, dict]:
    """Indexed by the validation file's own `meeting_id` field (A.5: the
    file carries the matching id directly, no hash-based join needed here).
    A meeting_id occurring in more than one file (a re-validated document)
    keeps whichever the filesystem yields last — this project has no
    re-validation ordering signal, and it is not this step's job to invent
    one; noted as a gap in this module's closing recommendation."""
    by_meeting: dict[int, dict] = {}
    if not validation_dir.exists():
        return by_meeting
    for path in sorted(validation_dir.glob("*.json")):
        data = json.loads(path.read_text())
        meeting_id = data.get("meeting_id")
        if meeting_id is not None:
            by_meeting[meeting_id] = data
    return by_meeting


def _load_batches_by_pdf_path(batch_jobs_dir: Path) -> dict[str, list[dict]]:
    """pdf_path -> every batch job whose id_map references it (one entry per
    batch file touched, deduplicated within a file — a document chunked into
    N pieces inside one batch is one match, not N)."""
    by_pdf: dict[str, list[dict]] = {}
    if not batch_jobs_dir.exists():
        return by_pdf
    for path in sorted(batch_jobs_dir.glob("*.json")):
        data = json.loads(path.read_text())
        pdf_paths = {entry["pdf_path"] for entry in data["id_map"].values()}
        for pdf_path in pdf_paths:
            by_pdf.setdefault(pdf_path, []).append({
                "batch_id": data["batch_id"],
                "submitted_at": data["submitted_at"],
                "model": data["model"],
            })
    return by_pdf


def meeting_provenance(
    session: Session,
    meeting_ids: list[int],
    validation_dir: Path = DEFAULT_VALIDATION_DIR,
    batch_jobs_dir: Path = DEFAULT_BATCH_JOBS_DIR,
) -> dict[int, dict]:
    """Part C.2's `provenance` object, one per requested meeting id.

    `run_id` is the most-recent-by-`submitted_at` batch touching the
    document (B.5) — a single arbitrary pick would misattribute which run
    produced the rows on screen — and `run_id_count` is how many batches
    were found in total, so a renderer can show "+N earlier" only when
    there's more than one. Both are `None`/`0` when the document was
    extracted by some path that left no batch record (A.5: 130 such
    meetings, non-batch extraction).
    """
    validation_by_meeting = _load_validation_by_meeting_id(validation_dir)
    batches_by_pdf = _load_batches_by_pdf_path(batch_jobs_dir)

    meetings = session.query(Meeting).filter(Meeting.id.in_(meeting_ids)).all()

    result: dict[int, dict] = {}
    for m in meetings:
        validation = validation_by_meeting.get(m.id)
        batches = batches_by_pdf.get(m.minutes_pdf_path, []) if m.minutes_pdf_path else []
        batches_sorted = sorted(batches, key=lambda b: b["submitted_at"], reverse=True)
        latest = batches_sorted[0] if batches_sorted else None

        result[m.id] = {
            "pdf_filename": Path(m.minutes_pdf_path).name if m.minutes_pdf_path else None,
            "pdf_url": m.minutes_pdf_url,
            "extracted_at": m.extracted_at.isoformat() if m.extracted_at else None,
            "run_id": latest["batch_id"] if latest else None,
            "run_id_count": len(batches_sorted),
            "model": latest["model"] if latest else None,
            "validation_status": validation["status"] if validation else None,
            "coverage_ratio": validation["coverage_ratio"] if validation else None,
        }
    return result


# ---------------------------------------------------------------------------
# Recommendation (B.5) — not built here, a pipeline change if ever taken up.
#
# Persisting run id, model and validation status into the schema would trade
# a live filesystem join (this module) for a write at extraction time. In
# favour: no per-request disk scan, and no ambiguity for the 31 minutes
# meetings whose document was resubmitted in a separate later batch (a
# column update at extraction time would just win, rather than needing the
# "most recent wins" rule above). Against: batch_jobs/ and validation/ are
# already the durable audit trail for exactly this data — duplicating it
# into the DB creates a second copy that can drift from the files if a
# batch is ever re-run without a matching migration. On balance, worth doing
# only once a second consumer (beyond this feed) needs the same join, since
# right now there is exactly one.
# ---------------------------------------------------------------------------
