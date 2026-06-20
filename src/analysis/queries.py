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
    BudgetItem,
    Councillor,
    Council,
    Deputation,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    Motion,
    MotionOutcome,
    Petition,
    PlanningApplication,
    PublicQuestion,
    Site,
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
    from sqlalchemy import extract as sql_extract

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
    from sqlalchemy import case, extract as sql_extract

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
    from sqlalchemy import case
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
