"""
Query helpers for the council ontology.

These functions operate at the boundary between the three ontology layers:
  Semantic  — who are the actors?
  Kinetic   — what did they do?
  Dynamic   — what patterns emerge?
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models import (
    ApplicationStatus,
    BudgetItem,
    Councillor,
    CouncillorTerm,
    Council,
    CommunitySubmission,
    Deputation,
    ExtractionEvidence,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    Motion,
    MotionOutcome,
    Petition,
    PlanningApplication,
    PublicQuestion,
    Site,
    Tender,
    Vote,
    VoteChoice,
)


def _year_filters(stmt, meeting_model, from_year: int | None, to_year: int | None):
    """Apply optional from_year / to_year filters to a SQLAlchemy statement."""
    from sqlalchemy import extract as sql_extract
    if from_year:
        stmt = stmt.where(sql_extract("year", meeting_model.meeting_date) >= from_year)
    if to_year:
        stmt = stmt.where(sql_extract("year", meeting_model.meeting_date) <= to_year)
    return stmt


def _year_filter_query(query, meeting_model, from_year: int | None, to_year: int | None):
    """Apply optional from_year / to_year filters to a legacy ORM query."""
    from sqlalchemy import extract as sql_extract
    if from_year:
        query = query.filter(sql_extract("year", meeting_model.meeting_date) >= from_year)
    if to_year:
        query = query.filter(sql_extract("year", meeting_model.meeting_date) <= to_year)
    return query


# ---------------------------------------------------------------------------
# Semantic layer queries
# ---------------------------------------------------------------------------


def get_council_by_name(session: Session, short_name: str) -> Council | None:
    return session.query(Council).filter_by(short_name=short_name).first()


def list_councillors(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_votes: int = 0,
) -> list[tuple[Councillor, int]]:
    """All councillors who have appeared in a vote, with their vote count."""
    q = (
        session.query(Councillor, func.count(Vote.id).label("n"))
        .join(Vote, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    q = q.group_by(Councillor.id).order_by(func.count(Vote.id).desc())
    rows = q.all()
    if min_votes:
        rows = [(c, n) for c, n in rows if n >= min_votes]
    return rows


# ---------------------------------------------------------------------------
# Semantic layer — councillor activity
# ---------------------------------------------------------------------------


@dataclass
class CouncillorActivity:
    councillor_id: int
    given_name: str
    family_name: str
    first_vote_date: date
    last_vote_date: date
    total_votes: int
    is_active: bool
    dissent_rate: float


def councillor_activity_ranges(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_votes: int = 10,
) -> list[CouncillorActivity]:
    """
    Per-councillor activity summary: date span, vote count, active status,
    and dissent rate (fraction of votes cast against a motion that carried).

    min_votes=10 suppresses AGM proxy voters (1-7 votes, single meeting).
    """

    # Base vote query
    base = (
        session.query(
            Councillor.id,
            Councillor.given_name,
            Councillor.family_name,
            func.min(Meeting.meeting_date).label("first"),
            func.max(Meeting.meeting_date).label("last"),
            func.count(Vote.id).label("total"),
        )
        .join(Vote, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    )
    base = _year_filter_query(base, Meeting, from_year, to_year)
    base = base.group_by(Councillor.id)
    rows = base.all()

    # Dissent: votes AGAINST on a motion that CARRIED
    dissent_q = (
        session.query(Vote.councillor_id, func.count(Vote.id).label("n"))
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Vote.choice == VoteChoice.AGAINST,
            Motion.outcome == MotionOutcome.CARRIED,
        )
    )
    dissent_q = _year_filter_query(dissent_q, Meeting, from_year, to_year)
    dissent_q = dissent_q.group_by(Vote.councillor_id)
    dissent_map: dict[int, int] = {cid: n for cid, n in dissent_q.all()}

    cutoff = date.today() - timedelta(days=548)  # ~18 months
    results = []
    for cid, given, family, first, last, total in rows:
        if total < min_votes:
            continue
        dissent = dissent_map.get(cid, 0)
        results.append(
            CouncillorActivity(
                councillor_id=cid,
                given_name=given or "",
                family_name=family or "",
                first_vote_date=first,
                last_vote_date=last,
                total_votes=total,
                is_active=last >= cutoff,
                dissent_rate=dissent / total if total else 0.0,
            )
        )
    results.sort(key=lambda r: r.total_votes, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Kinetic layer queries
# ---------------------------------------------------------------------------


def meetings_in_range(
    session: Session, council_id: int, start: date, end: date
) -> list[Meeting]:
    return (
        session.query(Meeting)
        .filter(
            Meeting.council_id == council_id,
            Meeting.meeting_date >= start,
            Meeting.meeting_date <= end,
        )
        .order_by(Meeting.meeting_date)
        .all()
    )


def motions_by_tag(
    session: Session,
    council_id: int,
    tag: str,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[Motion]:
    """Find motions whose tag list contains the given tag (case-insensitive)."""
    q = (
        session.query(Motion)
        .join(Meeting)
        .filter(
            Meeting.council_id == council_id,
            Motion.tags.ilike(f"%{tag}%"),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    return q.order_by(Meeting.meeting_date.desc()).all()


def planning_motions(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[Motion]:
    return motions_by_tag(session, council_id, "planning", from_year, to_year)


def contested_motions(
    session: Session,
    council_id: int,
    min_against: int = 2,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[Motion]:
    """Motions that passed but had meaningful opposition."""
    q = (
        session.query(Motion)
        .join(Meeting)
        .filter(
            Meeting.council_id == council_id,
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.votes_against >= min_against,
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    return q.order_by(Motion.votes_against.desc()).all()


# ---------------------------------------------------------------------------
# Kinetic layer — contestation and topic trends
# ---------------------------------------------------------------------------


@dataclass
class YearContestationStats:
    year: int
    total_carried: int
    contested: int
    contestation_rate: float
    most_contested: list[tuple[str, int]] = field(default_factory=list)


def contestation_by_year(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[YearContestationStats]:
    """Contestation rate (carried motions with ≥1 against) per year, minutes only."""
    from sqlalchemy import case

    q = (
        session.query(
            func.strftime("%Y", Meeting.meeting_date).label("yr"),
            func.count(Motion.id).label("total"),
            func.sum(
                case((Motion.votes_against >= 1, 1), else_=0)
            ).label("contested"),
        )
        .join(Motion, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.outcome == MotionOutcome.CARRIED,
            Meeting.document_type == "minutes",
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = q.group_by("yr").order_by("yr").all()

    # For each year, grab the top 3 most-contested motions
    results = []
    for yr_str, total, contested in rows:
        yr = int(yr_str)
        top_q = (
            session.query(Motion.title, Motion.votes_against)
            .join(Meeting, Motion.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Motion.outcome == MotionOutcome.CARRIED,
                Meeting.document_type == "minutes",
                Motion.votes_against >= 1,
                func.strftime("%Y", Meeting.meeting_date) == yr_str,
            )
            .order_by(Motion.votes_against.desc())
            .limit(3)
            .all()
        )
        results.append(
            YearContestationStats(
                year=yr,
                total_carried=total,
                contested=contested or 0,
                contestation_rate=(contested or 0) / total if total else 0.0,
                most_contested=[(t, n) for t, n in top_q],
            )
        )
    return results


def topic_distribution_by_year(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    top_tags: int = 8,
) -> dict[int, dict[str, int]]:
    """
    Returns {year: {tag: count}} for motions with non-null tags.

    Tags are comma-separated in the DB; split and counted per tag.
    Only the top_tags most frequent tags across the corpus are tracked;
    everything else is binned as 'other'.
    """
    q = (
        session.query(
            func.strftime("%Y", Meeting.meeting_date).label("yr"),
            Motion.tags,
        )
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.tags.isnot(None),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = q.all()

    # First pass: find the top_tags most frequent tags overall
    global_counts: dict[str, int] = defaultdict(int)
    parsed: list[tuple[int, list[str]]] = []
    for yr_str, tags_str in rows:
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        parsed.append((int(yr_str), tags))
        for tag in tags:
            global_counts[tag] += 1

    keep = {t for t, _ in sorted(global_counts.items(), key=lambda x: -x[1])[:top_tags]}

    # Second pass: bucket per year
    dist: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for yr, tags in parsed:
        for tag in tags:
            bucket = tag if tag in keep else "other"
            dist[yr][bucket] += 1

    return {yr: dict(counts) for yr, counts in sorted(dist.items())}


# ---------------------------------------------------------------------------
# Kinetic layer — co-mover pairs
# ---------------------------------------------------------------------------


@dataclass
class CoMoverPair:
    mover_id: int
    mover_name: str
    seconder_id: int
    seconder_name: str
    count: int


def co_mover_pairs(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_count: int = 5,
    active_only: bool = False,
) -> list[CoMoverPair]:
    """Pairs of (mover, seconder) ordered by frequency of co-proposing."""
    Mover = Councillor.__class__  # noqa — alias trick doesn't work; use explicit aliases
    from sqlalchemy.orm import aliased

    Mover = aliased(Councillor, name="mover")
    Seconder = aliased(Councillor, name="seconder")

    q = (
        session.query(
            Motion.moved_by_id,
            Motion.seconded_by_id,
            Mover.given_name,
            Mover.family_name,
            Seconder.given_name,
            Seconder.family_name,
            func.count(Motion.id).label("n"),
        )
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .join(Mover, Motion.moved_by_id == Mover.id)
        .join(Seconder, Motion.seconded_by_id == Seconder.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.moved_by_id.isnot(None),
            Motion.seconded_by_id.isnot(None),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    q = q.group_by(Motion.moved_by_id, Motion.seconded_by_id).having(
        func.count(Motion.id) >= min_count
    ).order_by(func.count(Motion.id).desc())
    rows = q.all()

    if active_only:
        active_ids = {
            a.councillor_id
            for a in councillor_activity_ranges(session, council_id, min_votes=1)
            if a.is_active
        }
        rows = [r for r in rows if r[0] in active_ids and r[1] in active_ids]

    return [
        CoMoverPair(
            mover_id=mid,
            seconder_id=sid,
            mover_name=f"{mg} {mf}".strip(),
            seconder_name=f"{sg} {sf}".strip(),
            count=n,
        )
        for mid, sid, mg, mf, sg, sf, n in rows
    ]


# ---------------------------------------------------------------------------
# Kinetic layer — interest declarations
# ---------------------------------------------------------------------------


@dataclass
class InterestSummary:
    councillor_id: int
    councillor_name: str
    total: int
    by_type: dict[str, int]
    top_topics: list[str]


def interest_declarations_summary(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[InterestSummary]:
    """Per-councillor interest declaration counts, broken down by type."""
    # Counts by councillor and type
    type_q = (
        session.query(
            InterestDeclaration.councillor_id,
            InterestDeclaration.interest_type,
            func.count(InterestDeclaration.id).label("n"),
        )
        .join(Meeting, InterestDeclaration.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            InterestDeclaration.councillor_id.isnot(None),
        )
    )
    type_q = _year_filter_query(type_q, Meeting, from_year, to_year)
    type_rows = type_q.group_by(
        InterestDeclaration.councillor_id, InterestDeclaration.interest_type
    ).all()

    # Accumulate by councillor
    by_cid: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[int, int] = defaultdict(int)
    for cid, itype, n in type_rows:
        key = itype.value if itype else "other"
        by_cid[cid][key] += n
        totals[cid] += n

    if not totals:
        return []

    # Councillor names
    cids = list(totals.keys())
    name_rows = session.query(Councillor.id, Councillor.given_name, Councillor.family_name).filter(
        Councillor.id.in_(cids)
    ).all()
    names = {cid: f"{g} {f}".strip() for cid, g, f in name_rows}

    # Top motion topics where each councillor declared (via meeting join → motions)
    # Approximation: tags from all motions in meetings where this councillor declared
    topic_q = (
        session.query(
            InterestDeclaration.councillor_id,
            Motion.tags,
        )
        .join(Meeting, InterestDeclaration.meeting_id == Meeting.id)
        .join(Motion, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            InterestDeclaration.councillor_id.isnot(None),
            Motion.tags.isnot(None),
        )
    )
    topic_q = _year_filter_query(topic_q, Meeting, from_year, to_year)
    topic_rows = topic_q.all()

    topic_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid, tags_str in topic_rows:
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                topic_counts[cid][tag] += 1

    results = []
    for cid in sorted(totals, key=lambda c: -totals[c]):
        top = sorted(topic_counts[cid].items(), key=lambda x: -x[1])[:3]
        results.append(
            InterestSummary(
                councillor_id=cid,
                councillor_name=names.get(cid, f"#{cid}"),
                total=totals[cid],
                by_type=dict(by_cid[cid]),
                top_topics=[t for t, _ in top],
            )
        )
    return results


# ---------------------------------------------------------------------------
# Kinetic layer — public engagement
# ---------------------------------------------------------------------------


@dataclass
class EngagementStats:
    year: int
    public_questions: int
    deputations: int
    petitions: int
    total: int


def public_engagement_by_year(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[EngagementStats]:
    """Public questions, deputations, and petitions per year (minutes only)."""

    def _count_by_year(model):
        q = (
            session.query(
                func.strftime("%Y", Meeting.meeting_date).label("yr"),
                func.count(model.id).label("n"),
            )
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Meeting.document_type == "minutes",
            )
        )
        q = _year_filter_query(q, Meeting, from_year, to_year)
        return {int(yr): n for yr, n in q.group_by("yr").all()}

    questions = _count_by_year(PublicQuestion)
    deputations = _count_by_year(Deputation)
    petitions = _count_by_year(Petition)

    all_years = sorted(set(questions) | set(deputations) | set(petitions))
    return [
        EngagementStats(
            year=yr,
            public_questions=questions.get(yr, 0),
            deputations=deputations.get(yr, 0),
            petitions=petitions.get(yr, 0),
            total=questions.get(yr, 0) + deputations.get(yr, 0) + petitions.get(yr, 0),
        )
        for yr in all_years
    ]


# ---------------------------------------------------------------------------
# Kinetic layer — budget
# ---------------------------------------------------------------------------


@dataclass
class BudgetYearStats:
    year: int
    total_items: int
    items_with_amount: int
    total_amount: float | None
    largest_items: list[tuple[str, float]]


def budget_by_year(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    top_n: int = 5,
) -> list[BudgetYearStats]:
    """Budget items per year: count, total amount (with caveats), top items."""
    from sqlalchemy import case

    q = (
        session.query(
            func.strftime("%Y", Meeting.meeting_date).label("yr"),
            func.count(BudgetItem.id).label("total"),
            func.sum(case((BudgetItem.amount.isnot(None), 1), else_=0)).label("with_amt"),
            func.sum(BudgetItem.amount).label("total_amt"),
        )
        .join(Meeting, BudgetItem.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = q.group_by("yr").order_by("yr").all()

    results = []
    for yr_str, total, with_amt, total_amt in rows:
        yr = int(yr_str)
        top_q = (
            session.query(BudgetItem.description, BudgetItem.amount)
            .join(Meeting, BudgetItem.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Meeting.document_type == "minutes",
                BudgetItem.amount.isnot(None),
                func.strftime("%Y", Meeting.meeting_date) == yr_str,
            )
            .order_by(BudgetItem.amount.desc())
            .limit(top_n)
            .all()
        )
        results.append(
            BudgetYearStats(
                year=yr,
                total_items=total,
                items_with_amount=with_amt or 0,
                total_amount=total_amt,
                largest_items=[(desc or "—", amt) for desc, amt in top_q],
            )
        )
    return results


# ---------------------------------------------------------------------------
# Kinetic layer — planning outcomes
# ---------------------------------------------------------------------------


@dataclass
class PlanningOutcomes:
    total: int
    approved: int
    refused: int
    deferred: int
    pending: int
    approval_rate: float
    top_sites: list[tuple[str, int]]
    top_applicants: list[tuple[str, int]]


def planning_outcomes(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    limit: int = 10,
) -> PlanningOutcomes:
    """Planning application outcome breakdown + top sites and applicants."""
    from src.models.ontology import ApplicationStatus

    q = (
        session.query(
            PlanningApplication.status,
            func.count(PlanningApplication.id).label("n"),
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    status_rows = q.group_by(PlanningApplication.status).all()

    counts: dict[str | None, int] = {s: n for s, n in status_rows}
    approved = counts.get(ApplicationStatus.APPROVED, 0)
    refused = counts.get(ApplicationStatus.REFUSED, 0)
    deferred = counts.get(ApplicationStatus.DEFERRED, 0)
    pending = counts.get(ApplicationStatus.PENDING, 0)
    total = sum(counts.values())
    decided = approved + refused
    approval_rate = approved / decided if decided else 0.0

    # Top sites
    site_q = (
        session.query(Site.address, func.count(PlanningApplication.id).label("n"))
        .join(PlanningApplication, PlanningApplication.site_id == Site.id)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Site.council_id == council_id)
    )
    site_q = _year_filter_query(site_q, Meeting, from_year, to_year)
    top_sites = [
        (addr, n)
        for addr, n in site_q.group_by(Site.id)
        .order_by(func.count(PlanningApplication.id).desc())
        .limit(limit)
        .all()
    ]

    # Top applicants
    app_q = (
        session.query(PlanningApplication.applicant_name, func.count(PlanningApplication.id).label("n"))
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.applicant_name.isnot(None),
        )
    )
    app_q = _year_filter_query(app_q, Meeting, from_year, to_year)
    top_applicants = [
        (name, n)
        for name, n in app_q.group_by(PlanningApplication.applicant_name)
        .order_by(func.count(PlanningApplication.id).desc())
        .limit(limit)
        .all()
    ]

    return PlanningOutcomes(
        total=total,
        approved=approved,
        refused=refused,
        deferred=deferred,
        pending=pending,
        approval_rate=approval_rate,
        top_sites=top_sites,
        top_applicants=top_applicants,
    )


# ---------------------------------------------------------------------------
# Dynamic layer — voting alignment patterns
# ---------------------------------------------------------------------------


@dataclass
class VotingAlignment:
    councillor_a: str
    councillor_b: str
    total_shared_votes: int
    agreements: int
    agreement_rate: float


def voting_alignment_matrix(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[VotingAlignment]:
    """
    Compute pairwise voting agreement between all councillors.

    Returns a list of VotingAlignment records sorted by agreement_rate descending.
    Useful for detecting blocs/coalitions (dynamic layer).
    """
    stmt = (
        select(
            Vote.motion_id,
            Vote.councillor_id,
            Vote.choice,
            Councillor.given_name,
            Councillor.family_name,
        )
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .where(Meeting.council_id == council_id)
        .where(Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]))
    )
    stmt = _year_filters(stmt, Meeting, from_year, to_year)
    rows = session.execute(stmt).all()

    # Build motion → {councillor_id: (choice, name)} map
    motion_votes: dict[int, dict[int, tuple[str, str, str]]] = {}
    for motion_id, cid, choice, given, family in rows:
        if motion_id not in motion_votes:
            motion_votes[motion_id] = {}
        motion_votes[motion_id][cid] = (choice, given, family)

    # Accumulate pairwise stats
    pair_totals: dict[tuple[int, int], int] = {}
    pair_agrees: dict[tuple[int, int], int] = {}
    pair_names: dict[tuple[int, int], tuple[str, str]] = {}

    for votes in motion_votes.values():
        cids = sorted(votes.keys())
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                a, b = cids[i], cids[j]
                pair = (a, b)
                choice_a, given_a, family_a = votes[a]
                choice_b, given_b, family_b = votes[b]
                pair_totals[pair] = pair_totals.get(pair, 0) + 1
                if choice_a == choice_b:
                    pair_agrees[pair] = pair_agrees.get(pair, 0) + 1
                pair_names[pair] = (
                    f"{given_a} {family_a}",
                    f"{given_b} {family_b}",
                )

    results: list[VotingAlignment] = []
    for pair, total in pair_totals.items():
        agrees = pair_agrees.get(pair, 0)
        name_a, name_b = pair_names[pair]
        results.append(
            VotingAlignment(
                councillor_a=name_a,
                councillor_b=name_b,
                total_shared_votes=total,
                agreements=agrees,
                agreement_rate=agrees / total if total else 0.0,
            )
        )

    results.sort(key=lambda r: r.agreement_rate, reverse=True)
    return results


def councillor_vote_summary(
    session: Session,
    councillor_id: int,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> dict:
    """Summary stats for a single councillor."""
    base = (
        session.query(Vote)
        .join(Motion)
        .join(Meeting)
        .filter(
            Vote.councillor_id == councillor_id,
            Meeting.council_id == council_id,
        )
    )
    base = _year_filter_query(base, Meeting, from_year, to_year)
    total = base.count()
    for_count = base.filter(Vote.choice == VoteChoice.FOR).count()
    against_count = base.filter(Vote.choice == VoteChoice.AGAINST).count()
    abstain_count = base.filter(Vote.choice == VoteChoice.ABSTAIN).count()
    interests = base.filter(Vote.declared_interest == True).count()  # noqa: E712

    return {
        "total_votes": total,
        "for": for_count,
        "against": against_count,
        "abstain": abstain_count,
        "declared_interests": interests,
        "dissent_rate": against_count / total if total else 0.0,
    }


def top_planning_sites(
    session: Session,
    council_id: int,
    limit: int = 20,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[tuple[str, int]]:
    """Sites with the most planning applications, ordered by count."""
    q = (
        session.query(Site.address, func.count(PlanningApplication.id).label("n"))
        .join(PlanningApplication, PlanningApplication.site_id == Site.id)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Site.council_id == council_id)
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = (
        q.group_by(Site.id)
        .order_by(func.count(PlanningApplication.id).desc())
        .limit(limit)
        .all()
    )
    return [(address, n) for address, n in rows]


# ---------------------------------------------------------------------------
# Planning trend + objection-effectiveness queries
# ---------------------------------------------------------------------------


@dataclass
class PlanningYearStats:
    year: int
    n_applications: int
    decided: int
    approved: int
    refused: int
    approval_pct: float


def planning_trend_by_year(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[PlanningYearStats]:
    """Planning application volume and approval rate per calendar year."""
    from sqlalchemy import case

    q = (
        session.query(
            func.strftime("%Y", Meeting.meeting_date).label("yr"),
            func.count(PlanningApplication.id).label("total"),
            func.sum(case((PlanningApplication.status == ApplicationStatus.APPROVED, 1), else_=0)).label("approved"),
            func.sum(case((PlanningApplication.status == ApplicationStatus.REFUSED, 1), else_=0)).label("refused"),
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = q.group_by("yr").order_by("yr").all()

    results = []
    for yr_str, total, approved, refused in rows:
        approved = approved or 0
        refused = refused or 0
        decided = approved + refused
        results.append(PlanningYearStats(
            year=int(yr_str),
            n_applications=total or 0,
            decided=decided,
            approved=approved,
            refused=refused,
            approval_pct=round(100 * approved / decided, 1) if decided else 0.0,
        ))
    return results


@dataclass
class PlanningObjectionStats:
    with_objection_n: int
    with_objection_approved: int
    with_objection_refused: int
    with_objection_pct: float
    no_objection_n: int
    no_objection_approved: int
    no_objection_refused: int
    no_objection_pct: float


def planning_objection_stats(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> PlanningObjectionStats:
    """Approval rate split by whether the application received community objections."""
    # Load all decided applications for this council
    q = (
        session.query(PlanningApplication.id, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    decided = q.all()

    if not decided:
        return PlanningObjectionStats(0, 0, 0, 0.0, 0, 0, 0, 0.0)

    app_ids = [row[0] for row in decided]

    # Which of those have at least one objection?
    objection_app_ids = {
        row[0] for row in
        session.query(CommunitySubmission.application_id)
        .filter(
            CommunitySubmission.application_id.in_(app_ids),
            CommunitySubmission.position == "object",
        )
        .distinct()
        .all()
    }

    with_obj: dict[str, int] = {"n": 0, "approved": 0, "refused": 0}
    no_obj: dict[str, int] = {"n": 0, "approved": 0, "refused": 0}

    for app_id, status in decided:
        bucket = with_obj if app_id in objection_app_ids else no_obj
        bucket["n"] += 1
        if status == ApplicationStatus.APPROVED:
            bucket["approved"] += 1
        else:
            bucket["refused"] += 1

    def _pct(d: dict) -> float:
        return round(100 * d["approved"] / d["n"], 1) if d["n"] else 0.0

    return PlanningObjectionStats(
        with_objection_n=with_obj["n"],
        with_objection_approved=with_obj["approved"],
        with_objection_refused=with_obj["refused"],
        with_objection_pct=_pct(with_obj),
        no_objection_n=no_obj["n"],
        no_objection_approved=no_obj["approved"],
        no_objection_refused=no_obj["refused"],
        no_objection_pct=_pct(no_obj),
    )


# ---------------------------------------------------------------------------
# Dissent analysis queries
# ---------------------------------------------------------------------------


@dataclass
class DissenterProfile:
    councillor_id: int
    name: str
    total_votes_on_carried: int
    against_count: int
    dissent_rate: float
    is_active: bool
    top_dissent_tags: list[str]


def dissent_profiles(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_votes: int = 50,
) -> list[DissenterProfile]:
    """Per-councillor dissent rate on carried motions, with top topics dissented on."""
    from sqlalchemy import case as sa_case

    # Votes on CARRIED motions: total and against count, plus last vote date for active flag
    q = (
        session.query(
            Vote.councillor_id,
            Councillor.given_name,
            Councillor.family_name,
            func.count(Vote.id).label("total"),
            func.sum(sa_case((Vote.choice == VoteChoice.AGAINST, 1), else_=0)).label("against"),
            func.max(Meeting.meeting_date).label("last_vote"),
        )
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.outcome == MotionOutcome.CARRIED,
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = [
        r for r in q.group_by(Vote.councillor_id).all()
        if r[3] >= min_votes
    ]

    if not rows:
        return []

    # Top dissent tags per councillor: tags from motions they voted AGAINST (still CARRIED)
    cid_list = [r[0] for r in rows]
    tag_q = (
        session.query(Vote.councillor_id, Motion.tags)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Vote.councillor_id.in_(cid_list),
            Vote.choice == VoteChoice.AGAINST,
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.tags.isnot(None),
        )
    )
    tag_q = _year_filter_query(tag_q, Meeting, from_year, to_year)

    tag_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for cid, tags_str in tag_q.all():
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag_counts[cid][tag] += 1

    cutoff = date.today() - timedelta(days=548)  # ~18 months

    results = []
    for cid, given, family, total, against, last_vote in rows:
        against = against or 0
        top_tags = [t for t, _ in sorted(tag_counts[cid].items(), key=lambda x: -x[1])[:3]]
        results.append(DissenterProfile(
            councillor_id=cid,
            name=f"{given or ''} {family or ''}".strip(),
            total_votes_on_carried=total,
            against_count=against,
            dissent_rate=round(against / total, 4),
            is_active=last_vote >= cutoff if last_vote else False,
            top_dissent_tags=top_tags,
        ))

    results.sort(key=lambda r: r.dissent_rate, reverse=True)
    return results


@dataclass
class DissentPair:
    id_a: int
    name_a: str
    id_b: int
    name_b: str
    shared_dissent: int


def dissent_coalition_pairs(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_count: int = 10,
) -> list[DissentPair]:
    """Pairs of councillors who most often voted AGAINST the same carried motions."""
    from sqlalchemy.orm import aliased
    from sqlalchemy import and_

    V2 = aliased(Vote, name="v2")
    C1 = aliased(Councillor, name="c1")
    C2 = aliased(Councillor, name="c2")

    q = (
        session.query(
            Vote.councillor_id.label("cid_a"),
            V2.councillor_id.label("cid_b"),
            C1.given_name.label("gn_a"),
            C1.family_name.label("fn_a"),
            C2.given_name.label("gn_b"),
            C2.family_name.label("fn_b"),
            func.count().label("n"),
        )
        .join(V2, and_(
            V2.motion_id == Vote.motion_id,
            V2.councillor_id > Vote.councillor_id,
            V2.choice == VoteChoice.AGAINST,
        ))
        .join(Motion, Motion.id == Vote.motion_id)
        .join(Meeting, Meeting.id == Motion.meeting_id)
        .join(C1, C1.id == Vote.councillor_id)
        .join(C2, C2.id == V2.councillor_id)
        .filter(
            Meeting.council_id == council_id,
            Vote.choice == VoteChoice.AGAINST,
            Motion.outcome == MotionOutcome.CARRIED,
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    q = (
        q.group_by(Vote.councillor_id, V2.councillor_id)
        .having(func.count() >= min_count)
        .order_by(func.count().desc())
    )

    return [
        DissentPair(
            id_a=cid_a,
            name_a=f"{gn_a or ''} {fn_a or ''}".strip(),
            id_b=cid_b,
            name_b=f"{gn_b or ''} {fn_b or ''}".strip(),
            shared_dissent=n,
        )
        for cid_a, cid_b, gn_a, fn_a, gn_b, fn_b, n in q.all()
    ]


# ---------------------------------------------------------------------------
# Voting power — who wins on a split council?
# ---------------------------------------------------------------------------

@dataclass
class ContestedVoteDetail:
    """One contested vote a councillor cast, expanded for the drill-down drawer."""
    date: str                  # YYYY-MM-DD
    item: str | None           # agenda item number
    title: str | None          # the motion title
    choice: str                # "For" / "Against"
    outcome: str               # "Carried" / "Lost"
    won: bool                  # voted on the winning side
    margin: int | None         # votes_for − votes_against
    quote: str | None          # verbatim minute text (extraction_evidence, motions)


@dataclass
class PowerProfile:
    councillor_id: int
    name: str
    n: int                              # contested votes cast (FOR/AGAINST)
    win_rate: float                     # share on the winning side
    dissent_rate: float                 # share voted AGAINST
    dissent_n: int                      # number of AGAINST votes
    dissent_effectiveness: float | None  # of AGAINST votes, share where motion LOST
    is_active: bool
    n_shown: int = 0                    # contested votes inlined for the drill-down
    votes: list[ContestedVoteDetail] = field(default_factory=list)


@dataclass
class PowerTermPoint:
    term: str
    win_rate: float
    n: int


@dataclass
class PowerOverTime:
    name: str
    points: list[PowerTermPoint] = field(default_factory=list)


@dataclass
class VotingPowerStats:
    profiles: list[PowerProfile]
    base_carry_rate: float   # share of contested motions that still carried (~pure-FOR win rate)
    base_fail_rate: float    # share that failed — the chance baseline for dissent effectiveness
    n_contested: int
    over_time: list[PowerOverTime] = field(default_factory=list)


# Four-year council terms (vote data only densifies from the 2003 election on).
_POWER_TERMS = [
    ("2003-07", date(2003, 5, 1), date(2007, 10, 1)),
    ("2007-11", date(2007, 10, 1), date(2011, 10, 1)),
    ("2011-15", date(2011, 10, 1), date(2015, 10, 1)),
    ("2015-19", date(2015, 10, 1), date(2019, 10, 1)),
    ("2019-23", date(2019, 10, 1), date(2023, 10, 1)),
    ("2023-27", date(2023, 10, 1), date(2027, 10, 1)),
]


def _populate_contested_votes(session, council_id, profiles, cap: int = 50) -> None:
    """Attach each profiled councillor's most-recent contested votes for the drawer.

    Drives off the same contested motions the spectrum bar is built from (motion
    drew an AGAINST vote and CARRIED/LOST; the councillor cast FOR/AGAINST), so the
    drawer matches the bar. Capped to ``cap`` most recent per councillor (the full
    count stays on PowerProfile.n). Receipt: a verbatim minute quote on the motion.
    """
    if not profiles:
        return
    ids = [p.councillor_id for p in profiles]

    rows = (
        session.query(
            Vote.councillor_id, Vote.choice,
            Motion.id, Motion.item_number, Motion.title, Motion.outcome,
            Motion.votes_for, Motion.votes_against, Meeting.meeting_date,
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.votes_against > 0,
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
            Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]),
            Vote.councillor_id.in_(ids),
        )
        .all()
    )

    by_councillor: dict[int, list[tuple]] = defaultdict(list)
    for cid, choice, mid, item, title, outcome, vf, va, mdate in rows:
        by_councillor[cid].append((cid, choice, mid, item, title, outcome, vf, va, mdate))

    # Most recent `cap` per councillor; collect their motion ids for the receipts.
    capped: dict[int, list[tuple]] = {}
    motion_ids: list[int] = []
    for cid in ids:
        rs = sorted(by_councillor.get(cid, []),
                    key=lambda r: r[8] or date.min, reverse=True)[:cap]
        capped[cid] = rs
        motion_ids.extend(r[2] for r in rs)

    quote_by_motion: dict[int, str] = {}
    if motion_ids:
        for mid, q in (
            session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text)
            .filter(
                ExtractionEvidence.entity_table == "motions",
                ExtractionEvidence.entity_id.in_(motion_ids),
                ExtractionEvidence.quote_text.isnot(None),
            )
        ):
            quote_by_motion.setdefault(mid, q)

    for p in profiles:
        details = []
        for _cid, choice, mid, item, title, outcome, vf, va, mdate in capped.get(p.councillor_id, []):
            won = (choice == VoteChoice.FOR and outcome == MotionOutcome.CARRIED) or \
                  (choice == VoteChoice.AGAINST and outcome == MotionOutcome.LOST)
            margin = (vf - va) if vf is not None and va is not None else None
            details.append(ContestedVoteDetail(
                date=mdate.isoformat() if mdate else "",
                item=item,
                title=title,
                choice="For" if choice == VoteChoice.FOR else "Against",
                outcome="Carried" if outcome == MotionOutcome.CARRIED else "Lost",
                won=won,
                margin=margin,
                quote=quote_by_motion.get(mid),
            ))
        p.votes = details
        p.n_shown = len(details)


def voting_power(
    session: Session,
    council_id: int,
    min_votes: int = 30,
    min_dissents: int = 15,
) -> VotingPowerStats:
    """
    Who wins on contested decisions?

    Over every motion that drew at least one AGAINST vote and CARRIED or was
    LOST, classify each councillor's vote as on the winning side (FOR a carried
    motion, or AGAINST a lost one) or not. Reports per councillor:
      - win_rate: share of their contested votes on the winning side
      - dissent_rate / dissent_effectiveness: how often they vote AGAINST, and
        of those, how often the motion actually failed (their objection prevailed)

    The chance baseline for dissent effectiveness is the overall fail rate
    (~24%): a councillor above it lands genuine opposition; below it, they
    object to things that pass anyway. Win rate's baseline is the carry rate
    (~76%) — what a councillor who simply voted FOR on everything would score.
    """
    rows = (
        session.query(
            Vote.councillor_id,
            Councillor.given_name,
            Councillor.family_name,
            Vote.choice,
            Motion.outcome,
            Meeting.meeting_date,
        )
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.votes_against > 0,
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
            Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]),
        )
        .all()
    )

    # Base rates over the contested motions themselves (not vote rows).
    contested = (
        session.query(Motion.outcome, func.count(Motion.id))
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.votes_against > 0,
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
        )
        .group_by(Motion.outcome)
        .all()
    )
    n_contested = sum(c for _, c in contested)
    carried = sum(c for o, c in contested if o == MotionOutcome.CARRIED)
    base_carry_rate = round(carried / n_contested, 4) if n_contested else 0.0
    base_fail_rate = round(1 - base_carry_rate, 4)

    cutoff = date.today() - timedelta(days=548)  # ~18 months

    agg: dict[int, dict] = defaultdict(lambda: {
        "name": "", "n": 0, "win": 0, "diss": 0, "diss_win": 0,
        "last": None, "terms": defaultdict(lambda: [0, 0]),  # term -> [n, win]
    })

    for cid, given, family, choice, outcome, mdate in rows:
        a = agg[cid]
        a["name"] = f"{given or ''} {family or ''}".strip()
        a["n"] += 1
        won = (choice == VoteChoice.FOR and outcome == MotionOutcome.CARRIED) or \
              (choice == VoteChoice.AGAINST and outcome == MotionOutcome.LOST)
        if won:
            a["win"] += 1
        if choice == VoteChoice.AGAINST:
            a["diss"] += 1
            if outcome == MotionOutcome.LOST:
                a["diss_win"] += 1
        if mdate and (a["last"] is None or mdate > a["last"]):
            a["last"] = mdate
        # term bucket
        if mdate:
            for label, ts, te in _POWER_TERMS:
                if ts <= mdate < te:
                    bucket = a["terms"][label]
                    bucket[0] += 1
                    if won:
                        bucket[1] += 1
                    break

    profiles: list[PowerProfile] = []
    over_raw: list[tuple[int, dict]] = []
    for cid, a in agg.items():
        name = a["name"]
        if a["n"] < min_votes or "unknown" in name.lower() or not name:
            continue
        profiles.append(PowerProfile(
            councillor_id=cid,
            name=name,
            n=a["n"],
            win_rate=round(a["win"] / a["n"], 4),
            dissent_rate=round(a["diss"] / a["n"], 4),
            dissent_n=a["diss"],
            dissent_effectiveness=(round(a["diss_win"] / a["diss"], 4)
                                   if a["diss"] >= min_dissents else None),
            is_active=a["last"] >= cutoff if a["last"] else False,
        ))
        over_raw.append((cid, a))

    profiles.sort(key=lambda p: p.win_rate)
    _populate_contested_votes(session, council_id, profiles, cap=50)

    # Power over time: long-servers active across >=3 terms, top by total votes.
    over_time: list[PowerOverTime] = []
    over_raw.sort(key=lambda x: -x[1]["n"])
    for cid, a in over_raw:
        pts = [
            PowerTermPoint(term=label, win_rate=round(w / n, 4), n=n)
            for label in (t[0] for t in _POWER_TERMS)
            for (n, w) in [a["terms"].get(label, [0, 0])]
            if n >= 10
        ]
        if len(pts) >= 3:
            over_time.append(PowerOverTime(name=a["name"], points=pts))
        if len(over_time) >= 6:
            break

    return VotingPowerStats(
        profiles=profiles,
        base_carry_rate=base_carry_rate,
        base_fail_rate=base_fail_rate,
        n_contested=n_contested,
        over_time=over_time,
    )


@dataclass
class TagContestationStats:
    tag: str
    total_carried: int
    contested: int
    contestation_rate: float


def contestation_by_tag(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_motions: int = 20,
) -> list[TagContestationStats]:
    """Contestation rate broken down by motion topic tag (minutes only)."""
    q = (
        session.query(Motion.tags, Motion.votes_against)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.tags.isnot(None),
            Meeting.document_type == "minutes",
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)

    tag_total: dict[str, int] = defaultdict(int)
    tag_contested: dict[str, int] = defaultdict(int)

    for tags_str, votes_against in q.all():
        is_contested = (votes_against or 0) >= 1
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag_total[tag] += 1
                if is_contested:
                    tag_contested[tag] += 1

    results = [
        TagContestationStats(
            tag=tag,
            total_carried=total,
            contested=tag_contested.get(tag, 0),
            contestation_rate=round(tag_contested.get(tag, 0) / total, 4),
        )
        for tag, total in tag_total.items()
        if total >= min_motions
    ]
    results.sort(key=lambda r: r.contestation_rate, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Conflict of interest — recusal behaviour
# ---------------------------------------------------------------------------


@dataclass
class DeclarationDetail:
    """One declared-interest vote, expanded for the drill-down drawer."""
    date: str                  # YYYY-MM-DD
    item: str | None           # agenda item number / reference
    title: str | None          # the motion title
    interest_type: str | None  # financial / proximity / impartiality / other (best-effort)
    what: str | None           # the actual interest description — "what it is"
    action: str                # "Stepped out" / "Stayed — voted for" / "Stayed — voted against"
    must_leave: bool           # financial/proximity legally require leaving
    quote: str | None          # verbatim minute text (extraction_evidence)


@dataclass
class RecusalProfile:
    councillor_id: int
    name: str
    declared_votes: int
    recused: int          # ABSENT on a declared-interest vote = stepped out
    recusal_rate: float
    is_active: bool
    declarations: list[DeclarationDetail] = field(default_factory=list)


@dataclass
class ConflictRecusalStats:
    # Headline contrast: recusal & against rates for declared vs not-declared
    declared_total: int
    declared_recused: int
    declared_recusal_pct: float
    declared_against_pct: float       # of votes actually cast (FOR/AGAINST)
    baseline_total: int
    baseline_recusal_pct: float
    baseline_against_pct: float
    profiles: list[RecusalProfile] = field(default_factory=list)


_MUST_LEAVE_TYPES = {InterestDeclarationType.FINANCIAL, InterestDeclarationType.PROXIMITY}


def _enum_str(v) -> str | None:
    """Render an enum/str interest_type as a plain lowercase word."""
    if v is None:
        return None
    return getattr(v, "value", str(v))


def _populate_declaration_details(session, council_id, profiles, from_year, to_year) -> None:
    """Attach the per-vote drill-down list to each RecusalProfile.

    Drives off the councillor's declared-interest VOTES (so the drawer matches the
    bar), then enriches each with the interest TYPE, the DESCRIPTION ("what it is")
    and a verbatim minute QUOTE by a meeting-scoped link to interest_declarations
    (item_reference == motion.item_number within the same meeting — the [19] join).
    Falls back to the vote's own interest_description where no declaration matches.
    """
    if not profiles:
        return
    ids = [p.councillor_id for p in profiles]

    # 1. declared-interest votes for the profiled councillors
    vq = (
        session.query(
            Vote.councillor_id, Vote.choice, Vote.interest_description,
            Motion.item_number, Motion.title, Meeting.id, Meeting.meeting_date,
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Vote.declared_interest == True,  # noqa: E712
            Vote.councillor_id.in_(ids),
        )
    )
    vq = _year_filter_query(vq, Meeting, from_year, to_year)

    # 2. declarations for those councillors, keyed for a meeting-scoped item match
    decls = (
        session.query(
            InterestDeclaration.id, InterestDeclaration.councillor_id,
            InterestDeclaration.meeting_id, InterestDeclaration.item_reference,
            InterestDeclaration.interest_type, InterestDeclaration.description,
        )
        .filter(InterestDeclaration.councillor_id.in_(ids))
        .all()
    )
    decl_by_key: dict[tuple, tuple] = {}
    decl_ids: list[int] = []
    for did, cid, mid, iref, itype, desc in decls:
        decl_ids.append(did)
        if iref:
            decl_by_key[(cid, mid, iref)] = (did, itype, desc)

    # 3. one representative minute quote per declaration
    quote_by_decl: dict[int, str] = {}
    if decl_ids:
        for did, q in (
            session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text)
            .filter(
                ExtractionEvidence.entity_table == "interest_declarations",
                ExtractionEvidence.entity_id.in_(decl_ids),
                ExtractionEvidence.quote_text.isnot(None),
            )
        ):
            quote_by_decl.setdefault(did, q)

    by_councillor: dict[int, list[DeclarationDetail]] = {cid: [] for cid in ids}
    for cid, choice, vote_desc, item_no, title, mid, mdate in vq:
        matched = decl_by_key.get((cid, mid, item_no)) if item_no else None
        itype = _enum_str(matched[1]) if matched else None
        what = (matched[2] if matched and matched[2] else None) or vote_desc
        quote = quote_by_decl.get(matched[0]) if matched else None
        must_leave = bool(matched and matched[1] in _MUST_LEAVE_TYPES)
        if choice == VoteChoice.ABSENT:
            action = "Stepped out"
        elif choice == VoteChoice.AGAINST:
            action = "Stayed — voted against"
        elif choice == VoteChoice.FOR:
            action = "Stayed — voted for"
        else:
            action = "Stayed"
        by_councillor.setdefault(cid, []).append(DeclarationDetail(
            date=mdate.isoformat() if mdate else "",
            item=item_no,
            title=title,
            interest_type=itype,
            what=what,
            action=action,
            must_leave=must_leave,
            quote=quote,
        ))

    for p in profiles:
        rows = by_councillor.get(p.councillor_id, [])
        rows.sort(key=lambda d: d.date, reverse=True)
        p.declarations = rows


def conflict_recusal_stats(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_declared: int = 8,
) -> ConflictRecusalStats:
    """
    How declaring a conflict of interest changes voting behaviour.

    Uses Vote.declared_interest as ground truth. A vote of ABSENT on a
    declared-interest item is read as a recusal (the councillor stepped out).
    Returns the declared-vs-baseline contrast plus per-councillor recusal
    rates for councillors with at least ``min_declared`` declared votes.
    """
    from sqlalchemy import case as sa_case

    def _bucket(declared: bool):
        q = (
            session.query(
                func.count(Vote.id).label("total"),
                func.sum(sa_case((Vote.choice == VoteChoice.ABSENT, 1), else_=0)).label("absent"),
                func.sum(sa_case((Vote.choice == VoteChoice.AGAINST, 1), else_=0)).label("against"),
                func.sum(sa_case((Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]), 1), else_=0)).label("cast"),
            )
            .join(Motion, Vote.motion_id == Motion.id)
            .join(Meeting, Motion.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Vote.declared_interest == declared,  # noqa: E712
            )
        )
        q = _year_filter_query(q, Meeting, from_year, to_year)
        total, absent, against, cast = q.one()
        total = total or 0
        absent = absent or 0
        against = against or 0
        cast = cast or 0
        return total, absent, against, cast

    d_total, d_absent, d_against, d_cast = _bucket(True)
    b_total, b_absent, b_against, b_cast = _bucket(False)

    # Per-councillor recusal rate on declared votes
    prof_q = (
        session.query(
            Vote.councillor_id,
            Councillor.given_name,
            Councillor.family_name,
            func.count(Vote.id).label("declared"),
            func.sum(sa_case((Vote.choice == VoteChoice.ABSENT, 1), else_=0)).label("recused"),
            func.max(Meeting.meeting_date).label("last_vote"),
        )
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Vote.declared_interest == True,  # noqa: E712
        )
    )
    prof_q = _year_filter_query(prof_q, Meeting, from_year, to_year)
    prof_rows = prof_q.group_by(Vote.councillor_id).all()

    cutoff = date.today() - timedelta(days=548)  # ~18 months
    profiles = []
    for cid, given, family, declared, recused, last_vote in prof_rows:
        if declared < min_declared:
            continue
        recused = recused or 0
        profiles.append(RecusalProfile(
            councillor_id=cid,
            name=f"{given or ''} {family or ''}".strip(),
            declared_votes=declared,
            recused=recused,
            recusal_rate=round(recused / declared, 4) if declared else 0.0,
            is_active=last_vote >= cutoff if last_vote else False,
        ))
    # Sort by recusal rate desc, then by declared count desc
    profiles.sort(key=lambda r: (r.recusal_rate, r.declared_votes), reverse=True)

    _populate_declaration_details(session, council_id, profiles, from_year, to_year)

    return ConflictRecusalStats(
        declared_total=d_total,
        declared_recused=d_absent,
        declared_recusal_pct=round(100 * d_absent / d_total, 1) if d_total else 0.0,
        declared_against_pct=round(100 * d_against / d_cast, 1) if d_cast else 0.0,
        baseline_total=b_total,
        baseline_recusal_pct=round(100 * b_absent / b_total, 1) if b_total else 0.0,
        baseline_against_pct=round(100 * b_against / b_cast, 1) if b_cast else 0.0,
        profiles=profiles,
    )


# ---------------------------------------------------------------------------
# Tenders — where the money went
# ---------------------------------------------------------------------------


def _normalise_contractor(name: str) -> str:
    """Collapse spelling/whitespace/suffix variants so 'R J Vincent' == 'RJ Vincent'."""
    n = name.lower().strip()
    for suffix in (" pty ltd", " pty. ltd.", " pty ltd.", " ltd", " pty", " p/l"):
        n = n.replace(suffix, "")
    n = n.replace(".", "").replace(",", "")
    n = "".join(n.split())  # drop all internal whitespace: 'r j vincent' -> 'rjvincent'
    return n


@dataclass
class TenderAward:
    """One award to a contractor, expanded for the drill-down drawer."""
    date: str                   # YYYY-MM-DD
    description: str | None
    amount: float
    reference: str | None
    is_confidential: bool
    quote: str | None           # verbatim minute text (extraction_evidence)


@dataclass
class ContractorTotal:
    name: str
    n_awards: int
    total_amount: float
    awards: list[TenderAward] = field(default_factory=list)


@dataclass
class TenderConcentration:
    total_awards: int          # awards with a known amount
    total_amount: float
    named_awards: int
    named_amount: float
    redacted_awards: int       # confidential "Respondent N" placeholders + unnamed
    redacted_amount: float
    distinct_named: int
    top10_amount: float
    top10_share: float         # top-10 contractors' share of the named dollars
    contractors: list[ContractorTotal] = field(default_factory=list)


def tender_concentration(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    limit: int = 15,
) -> TenderConcentration:
    """
    Concentration of tendered spend among contractors.

    Splits the corpus into *named* contractors and the confidential
    "Respondent N" placeholders used in closed tender reports, then ranks
    named contractors by total awarded dollars (spelling variants merged).
    """
    q = (
        session.query(
            Tender.id, Tender.awarded_to, Tender.amount,
            Tender.description, Tender.reference_number, Tender.is_confidential,
            Meeting.meeting_date,
        )
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Tender.amount.isnot(None),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year)
    rows = q.all()

    total_amount = 0.0
    total_awards = 0
    redacted_awards = 0       # confidential "Respondent N" or no named recipient
    redacted_amount = 0.0
    agg_amount: dict[str, float] = defaultdict(float)
    agg_count: dict[str, int] = defaultdict(int)
    display_name: dict[str, str] = {}
    # raw award rows per contractor key, for the drill-down on the top contractors
    awards_by_key: dict[str, list[tuple]] = defaultdict(list)

    for tid, awarded_to, amount, desc, ref, conf, mdate in rows:
        amount = float(amount or 0)
        total_amount += amount
        total_awards += 1
        name = (awarded_to or "").strip()
        key = _normalise_contractor(name) if name else ""
        if not key or name.lower().startswith("respondent"):
            redacted_awards += 1
            redacted_amount += amount
            continue
        agg_amount[key] += amount
        agg_count[key] += 1
        awards_by_key[key].append((tid, amount, desc, ref, bool(conf), mdate))
        # Keep the longest spelling seen as the display label
        if awarded_to.strip() and len(awarded_to.strip()) > len(display_name.get(key, "")):
            display_name[key] = awarded_to.strip()

    named_amount = sum(agg_amount.values())
    named_awards = sum(agg_count.values())

    ranked = sorted(agg_amount.items(), key=lambda kv: -kv[1])
    top10_amount = sum(amt for _, amt in ranked[:10])
    top_keys = [key for key, _ in ranked[:limit]]

    # one representative minute quote per tender, for the drill-down receipts
    quote_by_tender: dict[int, str] = {}
    top_tender_ids = [a[0] for key in top_keys for a in awards_by_key[key]]
    if top_tender_ids:
        for tid, qt in (
            session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text)
            .filter(
                ExtractionEvidence.entity_table == "tenders",
                ExtractionEvidence.entity_id.in_(top_tender_ids),
                ExtractionEvidence.quote_text.isnot(None),
            )
        ):
            quote_by_tender.setdefault(tid, qt)

    contractors = []
    for key in top_keys:
        awards = sorted(
            awards_by_key[key], key=lambda a: a[5] or date.min, reverse=True
        )
        contractors.append(ContractorTotal(
            name=display_name.get(key, key),
            n_awards=agg_count[key],
            total_amount=round(agg_amount[key]),
            awards=[
                TenderAward(
                    date=mdate.isoformat() if mdate else "",
                    description=desc,
                    amount=round(amt),
                    reference=ref,
                    is_confidential=conf,
                    quote=quote_by_tender.get(tid),
                )
                for tid, amt, desc, ref, conf, mdate in awards
            ],
        ))

    return TenderConcentration(
        total_awards=total_awards,
        total_amount=round(total_amount),
        named_awards=named_awards,
        named_amount=round(named_amount),
        redacted_awards=redacted_awards,
        redacted_amount=round(redacted_amount),
        distinct_named=len(agg_amount),
        top10_amount=round(top10_amount),
        top10_share=round(top10_amount / named_amount, 4) if named_amount else 0.0,
        contractors=contractors,
    )


# ---------------------------------------------------------------------------
# Objection dose-response — how many objectors does it take to sink a DA?
# ---------------------------------------------------------------------------

@dataclass
class ObjectionDoseBucket:
    label: str          # "0", "1", "2-4", "5+"
    n: int              # decided applications in this bucket
    refused: int
    refusal_pct: float


@dataclass
class ObjectionDoseStats:
    buckets: list[ObjectionDoseBucket]
    total_decided: int
    max_objections: int          # most objections seen on any single decided app
    headline_examples: list[str] = field(default_factory=list)  # high-objector refusals


def objection_dose_response(session: Session, council_id: int) -> ObjectionDoseStats:
    """
    Refusal rate as a function of *how many* community objections an application
    drew. The existing objection panel treats objection as binary; this asks
    whether there is a threshold where neighbour opposition starts to bite.

    Buckets: 0, 1, 2-4, 5+ objectors. Decided applications only (APPROVED /
    REFUSED). Objections = community_submissions with position='object'.
    """
    rows = (
        session.query(
            PlanningApplication.id,
            PlanningApplication.status,
            PlanningApplication.description,
            PlanningApplication.reference_number,
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
            PlanningApplication.status.in_(
                [ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]
            ),
        )
        .group_by(PlanningApplication.id)
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
    agg: dict[str, list[int]] = {k: [0, 0] for k in order}  # [n, refused]
    max_obj = 0
    examples: list[tuple[int, str]] = []
    for _id, status, desc, ref, n_obj in rows:
        n_obj = int(n_obj or 0)
        max_obj = max(max_obj, n_obj)
        refused = status == ApplicationStatus.REFUSED
        b = _bucket(n_obj)
        agg[b][0] += 1
        agg[b][1] += 1 if refused else 0
        if n_obj >= 5 and refused:
            examples.append((n_obj, (desc or ref or "").strip()))

    buckets = [
        ObjectionDoseBucket(
            label=k,
            n=agg[k][0],
            refused=agg[k][1],
            refusal_pct=round(100 * agg[k][1] / agg[k][0], 1) if agg[k][0] else 0.0,
        )
        for k in order
    ]
    examples.sort(key=lambda e: -e[0])
    headline = [f"{n} objectors — {txt[:80]}" for n, txt in examples[:4]]

    return ObjectionDoseStats(
        buckets=buckets,
        total_decided=sum(b.n for b in buckets),
        max_objections=max_obj,
        headline_examples=headline,
    )


# ---------------------------------------------------------------------------
# Transparency — share of council business decided behind closed doors
# ---------------------------------------------------------------------------

@dataclass
class TransparencyYear:
    year: int
    total: int
    confidential: int
    confidential_pct: float


@dataclass
class TransparencyStats:
    years: list[TransparencyYear]
    pre_era_pct: float          # avg confidential % 1995-2017
    peak_year: int
    peak_pct: float
    category_totals: dict[str, dict[str, int]]  # {tenders: {total, confidential}, ...}


def transparency_by_year(session: Session, council_id: int) -> TransparencyStats:
    """
    Share of decided council items recorded as confidential, per year.

    Pools four item types that carry an is_confidential flag — tenders,
    'other items', delegated decisions and budget items — over minutes (not
    agendas). Surfaces whether the proportion of business taken behind closed
    doors has shifted over the 30-year record.
    """
    from sqlalchemy import text as sql_text

    sql = sql_text(
        """
        WITH allitems AS (
            SELECT m.meeting_date d, t.is_confidential c, 'tenders' AS cat
              FROM tenders t JOIN meetings m ON t.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
            UNION ALL
            SELECT m.meeting_date, o.is_confidential, 'other'
              FROM other_items o JOIN meetings m ON o.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
            UNION ALL
            SELECT m.meeting_date, dd.is_confidential, 'delegated'
              FROM delegated_decisions dd JOIN meetings m ON dd.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
            UNION ALL
            SELECT m.meeting_date, b.is_confidential, 'budget'
              FROM budget_items b JOIN meetings m ON b.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
        )
        SELECT CAST(substr(d, 1, 4) AS INTEGER) yr,
               cat,
               COUNT(*) tot,
               SUM(CASE WHEN c THEN 1 ELSE 0 END) conf
          FROM allitems
         WHERE d IS NOT NULL
         GROUP BY yr, cat
        """
    )
    rows = session.execute(sql, {"cid": council_id}).fetchall()

    per_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])  # [total, conf]
    cat_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confidential": 0})
    for yr, cat, tot, conf in rows:
        per_year[yr][0] += tot
        per_year[yr][1] += conf or 0
        cat_totals[cat]["total"] += tot
        cat_totals[cat]["confidential"] += conf or 0

    years = [
        TransparencyYear(
            year=yr,
            total=tot,
            confidential=conf,
            confidential_pct=round(100 * conf / tot, 1) if tot else 0.0,
        )
        for yr, (tot, conf) in sorted(per_year.items())
    ]

    # Pre-2018 baseline (the two-decade norm) vs the peak year
    pre = [y for y in years if y.year <= 2017]
    pre_tot = sum(y.total for y in pre)
    pre_conf = sum(y.confidential for y in pre)
    pre_pct = round(100 * pre_conf / pre_tot, 1) if pre_tot else 0.0
    # Peak by % among years with a meaningful sample (>= 50 items)
    eligible = [y for y in years if y.total >= 50]
    peak = max(eligible, key=lambda y: y.confidential_pct) if eligible else years[-1]

    return TransparencyStats(
        years=years,
        pre_era_pct=pre_pct,
        peak_year=peak.year,
        peak_pct=peak.confidential_pct,
        category_totals=dict(cat_totals),
    )


# ---------------------------------------------------------------------------
# Tenure — career councillors vs one-term blow-ins
# ---------------------------------------------------------------------------

@dataclass
class TenureProfile:
    name: str
    years: float
    n_votes: int
    first: str          # YYYY-MM
    last: str
    is_active: bool


@dataclass
class TenureStats:
    profiles: list[TenureProfile]       # longest-serving first
    histogram: dict[str, int]           # service-length buckets
    median_years: float
    n_councillors: int


def councillor_tenure(session: Session, council_id: int, min_votes: int = 20) -> TenureStats:
    """
    Length of service per councillor, derived from the span of their recorded
    votes (councillor_terms is too sparse to use directly). Returns a
    longest-serving leaderboard plus a histogram of service length.
    """
    rows = (
        session.query(
            Councillor.given_name,
            Councillor.family_name,
            func.count(Vote.id).label("n"),
            func.min(Meeting.meeting_date).label("first"),
            func.max(Meeting.meeting_date).label("last"),
        )
        .join(Vote, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .group_by(Councillor.id)
        .having(func.count(Vote.id) >= min_votes)
        .all()
    )

    cutoff = date.today() - timedelta(days=548)  # ~18 months
    profiles: list[TenureProfile] = []
    for given, family, n, first, last in rows:
        name = f"{given or ''} {family or ''}".strip()
        if "unknown" in name.lower() or not first or not last:
            continue  # drop mis-split / undated identities
        yrs = (last.year + last.month / 12) - (first.year + first.month / 12)
        profiles.append(TenureProfile(
            name=name,
            years=round(yrs, 1),
            n_votes=n,
            first=first.strftime("%Y-%m"),
            last=last.strftime("%Y-%m"),
            is_active=last >= cutoff,
        ))

    profiles.sort(key=lambda p: p.years, reverse=True)

    buckets = {"<2y": 0, "2-5y": 0, "5-10y": 0, "10-15y": 0, "15y+": 0}
    for p in profiles:
        if p.years < 2:
            buckets["<2y"] += 1
        elif p.years < 5:
            buckets["2-5y"] += 1
        elif p.years < 10:
            buckets["5-10y"] += 1
        elif p.years < 15:
            buckets["10-15y"] += 1
        else:
            buckets["15y+"] += 1

    spans = sorted(p.years for p in profiles)
    n = len(spans)
    median = spans[n // 2] if n % 2 else (spans[n // 2 - 1] + spans[n // 2]) / 2 if n else 0.0

    return TenureStats(
        profiles=profiles,
        histogram=buckets,
        median_years=round(median, 1),
        n_councillors=n,
    )


# ---------------------------------------------------------------------------
# Mayoral agenda-setting — does the chamber fall in line behind the Mayor?
# ---------------------------------------------------------------------------

@dataclass
class MayorContest:
    name: str
    carried: int          # carried motions moved while serving as Mayor
    contested: int        # of those, how many drew a dissenting (AGAINST) vote
    contest_pct: float


@dataclass
class MayoralStats:
    mayor_moved: int
    mayor_carried_pct: float
    mayor_contest_pct: float        # of carried mayor-moved motions, % that drew dissent
    other_moved: int
    other_carried_pct: float
    other_contest_pct: float
    contest_factor: float           # mayor_contest_pct / other_contest_pct
    per_mayor: list[MayorContest] = field(default_factory=list)


def mayoral_agenda_setting(
    session: Session, council_id: int, min_carried: int = 10
) -> MayoralStats:
    """
    Whether motions personally moved by the sitting Mayor enjoy a procedural
    advantage. Tags each moved motion as mayor- or backbench-moved by checking
    whether the mover held a 'Mayor' term covering the meeting date, then
    compares passage rate and the share of *carried* motions that drew at least
    one dissenting (AGAINST) vote.

    Only 7 mayors carry dated terms (1999–), so pre-1999 mayoral motions fall
    into the 'other' bucket — reported honestly in the panel note.
    """
    terms = (
        session.query(
            CouncillorTerm.councillor_id,
            CouncillorTerm.term_start,
            CouncillorTerm.term_end,
        )
        .filter(CouncillorTerm.role == "Mayor")
        .all()
    )

    def mayor_at(cid: int, d: date) -> bool:
        for mc, ts, te in terms:
            if mc == cid and (ts is None or ts <= d) and (te is None or d <= te):
                return True
        return False

    rows = (
        session.query(
            Motion.moved_by_id,
            Meeting.meeting_date,
            Motion.outcome,
            Motion.votes_against,
            Councillor.given_name,
            Councillor.family_name,
        )
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .join(Councillor, Motion.moved_by_id == Councillor.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.moved_by_id.isnot(None),
            Meeting.meeting_date.isnot(None),
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
        )
        .all()
    )

    agg = {"mayor": {"n": 0, "carried": 0, "contested": 0},
           "other": {"n": 0, "carried": 0, "contested": 0}}
    per_mayor: dict[int, dict] = defaultdict(
        lambda: {"name": "", "carried": 0, "contested": 0}
    )

    for cid, d, outcome, va, given, family in rows:
        is_mayor = mayor_at(cid, d)
        bucket = agg["mayor" if is_mayor else "other"]
        bucket["n"] += 1
        if outcome == MotionOutcome.CARRIED:
            bucket["carried"] += 1
            contested = (va or 0) > 0
            if contested:
                bucket["contested"] += 1
            if is_mayor:
                pm = per_mayor[cid]
                pm["name"] = f"{given or ''} {family or ''}".strip()
                pm["carried"] += 1
                pm["contested"] += 1 if contested else 0

    def _pct(a, b):
        return round(100 * a / b, 1) if b else 0.0

    m, o = agg["mayor"], agg["other"]
    m_contest = _pct(m["contested"], m["carried"])
    o_contest = _pct(o["contested"], o["carried"])

    mayors = [
        MayorContest(
            name=pm["name"],
            carried=pm["carried"],
            contested=pm["contested"],
            contest_pct=_pct(pm["contested"], pm["carried"]),
        )
        for pm in per_mayor.values()
        if pm["carried"] >= min_carried
    ]
    mayors.sort(key=lambda x: x.contest_pct, reverse=True)

    return MayoralStats(
        mayor_moved=m["n"],
        mayor_carried_pct=_pct(m["carried"], m["n"]),
        mayor_contest_pct=m_contest,
        other_moved=o["n"],
        other_carried_pct=_pct(o["carried"], o["n"]),
        other_contest_pct=o_contest,
        contest_factor=round(m_contest / o_contest, 1) if o_contest else 0.0,
        per_mayor=mayors,
    )


# ---------------------------------------------------------------------------
# Recusal compliance over time — did "declare a conflict, then stay" become
# the norm, and did it track the 2018–2021 Authorised Inquiry?
# ---------------------------------------------------------------------------
#
# Builds on the pooled ConflictRecusalPanel by adding the TWO dimensions that
# panel collapses away: TIME (era) and the legal TYPE of interest.
#
# Under the WA Local Government Act a *financial* interest (and the financial
# flavour of a *proximity* interest) obliges a member to leave the room and not
# vote — "must-leave" interests. An *impartiality* interest only has to be
# disclosed; the member may stay and vote. So the headline test is whether
# recusal collapsed even WITHIN the must-leave categories (which a shift in the
# legal mix toward impartiality interests cannot explain).
#
# Linkage is item-level: interest_declarations.item_reference == motions.item_number
# at the same meeting, then that councillor's vote on that motion. This avoids the
# meeting-level cross-contamination where a councillor declaring several interest
# types at one meeting would otherwise have every type attributed to every vote.

_RECUSAL_ERAS = [
    ("pre", "Before Inquiry (pre-2018)", None, 2017),
    ("inquiry", "Authorised Inquiry (2018–2021)", 2018, 2021),
    ("post", "After Inquiry (2022+)", 2022, None),
]
_MUST_LEAVE = ("FINANCIAL", "PROXIMITY")


def _recusal_era(year: int) -> str:
    if year < 2018:
        return "pre"
    if year <= 2021:
        return "inquiry"
    return "post"


@dataclass
class RecusalDeclarationDetail:
    """One item-linked declaration behind an era×type cell, for the drill-down."""
    date: str             # YYYY-MM-DD
    item: str | None      # agenda item reference
    councillor: str
    action: str           # "Stepped out" / "Stayed — voted"
    what: str | None      # the interest description
    quote: str | None     # verbatim minute text (extraction_evidence)


@dataclass
class RecusalTypeEra:
    interest_type: str    # financial / proximity / impartiality / other
    era: str              # pre / inquiry / post
    declared: int
    recused: int
    recusal_pct: float
    n_shown: int = 0      # declarations inlined for the drill-down (capped)
    declarations: list[RecusalDeclarationDetail] = field(default_factory=list)


@dataclass
class RecusalYearPoint:
    year: int
    must_leave_declared: int
    must_leave_recused: int
    must_leave_pct: float | None     # None when n too small to plot a rate
    declared_share_pct: float         # declared-interest votes / all votes that year


@dataclass
class RecusalDriver:
    name: str
    stayed: int           # must-leave declarations where they stayed and voted (post-2022)
    total: int


@dataclass
class RecusalTrendStats:
    inquiry_window: list[int]
    # headline: must-leave recusal by era
    must_leave_pre_pct: float
    must_leave_pre_n: int
    must_leave_inquiry_pct: float
    must_leave_inquiry_n: int
    must_leave_post_pct: float
    must_leave_post_n: int
    # financial-only (the confound-beater): recusal even where leaving is mandatory
    financial_inquiry_pct: float
    financial_inquiry_n: int
    financial_post_pct: float
    financial_post_n: int
    # impartiality boilerplate explosion
    impartiality_post_declared: int
    impartiality_post_recusal_pct: float
    by_type_era: list[RecusalTypeEra]
    by_year: list[RecusalYearPoint]
    drivers: list[RecusalDriver]


def recusal_compliance_trend(
    session: Session,
    council_id: int,
    min_year_n: int = 4,
) -> RecusalTrendStats:
    """Recusal compliance over time, split by the legal type of interest."""
    from sqlalchemy import text

    # Item-level linked declaration -> that councillor's vote on that item.
    linked = session.execute(text("""
        SELECT i.interest_type AS itype,
               CAST(strftime('%Y', mt.meeting_date) AS INTEGER) AS yr,
               v.choice AS choice,
               (c.given_name || ' ' || c.family_name) AS name,
               i.id AS did,
               i.item_reference AS item,
               i.description AS descr,
               mt.meeting_date AS mdate
        FROM interest_declarations i
        JOIN meetings mt ON i.meeting_id = mt.id
        JOIN motions m ON m.meeting_id = i.meeting_id
            AND lower(trim(m.item_number)) = lower(trim(i.item_reference))
        JOIN votes v ON v.motion_id = m.id AND v.councillor_id = i.councillor_id
        JOIN councillors c ON c.id = i.councillor_id
        WHERE mt.council_id = :cid
          AND mt.document_type = 'minutes'
          AND i.councillor_id IS NOT NULL
          AND i.item_reference IS NOT NULL AND trim(i.item_reference) != ''
    """), {"cid": council_id}).all()

    def _norm_type(t) -> str:
        t = (t or "OTHER").upper()
        return t.lower()

    def _recused(choice) -> bool:
        # Enum stored uppercase; ABSENT == stepped out of the room.
        return (choice or "").upper() == "ABSENT"

    # by type x era
    te: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])  # [declared, recused]
    # must-leave by year
    ml_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    # post-2022 must-leave drivers (stayed and voted)
    drv: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [stayed, total]
    # raw declaration rows behind each (type, era) cell, for the drill-down
    te_rows: dict[tuple[str, str], list[tuple]] = defaultdict(list)

    for itype, yr, choice, name, did, item, descr, mdate in linked:
        t = _norm_type(itype)
        era = _recusal_era(yr)
        rec = _recused(choice)
        te[(t, era)][0] += 1
        if rec:
            te[(t, era)][1] += 1
        te_rows[(t, era)].append((did, item, name, rec, descr, mdate))
        if (itype or "").upper() in _MUST_LEAVE:
            ml_year[yr][0] += 1
            if rec:
                ml_year[yr][1] += 1
            if yr >= 2022:
                drv[name][1] += 1
                if not rec:
                    drv[name][0] += 1

    # one representative minute quote per declaration behind a cell
    _CELL_CAP = 60
    all_dids = [r[0] for rows in te_rows.values() for r in sorted(
        rows, key=lambda x: x[5] or "", reverse=True)[:_CELL_CAP]]
    quote_by_decl: dict[int, str] = {}
    if all_dids:
        for did, q in (
            session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text)
            .filter(
                ExtractionEvidence.entity_table == "interest_declarations",
                ExtractionEvidence.entity_id.in_(all_dids),
                ExtractionEvidence.quote_text.isnot(None),
            )
        ):
            quote_by_decl.setdefault(did, q)

    def _cell_details(rows) -> list[RecusalDeclarationDetail]:
        rows = sorted(rows, key=lambda x: x[5] or "", reverse=True)[:_CELL_CAP]
        out = []
        for did, item, name, rec, descr, mdate in rows:
            out.append(RecusalDeclarationDetail(
                date=str(mdate)[:10] if mdate else "",
                item=item,
                councillor=name,
                action="Stepped out" if rec else "Stayed — voted",
                what=descr,
                quote=quote_by_decl.get(did),
            ))
        return out

    by_type_era = [
        RecusalTypeEra(
            interest_type=t, era=era, declared=d, recused=r,
            recusal_pct=round(100 * r / d, 1) if d else 0.0,
            n_shown=min(d, _CELL_CAP),
            declarations=_cell_details(te_rows[(t, era)]),
        )
        for (t, era), (d, r) in sorted(te.items())
        if d > 0
    ]

    # declared-interest share of all votes, per year (the "declarations rising" leg)
    share_rows = session.execute(text("""
        SELECT CAST(strftime('%Y', mt.meeting_date) AS INTEGER) AS yr,
               SUM(CASE WHEN v.declared_interest = 1 THEN 1 ELSE 0 END) AS dec,
               COUNT(*) AS tot
        FROM votes v
        JOIN motions m ON v.motion_id = m.id
        JOIN meetings mt ON m.meeting_id = mt.id
        WHERE mt.council_id = :cid AND mt.document_type = 'minutes'
        GROUP BY yr
    """), {"cid": council_id}).all()
    share = {yr: (100 * dec / tot if tot else 0.0) for yr, dec, tot in share_rows}

    years = sorted(set(ml_year) | set(share))
    by_year = [
        RecusalYearPoint(
            year=yr,
            must_leave_declared=ml_year[yr][0],
            must_leave_recused=ml_year[yr][1],
            must_leave_pct=(round(100 * ml_year[yr][1] / ml_year[yr][0], 1)
                            if ml_year[yr][0] >= min_year_n else None),
            declared_share_pct=round(share.get(yr, 0.0), 1),
        )
        for yr in years
    ]

    def _era_pct(types, era):
        d = sum(te[(t, era)][0] for t in types if (t, era) in te)
        r = sum(te[(t, era)][1] for t in types if (t, era) in te)
        return (round(100 * r / d, 1) if d else 0.0), d

    ml = ("financial", "proximity")
    ml_pre_pct, ml_pre_n = _era_pct(ml, "pre")
    ml_inq_pct, ml_inq_n = _era_pct(ml, "inquiry")
    ml_post_pct, ml_post_n = _era_pct(ml, "post")
    fin_inq_pct, fin_inq_n = _era_pct(("financial",), "inquiry")
    fin_post_pct, fin_post_n = _era_pct(("financial",), "post")
    imp_post_pct, imp_post_n = _era_pct(("impartiality",), "post")

    drivers = [
        RecusalDriver(name=n, stayed=s, total=t)
        for n, (s, t) in sorted(drv.items(), key=lambda kv: -kv[1][0])
        if t >= 3 and s >= 1
    ][:8]

    return RecusalTrendStats(
        inquiry_window=[2018, 2021],
        must_leave_pre_pct=ml_pre_pct, must_leave_pre_n=ml_pre_n,
        must_leave_inquiry_pct=ml_inq_pct, must_leave_inquiry_n=ml_inq_n,
        must_leave_post_pct=ml_post_pct, must_leave_post_n=ml_post_n,
        financial_inquiry_pct=fin_inq_pct, financial_inquiry_n=fin_inq_n,
        financial_post_pct=fin_post_pct, financial_post_n=fin_post_n,
        impartiality_post_declared=imp_post_n,
        impartiality_post_recusal_pct=imp_post_pct,
        by_type_era=by_type_era,
        by_year=by_year,
        drivers=drivers,
    )


# ---------------------------------------------------------------------------
# Public-question responsiveness — answered in the room, or "taken on notice"?
#
# Public question time is a statutory engagement channel (CIPFA-B). A question
# ANSWERED in the meeting is live accountability; one "taken on notice" / deferred
# is engagement without in-room response. This query classifies every public
# question by whether its recorded response is an in-meeting answer vs a deferral,
# and tracks the deferral share across the pre / Inquiry (2018–21) / post eras —
# the same before/during/after shock lens as recusal [19] and transparency [9].
# The classifier is conservative (a deferral phrased as an answer is counted
# answered), so the on-notice share is a FLOOR. Severity: Governance concern —
# "engagement without response is theatre" (Part 3.4), but "on notice" is lawful
# and often appropriate, so it is a responsiveness signal, not impropriety.
# ---------------------------------------------------------------------------
import re as _re_pqr

# phrases that mark a response as deferred rather than answered in the meeting
_ON_NOTICE_RE = _re_pqr.compile(
    r"taken on notice|on notice|no response|not answered|deferred|will be provided|"
    r"to be provided|provided later|will respond|responded to in writing|"
    r"respond(?:ed)?\s+in\s+writing|provide[d]?.{0,20}writing|answer(?:ed)?.{0,20}writing",
    _re_pqr.IGNORECASE,
)
# best-effort "who fielded it" — a leading role/name in the recorded response
_FIELDED_RE = _re_pqr.compile(
    r"^\s*(Mayor|Deputy Mayor|Acting Mayor|CEO|Chief Executive[^,.;]*|"
    r"(?:Acting\s+)?Director[^,.;]*|Manager[^,.;]*|Cr\.?\s+[A-Z][a-zA-Z'-]+|"
    r"Presiding Member)",
    _re_pqr.IGNORECASE,
)


def _pqr_classify(resp: str | None) -> str:
    r = (resp or "").strip()
    if not r:
        return "blank"
    if _ON_NOTICE_RE.search(r):
        return "on_notice"
    return "answered"


@dataclass
class PQResponseDetail:
    """One public question behind an era cell, for the drill-down."""
    date: str                 # YYYY-MM-DD
    questioner: str | None
    question: str | None      # the question summary (truncated)
    status: str               # "Answered in meeting" / "Taken on notice"
    fielded_by: str | None    # best-effort role/name that responded
    quote: str | None         # verbatim minute text (extraction_evidence)


@dataclass
class PQEraStat:
    era: str                  # pre / inquiry / post
    answered: int
    on_notice: int
    blank: int
    on_notice_pct: float      # of non-blank
    n_shown: int = 0
    questions: list[PQResponseDetail] = field(default_factory=list)


@dataclass
class PQYearPoint:
    year: int
    answered: int
    on_notice: int
    n_nonblank: int
    on_notice_pct: float | None   # None when n too small to plot a rate


@dataclass
class PQResponsivenessStats:
    inquiry_window: list[int]
    total: int
    answered: int
    on_notice: int
    blank: int
    answered_pct: float
    on_notice_pct: float          # of non-blank, overall
    pre_pct: float
    pre_n: int
    inquiry_pct: float
    inquiry_n: int
    post_pct: float
    post_n: int
    peak_year: int | None
    peak_pct: float | None
    by_era: list[PQEraStat]
    by_year: list[PQYearPoint]


def public_question_responsiveness(
    session: Session,
    council_id: int,
    min_year_n: int = 15,
    cell_cap: int = 60,
) -> PQResponsivenessStats:
    """Are public questions answered in the meeting, or 'taken on notice'?"""
    from sqlalchemy import text

    rows = session.execute(text("""
        SELECT pq.id AS pid,
               CAST(strftime('%Y', mt.meeting_date) AS INTEGER) AS yr,
               mt.meeting_date AS mdate,
               pq.questioner_name AS questioner,
               pq.question_summary AS question,
               pq.response_summary AS response
        FROM public_questions pq
        JOIN meetings mt ON pq.meeting_id = mt.id
        WHERE mt.council_id = :cid AND mt.document_type = 'minutes'
    """), {"cid": council_id}).all()

    # overall + era + year tallies
    era_ct: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # [answered, on_notice, blank]
    yr_ct: dict[int, list[int]] = defaultdict(lambda: [0, 0])      # [answered, on_notice] (non-blank)
    era_rows: dict[str, list[tuple]] = defaultdict(list)
    tot = [0, 0, 0]

    for pid, yr, mdate, questioner, question, response in rows:
        cls = _pqr_classify(response)
        era = _recusal_era(yr) if yr is not None else "pre"
        if cls == "answered":
            era_ct[era][0] += 1
            tot[0] += 1
            yr_ct[yr][0] += 1
        elif cls == "on_notice":
            era_ct[era][1] += 1
            tot[1] += 1
            yr_ct[yr][1] += 1
        else:
            era_ct[era][2] += 1
            tot[2] += 1
        # keep on-notice + a sample of answered rows for the drill-down
        era_rows[era].append((pid, mdate, questioner, question, response, cls))

    # representative minute quote per question shown in a drill-down
    def _era_details(era: str) -> tuple[list[tuple], list[int]]:
        # prioritise on-notice (the finding), newest first; then a few answered
        on = [r for r in era_rows[era] if r[5] == "on_notice"]
        ans = [r for r in era_rows[era] if r[5] == "answered"]
        on.sort(key=lambda x: str(x[1] or ""), reverse=True)
        ans.sort(key=lambda x: str(x[1] or ""), reverse=True)
        chosen = (on + ans)[:cell_cap]
        return chosen, [r[0] for r in chosen]

    chosen_by_era = {e: _era_details(e) for e in ("pre", "inquiry", "post")}
    all_pids = [pid for _era, (rows_, pids) in chosen_by_era.items() for pid in pids]
    quote_by_q: dict[int, str] = {}
    if all_pids:
        for pid, q in (
            session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text)
            .filter(
                ExtractionEvidence.entity_table == "public_questions",
                ExtractionEvidence.entity_id.in_(all_pids),
                ExtractionEvidence.quote_text.isnot(None),
            )
        ):
            quote_by_q.setdefault(pid, q)

    def _fielded(resp: str | None) -> str | None:
        m = _FIELDED_RE.search((resp or "").strip())
        return m.group(1).strip() if m else None

    def _details(era: str) -> list[PQResponseDetail]:
        chosen, _ = chosen_by_era[era]
        out = []
        for pid, mdate, questioner, question, response, cls in chosen:
            out.append(PQResponseDetail(
                date=str(mdate)[:10] if mdate else "",
                questioner=(questioner or None),
                question=((question or "")[:220] or None),
                status="Taken on notice" if cls == "on_notice" else "Answered in meeting",
                fielded_by=_fielded(response),
                quote=quote_by_q.get(pid),
            ))
        return out

    def _pct(a: int, o: int) -> float:
        nb = a + o
        return round(100 * o / nb, 1) if nb else 0.0

    by_era = [
        PQEraStat(
            era=e, answered=era_ct[e][0], on_notice=era_ct[e][1], blank=era_ct[e][2],
            on_notice_pct=_pct(era_ct[e][0], era_ct[e][1]),
            n_shown=len(chosen_by_era[e][0]),
            questions=_details(e),
        )
        for e in ("pre", "inquiry", "post")
    ]

    by_year = []
    peak_year, peak_pct = None, None
    for yr in sorted(yr_ct):
        a, o = yr_ct[yr]
        nb = a + o
        pct = round(100 * o / nb, 1) if nb >= min_year_n else None
        by_year.append(PQYearPoint(year=yr, answered=a, on_notice=o, n_nonblank=nb, on_notice_pct=pct))
        if pct is not None and (peak_pct is None or pct > peak_pct):
            peak_pct, peak_year = pct, yr

    ev = {e.era: e for e in by_era}
    return PQResponsivenessStats(
        inquiry_window=[2018, 2021],
        total=len(rows), answered=tot[0], on_notice=tot[1], blank=tot[2],
        answered_pct=round(100 * tot[0] / len(rows), 1) if rows else 0.0,
        on_notice_pct=_pct(tot[0], tot[1]),
        pre_pct=ev["pre"].on_notice_pct, pre_n=ev["pre"].answered + ev["pre"].on_notice,
        inquiry_pct=ev["inquiry"].on_notice_pct, inquiry_n=ev["inquiry"].answered + ev["inquiry"].on_notice,
        post_pct=ev["post"].on_notice_pct, post_n=ev["post"].answered + ev["post"].on_notice,
        peak_year=peak_year, peak_pct=peak_pct,
        by_era=by_era, by_year=by_year,
    )


# ---------------------------------------------------------------------------
# Sponsorship network — who BACKED whose motions in a near-unanimous chamber?
#
# In a chamber that votes ~90%+ unanimously, the recorded VOTE cannot separate
# allies — everyone votes FOR. The mover->seconder ("sponsorship") record can:
# seconding a motion is a low-cost public sponsorship signal. This query mines
# that signal, controlling for activity volume via a lift statistic
# (observed sponsorships / expected-under-independence), and VALIDATES each
# strong tie against how the pair actually voted on contested motions —
# distinguishing real alliances (sponsor AND vote together) from procedural
# "courtesy" seconding (sponsor, but vote oppositely on divisive items).
#
# Severity: Observation. No impropriety is implied — sponsoring an ally's
# motions is ordinary politics. The point is descriptive: surfacing working
# structure the unanimous vote hides. Maps to CIPFA principle B (how the
# chamber actually conducts business) / Nolan Openness.
# ---------------------------------------------------------------------------

# ~4-year WA electoral blocks (biennial Oct odd-year elections, 4-yr terms).
_SPON_ERAS = [
    ("1996–99", 1996, 1999),
    ("2000–03", 2000, 2003),
    ("2004–07", 2004, 2007),
    ("2008–11", 2008, 2011),
    ("2012–15", 2012, 2015),
    ("2016–19", 2016, 2019),
    ("2020–23", 2020, 2023),
]
_OLDGUARD = ("2000–07", 2000, 2007)


@dataclass
class SponsorEdge:
    era_label: str
    name_a: str
    name_b: str
    sponsorships: int          # mutual mover<->seconder count in the window
    lift: float                # observed / expected-under-independence
    agree_pct: float | None    # contested-vote agreement (None if too few shared)
    agree_n: int               # shared contested votes
    kind: str                  # "alliance" | "procedural" | "mixed"


@dataclass
class SponsorNode:
    name: str
    moved: int
    seconded: int
    in_core: bool


@dataclass
class SponsorEra:
    label: str
    year_from: int
    year_to: int
    n_events: int
    n_active: int
    cluster_size: int          # largest high-lift connected component
    core_names: list[str]
    structure: str             # short descriptive label


@dataclass
class SponsorshipNetworkStats:
    # Part 1 — validated alliances across all eras
    alliances: list[SponsorEdge]
    procedural: list[SponsorEdge]
    convergence_high_agree: float   # mean contested agreement of high-lift pairs
    convergence_low_agree: float    # ... of low-lift pairs (the base rate)
    # Part 2 — the 2000s old-guard network
    oldguard_label: str
    oldguard_unanimous_pct: float
    oldguard_nodes: list[SponsorNode]
    oldguard_edges: list[SponsorEdge]
    # Part 3 — structural history across electoral terms
    eras: list[SponsorEra]


def _spon_load(session, council_id, from_year, to_year):
    """Return (moves, seconds, pair, name, N) for a window (minutes only)."""
    rows = (
        session.query(Motion.moved_by_id, Motion.seconded_by_id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.moved_by_id.isnot(None),
            Motion.seconded_by_id.isnot(None),
            Motion.moved_by_id != Motion.seconded_by_id,
        )
    )
    rows = _year_filter_query(rows, Meeting, from_year, to_year).all()
    moves: dict[int, int] = defaultdict(int)
    seconds: dict[int, int] = defaultdict(int)
    pair: dict[tuple[int, int], int] = defaultdict(int)
    N = 0
    for mv, sc in rows:
        moves[mv] += 1
        seconds[sc] += 1
        pair[(mv, sc)] += 1
        N += 1
    return moves, seconds, pair, N


def _spon_agreement(session, council_id, from_year, to_year):
    """Per-pair contested-vote agreement: {(min,max): [same, total]} (minutes only)."""
    rows = (
        session.query(Vote.motion_id, Vote.councillor_id, Vote.choice)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.votes_against > 0,
            Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]),
        )
    )
    rows = _year_filter_query(rows, Meeting, from_year, to_year).all()
    bymot: dict[int, dict[int, object]] = defaultdict(dict)
    for mid, cid, ch in rows:
        bymot[mid][cid] = ch
    agree: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for d in bymot.values():
        ids = sorted(d)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                key = (a, b)
                agree[key][1] += 1
                if d[a] == d[b]:
                    agree[key][0] += 1
    return agree


def _spon_edges(moves, seconds, pair, N, names, agree,
                min_moved=15, min_sec=15, min_obs=8):
    """Volume-controlled mutual-sponsorship edges among active members, with
    contested-vote agreement attached. Returns list of dicts."""
    active = [p for p in set(list(moves) + list(seconds))
              if moves[p] >= min_moved and seconds[p] >= min_sec]
    out = []
    for i, a in enumerate(sorted(active)):
        for b in sorted(active)[i + 1:]:
            obs = pair.get((a, b), 0) + pair.get((b, a), 0)
            if obs < min_obs:
                continue
            exp = moves[a] * seconds[b] / N + moves[b] * seconds[a] / N
            lift = obs / exp if exp > 0 else 0.0
            sa, ta = agree.get((min(a, b), max(a, b)), [0, 0])
            agp = round(sa / ta * 100, 1) if ta >= 1 else None
            out.append({
                "a": a, "b": b, "obs": obs, "lift": round(lift, 2),
                "agree_pct": agp, "agree_n": ta,
                "na": names.get(a, ""), "nb": names.get(b, ""),
            })
    return out, set(active)


def _spon_clusters(edges, active, thr=1.8):
    """Largest connected component among high-lift edges."""
    adj: dict[int, set] = defaultdict(set)
    for e in edges:
        if e["lift"] >= thr:
            adj[e["a"]].add(e["b"])
            adj[e["b"]].add(e["a"])
    seen, comps = set(), []
    for n in list(adj):
        if n in seen:
            continue
        stack, comp = [n], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.add(x)
            stack += [y for y in adj[x] if y not in seen]
        if len(comp) >= 3:
            comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def _classify(agree_pct):
    if agree_pct is None:
        return "mixed"
    if agree_pct >= 70:
        return "alliance"
    if agree_pct <= 50:
        return "procedural"
    return "mixed"


def sponsorship_network(session: Session, council_id: int) -> SponsorshipNetworkStats:
    names = {
        cid: f"{gn or ''} {fn or ''}".strip()
        for cid, gn, fn in session.query(
            Councillor.id, Councillor.given_name, Councillor.family_name
        ).all()
    }

    def _named(cid):
        n = names.get(cid, "")
        return n and "unknown" not in n.lower()

    # ---- Part 1: validated alliances across all electoral eras -------------
    best: dict[tuple[int, int], dict] = {}   # pair -> strongest-lift instance
    hi_agree, lo_agree = [], []
    for label, f, t in _SPON_ERAS:
        moves, seconds, pair, N = _spon_load(session, council_id, f, t)
        if N < 200:
            continue
        agree = _spon_agreement(session, council_id, f, t)
        edges, _ = _spon_edges(moves, seconds, pair, N, names, agree)
        for e in edges:
            if not (_named(e["a"]) and _named(e["b"])):
                continue
            if e["agree_pct"] is not None and e["agree_n"] >= 25:
                (hi_agree if e["lift"] >= 2.0 else
                 lo_agree if e["lift"] < 1.0 else []).append(e["agree_pct"])
            key = (min(e["a"], e["b"]), max(e["a"], e["b"]))
            cur = best.get(key)
            if cur is None or e["lift"] > cur["lift"]:
                best[key] = {**e, "era": label}

    def _edge(e):
        return SponsorEdge(
            era_label=e["era"], name_a=e["na"], name_b=e["nb"],
            sponsorships=e["obs"], lift=e["lift"],
            agree_pct=e["agree_pct"], agree_n=e["agree_n"],
            kind=_classify(e["agree_pct"]),
        )

    strong = [e for e in best.values() if e["lift"] >= 2.0 and e["agree_n"] >= 30]
    alliances = sorted(
        [_edge(e) for e in strong if (e["agree_pct"] or 0) >= 70],
        key=lambda x: -x.lift,
    )[:12]
    procedural = sorted(
        [_edge(e) for e in strong if (e["agree_pct"] or 100) <= 55],
        key=lambda x: -x.lift,
    )[:6]

    conv_hi = round(sum(hi_agree) / len(hi_agree), 1) if hi_agree else 0.0
    conv_lo = round(sum(lo_agree) / len(lo_agree), 1) if lo_agree else 0.0

    # ---- Part 2: the 2000s old-guard network -------------------------------
    label, f, t = _OLDGUARD
    moves, seconds, pair, N = _spon_load(session, council_id, f, t)
    agree = _spon_agreement(session, council_id, f, t)
    og_edges_raw, og_active = _spon_edges(moves, seconds, pair, N, names, agree, min_obs=10)
    og_edges_raw = [e for e in og_edges_raw if _named(e["a"]) and _named(e["b"])]
    # unanimity rate of the era
    carried = (
        session.query(func.count(Motion.id))
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED)
    )
    carried = _year_filter_query(carried, Meeting, f, t).scalar() or 0
    contested = (
        session.query(func.count(Motion.id))
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED, Motion.votes_against > 0)
    )
    contested = _year_filter_query(contested, Meeting, f, t).scalar() or 0
    unanimous_pct = round((carried - contested) / carried * 100, 1) if carried else 0.0
    # keep the meaningful edges (lift >= 1.5) for the diagram; cap for readability
    og_edges = sorted(og_edges_raw, key=lambda e: -e["lift"])
    og_edges = [e for e in og_edges if e["lift"] >= 1.5][:18]
    core_ids = {e["a"] for e in og_edges} | {e["b"] for e in og_edges}
    og_nodes = sorted(
        [SponsorNode(name=names.get(c, ""), moved=moves[c], seconded=seconds[c],
                     in_core=c in core_ids)
         for c in og_active if _named(c)],
        key=lambda n: -(n.moved + n.seconded),
    )
    oldguard_edges = [_edge({**e, "era": label}) for e in og_edges]

    # ---- Part 3: structural history across electoral terms -----------------
    _STRUCT = {
        "1996–99": "forming",
        "2000–03": "old guard consolidates",
        "2004–07": "old guard at its peak",
        "2008–11": "fragmented",
        "2012–15": "small nucleus",
        "2016–19": "broad / hyperactive",
        "2020–23": "reshuffled, no durable bloc",
    }
    eras: list[SponsorEra] = []
    for lab, ff, tt in _SPON_ERAS:
        mv, sc, pr, NN = _spon_load(session, council_id, ff, tt)
        if NN < 50:
            continue
        ag = _spon_agreement(session, council_id, ff, tt)
        eds, act = _spon_edges(mv, sc, pr, NN, names, ag)
        eds = [e for e in eds if _named(e["a"]) and _named(e["b"])]
        comps = _spon_clusters(eds, act)
        big = comps[0] if comps else set()
        core = sorted((names.get(c, "") for c in big), key=lambda s: s)
        eras.append(SponsorEra(
            label=lab, year_from=ff, year_to=tt, n_events=NN,
            n_active=len([a for a in act if _named(a)]),
            cluster_size=len(big), core_names=core[:8],
            structure=_STRUCT.get(lab, ""),
        ))

    return SponsorshipNetworkStats(
        alliances=alliances,
        procedural=procedural,
        convergence_high_agree=conv_hi,
        convergence_low_agree=conv_lo,
        oldguard_label=label,
        oldguard_unanimous_pct=unanimous_pct,
        oldguard_nodes=og_nodes,
        oldguard_edges=oldguard_edges,
        eras=eras,
    )
