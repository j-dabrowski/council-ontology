"""
Gold-fact-table views (docs/uplift/migration/02-claim-layer.md Step 2;
target grain declarations docs/uplift/02-claim-layer.md "Gold table grain
declarations").

Additive: plain query functions over the existing raw tables, no schema
migration of `src/models/ontology.py`. Each of the 7 target tables gets a
declared grain (validated via `src.analysis.claims.parse_grain` at import
time, not just asserted in a comment) and a row dataclass. Three tables
(`vote_fact`, `application_fact`, `motion_fact`) map cleanly onto an
existing table already at roughly the right grain; the other four are
missing at least one target attribute the raw schema has no column for —
each gap is called out in that function's own docstring rather than
silently invented, per `00-README.md`'s "no re-running extraction" and
this project's own house rule against false confidence.

Nothing here queries `TestResult`/`tests.py`; a `_t_*` generator starts
reading these views only in Step 6.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.analysis.claims import parse_grain
from src.analysis.queries import _normalise_contractor, contractor_display_names
from src.models import (
    Appointment,
    AttendanceStatus,
    CommunitySubmission,
    InterestDeclaration,
    Meeting,
    MeetingAttendance,
    Motion,
    PlanningApplication,
    PublicQuestion,
    Tender,
    Vote,
    VoteChoice,
)

# ── declared grains ──────────────────────────────────────────────────────
GOLD_GRAINS: dict[str, str] = {
    "vote_fact": "(meeting, item, councillor)",
    "declaration_fact": "(meeting, item, councillor, interest_type)",
    "tender_fact": "(meeting, award)",
    "application_fact": "(application)",
    "question_fact": "(meeting, question)",
    "membership_fact": "(councillor, body, term)",
    "motion_fact": "(meeting, item)",
}

# Fail fast at import time on a typo'd grain string — the same validation
# a real Population.grain would get, run once here rather than trusted.
for _name, _grain in GOLD_GRAINS.items():
    parse_grain(_grain)


# ── vote_fact ────────────────────────────────────────────────────────────

POSITION_FOR = "for"
POSITION_AGAINST = "against"
POSITION_ABSTAIN = "abstain"
POSITION_ABSENT_RECUSAL = "absent_recusal"
POSITION_ABSENT_NON_ATTENDANCE = "absent_non_attendance"
POSITION_ABSENT_UNKNOWN = "absent_unknown"


@dataclass(frozen=True)
class VoteFactRow:
    meeting_id: int
    item_number: str | None
    motion_id: int
    councillor_id: int
    position: str


def _absent_subtype(declared_interest: bool, attendance_status) -> str:
    """Sub-type an ABSENT vote — target grain requires ABSENT split into
    recusal / non_attendance / unknown, not left as one undifferentiated
    bucket. `attendance_status` beats declaration: a councillor recorded
    as an apology for the whole meeting was never going to vote on
    anything in it, declared interest or not. Absent both signals, the
    honest answer is "unknown," not a guess either way.
    """
    if attendance_status == AttendanceStatus.APOLOGY:
        return POSITION_ABSENT_NON_ATTENDANCE
    if declared_interest:
        return POSITION_ABSENT_RECUSAL
    return POSITION_ABSENT_UNKNOWN


def vote_fact(session: Session, council_id: int) -> list[VoteFactRow]:
    """Grain: `(meeting, item, councillor)` — genuinely close to clean
    (`votes` carries `UNIQUE(motion_id, councillor_id)`), but note the
    same caveat `LinkedDeclaredVote` already documents: when a meeting has
    more than one motion sharing an `item_number`, `(meeting, item,
    councillor)` is not itself unique — the true unique key is
    `(motion_id, councillor_id)`, exposed here as `motion_id` alongside
    the declared grain fields rather than silently dropped.
    """
    attendance: dict[tuple[int, int], AttendanceStatus] = {
        (mid, cid): status
        for mid, cid, status in (
            session.query(
                MeetingAttendance.meeting_id, MeetingAttendance.councillor_id, MeetingAttendance.status
            )
            .join(Meeting, MeetingAttendance.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id)
        )
    }
    rows = (
        session.query(
            Meeting.id, Motion.item_number, Motion.id, Vote.councillor_id,
            Vote.choice, Vote.declared_interest,
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    out: list[VoteFactRow] = []
    for meeting_id, item_no, motion_id, cid, choice, declared in rows:
        if choice == VoteChoice.ABSENT:
            position = _absent_subtype(bool(declared), attendance.get((meeting_id, cid)))
        else:
            position = choice.value
        out.append(VoteFactRow(
            meeting_id=meeting_id, item_number=item_no, motion_id=motion_id,
            councillor_id=cid, position=position,
        ))
    return out


# ── declaration_fact ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeclarationFactRow:
    meeting_id: int
    item_reference: str | None
    councillor_id: int | None
    interest_type: str | None
    declaration_id: int
    # None: the s5.68 (council-resolution permission) detector isn't built
    # yet — docs/uplift/migration/04-jurisdiction.md Step 4 is blocked on a
    # human decision about evidentiary standard (see project memory,
    # 2026-09-19). Not False — False would assert "no permission was
    # granted," which this view cannot yet determine.
    s5_68_permission_granted: bool | None = None


def declaration_fact(session: Session, council_id: int) -> list[DeclarationFactRow]:
    """Grain: `(meeting, item, councillor, interest_type)`. No unique
    constraint on this tuple exists in `interest_declarations` today — this
    view does not enforce one, it exposes the raw rows at the declared
    grain so a future linter check (L-06/L-08 style) can detect a
    duplicate itself rather than this view silently deduping.
    """
    rows = (
        session.query(
            InterestDeclaration.id, InterestDeclaration.meeting_id,
            InterestDeclaration.councillor_id, InterestDeclaration.item_reference,
            InterestDeclaration.interest_type,
        )
        .join(Meeting, InterestDeclaration.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    return [
        DeclarationFactRow(
            meeting_id=mid, item_reference=iref, councillor_id=cid,
            interest_type=(itype.value if itype is not None else None),
            declaration_id=did,
        )
        for did, mid, cid, iref, itype in rows
    ]


# ── tender_fact ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TenderFactRow:
    meeting_id: int
    tender_id: int
    reference_number: str | None
    # No canonical-contractor-id table exists — this is the same
    # normalised string key `_normalise_contractor` already produces for
    # `tender_concentration()`/`procurement.incumbency`, reused rather than
    # re-derived, not a real silver-table id (L-17's gap).
    contractor_key: str | None
    contractor_display_name: str | None
    amount: float | None
    value_recorded: bool
    confidential: bool


def tender_fact(session: Session, council_id: int) -> list[TenderFactRow]:
    """Grain: `(meeting, award)` — one row per `Tender`, roughly clean.
    Multi-recipient awards (a single tender text naming more than one
    firm) are not split out — `awarded_to` is treated as one string, same
    limitation `_normalise_contractor` already has everywhere else it's
    used.
    """
    rows = (
        session.query(
            Meeting.id, Tender.id, Tender.reference_number, Tender.awarded_to,
            Tender.amount, Tender.is_confidential,
        )
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    names = [n for _mid, _tid, _ref, n, _a, _c in rows if n]
    display = contractor_display_names(names)
    out: list[TenderFactRow] = []
    for meeting_id, tid, ref, awarded_to, amount, confidential in rows:
        key = _normalise_contractor(awarded_to) if awarded_to else None
        out.append(TenderFactRow(
            meeting_id=meeting_id, tender_id=tid, reference_number=ref,
            contractor_key=key,
            contractor_display_name=display.get(key) if key else None,
            amount=amount, value_recorded=amount is not None,
            confidential=bool(confidential),
        ))
    return out


# ── application_fact ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ApplicationFactRow:
    application_id: int
    reference_number: str | None
    # No canonical applicant id exists (no normaliser analogous to
    # `_normalise_contractor` has ever been built for applicant names) —
    # raw `applicant_name`, not a resolved identity.
    applicant_name: str | None
    value: float | None
    value_recorded: bool
    objector_count: int
    outcome: str | None


def application_fact(session: Session, council_id: int) -> list[ApplicationFactRow]:
    """Grain: `(application)` — one row per `PlanningApplication`, clean
    grain (per `00-codebase-map.md` §3). `objector_count` is a live COUNT
    of linked `CommunitySubmission` rows with `position="object"`, not a
    stored column.
    """
    apps = (
        session.query(
            PlanningApplication.id, PlanningApplication.reference_number,
            PlanningApplication.applicant_name, PlanningApplication.estimated_value,
            PlanningApplication.status,
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    app_ids = [a[0] for a in apps]
    objectors: dict[int, int] = defaultdict(int)
    if app_ids:
        for aid, cnt in (
            session.query(CommunitySubmission.application_id, CommunitySubmission.count)
            .filter(
                CommunitySubmission.application_id.in_(app_ids),
                CommunitySubmission.position == "object",
            )
        ):
            objectors[aid] += cnt if cnt else 1
    return [
        ApplicationFactRow(
            application_id=aid, reference_number=ref, applicant_name=applicant,
            value=value, value_recorded=value is not None,
            objector_count=objectors.get(aid, 0),
            outcome=(status.value if status is not None else None),
        )
        for aid, ref, applicant, value, status in apps
    ]


# ── question_fact ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuestionFactRow:
    meeting_id: int
    question_id: int
    questioner_name: str | None
    # "deferred" is not distinguishable from "unknown" with the current
    # schema — `PublicQuestion` has no status column, only a free-text
    # `response_summary`, so this collapses to answered/unknown until a
    # status field is extracted.
    status: str  # "answered" | "unknown"


def question_fact(session: Session, council_id: int) -> list[QuestionFactRow]:
    """Grain: `(meeting, question)` — one row per `PublicQuestion`."""
    rows = (
        session.query(
            Meeting.id, PublicQuestion.id, PublicQuestion.questioner_name,
            PublicQuestion.response_summary,
        )
        .join(Meeting, PublicQuestion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    return [
        QuestionFactRow(
            meeting_id=mid, question_id=qid, questioner_name=name,
            status="answered" if response else "unknown",
        )
        for mid, qid, name, response in rows
    ]


# ── membership_fact ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class MembershipFactRow:
    councillor_id: int | None
    body_name: str | None
    role: str | None
    meeting_id: int
    appointment_id: int


def membership_fact(session: Session, council_id: int) -> list[MembershipFactRow]:
    """Grain: `(councillor, body, term)` — `term` is aspirational today:
    `Appointment` carries no term_start/term_end of its own, only the
    `meeting_id` the appointment was recorded at. This view exposes that
    meeting as the closest available time anchor rather than inventing a
    term window; joining to `CouncillorTerm` for a real window is future
    work, not done here (per `01-known-defects.md`'s note that this table
    is "populated but underused," not absent).
    """
    rows = (
        session.query(
            Appointment.id, Appointment.councillor_id, Appointment.role,
            Appointment.body_name, Appointment.meeting_id,
        )
        .join(Meeting, Appointment.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    return [
        MembershipFactRow(
            councillor_id=cid, body_name=body, role=role,
            meeting_id=mid, appointment_id=aid,
        )
        for aid, cid, role, body, mid in rows
    ]


# ── motion_fact ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MotionFactRow:
    meeting_id: int
    item_number: str | None
    motion_id: int
    mover_id: int | None
    seconder_id: int | None
    officer_recommendation: str | None
    outcome: str | None
    # None: no stored amendment flag exists, and `officer_divergence()`
    # (src/analysis/divergence.py) cannot detect a motion-text amendment at
    # all today (G-25) — not False, which would assert "confirmed
    # unamended."
    amendment_flag: bool | None = None


def motion_fact(session: Session, council_id: int) -> list[MotionFactRow]:
    """Grain: `(meeting, item)` — one row per `Motion`, clean grain (per
    `00-codebase-map.md` §3), same `(meeting, item)` caveat as `vote_fact`
    when more than one motion in a meeting shares an `item_number`."""
    rows = (
        session.query(
            Meeting.id, Motion.item_number, Motion.id, Motion.moved_by_id,
            Motion.seconded_by_id, Motion.officer_recommendation, Motion.outcome,
        )
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .all()
    )
    return [
        MotionFactRow(
            meeting_id=mid, item_number=item_no, motion_id=motion_id,
            mover_id=mover_id, seconder_id=seconder_id,
            officer_recommendation=rec,
            outcome=(outcome.value if outcome is not None else None),
        )
        for mid, item_no, motion_id, mover_id, seconder_id, rec, outcome in rows
    ]
