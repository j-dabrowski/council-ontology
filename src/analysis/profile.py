"""
S2: the corpus profile (docs/INFORMATION_ARCHITECTURE.md §3).

A scripted, no-LLM pass over an already-extracted corpus that answers "what
does this data actually look like" as one machine-readable document — NULL
rates, document/date spans, identity-resolution state, and record-quality
metrics — instead of the hand-maintained prose in
`docs/investigator/Investigator_prompt.txt` Part 0. Council-agnostic: every
query here is keyed off the ontology's own tables and columns
(`src/models/ontology.py`), not any Cambridge-specific content, so it runs
unchanged against any council loaded into this schema.

`compute_corpus_profile()` is the whole surface; `council profile <council>`
(src/cli.py) is the only caller today. Consumed by later stages once they
exist (S3 discovery feasibility, S7 clean-bill checks) — not wired to either
yet; that's `docs/AGENT_DESIGN.md` §6 Step 5's job.
"""

from __future__ import annotations

from calendar import month_abbr
from dataclasses import asdict, dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models import (
    Appointment,
    BudgetItem,
    BuildingPermit,
    CommitteeReport,
    CommunitySubmission,
    Councillor,
    CouncillorTerm,
    DelegatedDecision,
    Deputation,
    ExtractionEvidence,
    InterestDeclaration,
    Meeting,
    Motion,
    OtherItem,
    Petition,
    PlanningApplication,
    PublicQuestion,
    Tender,
    Vote,
)


@dataclass
class SpanProfile:
    total_documents: int
    by_document_type: dict[str, int]
    date_min: str | None
    date_max: str | None
    meetings_by_year: dict[int, int]
    # "YYYY-MM" strings with zero meetings, within [date_min, date_max] —
    # a candidate-gap signal computed from the data itself, not a
    # hand-maintained list of known corpus gaps.
    zero_meeting_months_in_span: list[str] = field(default_factory=list)


@dataclass
class EntityCounts:
    councillors: int
    meetings: int
    motions: int
    votes: int
    planning_applications: int
    community_submissions: int
    tenders: int
    interest_declarations: int
    deputations: int
    petitions: int
    public_questions: int
    budget_items: int
    appointments: int
    committee_reports: int
    delegated_decisions: int
    building_permits: int
    other_items: int
    extraction_evidence: int


@dataclass
class RecordQuality:
    planning_application_date_null_rate: float | None
    planning_decision_date_null_rate: float | None
    motion_outcome_null_rate: float | None
    vote_declared_interest_rate: float | None
    vote_choice_distribution: dict[str, int]
    councillor_term_coverage_rate: float | None  # of councillors active by vote, share with a term row
    tender_confidential_rate: float | None
    tender_amount_null_rate: float | None
    # distinct submitter_name / total rows — low means mostly generic
    # placeholders ("Adjoining neighbour"), not real identities.
    # Unscoped by council (see compute_corpus_profile docstring note).
    community_submission_distinct_submitter_ratio: float | None


@dataclass
class IdentityResolution:
    councillor_count: int
    with_terms: int
    with_votes: int
    with_neither: int  # zero votes AND zero terms — a "may not be a real councillor" signal
    # councillors sharing an exact (lowercased, trimmed) family_name with
    # another councillor in this set — a "worth reviewing" heuristic, not a
    # definitive split-identity count (see Investigator_prompt.txt §0.4).
    duplicate_family_name_groups: int


@dataclass
class CorpusProfile:
    council: str
    generated_at: str
    span: SpanProfile
    entity_counts: EntityCounts
    record_quality: RecordQuality
    identity_resolution: IdentityResolution


def _count_via_meeting(session: Session, model, council_id: int) -> int:
    return (
        session.query(func.count(model.id))
        .join(Meeting, model.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .scalar()
    ) or 0


def _count_via_motion(session: Session, model, council_id: int) -> int:
    return (
        session.query(func.count(model.id))
        .join(Motion, model.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .scalar()
    ) or 0


def _null_rate_via_motion(session: Session, model, column, council_id: int) -> float | None:
    total = _count_via_motion(session, model, council_id)
    if total == 0:
        return None
    nulls = (
        session.query(func.count(model.id))
        .join(Motion, model.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, column.is_(None))
        .scalar()
    ) or 0
    return round(nulls / total, 3)


def _span_profile(session: Session, council_id: int) -> SpanProfile:
    total = session.query(func.count(Meeting.id)).filter(Meeting.council_id == council_id).scalar() or 0
    by_type = dict(
        session.query(Meeting.document_type, func.count(Meeting.id))
        .filter(Meeting.council_id == council_id)
        .group_by(Meeting.document_type)
        .all()
    )
    date_min, date_max = (
        session.query(func.min(Meeting.meeting_date), func.max(Meeting.meeting_date))
        .filter(Meeting.council_id == council_id)
        .one()
    )
    dates = [
        d for (d,) in session.query(Meeting.meeting_date).filter(Meeting.council_id == council_id).all()
    ]
    by_year: dict[int, int] = {}
    observed_months: set[tuple[int, int]] = set()
    for d in dates:
        by_year[d.year] = by_year.get(d.year, 0) + 1
        observed_months.add((d.year, d.month))

    zero_months: list[str] = []
    if date_min and date_max:
        y, m = date_min.year, date_min.month
        while (y, m) <= (date_max.year, date_max.month):
            if (y, m) not in observed_months:
                zero_months.append(f"{y}-{m:02d} ({month_abbr[m]})")
            m += 1
            if m > 12:
                m = 1
                y += 1

    return SpanProfile(
        total_documents=total,
        by_document_type=by_type,
        date_min=date_min.isoformat() if date_min else None,
        date_max=date_max.isoformat() if date_max else None,
        meetings_by_year=dict(sorted(by_year.items())),
        zero_meeting_months_in_span=zero_months,
    )


def _entity_counts(session: Session, council_id: int) -> EntityCounts:
    active_ids, _with_terms, _with_votes = _identity_ids(session, council_id)
    return EntityCounts(
        councillors=len(active_ids),
        meetings=session.query(func.count(Meeting.id)).filter(Meeting.council_id == council_id).scalar() or 0,
        motions=_count_via_meeting(session, Motion, council_id),
        votes=_count_via_motion(session, Vote, council_id),
        planning_applications=_count_via_motion(session, PlanningApplication, council_id),
        # Not council-scoped: community_submissions links via motion_id OR
        # application_id (both optional), and this project runs a
        # single-council DB today, so an unscoped total is exact in
        # practice. Revisit with a proper two-path join once a second
        # council shares one database.
        community_submissions=session.query(func.count(CommunitySubmission.id)).scalar() or 0,
        tenders=_count_via_meeting(session, Tender, council_id),
        interest_declarations=_count_via_meeting(session, InterestDeclaration, council_id),
        deputations=_count_via_meeting(session, Deputation, council_id),
        petitions=_count_via_meeting(session, Petition, council_id),
        public_questions=_count_via_meeting(session, PublicQuestion, council_id),
        budget_items=_count_via_meeting(session, BudgetItem, council_id),
        appointments=_count_via_meeting(session, Appointment, council_id),
        committee_reports=_count_via_meeting(session, CommitteeReport, council_id),
        delegated_decisions=_count_via_meeting(session, DelegatedDecision, council_id),
        building_permits=_count_via_meeting(session, BuildingPermit, council_id),
        other_items=_count_via_meeting(session, OtherItem, council_id),
        extraction_evidence=_count_via_meeting(session, ExtractionEvidence, council_id),
    )


def _identity_ids(session: Session, council_id: int) -> tuple[set[int], set[int], set[int]]:
    """(all councillor ids active on this council, ids with a term row, ids
    with a vote) — "active" means reachable via either signal, matching the
    union already used elsewhere (src/cli.py's councillor-profile candidate
    set) rather than the electoral-commission-only `councillor_terms` join,
    which is known-incomplete (docs/TESTING.md's Build log references,
    2026-08-23 Fixer commit).
    """
    with_terms = {
        cid for (cid,) in
        session.query(CouncillorTerm.councillor_id.distinct())
        .filter(CouncillorTerm.council_id == council_id).all()
    }
    with_votes = {
        cid for (cid,) in
        session.query(Vote.councillor_id.distinct())
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id).all()
    }
    return with_terms | with_votes, with_terms, with_votes


def _record_quality(session: Session, council_id: int) -> RecordQuality:
    active_ids, with_terms, _with_votes = _identity_ids(session, council_id)

    motion_total = _count_via_meeting(session, Motion, council_id)
    motion_outcome_nulls = (
        session.query(func.count(Motion.id))
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Motion.outcome.is_(None))
        .scalar()
    ) or 0

    vote_total = _count_via_motion(session, Vote, council_id)
    vote_declared = (
        session.query(func.count(Vote.id))
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Vote.declared_interest.is_(True))
        .scalar()
    ) or 0
    choice_rows = (
        session.query(Vote.choice, func.count(Vote.id))
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .group_by(Vote.choice)
        .all()
    )
    choice_dist = {c.value: n for c, n in choice_rows}

    tender_total = _count_via_meeting(session, Tender, council_id)
    tender_confidential = (
        session.query(func.count(Tender.id))
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Tender.is_confidential.is_(True))
        .scalar()
    ) or 0
    tender_amount_nulls = (
        session.query(func.count(Tender.id))
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Tender.amount.is_(None))
        .scalar()
    ) or 0

    sub_total = session.query(func.count(CommunitySubmission.id)).scalar() or 0
    sub_distinct = session.query(func.count(func.distinct(CommunitySubmission.submitter_name))).scalar() or 0

    return RecordQuality(
        planning_application_date_null_rate=_null_rate_via_motion(
            session, PlanningApplication, PlanningApplication.application_date, council_id,
        ),
        planning_decision_date_null_rate=_null_rate_via_motion(
            session, PlanningApplication, PlanningApplication.decision_date, council_id,
        ),
        motion_outcome_null_rate=round(motion_outcome_nulls / motion_total, 3) if motion_total else None,
        vote_declared_interest_rate=round(vote_declared / vote_total, 3) if vote_total else None,
        vote_choice_distribution=choice_dist,
        councillor_term_coverage_rate=(
            round(len(with_terms & active_ids) / len(active_ids), 3) if active_ids else None
        ),
        tender_confidential_rate=round(tender_confidential / tender_total, 3) if tender_total else None,
        tender_amount_null_rate=round(tender_amount_nulls / tender_total, 3) if tender_total else None,
        community_submission_distinct_submitter_ratio=(
            round(sub_distinct / sub_total, 3) if sub_total else None
        ),
    )


def _identity_resolution(session: Session, council_id: int) -> IdentityResolution:
    active_ids, with_terms, with_votes = _identity_ids(session, council_id)
    if not active_ids:
        return IdentityResolution(
            councillor_count=0, with_terms=0, with_votes=0, with_neither=0,
            duplicate_family_name_groups=0,
        )

    with_neither = active_ids - with_terms - with_votes
    names = (
        session.query(Councillor.id, Councillor.family_name)
        .filter(Councillor.id.in_(active_ids)).all()
    )
    by_family: dict[str, set[int]] = {}
    for cid, family_name in names:
        key = (family_name or "").strip().lower()
        if not key:
            continue
        by_family.setdefault(key, set()).add(cid)
    duplicate_groups = sum(1 for ids in by_family.values() if len(ids) > 1)

    return IdentityResolution(
        councillor_count=len(active_ids),
        with_terms=len(with_terms & active_ids),
        with_votes=len(with_votes & active_ids),
        with_neither=len(with_neither),
        duplicate_family_name_groups=duplicate_groups,
    )


def compute_corpus_profile(session: Session, council_id: int, council_key: str, generated_at: str) -> CorpusProfile:
    """The whole S2 pass: one machine-readable document over an
    already-extracted corpus. Read-only; makes no judgement about whether a
    number is "good" — that's for a future consumer (S3 feasibility checks,
    a future records-quality battery test) to interpret.
    """
    return CorpusProfile(
        council=council_key,
        generated_at=generated_at,
        span=_span_profile(session, council_id),
        entity_counts=_entity_counts(session, council_id),
        record_quality=_record_quality(session, council_id),
        identity_resolution=_identity_resolution(session, council_id),
    )


def profile_to_dict(profile: CorpusProfile) -> dict:
    return asdict(profile)
