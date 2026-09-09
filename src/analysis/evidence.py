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

import re
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
    source_cache: dict[int, _MeetingSource] | None = None,
) -> list[dict]:
    """Resolve Part C evidence entries for a list of (entity_table, entity_id, role).

    One entry per ref, always — an entity with no evidence rows still gets
    an entry: `quotes: []`, `tier: "no_evidence"` (B.5). `quotes[].text` is
    returned exactly as stored, never trimmed or tidied (B.6). Tiers are
    computed here, at request time, over the four-tier vocabulary of B.2 —
    never read from `char_offset` (A.2).

    `source_cache`, when passed in, is read from and written to in place —
    a meeting's PDF is only ever opened and parsed once across however many
    `resolve_evidence()` calls share the same dict, which matters once
    `src/cli.py`'s `cmd_draft` calls this once per test in the same run and
    many tests' entities share meetings. Omit it (the default) for a single
    self-contained call — a fresh, call-scoped cache, as before.
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

    if source_cache is None:
        source_cache = {}

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
    session: Session, council_id: int, year: int | None = None,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.officer_ratification: both sides — the
    agenda motion and the matched minutes motion — of every
    officer_divergence() pair, grouped by pair (Part C).

    `year`, when given, narrows to that one year (officer_divergence()'s
    own from_year/to_year, both set to it) — the only filter this test's
    underlying query supports (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 2).

    `source_cache`: see resolve_evidence() — pass one shared dict across
    every evidence_for_*() call in the same `cmd_draft` run so an overlapping
    meeting's PDF is parsed once, not once per test.
    """
    pairs = officer_divergence(session, council_id, from_year=year, to_year=year)

    refs: list[EntityRef] = []
    for pair in pairs:
        if pair.agenda_motion_id is not None:
            refs.append(("motions", pair.agenda_motion_id, "agenda_motion"))
        if pair.minutes_motion_id is not None:
            refs.append(("motions", pair.minutes_motion_id, "minutes_motion"))

    entries = resolve_evidence(session, refs, council_id, source_cache)
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


def evidence_for_objection_responsiveness(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for planning.objection_responsiveness.

    Selects the same population `src/cli.py`'s `cmd_draft` already exports
    onto `dose.json` — decided (approved/refused) planning applications,
    bucketed by objector count, capped to `cap` per bucket, highest-
    objector-count first — and resolves each to its full evidence chain.

    Deliberately carries only `entity_table`/`entity_id`/etc. (Part C), not
    `dose.json`'s business fields (reference, address, description,
    outcome) — the frontend joins the two by `entity_id` rather than this
    file duplicating them.

    `source_cache`: see resolve_evidence().
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
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "applications": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in order
        ]
    }


def evidence_for_transparency(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for transparency.confidential_share.

    Selects the same population `src/cli.py`'s `cmd_draft` already exports
    onto `transparency.json`'s per-year items lists: confidential tenders,
    other_items, delegated_decisions and budget_items, capped to `cap` per
    table per year (each UNION ALL branch's own `ROW_NUMBER()` restarts at
    1 — the cap is not combined across tables, matching the existing
    query's real behaviour whether or not its own comment says so), newest
    first within a year — and resolves each to its full evidence chain.
    Same query cli.py's own `_CONF_ITEMS_SQL` runs, kept identical here
    rather than re-derived in the ORM, since it's a four-way UNION with a
    window function per branch.

    Deliberately carries only `entity_table`/`entity_id`/etc. (Part C), not
    `transparency.json`'s business fields (description, amount, date) —
    the frontend joins the two by (entity_table, entity_id).

    `source_cache`: see resolve_evidence().
    """
    from sqlalchemy import text

    sql = text("""
        SELECT year, entity_table, entity_id
        FROM (
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER) year,
                   'tenders' entity_table, t.id entity_id, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM tenders t JOIN meetings m ON t.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND t.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'other_items', o.id, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM other_items o JOIN meetings m ON o.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND o.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'delegated_decisions', dd.id, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM delegated_decisions dd JOIN meetings m ON dd.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND dd.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'budget_items', b.id, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM budget_items b JOIN meetings m ON b.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND b.is_confidential = 1
        ) WHERE rn <= :cap
        ORDER BY year, meeting_date DESC
    """)
    rows = session.execute(sql, {"cid": council_id, "cap": cap}).fetchall()

    refs_by_year: dict[int, list[EntityRef]] = {}
    for year, entity_table, entity_id in rows:
        refs_by_year.setdefault(year, []).append((entity_table, entity_id, "confidential_item"))

    all_refs: list[EntityRef] = [ref for refs in refs_by_year.values() for ref in refs]
    entries = resolve_evidence(session, all_refs, council_id, source_cache)
    entries_by_ref = {(e["entity_table"], e["entity_id"]): e for e in entries}

    return {
        "years": [
            {
                "year": year,
                "items": [entries_by_ref[(t, i)] for (t, i, _role) in refs_by_year[year]],
            }
            for year in sorted(refs_by_year)
        ]
    }


def evidence_for_chair_capture(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.chair_capture.

    Selects the same population `src/cli.py`'s `cmd_draft` already exports
    onto `mayoral.json`'s per-mayor motion lists: carried motions that drew
    at least one AGAINST vote, moved by someone who held the 'Mayor' role
    at the time, capped to `cap` per mayor, newest first — and resolves
    each to its full evidence chain.

    Deliberately carries only `entity_table`/`entity_id`/etc. (Part C), not
    `mayoral.json`'s business fields (title, date, votes_for/against) —
    the frontend joins the two by `entity_id`. A mayor with zero qualifying
    motions is absent from `mayors` entirely (this file is entity-driven,
    unlike `mayoral.json`'s own per-mayor list, which enumerates every
    mayor from its own aggregate query) — harmless, since the frontend
    joins by entity_id across all mayors, never by mayor name.

    `source_cache`: see resolve_evidence().
    """
    from datetime import date as _date

    from src.models import Councillor, CouncillorTerm, Meeting, Motion, MotionOutcome

    mayor_terms = (
        session.query(
            CouncillorTerm.councillor_id,
            CouncillorTerm.term_start,
            CouncillorTerm.term_end,
            Councillor.given_name,
            Councillor.family_name,
        )
        .join(Councillor, CouncillorTerm.councillor_id == Councillor.id)
        .filter(CouncillorTerm.role == "Mayor")
        .all()
    )
    mayor_name = {mc: f"{gn or ''} {fn or ''}".strip() for mc, _ts, _te, gn, fn in mayor_terms}

    def _was_mayor(cid: int, d: _date) -> bool:
        return any(
            mc == cid and (ts is None or ts <= d) and (te is None or d <= te)
            for mc, ts, te, *_ in mayor_terms
        )

    contested_rows = (
        session.query(Motion.id, Motion.moved_by_id, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.moved_by_id.in_(list(mayor_name.keys())),
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.votes_against > 0,
            Meeting.meeting_date.isnot(None),
        )
        .order_by(Meeting.meeting_date.desc())
        .all()
    )

    ids_by_mayor: dict[str, list[int]] = {}
    for motion_id, mover_id, meeting_date in contested_rows:
        md = meeting_date if isinstance(meeting_date, _date) else _date.fromisoformat(str(meeting_date))
        if not _was_mayor(mover_id, md):
            continue
        name = mayor_name[mover_id]
        ids = ids_by_mayor.setdefault(name, [])
        if len(ids) < cap:
            ids.append(motion_id)

    refs: list[EntityRef] = [
        ("motions", motion_id, "mayoral_motion")
        for ids in ids_by_mayor.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "mayors": [
            {"name": name, "motions": [entries_by_id[i] for i in ids]}
            for name, ids in ids_by_mayor.items()
        ]
    }


# ---------------------------------------------------------------------------
# tests.<generator> group (Phase 2, Step 6 continued): unlike the tests
# above, these have no existing snapshot or drill-down to reuse or upgrade
# — src/analysis/tests.py's generator computes its chart inline, with no
# capped entity list anywhere. Each builder below re-derives its test's own
# population from scratch and returns the shared shape the frontend's one
# generic BatteryTestBody drill-down reads for all of them:
#   {"buckets": [{"label": <matches the chart bar/point label>,
#                 "entries": [EvidenceEntry, ...]}]}
# "entries" (not a test-specific field name) is deliberate — one frontend
# consumer serves every test in this group, so the shape must be identical
# across all of them, unlike the four tests above which each already had
# their own bespoke panel and could keep their own field names.
# ---------------------------------------------------------------------------

def evidence_for_threshold_gaming(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for procurement.threshold_gaming.

    Same population and $-bin edges as tests._t_threshold_gaming's own
    histogram: tenders on minutes meetings with an amount, 2015 onward
    (the $250k-threshold era the test examines). Capped to `cap` per bin,
    newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Tender

    rows = (
        session.query(Tender.id, Tender.amount, Meeting.meeting_date)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Tender.amount.isnot(None),
        )
        .all()
    )

    # Same edges/labels as _t_threshold_gaming (tests.py) — kept identical
    # so a bucket label here always matches the chart bar it's clicked from.
    edges = [0, 50_000, 100_000, 150_000, 200_000, 250_000, 300_000, 350_000, 400_000]
    labels = ["<50k", "50–100k", "100–150k", "150–200k", "200–250k",
              "250–300k", "300–350k", "350–400k", "400k+"]

    def _bin_label(amount: float) -> str:
        idx = next((i for i, e in enumerate(edges) if amount < e), None)
        return labels[(idx - 1) if idx else (len(labels) - 1)]

    modern = [
        (tender_id, amount, meeting_date)
        for tender_id, amount, meeting_date in rows
        if meeting_date and meeting_date.year >= 2015
    ]
    modern.sort(key=lambda r: r[2], reverse=True)  # newest first within each bin

    ids_by_bucket: dict[str, list[int]] = {label: [] for label in labels}
    for tender_id, amount, _mdate in modern:
        ids = ids_by_bucket[_bin_label(amount)]
        if len(ids) < cap:
            ids.append(tender_id)

    refs: list[EntityRef] = [
        ("tenders", tender_id, "tender")
        for ids in ids_by_bucket.values()
        for tender_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_eoy_spending(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for finance.eoy_spending.

    Same population as tests._t_eoy_spending's own chart: tenders on
    minutes meetings with a non-zero amount, all years combined, bucketed
    by calendar month. Capped to `cap` per month, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Tender

    rows = (
        session.query(Tender.id, Meeting.meeting_date, Tender.amount)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Tender.amount.isnot(None),
            Tender.amount != 0,
        )
        .all()
    )

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    modern = [(tender_id, meeting_date) for tender_id, meeting_date, _amount in rows if meeting_date]
    modern.sort(key=lambda r: r[1], reverse=True)  # newest first within each month

    ids_by_bucket: dict[str, list[int]] = {label: [] for label in months}
    for tender_id, meeting_date in modern:
        ids = ids_by_bucket[months[meeting_date.month - 1]]
        if len(ids) < cap:
            ids.append(tender_id)

    refs: list[EntityRef] = [
        ("tenders", tender_id, "tender")
        for ids in ids_by_bucket.values()
        for tender_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in months
        ]
    }


def evidence_for_big_dollar_leniency(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for planning.big_dollar_leniency.

    Same population and equal-count quartile split as tests._t_big_dollar_
    leniency's own chart: decided (approved/refused) planning applications
    with a positive estimated_value, sorted by value into four quartiles by
    count (not by value range). Below the same n<20 floor the test itself
    uses, every bucket is empty rather than guessing at boundaries the real
    test wouldn't compute either. Capped to `cap` per quartile, highest
    value first. Unlike the aggregate test's own query (which has no
    council_id filter at all — harmless on a single-council corpus, but
    this resolver stays scoped like every other one here), this joins
    through motions to meetings to filter correctly.

    `source_cache`: see resolve_evidence().
    """
    from src.models import ApplicationStatus, Meeting, Motion, PlanningApplication

    rows = (
        session.query(PlanningApplication.id, PlanningApplication.estimated_value)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.estimated_value.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        )
        .all()
    )

    labels = ["Q1 (lowest $)", "Q2", "Q3", "Q4 (highest $)"]
    vals = sorted(((app_id, v) for app_id, v in rows if v and v > 0), key=lambda t: t[1])

    ids_by_bucket: dict[str, list[int]] = {label: [] for label in labels}
    if len(vals) >= 20:
        q = len(vals) // 4
        quartile_groups = [vals[:q], vals[q:2 * q], vals[2 * q:3 * q], vals[3 * q:]]
        for label, group in zip(labels, quartile_groups):
            highest_first = sorted(group, key=lambda t: t[1], reverse=True)
            ids_by_bucket[label] = [app_id for app_id, _v in highest_first[:cap]]

    refs: list[EntityRef] = [
        ("planning_applications", app_id, "application")
        for ids in ids_by_bucket.values()
        for app_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_repeat_applicant(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for planning.repeat_applicant.

    Same population and frequency-bucket split as tests._t_repeat_
    applicant's own chart: decided (approved/refused) planning applications
    with a named applicant, grouped by normalised (stripped, lower-cased)
    applicant name into 1 / 2-3 / 4-6 / 7+ buckets by that name's total
    count across the whole corpus. Capped to `cap` applications per bucket,
    newest first — not per applicant, since the aggregate test doesn't
    care which applicant an example comes from, only the frequency band.

    `source_cache`: see resolve_evidence().
    """
    from src.models import ApplicationStatus, Meeting, Motion, PlanningApplication

    rows = (
        session.query(PlanningApplication.id, PlanningApplication.applicant_name, Meeting.meeting_date)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.applicant_name.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        )
        .all()
    )

    freq: dict[str, list[tuple[int, object]]] = {}
    for app_id, name, meeting_date in rows:
        nm = (name or "").strip().lower()
        if not nm:
            continue
        freq.setdefault(nm, []).append((app_id, meeting_date))

    labels = ["1 app", "2–3", "4–6", "7+"]

    def _bucket_for_count(c: int) -> str:
        if c == 1:
            return "1 app"
        if c <= 3:
            return "2–3"
        if c <= 6:
            return "4–6"
        return "7+"

    grouped: dict[str, list[tuple[int, object]]] = {label: [] for label in labels}
    for items in freq.values():
        grouped[_bucket_for_count(len(items))].extend(items)

    ids_by_bucket: dict[str, list[int]] = {}
    for label, items in grouped.items():
        newest_first = sorted(items, key=lambda t: t[1], reverse=True)
        ids_by_bucket[label] = [app_id for app_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("planning_applications", app_id, "application")
        for ids in ids_by_bucket.values()
        for app_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_unanimity_trend(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.unanimity_trend — the first line-chart
    test in this group, so the bucket label is a year string, matching
    ChartView's line-point click (`String(p.payload.x)`), not a chart bar
    label.

    Same year floor as tests._t_unanimity_trend's own line: only years
    with >=30 carried motions (on minutes meetings) are plotted at all.
    For each plotted year, exports the *contested* carried motions
    (votes_against > 0) that year, capped to `cap`, newest first — the
    motions actually behind that year's dissent share, not an
    uninformative sample of the largely-unanimous rest. A plotted year
    with zero contested motions still gets a bucket, empty (a real fact:
    nothing split the chamber that year), same as any other no-evidence
    case in this file.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Motion, MotionOutcome

    rows = (
        session.query(Motion.id, Motion.votes_against, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.outcome == MotionOutcome.CARRIED,
        )
        .all()
    )

    total_by_year: dict[int, int] = {}
    contested_by_year: dict[int, list[tuple[int, object]]] = {}
    for motion_id, votes_against, meeting_date in rows:
        if not meeting_date:
            continue
        year = meeting_date.year
        total_by_year[year] = total_by_year.get(year, 0) + 1
        if (votes_against or 0) > 0:
            contested_by_year.setdefault(year, []).append((motion_id, meeting_date))

    plotted_years = sorted(year for year, n in total_by_year.items() if n >= 30)

    ids_by_year: dict[int, list[int]] = {}
    for year in plotted_years:
        newest_first = sorted(contested_by_year.get(year, []), key=lambda t: t[1], reverse=True)
        ids_by_year[year] = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("motions", motion_id, "contested_motion")
        for ids in ids_by_year.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": str(year), "entries": [entries_by_id[i] for i in ids_by_year[year]]}
            for year in plotted_years
        ]
    }


def evidence_for_confidential_tender_size(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for transparency.confidential_tender_size.

    Same population as tests._t_confidential_tender_size's own chart:
    tenders on minutes meetings with a positive amount, split into
    "Confidential" and "Open" buckets by the is_confidential flag (never
    by award-field missingness — the aggregate test's own docstring calls
    that out as a trap it deliberately avoids). Capped to `cap` per
    bucket, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Tender

    rows = (
        session.query(Tender.id, Tender.is_confidential, Meeting.meeting_date)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Tender.amount.isnot(None),
            Tender.amount > 0,
        )
        .all()
    )

    labels = ["Confidential", "Open"]
    grouped: dict[str, list[tuple[int, object]]] = {label: [] for label in labels}
    for tender_id, is_confidential, meeting_date in rows:
        grouped["Confidential" if is_confidential else "Open"].append((tender_id, meeting_date))

    ids_by_bucket: dict[str, list[int]] = {}
    for label, items in grouped.items():
        newest_first = sorted(items, key=lambda t: t[1], reverse=True)
        ids_by_bucket[label] = [tender_id for tender_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("tenders", tender_id, "tender")
        for ids in ids_by_bucket.values()
        for tender_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


# Same six theme regexes as tests._t_confidential_topics (tests.py), kept
# identical so a bucket here always matches its chart bar.
_CONFIDENTIAL_TOPIC_THEMES = [
    ("Commercial-in-conf", r"commercial|in-confidence|negotiation|proposal|confidential"),
    ("Tender/procurement", r"tender|rft|contract|procure|quotation|supplier|panel"),
    ("Personnel/HR",
     r"\bceo\b|chief executive|staff|employee|personnel|recruit|remuneration|salary|human resource"),
    ("Legal/litigation", r"legal|litigation|court|claim|settlement|solicitor|counsel|dispute"),
    ("Land/property deal",
     r"lease|land|acquisition|dispose|disposal|purchase of|sale of|easement|freehold|valuation"),
    ("Named development",
     r"development|structure plan|precinct|activity centre|rezoning|subdivision|building height"),
]

# Same "Confidential Reports - Nil" placeholder-heading exclusion as
# tests.py's _is_nil_placeholder — these rows are an extraction artefact
# (a standing agenda-section header), not a real decided item.
_NIL_PLACEHOLDER_RE = re.compile(r"^confidential reports?(\s+section)?\s*-\s*nil\b", re.IGNORECASE)


def evidence_for_confidential_topics(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for transparency.confidential_topics.

    Same population and theme regexes as tests._t_confidential_topics's
    own chart: descriptions across tenders/other_items/delegated_decisions
    on minutes meetings, excluding the nil-placeholder heading. An item
    can match more than one theme — the aggregate test's own regexes
    aren't mutually exclusive — so an entity can legitimately appear in
    more than one bucket here too, not a bug. Exports the *confidential*
    items matching each theme (the chart's bar is %-confidential within
    the theme, driven by these, not by the open items also in it), capped
    to `cap` per theme, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import DelegatedDecision, Meeting, OtherItem, Tender

    rows: list[tuple[str, int, str, bool, object]] = []
    for model, table_name in (
        (Tender, "tenders"), (OtherItem, "other_items"), (DelegatedDecision, "delegated_decisions"),
    ):
        query_rows = (
            session.query(model.id, model.description, model.is_confidential, Meeting.meeting_date)
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
            .all()
        )
        for row_id, desc, is_confidential, meeting_date in query_rows:
            if desc and _NIL_PLACEHOLDER_RE.match(desc.strip()):
                continue
            rows.append((table_name, row_id, (desc or "").lower(), bool(is_confidential), meeting_date))

    ids_by_theme: dict[str, list[tuple[str, int]]] = {}
    for name, pattern in _CONFIDENTIAL_TOPIC_THEMES:
        rx = re.compile(pattern)
        matching_confidential = [
            (table_name, row_id, meeting_date)
            for table_name, row_id, desc_lower, is_confidential, meeting_date in rows
            if is_confidential and rx.search(desc_lower)
        ]
        newest_first = sorted(matching_confidential, key=lambda t: t[2], reverse=True)
        ids_by_theme[name] = [(table_name, row_id) for table_name, row_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        (table_name, row_id, "confidential_topic_item")
        for pairs in ids_by_theme.values()
        for table_name, row_id in pairs
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_ref = {(e["entity_table"], e["entity_id"]): e for e in entries}

    return {
        "buckets": [
            {
                "label": name,
                "entries": [entries_by_ref[(t, i)] for t, i in ids_by_theme[name]],
            }
            for name, _pattern in _CONFIDENTIAL_TOPIC_THEMES
        ]
    }


def evidence_for_incumbency(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for procurement.incumbency.

    Same population, normalisation and exclusions as tests._t_procurement_
    incumbency's own chart: tenders on minutes meetings with an
    awarded_to name, grouped by `_normalise_contractor(awarded_to)`
    (dropping names that normalise to empty or contain "respondent"), then
    the top 10 firms by *distinct years won* — the same top-10 the chart
    actually plots. (A separate top-10-by-dollar-value ranking feeds only
    the aggregate test's internal overlap flag and is never charted, so it
    has no bucket here — nothing could ever click into it.)

    Bucket labels are `key.title()[:22]`, matching the chart bar label
    exactly, even where normalisation has collapsed a name past
    readability (e.g. "R J Vincent" -> "rjvincent" -> "Rjvincent") —
    because that IS the label a click has to match.

    Capped to `cap` tenders per firm, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.analysis.queries import _normalise_contractor
    from src.models import Meeting, Tender

    rows = (
        session.query(Tender.id, Tender.awarded_to, Meeting.meeting_date)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )

    by_firm: dict[str, dict] = {}
    for tender_id, name, meeting_date in rows:
        if not name:
            continue
        key = _normalise_contractor(name)
        if not key or "respondent" in key:
            continue
        rec = by_firm.setdefault(key, {"years": set(), "tenders": []})
        if meeting_date:
            rec["years"].add(meeting_date.year)
        rec["tenders"].append((tender_id, meeting_date))

    top_recurring = sorted(by_firm.items(), key=lambda kv: len(kv[1]["years"]), reverse=True)[:10]

    ids_by_bucket: dict[str, list[int]] = {}
    for key, rec in top_recurring:
        label = key.title()[:22]
        newest_first = sorted(rec["tenders"], key=lambda t: t[1], reverse=True)
        ids_by_bucket[label] = [tender_id for tender_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("tenders", tender_id, "tender")
        for ids in ids_by_bucket.values()
        for tender_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids]}
            for label, ids in ids_by_bucket.items()
        ]
    }


def evidence_for_deputation_dissent(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for engagement.deputation_dissent.

    Same population as tests._t_deputation_dissent's own chart: carried
    motions on minutes meetings, split into "With a deputation" / "Without"
    by whether that motion's *meeting* had at least one deputation — not
    whether the deputation relates to that motion at all. The aggregate
    test is a whole-meeting classifier (its own verdict already concedes
    the comparison is confounded by busy meetings having more of both),
    so both buckets export the *contested* motions (votes_against > 0)
    driving the %-contested figure — the same entity type on both sides,
    rather than deputations on one side and motions on the other, which
    would be two different kinds of evidence for the same statistic and
    could read as more directly linked than the test actually claims.
    Capped to `cap` per bucket, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Deputation, Meeting, Motion, MotionOutcome

    dep_meetings = {
        mid for (mid,) in
        session.query(Deputation.meeting_id)
        .join(Meeting, Deputation.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .distinct()
        .all()
    }

    rows = (
        session.query(Motion.id, Motion.meeting_id, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.votes_against > 0,
        )
        .all()
    )

    labels = ["With a deputation", "Without"]
    grouped: dict[str, list[tuple[int, object]]] = {label: [] for label in labels}
    for motion_id, meeting_id, meeting_date in rows:
        label = "With a deputation" if meeting_id in dep_meetings else "Without"
        grouped[label].append((motion_id, meeting_date))

    ids_by_bucket: dict[str, list[int]] = {}
    for label, items in grouped.items():
        newest_first = sorted(items, key=lambda t: t[1], reverse=True)
        ids_by_bucket[label] = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("motions", motion_id, "contested_motion")
        for ids in ids_by_bucket.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_freshman_effect(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.freshman_effect.

    Same population as tests._t_freshman's own chart: votes on carried
    motions (minutes), bucketed "First 12 months" / "Later service" by
    days since that councillor's own first recorded vote. A vote has no
    quote of its own (deliberately out of scope — a vote is never
    independently extracted; its receipt is always the parent motion's
    own text, the same design PowerPanel already uses), so this resolves
    the motion behind each AGAINST vote — the dissent the chart is
    actually about, not the much larger population of FOR votes that also
    count toward the chart's denominator.

    Deduplicated within a bucket: a motion two different freshmen
    dissented on appears once in "First 12 months", not twice. A motion
    CAN legitimately appear in both buckets, though — one that drew
    dissent from both a first-year and a veteran councillor genuinely
    belongs in both, not a duplicate. Capped to `cap` per bucket, newest
    first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Motion, MotionOutcome, Vote, VoteChoice

    rows = (
        session.query(Vote.councillor_id, Vote.choice, Motion.id, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.outcome == MotionOutcome.CARRIED,
        )
        .all()
    )

    first_seen: dict[int, object] = {}
    for cid, _choice, _motion_id, meeting_date in rows:
        if meeting_date and (cid not in first_seen or meeting_date < first_seen[cid]):
            first_seen[cid] = meeting_date

    labels = ["First 12 months", "Later service"]
    grouped: dict[str, dict[int, object]] = {label: {} for label in labels}
    for cid, choice, motion_id, meeting_date in rows:
        if choice != VoteChoice.AGAINST:
            continue
        days = (meeting_date - first_seen[cid]).days if (meeting_date and cid in first_seen) else 9999
        label = "First 12 months" if days <= 365 else "Later service"
        existing = grouped[label].get(motion_id)
        if existing is None or (meeting_date and meeting_date > existing):
            grouped[label][motion_id] = meeting_date

    ids_by_bucket: dict[str, list[int]] = {}
    for label, motions in grouped.items():
        newest_first = sorted(motions.items(), key=lambda kv: kv[1], reverse=True)
        ids_by_bucket[label] = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("motions", motion_id, "dissenting_vote_motion")
        for ids in ids_by_bucket.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_election_cycle(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.election_cycle.

    Same population as tests._t_election_cycle's own chart: votes on
    carried motions (minutes), classified by whether the meeting falls in
    the pre-election window (WA: biennial October elections in odd years,
    window = Apr-Oct of an odd year) or not. Votes have no quote of their
    own (see evidence_for_freshman_effect's docstring); this resolves the
    parent motion behind each AGAINST vote — the dissent the chart is
    about.

    Unlike freshman_effect, the window is a pure function of the meeting
    date, not of any one councillor, so a motion can only ever fall in one
    bucket here — still deduplicated per bucket in case more than one
    councillor dissented on the same motion. Capped to `cap` per bucket,
    newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Motion, MotionOutcome, Vote, VoteChoice

    rows = (
        session.query(Vote.choice, Motion.id, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.outcome == MotionOutcome.CARRIED,
        )
        .all()
    )

    # Same labels as tests._t_election_cycle's own chart, en dash included.
    labels = ["Pre-election (Apr–Oct odd yr)", "Rest of cycle"]
    grouped: dict[str, dict[int, object]] = {label: {} for label in labels}
    for choice, motion_id, meeting_date in rows:
        if choice != VoteChoice.AGAINST or not meeting_date:
            continue
        in_window = (meeting_date.year % 2 == 1) and (4 <= meeting_date.month <= 10)
        label = labels[0] if in_window else labels[1]
        existing = grouped[label].get(motion_id)
        if existing is None or meeting_date > existing:
            grouped[label][motion_id] = meeting_date

    ids_by_bucket: dict[str, list[int]] = {}
    for label, motions in grouped.items():
        newest_first = sorted(motions.items(), key=lambda kv: kv[1], reverse=True)
        ids_by_bucket[label] = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("motions", motion_id, "dissenting_vote_motion")
        for ids in ids_by_bucket.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


def evidence_for_attendance(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for governance.attendance.

    Same population as tests._t_attendance's own chart: ALL votes on
    minutes meetings — no CARRIED-only filter, unlike freshman_effect and
    election_cycle, since this test's own query has none — restricted to
    ABSENT rows, split into "Recusal (declared)" (declared_interest=True)
    and "Genuine absence" (declared_interest=False). This is a composition
    split of the ABSENT subset, not a dissent measure. Votes have no quote
    of their own (see evidence_for_freshman_effect's docstring); this
    resolves the parent motion behind each ABSENT vote.

    A motion with more than one ABSENT voter can have some declared and
    some not — like freshman_effect (and unlike election_cycle), a motion
    can legitimately appear in both buckets; deduplicated within each.
    Capped to `cap` per bucket, newest first.

    `source_cache`: see resolve_evidence().
    """
    from src.models import Meeting, Motion, Vote, VoteChoice

    rows = (
        session.query(Vote.choice, Vote.declared_interest, Motion.id, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )

    labels = ["Recusal (declared)", "Genuine absence"]
    grouped: dict[str, dict[int, object]] = {label: {} for label in labels}
    for choice, declared_interest, motion_id, meeting_date in rows:
        if choice != VoteChoice.ABSENT:
            continue
        label = "Recusal (declared)" if declared_interest else "Genuine absence"
        existing = grouped[label].get(motion_id)
        if existing is None or (meeting_date and meeting_date > existing):
            grouped[label][motion_id] = meeting_date

    ids_by_bucket: dict[str, list[int]] = {}
    for label, motions in grouped.items():
        newest_first = sorted(motions.items(), key=lambda kv: kv[1], reverse=True)
        ids_by_bucket[label] = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [
        ("motions", motion_id, "absent_vote_motion")
        for ids in ids_by_bucket.values()
        for motion_id in ids
    ]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": label, "entries": [entries_by_id[i] for i in ids_by_bucket[label]]}
            for label in labels
        ]
    }


# ---------------------------------------------------------------------------
# The 11 remaining bespoke/generic-panel tests: unlike the tests.<generator>
# group, these have a real query function in src/analysis/queries.py. Some
# already join ExtractionEvidence inside that function (a real cap/order
# already chosen — reused verbatim here rather than re-decided); others have
# no drill-down anywhere yet, same starting point as the tests.<generator>
# group.
# ---------------------------------------------------------------------------

def evidence_for_decider_supplier_conflict(
    session: Session, council_id: int, cap: int = 30,
    source_cache: dict[int, _MeetingSource] | None = None,
) -> dict:
    """Evidence chain for procurement.decider_supplier_conflict.

    "Tender-award votes" bucket: the same keyword-matched tender-award
    motions decider_supplier_conflict()'s own Limb 1 identifies (title/
    motion_text keyword match, minutes only — copied verbatim from that
    function so the population matches exactly) — capped to `cap`, newest
    first. Lets a reader verify the keyword classification itself, since
    that is what the chart's declaration-rate figure is computed over.

    "Chamber base rate" is deliberately an empty bucket: it is a baseline
    over every minutes vote corpus-wide (15,000+), with no notable subset
    to single out — sampling it arbitrarily would not verify anything the
    chart claims, unlike every other bucket in this file.

    Not covered here: the function's own Limb 2 (surname collisions
    between a tender winner and a councillor) is the rarer, more
    interesting finding — and the one the function's own docstring says
    needs a source quote to resolve — but it is never charted (only
    mentioned in prose), so there is no bar a click could reach it from.
    Flagged, not built, since this mechanism is driven by chart-bar
    clicks, not a bespoke third list.

    `source_cache`: see resolve_evidence().
    """
    from sqlalchemy import func

    from src.models import Meeting, Motion

    tender_kw = (
        func.lower(Motion.title).like("%tender%")
        | func.lower(Motion.title).like("% rft %")
        | func.lower(Motion.title).like("rft %")
        | func.lower(Motion.title).like("%contract%award%")
        | func.lower(Motion.motion_text).like("%accept the tender%")
        | func.lower(Motion.motion_text).like("%awards%contract%")
        | func.lower(Motion.motion_text).like("%rft %")
    )
    rows = (
        session.query(Motion.id, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            tender_kw,
        )
        .all()
    )
    newest_first = sorted(rows, key=lambda t: t[1], reverse=True)
    ids = [motion_id for motion_id, _d in newest_first[:cap]]

    refs: list[EntityRef] = [("motions", motion_id, "tender_award_motion") for motion_id in ids]
    entries = resolve_evidence(session, refs, council_id, source_cache)
    entries_by_id = {e["entity_id"]: e for e in entries}

    return {
        "buckets": [
            {"label": "Tender-award votes", "entries": [entries_by_id[i] for i in ids]},
            {"label": "Chamber base rate", "entries": []},
        ]
    }
