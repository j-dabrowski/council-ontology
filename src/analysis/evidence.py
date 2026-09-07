"""
Evidence resolution: figure -> rows -> verbatim quote -> source document.

The one place `ExtractionEvidence` is joined for the drill-down chain that
lets a reader trace a panel's figure down to the exact minute text it came
from. See docs/frontend/EVIDENCE_CHAIN_PLAN.md Parts A-C for the design —
in particular why `char_offset IS NULL` must never be read as a paraphrase
signal (A.2) and why tiers are computed at request time by reusing
src/validation/core.py's normalisers, never a new matcher (B.2).

`resolve_evidence()` is entity_table-agnostic provided the table has a
direct `meeting_id` column, or is listed in `_MEETING_ID_VIA` for the
tables that don't (`planning_applications` links via `motion_id` instead —
extend that map, not this docstring's exception list, as more such tables
are generalised, per B.1: this file is the only place such a join is
written).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.divergence import officer_divergence
from src.models import Base, ExtractionEvidence, Meeting
from src.validation.core import _MIN_STRIPPED_LEN, _norm, _norm_stripped, _strip_page_headers

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# (entity_table, entity_id, role)
EntityRef = tuple[str, int, str]

# entity_table -> (fk_column_on_entity_table, table_that_has_meeting_id),
# for the entity tables without a direct meeting_id column.
_MEETING_ID_VIA: dict[str, tuple[str, str]] = {
    "planning_applications": ("motion_id", "motions"),
}


@dataclass
class _MeetingSource:
    """One meeting's resolved source text, prepared once and reused across
    every quote that belongs to it."""

    resolved_against: str  # "pdf" | "minutes_text"
    raw_text: str
    norm_text: str
    stripped_text: str
    pages_raw: list[str] | None       # None when resolved against minutes_text
    pages_norm: list[str] | None
    pages_stripped: list[str] | None


def _pdf_pages(meeting: Meeting) -> list[str] | None:
    """Per-page text of the meeting's PDF, or None if it isn't on disk."""
    if not meeting.minutes_pdf_path:
        return None
    path = _REPO_ROOT / meeting.minutes_pdf_path
    if not path.exists():
        return None
    try:
        doc = fitz.open(str(path))
        pages = [_strip_page_headers(page.get_text() or "") for page in doc]
        doc.close()
        return pages
    except Exception:
        return None


def _build_meeting_source(meeting: Meeting) -> _MeetingSource:
    pages_raw = _pdf_pages(meeting)
    if pages_raw is not None:
        resolved_against = "pdf"
        raw_text = "\n".join(pages_raw)
    else:
        resolved_against = "minutes_text"
        raw_text = _strip_page_headers(meeting.minutes_text or "")

    norm_text = _norm(raw_text)
    stripped_text = _norm_stripped(norm_text)
    pages_norm = [_norm(p) for p in pages_raw] if pages_raw is not None else None
    pages_stripped = [_norm_stripped(p) for p in pages_norm] if pages_norm is not None else None

    return _MeetingSource(
        resolved_against=resolved_against,
        raw_text=raw_text,
        norm_text=norm_text,
        stripped_text=stripped_text,
        pages_raw=pages_raw,
        pages_norm=pages_norm,
        pages_stripped=pages_stripped,
    )


def _find_page(needle: str, pages: list[str] | None) -> int | None:
    """1-based page number of the first page containing needle, else None.

    `pages` and `needle` must already be in the same normalisation space
    (both raw, both _norm'd, or both _norm_stripped'd) as whichever tier
    matched — a quote spanning a page break legitimately resolves to no
    single page, which is B.4's "page not recorded", not a bug.
    """
    if not pages or not needle:
        return None
    for i, page_text in enumerate(pages):
        if needle in page_text:
            return i + 1
    return None


def _classify(quote_text: str, src: _MeetingSource) -> tuple[str, int | None, int | None]:
    """Classify one quote against one meeting's source text.

    Returns (tier, resolved_offset, page). Never modifies quote_text (B.6).
    `resolved_offset` is the offset the matching tier found it at — raw-text
    offset for `exact`, normalised-text offset for `normalised`/`stripped` —
    kept only to make the char_offset discrepancy inspectable (Part C), not
    for cross-tier comparison.
    """
    idx = src.raw_text.find(quote_text)
    if idx >= 0:
        return "exact", idx, _find_page(quote_text, src.pages_raw)

    nq = _norm(quote_text)
    idx = src.norm_text.find(nq)
    if idx >= 0:
        return "normalised", idx, _find_page(nq, src.pages_norm)

    snq = _norm_stripped(nq)
    if len(snq) >= _MIN_STRIPPED_LEN:
        sidx = src.stripped_text.find(snq)
        if sidx >= 0:
            return "stripped", sidx, _find_page(snq, src.pages_stripped)

    return "paraphrase", None, None


def resolve_evidence(
    session: Session,
    entity_refs: list[EntityRef],
    council_id: int,
) -> list[dict]:
    """Resolve Part C evidence entries for a list of (entity_table, entity_id, role).

    One entry per ref, always — an entity with no evidence rows still gets
    an entry: `quotes: []`, `tier: "no_evidence"` (B.5). `quotes[].text` is
    returned exactly as stored, never trimmed or tidied (B.6). Tiers are
    computed here, at request time, over the four-tier vocabulary of B.2 —
    never read from `char_offset` (A.2).
    """
    if not entity_refs:
        return []

    by_table: dict[str, set[int]] = {}
    for entity_table, entity_id, _role in entity_refs:
        by_table.setdefault(entity_table, set()).add(entity_id)

    # meeting_id per (entity_table, entity_id), read off the entity's own
    # row so an entity with zero evidence rows still resolves to a meeting.
    meeting_id_by_ref: dict[tuple[str, int], int | None] = {}
    for entity_table, ids in by_table.items():
        table = Base.metadata.tables[entity_table]
        if "meeting_id" in table.c:
            rows = session.execute(
                select(table.c.id, table.c.meeting_id).where(table.c.id.in_(ids))
            ).all()
        elif entity_table in _MEETING_ID_VIA:
            fk_col, via_table_name = _MEETING_ID_VIA[entity_table]
            via_table = Base.metadata.tables[via_table_name]
            rows = session.execute(
                select(table.c.id, via_table.c.meeting_id)
                .select_from(table.join(via_table, table.c[fk_col] == via_table.c.id))
                .where(table.c.id.in_(ids))
            ).all()
        else:
            raise NotImplementedError(
                f"resolve_evidence: entity table {entity_table!r} has no direct "
                "meeting_id column and isn't in _MEETING_ID_VIA — add an entry "
                "there (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 6)."
            )
        for entity_id, meeting_id in rows:
            meeting_id_by_ref[(entity_table, entity_id)] = meeting_id

    # every ExtractionEvidence row for the requested (table, id) pairs
    evidence_by_ref: dict[tuple[str, int], list[ExtractionEvidence]] = {}
    for entity_table, ids in by_table.items():
        rows = (
            session.query(ExtractionEvidence)
            .filter(
                ExtractionEvidence.entity_table == entity_table,
                ExtractionEvidence.entity_id.in_(ids),
            )
            .all()
        )
        for row in rows:
            evidence_by_ref.setdefault((entity_table, row.entity_id), []).append(row)

    meeting_ids = {mid for mid in meeting_id_by_ref.values() if mid is not None}
    meetings: dict[int, Meeting] = (
        {m.id: m for m in session.query(Meeting).filter(Meeting.id.in_(meeting_ids)).all()}
        if meeting_ids
        else {}
    )

    source_cache: dict[int, _MeetingSource] = {}

    def _source_for(meeting_id: int) -> _MeetingSource:
        if meeting_id not in source_cache:
            source_cache[meeting_id] = _build_meeting_source(meetings[meeting_id])
        return source_cache[meeting_id]

    entries: list[dict] = []
    for entity_table, entity_id, role in entity_refs:
        meeting_id = meeting_id_by_ref.get((entity_table, entity_id))
        meeting = meetings.get(meeting_id) if meeting_id is not None else None
        rows = evidence_by_ref.get((entity_table, entity_id), [])

        quotes: list[dict] = []
        page: int | None = None
        src = _source_for(meeting_id) if meeting is not None else None
        for row in rows:
            if src is not None:
                tier, resolved_offset, q_page = _classify(row.quote_text, src)
                resolved_against = src.resolved_against
            else:
                tier, resolved_offset, q_page, resolved_against = (
                    "paraphrase", None, None, None,
                )
            if page is None and q_page is not None:
                page = q_page
            quotes.append({
                "text": row.quote_text,
                "tier": tier,
                "char_offset": row.char_offset,
                "resolved_offset": resolved_offset,
                "resolved_against": resolved_against,
            })

        document = None
        if meeting is not None:
            document = {
                "filename": Path(meeting.minutes_pdf_path).name if meeting.minutes_pdf_path else None,
                "url": meeting.minutes_pdf_url,
                "page": page,
            }

        entry: dict = {
            "entity_table": entity_table,
            "entity_id": entity_id,
            "role": role,
            "meeting_id": meeting_id,
            "meeting_date": meeting.meeting_date.isoformat() if meeting and meeting.meeting_date else None,
            "document": document,
            "quotes": quotes,
        }
        if not rows:
            entry["tier"] = "no_evidence"
        entries.append(entry)

    return entries


def evidence_for_officer_ratification(
    session: Session, council_id: int, year: int | None = None
) -> dict:
    """Evidence chain for governance.officer_ratification: both sides — the
    agenda motion and the matched minutes motion — of every
    officer_divergence() pair, grouped by pair (Part C).

    `year`, when given, narrows to that one year (officer_divergence()'s
    own from_year/to_year, both set to it) — the only filter this test's
    underlying query supports (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 2).
    """
    pairs = officer_divergence(session, council_id, from_year=year, to_year=year)

    refs: list[EntityRef] = []
    for pair in pairs:
        if pair.agenda_motion_id is not None:
            refs.append(("motions", pair.agenda_motion_id, "agenda_motion"))
        if pair.minutes_motion_id is not None:
            refs.append(("motions", pair.minutes_motion_id, "minutes_motion"))

    entries = resolve_evidence(session, refs, council_id)
    entries_by_ref: dict[tuple[str, int], dict] = {
        (e["entity_table"], e["entity_id"]): e for e in entries
    }

    pair_entries = []
    for pair in pairs:
        agenda_entry = (
            entries_by_ref.get(("motions", pair.agenda_motion_id))
            if pair.agenda_motion_id is not None else None
        )
        minutes_entry = (
            entries_by_ref.get(("motions", pair.minutes_motion_id))
            if pair.minutes_motion_id is not None else None
        )
        pair_entries.append({
            "meeting_date": pair.meeting_date.isoformat() if pair.meeting_date else None,
            "item_number": pair.item_number,
            "title": pair.title,
            "diverged": pair.diverged,
            "council_outcome": pair.council_outcome,
            "agenda_motion": agenda_entry,
            "minutes_motion": minutes_entry,
        })

    return {"pairs": pair_entries}


def evidence_for_objection_responsiveness(session: Session, council_id: int, cap: int = 30) -> dict:
    """Evidence chain for planning.objection_responsiveness.

    Selects the same population `src/cli.py`'s `cmd_draft` already exports
    onto `dose.json` — decided (approved/refused) planning applications,
    bucketed by objector count, capped to `cap` per bucket, highest-
    objector-count first — and resolves each to its full evidence chain.

    Deliberately carries only `entity_table`/`entity_id`/etc. (Part C), not
    `dose.json`'s business fields (reference, address, description,
    outcome) — the frontend joins the two by `entity_id` rather than this
    file duplicating them.
    """
    from sqlalchemy import func

    from src.models import ApplicationStatus, CommunitySubmission, Meeting, Motion, PlanningApplication

    rows = (
        session.query(
            PlanningApplication.id,
            func.count(CommunitySubmission.id).label("n_obj"),
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .outerjoin(
            CommunitySubmission,
            (CommunitySubmission.application_id == PlanningApplication.id)
            & (func.lower(CommunitySubmission.position) == "object"),
        )
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        )
        .group_by(PlanningApplication.id)
        .order_by(func.count(CommunitySubmission.id).desc())
        .all()
    )

    def _bucket(n: int) -> str:
        if n == 0:
            return "0"
        if n == 1:
            return "1"
        if n <= 4:
            return "2-4"
        return "5+"

    order = ["0", "1", "2-4", "5+"]
    ids_by_bucket: dict[str, list[int]] = {k: [] for k in order}
    for app_id, n_obj in rows:
        b = _bucket(int(n_obj or 0))
        if len(ids_by_bucket[b]) < cap:
            ids_by_bucket[b].append(app_id)

    refs: list[EntityRef] = [
        ("planning_applications", app_id, "application")
        for ids in ids_by_bucket.values()
        for app_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "applications": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in order
        ]
    }
