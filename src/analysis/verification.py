"""
Document-derived, zero-model verification checks (docs/uplift/migration/
05-verification.md, Steps 1-3 — V-1/V-2/V-3 of the target's 10-layer
verification pyramid).

These three checks are the "load-bearing sentence" the target's own
published-method-text example leads with: a real, document-derived accuracy
anchor that costs nothing to compute, because both sides of every
comparison already sit in the database, extracted once, never compared.
No new extraction, no new pipeline stage, no model call of any kind.

V-1 (`reconcile_stated_tallies`): a motion's stated tally ("CARRIED 8/1")
vs. a COUNT() of its own individual Vote rows.
V-2 (`sweep_contradictions`): five classes of internal self-contradiction —
double-recorded ABSENT+vote, orphan interest declarations, out-of-term
votes, absent mover/seconder, tally exceeding chamber size.
V-3 (`reconcile_cross_document`): agenda-to-minutes item-number matching
(generalised from `officer_divergence()`, the one existing instance of this
class of check) plus tender-value-vs-aggregate and councillor-name-vs-terms
checks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import re

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.models import (
    CommitteeReport,
    Contradiction,
    CouncillorTerm,
    Meeting,
    MeetingAttendance,
    Motion,
    OtherItem,
    Tender,
    Vote,
    VoteChoice,
)
from src.models.ontology import AttendanceStatus, InterestDeclaration

# ---------------------------------------------------------------------------
# V-1: stated-tally reconciliation
# ---------------------------------------------------------------------------

_TALLY_CHOICES = (VoteChoice.FOR, VoteChoice.AGAINST, VoteChoice.ABSTAIN)


@dataclass
class TallyMismatch:
    motion_id: int
    meeting_id: int
    meeting_date: str
    item_number: str | None
    stated_for: int | None
    stated_against: int | None
    stated_abstain: int | None
    counted_for: int
    counted_against: int
    counted_abstain: int


@dataclass
class YearlyTallyStat:
    year: int
    checked: int
    matched: int
    match_rate: float | None  # None below a thin-n floor


@dataclass
class TallyReconciliation:
    total_with_stated_tally: int   # motions with >=1 stated field, minutes only
    checkable: int                 # of those, motions with >=1 individual vote row too
    matched: int
    mismatched: int
    match_rate: float | None       # None if checkable == 0
    by_year: list[YearlyTallyStat] = field(default_factory=list)
    mismatches: list[TallyMismatch] = field(default_factory=list)


def reconcile_stated_tallies(
    session: Session, council_id: int, mismatch_cap: int = 200, min_year_n: int = 5,
) -> TallyReconciliation:
    """V-1. Every minutes motion with a stated tally (`votes_for`/
    `votes_against`/`votes_abstain`, extracted from text like "CARRIED
    (8/1)") is compared against a fresh `COUNT()` of its own `votes` rows,
    grouped by `choice` — the two sides of this comparison have always
    both existed in the database; nothing before this function has ever
    compared them.

    A motion only counts as "checkable" if it has at least one individual
    Vote row to compare against — a stated tally with zero individual
    votes recorded isn't a contradiction, it's simply not checkable (the
    minutes recorded the tally but not the roll call), and is excluded
    from `matched`/`mismatched` rather than counted as either.

    A stated field left null (not extracted) is treated as "not asserted"
    for that field, not as an implicit zero — only fields the extraction
    actually stated a number for are compared.
    """
    rows = (
        session.query(
            Motion.id, Motion.meeting_id, Motion.item_number,
            Motion.votes_for, Motion.votes_against, Motion.votes_abstain,
            Meeting.meeting_date,
        )
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            or_(
                Motion.votes_for.isnot(None),
                Motion.votes_against.isnot(None),
                Motion.votes_abstain.isnot(None),
            ),
        )
        .all()
    )
    total_with_stated_tally = len(rows)
    motion_ids = [r[0] for r in rows]

    counted: dict[int, dict[str, int]] = defaultdict(lambda: {"for": 0, "against": 0, "abstain": 0})
    if motion_ids:
        vote_q = (
            session.query(Vote.motion_id, Vote.choice, func.count(Vote.id))
            .filter(Vote.motion_id.in_(motion_ids), Vote.choice.in_(_TALLY_CHOICES))
            .group_by(Vote.motion_id, Vote.choice)
        )
        for mid, choice, cnt in vote_q:
            counted[mid][choice.value] += cnt

    matched = 0
    mismatched = 0
    mismatches: list[TallyMismatch] = []
    by_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # [checked, matched]

    for mid, meeting_id, item_no, s_for, s_against, s_abstain, mdate in rows:
        c = counted.get(mid)
        has_votes = c is not None and sum(c.values()) > 0
        if not has_votes:
            continue
        c_for, c_against, c_abstain = c["for"], c["against"], c["abstain"]
        is_match = (
            (s_for is None or s_for == c_for)
            and (s_against is None or s_against == c_against)
            and (s_abstain is None or s_abstain == c_abstain)
        )
        year = mdate.year if mdate else None
        if year is not None:
            by_year[year][0] += 1
        if is_match:
            matched += 1
            if year is not None:
                by_year[year][1] += 1
        else:
            mismatched += 1
            if len(mismatches) < mismatch_cap:
                mismatches.append(TallyMismatch(
                    motion_id=mid, meeting_id=meeting_id,
                    meeting_date=mdate.isoformat() if mdate else "",
                    item_number=item_no,
                    stated_for=s_for, stated_against=s_against, stated_abstain=s_abstain,
                    counted_for=c_for, counted_against=c_against, counted_abstain=c_abstain,
                ))

    checkable = matched + mismatched
    year_stats = [
        YearlyTallyStat(
            year=yr, checked=n, matched=m,
            match_rate=round(100 * m / n, 1) if n >= min_year_n else None,
        )
        for yr, (n, m) in sorted(by_year.items())
    ]

    return TallyReconciliation(
        total_with_stated_tally=total_with_stated_tally,
        checkable=checkable,
        matched=matched,
        mismatched=mismatched,
        match_rate=round(100 * matched / checkable, 1) if checkable else None,
        by_year=year_stats,
        mismatches=mismatches,
    )


# ---------------------------------------------------------------------------
# V-2: internal contradiction sweep
# ---------------------------------------------------------------------------

_VOTED_CHOICES = (VoteChoice.FOR, VoteChoice.AGAINST, VoteChoice.ABSTAIN)


@dataclass
class ContradictionClassStat:
    contradiction_class: str
    count: int
    # How many records this check could even examine — None where the
    # concept doesn't apply. Reported alongside the count so a small count
    # is never misread as "clean" when it's really "barely checkable" (the
    # out-of-term and mover/seconder checks are both real ingredient gaps,
    # not full-coverage sweeps — see each helper's own docstring).
    coverage_denominator: int | None
    coverage_note: str


@dataclass
class ContradictionSweep:
    total: int
    by_class: list[ContradictionClassStat] = field(default_factory=list)


def _sweep_absent_and_voted(session: Session, council_id: int) -> tuple[list[Contradiction], ContradictionClassStat]:
    """Class 1: a councillor recorded as an apology for the whole meeting
    (`MeetingAttendance.status == APOLOGY`) yet also cast a real vote
    (FOR/AGAINST/ABSTAIN — not ABSENT) on some motion in that same meeting.
    Requires `MeetingAttendance` data (docs/uplift/migration/
    01-known-defects.md G-09's fix) — covers the ~54% of minutes meetings
    that fix could recover attendance for, not the full corpus.
    """
    apology_pairs = {
        (mid, cid) for mid, cid in (
            session.query(MeetingAttendance.meeting_id, MeetingAttendance.councillor_id)
            .join(Meeting, MeetingAttendance.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id, MeetingAttendance.status == AttendanceStatus.APOLOGY)
            .all()
        )
    }
    out: list[Contradiction] = []
    if apology_pairs:
        meeting_ids = {mid for mid, _ in apology_pairs}
        vote_rows = (
            session.query(Vote.motion_id, Motion.meeting_id, Vote.councillor_id, Vote.choice)
            .join(Motion, Vote.motion_id == Motion.id)
            .filter(Motion.meeting_id.in_(meeting_ids), Vote.choice.in_(_VOTED_CHOICES))
            .all()
        )
        for motion_id, mid, cid, choice in vote_rows:
            if (mid, cid) in apology_pairs:
                out.append(Contradiction(
                    council_id=council_id, contradiction_class="absent_and_voted",
                    meeting_id=mid, motion_id=motion_id, councillor_id=cid,
                    detail=(f"Councillor {cid} has an apology recorded for meeting {mid} "
                            f"but cast a {choice.value} vote on motion {motion_id}"),
                ))
    return out, ContradictionClassStat(
        contradiction_class="absent_and_voted", count=len(out),
        coverage_denominator=len(apology_pairs),
        coverage_note=f"{len(apology_pairs)} apology-marked (meeting, councillor) pairs checked",
    )


def _sweep_orphan_declarations(session: Session, council_id: int) -> tuple[list[Contradiction], ContradictionClassStat]:
    """Class 2: an interest declaration whose `item_reference` doesn't
    match any real motion's `item_number` in the same meeting. Only
    declarations with a non-null `item_reference` are checkable — one with
    no reference at all isn't a contradiction, it's simply unattributed."""
    decl_rows = (
        session.query(InterestDeclaration.id, InterestDeclaration.meeting_id,
                      InterestDeclaration.councillor_id, InterestDeclaration.item_reference)
        .join(Meeting, InterestDeclaration.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, InterestDeclaration.item_reference.isnot(None))
        .all()
    )
    meeting_ids = {mid for _, mid, _, _ in decl_rows}
    items_by_meeting: dict[int, set[str]] = defaultdict(set)
    if meeting_ids:
        for mid, item_no in (
            session.query(Motion.meeting_id, Motion.item_number)
            .filter(Motion.meeting_id.in_(meeting_ids), Motion.item_number.isnot(None))
        ):
            items_by_meeting[mid].add(item_no.strip())

    out: list[Contradiction] = []
    for did, mid, cid, item_ref in decl_rows:
        if item_ref.strip() not in items_by_meeting.get(mid, set()):
            out.append(Contradiction(
                council_id=council_id, contradiction_class="orphan_declaration",
                meeting_id=mid, councillor_id=cid, declaration_id=did,
                detail=f"Declaration {did} references item '{item_ref}', no matching motion in meeting {mid}",
            ))
    return out, ContradictionClassStat(
        contradiction_class="orphan_declaration", count=len(out),
        coverage_denominator=len(decl_rows),
        coverage_note=f"{len(decl_rows)} declarations with a stated item_reference checked",
    )


def _sweep_out_of_term_votes(session: Session, council_id: int) -> tuple[list[Contradiction], ContradictionClassStat]:
    """Class 3: a vote cast on a date outside every one of that councillor's
    known term windows. Excludes councillors with zero CouncillorTerm rows
    entirely from the denominator — `councillor_terms` is thin (125 rows /
    423 councillors per the codebase map), so most votes are structurally
    unable to be checked by this class, not clean by it."""
    terms: dict[int, list[tuple]] = defaultdict(list)
    for cid, start, end in (
        session.query(CouncillorTerm.councillor_id, CouncillorTerm.term_start, CouncillorTerm.term_end)
        .filter(CouncillorTerm.council_id == council_id)
    ):
        terms[cid].append((start, end))

    if not terms:
        return [], ContradictionClassStat(
            contradiction_class="out_of_term_vote", count=0, coverage_denominator=0,
            coverage_note="0 votes checkable — no councillor_terms rows for this council",
        )

    vote_rows = (
        session.query(Vote.id, Vote.motion_id, Motion.meeting_id, Vote.councillor_id, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Vote.councillor_id.in_(terms.keys()))
        .all()
    )
    out: list[Contradiction] = []
    for vid, motion_id, meeting_id, cid, mdate in vote_rows:
        if not mdate:
            continue
        windows = terms[cid]
        in_any = any(
            (start is None or mdate >= start) and (end is None or mdate <= end)
            for start, end in windows
        )
        if not in_any:
            out.append(Contradiction(
                council_id=council_id, contradiction_class="out_of_term_vote",
                meeting_id=meeting_id, motion_id=motion_id, councillor_id=cid,
                detail=f"Vote {vid} by councillor {cid} on {mdate.isoformat()} falls outside every known term window",
            ))
    return out, ContradictionClassStat(
        contradiction_class="out_of_term_vote", count=len(out),
        coverage_denominator=len(vote_rows),
        coverage_note=(f"{len(vote_rows)} votes checkable (councillor has >=1 known term) "
                       f"of {len(terms)} councillors with term data"),
    )


def _sweep_mover_seconder_absent(session: Session, council_id: int) -> tuple[list[Contradiction], ContradictionClassStat]:
    """Class 4: a motion's mover or seconder is not in the PRESENT roster
    for that meeting. Only meetings with at least one `MeetingAttendance`
    row are checkable — a meeting with no attendance data at all is
    excluded from the denominator, not assumed clean."""
    present: dict[int, set[int]] = defaultdict(set)
    known_meetings: set[int] = set()
    for mid, cid, status in (
        session.query(MeetingAttendance.meeting_id, MeetingAttendance.councillor_id, MeetingAttendance.status)
        .join(Meeting, MeetingAttendance.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    ):
        known_meetings.add(mid)
        if status == AttendanceStatus.PRESENT:
            present[mid].add(cid)

    if not known_meetings:
        return [], ContradictionClassStat(
            contradiction_class="mover_seconder_absent", count=0, coverage_denominator=0,
            coverage_note="0 motions checkable — no MeetingAttendance data for this council",
        )

    motion_rows = (
        session.query(Motion.id, Motion.meeting_id, Motion.moved_by_id, Motion.seconded_by_id)
        .filter(Motion.meeting_id.in_(known_meetings))
        .filter(or_(Motion.moved_by_id.isnot(None), Motion.seconded_by_id.isnot(None)))
        .all()
    )
    out: list[Contradiction] = []
    for motion_id, mid, mover_id, seconder_id in motion_rows:
        for role, cid in (("mover", mover_id), ("seconder", seconder_id)):
            if cid is not None and cid not in present.get(mid, set()):
                out.append(Contradiction(
                    council_id=council_id, contradiction_class="mover_seconder_absent",
                    meeting_id=mid, motion_id=motion_id, councillor_id=cid,
                    detail=f"Motion {motion_id}'s {role} (councillor {cid}) is not in meeting {mid}'s present roster",
                ))
    return out, ContradictionClassStat(
        contradiction_class="mover_seconder_absent", count=len(out),
        coverage_denominator=len(motion_rows),
        coverage_note=f"{len(motion_rows)} motions with a mover/seconder in an attendance-tracked meeting",
    )


def _sweep_tally_exceeds_chamber(session: Session, council_id: int) -> tuple[list[Contradiction], ContradictionClassStat]:
    """Class 5: a motion's stated tally total exceeds the number of
    distinct councillors who cast any vote anywhere in that same meeting —
    a data-driven ceiling (no fixed chamber-size table exists or is needed:
    a subset of a meeting's own recorded voters can't outnumber the whole)."""
    meeting_voters: dict[int, set[int]] = defaultdict(set)
    for mid, cid in (
        session.query(Motion.meeting_id, Vote.councillor_id)
        .join(Vote, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    ):
        meeting_voters[mid].add(cid)

    motion_rows = (
        session.query(Motion.id, Motion.meeting_id, Motion.votes_for, Motion.votes_against, Motion.votes_abstain)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            or_(Motion.votes_for.isnot(None), Motion.votes_against.isnot(None), Motion.votes_abstain.isnot(None)),
        )
        .all()
    )
    checkable = [r for r in motion_rows if r[1] in meeting_voters]
    out: list[Contradiction] = []
    for motion_id, mid, s_for, s_against, s_abstain in checkable:
        total = (s_for or 0) + (s_against or 0) + (s_abstain or 0)
        ceiling = len(meeting_voters[mid])
        if total > ceiling:
            out.append(Contradiction(
                council_id=council_id, contradiction_class="tally_exceeds_chamber",
                meeting_id=mid, motion_id=motion_id,
                detail=(f"Motion {motion_id}'s stated tally totals {total}, exceeding the "
                        f"{ceiling} distinct councillors recorded voting anywhere in meeting {mid}"),
            ))
    return out, ContradictionClassStat(
        contradiction_class="tally_exceeds_chamber", count=len(out),
        coverage_denominator=len(checkable),
        coverage_note=f"{len(checkable)} of {len(motion_rows)} stated-tally motions had a meeting-level voter ceiling to check against",
    )


def sweep_contradictions(session: Session, council_id: int, persist: bool = True) -> ContradictionSweep:
    """V-2. Runs all five contradiction classes corpus-wide (not sampled).
    When `persist` is true (the default), clears this council's prior rows
    in `contradictions` and writes the fresh sweep — safe to re-run after
    any re-extraction, additive to the schema, destructive only to this
    table's own prior run for this council.
    """
    sweeps = [
        _sweep_absent_and_voted(session, council_id),
        _sweep_orphan_declarations(session, council_id),
        _sweep_out_of_term_votes(session, council_id),
        _sweep_mover_seconder_absent(session, council_id),
        _sweep_tally_exceeds_chamber(session, council_id),
    ]
    all_rows = [row for rows, _stat in sweeps for row in rows]
    stats = [stat for _rows, stat in sweeps]

    if persist:
        session.query(Contradiction).filter(Contradiction.council_id == council_id).delete(
            synchronize_session=False
        )
        session.add_all(all_rows)
        session.flush()

    return ContradictionSweep(total=len(all_rows), by_class=stats)


# ---------------------------------------------------------------------------
# V-3: cross-document arithmetic (generalises the one existing instance of
# this check class — officer_divergence()'s agenda<->minutes item-number
# matching — and adds the three checks the target names alongside it)
# ---------------------------------------------------------------------------


@dataclass
class CrossDocumentCheck:
    name: str
    checked: int
    reconciled: int
    reconciliation_rate: float | None  # None if checked == 0
    note: str


@dataclass
class CrossDocumentReconciliation:
    checks: list[CrossDocumentCheck] = field(default_factory=list)


def _check_attendance_vs_votes(session: Session, council_id: int) -> CrossDocumentCheck:
    """Attendance lists vs. vote rows: a meeting's PRESENT roster size
    should never be smaller than the number of distinct councillors who
    cast a vote in it — a vote from someone not on the present list means
    one of the two source lists is wrong. Checked only for meetings with
    attendance data at all."""
    present_count: dict[int, int] = {}
    for mid, cnt in (
        session.query(MeetingAttendance.meeting_id, func.count(MeetingAttendance.id))
        .join(Meeting, MeetingAttendance.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, MeetingAttendance.status == AttendanceStatus.PRESENT)
        .group_by(MeetingAttendance.meeting_id)
    ):
        present_count[mid] = cnt

    voter_count: dict[int, int] = {}
    if present_count:
        for mid, cnt in (
            session.query(Motion.meeting_id, func.count(func.distinct(Vote.councillor_id)))
            .join(Vote, Vote.motion_id == Motion.id)
            .filter(Motion.meeting_id.in_(present_count.keys()))
            .group_by(Motion.meeting_id)
        ):
            voter_count[mid] = cnt

    checked = len(present_count)
    reconciled = sum(
        1 for mid, present in present_count.items() if voter_count.get(mid, 0) <= present
    )
    return CrossDocumentCheck(
        name="attendance_vs_votes", checked=checked, reconciled=reconciled,
        reconciliation_rate=round(100 * reconciled / checked, 1) if checked else None,
        note=f"{checked} attendance-tracked meetings; reconciled = distinct voters <= present count",
    )


def _check_agenda_minutes_items(session: Session, council_id: int) -> CrossDocumentCheck:
    """Agenda item numbering vs. minute item numbering — the exact matching
    `officer_divergence()` (`src/analysis/divergence.py`) already proved
    for the officer-recommendation panel, reused (not re-derived) here as a
    general-purpose reconciliation stat: what share of agenda items with an
    officer recommendation found ANY minutes match at all, at any
    confidence, independent of whether that match went on to diverge."""
    from src.analysis.divergence import officer_divergence

    # min_confidence=0.0: count every agenda item that had a minutes
    # counterpart to attempt a match against at all, not just the ones
    # officer_divergence's own 0.5 floor considered confident enough to use.
    pairs = officer_divergence(session, council_id, min_confidence=0.0)
    checked = len(pairs)
    reconciled = sum(1 for p in pairs if p.match_confidence >= 0.5)
    return CrossDocumentCheck(
        name="agenda_minutes_items", checked=checked, reconciled=reconciled,
        reconciliation_rate=round(100 * reconciled / checked, 1) if checked else None,
        note=f"{checked} agenda items with an officer recommendation on a date with a paired minutes document",
    )


_DOLLAR_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*(?:m|million)?", re.IGNORECASE)
_AGGREGATE_HINT_RE = re.compile(r"total|aggregate|combined", re.IGNORECASE)


def _check_tender_aggregates(session: Session, council_id: int) -> CrossDocumentCheck:
    """Tender award values against any stated aggregate in the same
    document. No schema field captures "a stated aggregate figure"
    directly — this scans `OtherItem`/`CommitteeReport` free text for a
    dollar figure near an aggregate-language hint ("total", "aggregate",
    "combined") in the same meeting, and compares it to that meeting's
    summed `Tender.amount`. Exploratory by construction: a near-zero
    checkable count is the honest answer if this corpus's minutes simply
    don't narrate tender totals in prose, not a bug in the check."""
    candidates: list[tuple[int, float]] = []  # (meeting_id, stated aggregate $)
    for meeting_id, text in (
        session.query(OtherItem.meeting_id, OtherItem.description)
        .join(Meeting, OtherItem.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    ):
        if text and _AGGREGATE_HINT_RE.search(text):
            m = _DOLLAR_RE.search(text)
            if m:
                candidates.append((meeting_id, float(m.group(1).replace(",", ""))))
    for meeting_id, text in (
        session.query(CommitteeReport.meeting_id, CommitteeReport.summary)
        .join(Meeting, CommitteeReport.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    ):
        if text and _AGGREGATE_HINT_RE.search(text):
            m = _DOLLAR_RE.search(text)
            if m:
                candidates.append((meeting_id, float(m.group(1).replace(",", ""))))

    checked = len(candidates)
    reconciled = 0
    if candidates:
        meeting_ids = {mid for mid, _ in candidates}
        tender_totals: dict[int, float] = defaultdict(float)
        for mid, amt in (
            session.query(Tender.meeting_id, Tender.amount)
            .filter(Tender.meeting_id.in_(meeting_ids), Tender.amount.isnot(None))
        ):
            tender_totals[mid] += amt
        for mid, stated in candidates:
            actual = tender_totals.get(mid, 0.0)
            if actual and abs(stated - actual) / actual <= 0.05:
                reconciled += 1
    return CrossDocumentCheck(
        name="tender_value_vs_aggregate", checked=checked, reconciled=reconciled,
        reconciliation_rate=round(100 * reconciled / checked, 1) if checked else None,
        note=(f"{checked} candidate stated-aggregate mentions found by scanning free text for "
              "aggregate-language + a dollar figure — no schema field states this directly"),
    )


def _check_councillor_terms_coverage(session: Session, council_id: int) -> CrossDocumentCheck:
    """Councillor names against the councillor-terms table: what share of
    councillors who actually cast a vote for this council have at least
    one CouncillorTerm row at all — a coverage stat on the terms table
    itself, distinct from V-2's per-vote out-of-term-window check."""
    voting_councillor_ids = {
        cid for (cid,) in (
            session.query(Vote.councillor_id.distinct())
            .join(Motion, Vote.motion_id == Motion.id)
            .join(Meeting, Motion.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id)
        )
    }
    with_terms = {
        cid for (cid,) in (
            session.query(CouncillorTerm.councillor_id.distinct())
            .filter(CouncillorTerm.council_id == council_id)
        )
    }
    checked = len(voting_councillor_ids)
    reconciled = len(voting_councillor_ids & with_terms)
    return CrossDocumentCheck(
        name="councillor_names_vs_terms", checked=checked, reconciled=reconciled,
        reconciliation_rate=round(100 * reconciled / checked, 1) if checked else None,
        note=f"{checked} distinct councillors cast >=1 vote; reconciled = has >=1 councillor_terms row",
    )


def reconcile_cross_document(session: Session, council_id: int) -> CrossDocumentReconciliation:
    """V-3. Four checks, none requiring any new extraction:
    attendance-vs-votes, agenda<->minutes item matching (generalised from
    `officer_divergence()`), tender-value-vs-stated-aggregate, and
    councillor-names-vs-terms coverage."""
    return CrossDocumentReconciliation(checks=[
        _check_attendance_vs_votes(session, council_id),
        _check_agenda_minutes_items(session, council_id),
        _check_tender_aggregates(session, council_id),
        _check_councillor_terms_coverage(session, council_id),
    ])
