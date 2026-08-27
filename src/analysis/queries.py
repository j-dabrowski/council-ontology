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
    Appointment,
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


def _year_filters(stmt, meeting_model, from_year: int | None, to_year: int | None,
                  meeting_id: int | None = None):
    """Apply optional from_year / to_year (or an exact meeting_id) filters to a
    SQLAlchemy statement. meeting_id narrows to one meeting — a future
    single-meeting-digest caller (docs/frontend/PRODUCT_ROADMAP.md F2) passes
    it instead of from_year/to_year, which are too coarse (year-level, not
    meeting-level) for that use."""
    from sqlalchemy import extract as sql_extract
    if meeting_id is not None:
        return stmt.where(meeting_model.id == meeting_id)
    if from_year:
        stmt = stmt.where(sql_extract("year", meeting_model.meeting_date) >= from_year)
    if to_year:
        stmt = stmt.where(sql_extract("year", meeting_model.meeting_date) <= to_year)
    return stmt


def _year_filter_query(query, meeting_model, from_year: int | None, to_year: int | None,
                       meeting_id: int | None = None):
    """Apply optional from_year / to_year (or an exact meeting_id) filters to a
    legacy ORM query. See `_year_filters` above — same meeting_id behaviour."""
    from sqlalchemy import extract as sql_extract
    if meeting_id is not None:
        return query.filter(meeting_model.id == meeting_id)
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


import re as _re_interests

# A declared-interest row always needs a councillor_id (the schema has no
# separate officer entity — see InterestDeclaration in src/models/ontology.py),
# so extraction attaches a council officer's own declaration to a fabricated
# "councillor" row named after their title/role instead. These aren't a
# duplicate-identity dedup case (scripts/dedup_councillors.py's passes all key
# off votes/terms, and these rows have neither) — they're not councillors at
# all. Verified against the full corpus (2026-08-23, defamation review pass 1
# BLOCKING flag 1.3): matches exactly the 14 rows where the officer's title
# itself landed in the name field, and no real councillor — it does not by
# itself verify the corpus's full officer population (pass 2 found three
# more, whose actual names were extracted correctly; see the second,
# independent exclusion below).
_OFFICER_TITLE_RE = _re_interests.compile(
    r"^(CEO|Chief Executive(?:\s+Officer)?|Acting Chief Executive(?:\s+Officer)?|"
    r"(?:Acting\s+)?Director|(?:Acting\s+)?(?:Executive\s+)?Manager)\b",
    _re_interests.IGNORECASE,
)

# The title regex only catches the case where the officer's title landed in
# the extracted name field itself. It misses officers whose actual personal
# name was extracted correctly (e.g. "CEO John Giorgi" -> given_name="John",
# family_name="Giorgi") — those rows still have zero votes and zero
# councillor_terms, the same non-councillor signal `scripts/
# dedup_councillors.py` treats as authoritative elsewhere, so it's applied
# here as a second, independent exclusion (defamation review pass 2 BLOCKING
# flag 1 — hand-verified against council.db 2026-08-23: this drops exactly
# the three confirmed officers — councillor_id 248 "John Giorgi" n=32, 211
# "Ian Birch" n=8, 401 "Cam Robbins" n=5 — plus a handful of already-regex-
# caught title rows (no change) and several total<=3 stubs that read as
# thin-but-real councillors rather than officers; excluding them from this
# one chart is defamation-safe either way since it drops an unattributed row
# rather than misattributing one — whether they're real split-identity
# fragments worth a dedup merge is a separate data-completeness question).


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

    # Councillor names — excluding council-officer rows (see _OFFICER_TITLE_RE
    # and the zero-votes/zero-terms exclusion just above it)
    cids = list(totals.keys())
    name_rows = session.query(Councillor.id, Councillor.given_name, Councillor.family_name).filter(
        Councillor.id.in_(cids)
    ).all()
    has_votes = {
        cid for (cid,) in session.query(Vote.councillor_id.distinct()).filter(
            Vote.councillor_id.in_(cids)
        ).all()
    }
    has_terms = {
        cid for (cid,) in session.query(CouncillorTerm.councillor_id.distinct()).filter(
            CouncillorTerm.councillor_id.in_(cids)
        ).all()
    }
    names = {
        cid: f"{g} {f}".strip() for cid, g, f in name_rows
        if not (_OFFICER_TITLE_RE.match(g or "") or _OFFICER_TITLE_RE.match(f or ""))
        and (cid in has_votes or cid in has_terms)
    }
    totals = {cid: n for cid, n in totals.items() if cid in names}
    if not totals:
        return []

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
    meeting_id: int | None = None,
) -> list[EngagementStats]:
    """Public questions, deputations, and petitions per year (minutes only).

    `meeting_id`, when set, narrows to that one meeting
    (docs/frontend/PRODUCT_ROADMAP.md F2's single-meeting digest) — the
    single-item result list still keys off `year`, just with one entry.
    """

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
        q = _year_filter_query(q, Meeting, from_year, to_year, meeting_id=meeting_id)
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


# The alignment matrix is built directly from Vote rows, so it isn't caught
# by the has-votes/has-terms non-councillor exclusion above (these rows have
# votes — that's the whole problem). Instead it needs the malformed-record
# signal `scripts/dedup_councillors.py` already treats as authoritative for
# "not a real name, not yet merged": given_name left empty (a family-only
# orphan stub — Pass 2/5's own bad-record shape) or family_name a bare
# extraction placeholder token (that script's own PLACEHOLDERS set). Verified
# against the full corpus (2026-08-23, defamation review pass 3 BLOCKING flag
# 1): drops exactly the "The" (councillor_id 288, given_name empty) and
# "Shannon Unknown" (councillor_id 16, family_name="Unknown") rows the review
# found sitting in the always-visible grid alongside real, profiled
# councillors, plus several zero-vote stubs of the same shape that were never
# reachable through this query anyway.
_ALIGNMENT_PLACEHOLDER_SURNAMES = ("unknown", "null", "none", "n/a", "name")


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
        .where(func.trim(func.coalesce(Councillor.given_name, "")) != "")
        .where(
            func.lower(func.trim(func.coalesce(Councillor.family_name, "")))
            .notin_(_ALIGNMENT_PLACEHOLDER_SURNAMES)
        )
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
    recusal_rate: float   # blended across ALL declared-interest types (financial,
                           # proximity AND impartiality) — do not use this alone to
                           # colour-code compliance; see must_leave_recusal_rate.
    is_active: bool
    # "Must-leave" split (financial/proximity interests legally require leaving the
    # room; impartiality interests permit staying and voting — see 0.4 in
    # Investigator_prompt.txt). Restricted to the subset of this councillor's
    # declared-interest VOTES that matched a financial/proximity declaration
    # (same match already computed in `declarations` below — reused, not
    # re-derived, to avoid a second join implementation that could disagree with
    # the drill-down list a reader can click into).
    must_leave_declared: int = 0
    must_leave_recused: int = 0
    # None (not 0.0) when the councillor has zero must-leave declarations on
    # record — lets a consumer (e.g. the frontend colour-coder) distinguish "no
    # mandatory conflicts to comply with" from "0% compliance on a real one."
    must_leave_recusal_rate: float | None = None
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


import re as _re_recusal

_LEFT_MEETING_RE = _re_recusal.compile(r"\bleft the (?:meeting|room)\b", _re_recusal.IGNORECASE)


def _actually_stepped_out(choice, quote: str | None) -> bool:
    """True if the councillor was not actually present to cast `choice`.

    `Vote.choice` is normally ground truth for "did they step out," but a
    handful of records carry a recorded FOR/AGAINST vote whose own linked
    declaration quote states outright that the councillor left the meeting
    before the item was decided — a direct contradiction between two fields
    of the same extracted record (verified against council.db, 2026-08-23
    defamation review pass 1 BLOCKING flag 1: O'Connor, Bradley, Barlow,
    Grinceri all carry at least one such record). The quote wins.
    """
    if choice == VoteChoice.ABSENT:
        return True
    return bool(quote and _LEFT_MEETING_RE.search(quote))


@dataclass
class LinkedDeclaredVote:
    """One declared-interest VOTE, linked to its matching declaration (if any).

    Vote-driven, not declaration-driven — `votes` carries `UNIQUE(motion_id,
    councillor_id)`, so this cannot fan out the way a raw
    declarations-JOIN-motions-JOIN-votes query can when a meeting has more
    than one motion sharing an item_number, or more than one declaration row
    for the same real declaration (both occur in this corpus). The
    declaration match is a dict lookup keyed (councillor, meeting, item
    reference) — last-wins on a duplicate key, never a row multiplier.

    This is the single, shared implementation of the [19] item-level link
    (item_reference == motion.item_number within one meeting). Every query
    that needs "which votes were cast on a declared conflict, and what kind"
    must build on this, not re-derive its own join — `recusal_compliance_trend`
    used to maintain an independent raw-SQL version of this same link without
    the `votes.declared_interest = 1` anchor, and it silently fabricated
    inflated counts (traced live: a false post-2022 stay-and-vote claim
    naming a real councillor, from meeting-258 fan-out) — see docs/review,
    BLOCKING flag, 2026-08-11 pass 3.
    """
    councillor_id: int
    name: str
    choice: "VoteChoice"
    item: str | None
    title: str | None
    meeting_id: int
    date: str          # YYYY-MM-DD
    year: int | None
    interest_type: str | None   # normalised lowercase, or None if unmatched
    what: str | None
    declaration_id: int | None
    quote: str | None


def _linked_declared_votes(
    session, council_id, from_year=None, to_year=None, councillor_ids=None,
    meeting_id=None,
) -> list[LinkedDeclaredVote]:
    """The one safe, vote-driven declared-interest linkage — see `LinkedDeclaredVote`."""
    vq = (
        session.query(
            Vote.councillor_id, Vote.choice, Vote.interest_description,
            Motion.item_number, Motion.title, Meeting.id, Meeting.meeting_date,
            Councillor.given_name, Councillor.family_name,
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .filter(
            Meeting.council_id == council_id,
            Vote.declared_interest == True,  # noqa: E712
        )
    )
    if councillor_ids:
        vq = vq.filter(Vote.councillor_id.in_(councillor_ids))
    vq = _year_filter_query(vq, Meeting, from_year, to_year, meeting_id=meeting_id)

    # declarations, keyed for a meeting-scoped item match (last-wins on a
    # duplicate key — a dict lookup can't multiply rows the way a join can)
    decl_q = session.query(
        InterestDeclaration.id, InterestDeclaration.councillor_id,
        InterestDeclaration.meeting_id, InterestDeclaration.item_reference,
        InterestDeclaration.interest_type, InterestDeclaration.description,
    )
    if councillor_ids:
        decl_q = decl_q.filter(InterestDeclaration.councillor_id.in_(councillor_ids))
    decl_by_key: dict[tuple, tuple] = {}
    decl_ids: list[int] = []
    for did, cid, mid, iref, itype, desc in decl_q:
        decl_ids.append(did)
        if iref:
            decl_by_key[(cid, mid, iref)] = (did, itype, desc)

    # All minute quotes per declaration, concatenated — a single declaration
    # is often extracted across more than one evidence row (e.g. the
    # announcement line and a separate "left the meeting at HH:MM" sentence),
    # and keeping only the first (the previous `setdefault` behaviour) could
    # silently drop the one sentence that contradicts a mis-recorded vote
    # choice. See _actually_stepped_out and 2026-08-23 defamation review
    # pass 1 BLOCKING flag 1 (Bradley's DV10.69 has exactly this shape: the
    # "left the meeting" evidence row exists but wasn't the first one returned).
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
            quote_by_decl[did] = f"{quote_by_decl[did]} {q}" if did in quote_by_decl else q

    out: list[LinkedDeclaredVote] = []
    for cid, choice, vote_desc, item_no, title, mid, mdate, given, family in vq:
        matched = decl_by_key.get((cid, mid, item_no)) if item_no else None
        itype = _enum_str(matched[1]) if matched else None
        what = (matched[2] if matched and matched[2] else None) or vote_desc
        quote = quote_by_decl.get(matched[0]) if matched else None
        out.append(LinkedDeclaredVote(
            councillor_id=cid,
            name=f"{given or ''} {family or ''}".strip(),
            choice=choice,
            item=item_no,
            title=title,
            meeting_id=mid,
            date=mdate.isoformat() if mdate else "",
            year=mdate.year if mdate else None,
            interest_type=itype,
            what=what,
            declaration_id=matched[0] if matched else None,
            quote=quote,
        ))
    return out


def _populate_declaration_details(session, council_id, profiles, from_year, to_year,
                                  meeting_id=None) -> None:
    """Attach the per-vote drill-down list to each RecusalProfile.

    Built on `_linked_declared_votes` — see that function for why this is
    fan-out-safe. Falls back to the vote's own interest_description where no
    declaration matches.
    """
    if not profiles:
        return
    ids = [p.councillor_id for p in profiles]
    linked = _linked_declared_votes(session, council_id, from_year, to_year, councillor_ids=ids,
                                    meeting_id=meeting_id)

    by_councillor: dict[int, list[DeclarationDetail]] = {cid: [] for cid in ids}
    for row in linked:
        must_leave = row.interest_type in {"financial", "proximity"}
        if _actually_stepped_out(row.choice, row.quote):
            action = "Stepped out"
        elif row.choice == VoteChoice.AGAINST:
            action = "Stayed — voted against"
        elif row.choice == VoteChoice.FOR:
            action = "Stayed — voted for"
        else:
            action = "Stayed"
        by_councillor.setdefault(row.councillor_id, []).append(DeclarationDetail(
            date=row.date,
            item=row.item,
            title=row.title,
            interest_type=row.interest_type,
            what=row.what,
            action=action,
            must_leave=must_leave,
            quote=row.quote,
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
    meeting_id: int | None = None,
) -> ConflictRecusalStats:
    """
    How declaring a conflict of interest changes voting behaviour.

    Uses Vote.declared_interest as ground truth. A vote of ABSENT on a
    declared-interest item is read as a recusal (the councillor stepped out).
    Returns the declared-vs-baseline contrast plus per-councillor recusal
    rates for councillors with at least ``min_declared`` declared votes.

    `meeting_id`, when set, overrides from_year/to_year and scopes every
    query below to that one meeting (docs/frontend/PRODUCT_ROADMAP.md F2's
    single-meeting digest) — pass a low `min_declared` (e.g. 1) alongside it,
    since a single meeting rarely has 8+ declared votes from one councillor.
    """
    from sqlalchemy import case as sa_case

    def _bucket(declared: bool, scope_to_meeting: bool = True):
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
        q = _year_filter_query(q, Meeting, from_year, to_year,
                               meeting_id=meeting_id if scope_to_meeting else None)
        total, absent, against, cast = q.one()
        total = total or 0
        absent = absent or 0
        against = against or 0
        cast = cast or 0
        return total, absent, against, cast

    d_total, d_absent, d_against, d_cast = _bucket(True)
    # The baseline (non-declared) bucket is NOT meeting-scoped even when
    # meeting_id is set: it's the "normal" rate a single meeting's declared-
    # interest behaviour is compared against (ConflictRecusalStats.
    # baseline_recusal_pct, read by _t_recusal_overall) — scoping it to the
    # same one meeting would compare a number to itself.
    b_total, b_absent, b_against, b_cast = _bucket(False, scope_to_meeting=False)

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
    prof_q = _year_filter_query(prof_q, Meeting, from_year, to_year, meeting_id=meeting_id)
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

    _populate_declaration_details(session, council_id, profiles, from_year, to_year,
                                  meeting_id=meeting_id)

    # Must-leave split, computed from the same per-declaration `must_leave` flag
    # already attached above (financial/proximity vs. impartiality/other) — not a
    # fresh SQL join, so it can't disagree with what the drill-down shows.
    # `recused`/`recusal_rate` (blended, set above from `prof_q`) are likewise
    # overridden here from `p.declarations` rather than left as `prof_q`'s raw
    # Vote.choice==ABSENT count — `prof_q` cannot see the quote-text override
    # `_actually_stepped_out` applies, so it would silently disagree with the
    # drill-down list a reader can click into (2026-08-23 defamation review
    # pass 1 BLOCKING flag 1).
    for p in profiles:
        ml_declared = sum(1 for d in p.declarations if d.must_leave)
        ml_recused = sum(1 for d in p.declarations if d.must_leave and d.action == "Stepped out")
        p.must_leave_declared = ml_declared
        p.must_leave_recused = ml_recused
        p.must_leave_recusal_rate = round(ml_recused / ml_declared, 4) if ml_declared else None
        p.recused = sum(1 for d in p.declarations if d.action == "Stepped out")
        p.recusal_rate = round(p.recused / p.declared_votes, 4) if p.declared_votes else 0.0

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


def _normalise_tender_ref(ref: str | None) -> str:
    """Collapse spacing/hyphen variants so 'RFT 2023-16' == 'RFT202316' == 'RFT2023-16'."""
    if not ref:
        return ""
    return "".join(ch for ch in ref.lower() if ch.isalnum())


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
    meeting_id: int | None = None,
) -> TenderConcentration:
    """
    Concentration of tendered spend among contractors.

    Splits the corpus into *named* contractors and the confidential
    "Respondent N" placeholders used in closed tender reports, then ranks
    named contractors by total awarded dollars (spelling variants merged).

    Filters to `document_type == 'minutes'` (matching `_tender_rows` in
    `tests.py`) and deduplicates rows that share the same contractor,
    normalised reference number, AND amount before aggregating. Both
    guards are needed: an agenda document can carry a near-duplicate row
    for the same tender that its own minutes document also records, AND a
    single minutes document has been seen to extract the same declared
    award twice. Without them a single real award gets summed once per
    extracted row — confirmed live for Kilmore Group Pty Ltd (one real
    $2.08M award reported as $6.24M / 3 awards) — see docs/investigator/
    AUDIT_2026-08-14.md. Only rows agreeing on amount are merged — two rows
    sharing a reference number but a genuinely different amount are left
    separate, since that's the signature of a legitimate multi-tranche
    award under one contract number, not a duplicate.
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
            Meeting.document_type == "minutes",
            Tender.amount.isnot(None),
        )
    )
    q = _year_filter_query(q, Meeting, from_year, to_year, meeting_id=meeting_id)
    all_rows = q.all()

    # Dedup: same contractor + same normalised reference + same amount ==
    # one real award extracted more than once, not independent awards.
    seen: dict[tuple[str, str, float], int] = {}  # (contractor_key, ref_key, amount) -> row index
    rows = []
    for r in all_rows:
        tid, awarded_to, amount, desc, ref, conf, mdate = r
        contractor_key = _normalise_contractor((awarded_to or "").strip())
        ref_key = _normalise_tender_ref(ref)
        amt = float(amount or 0)
        if ref_key and contractor_key:
            dedup_key = (contractor_key, ref_key, amt)
            if dedup_key in seen:
                continue  # duplicate extraction of the same real award — skip
            seen[dedup_key] = tid
        rows.append(r)

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
# Decider x supplier — the Part 3.3 conflict-of-interest join between who
# AWARDS a tender and who WINS it
# ---------------------------------------------------------------------------


@dataclass
class SurnameCollision:
    """One raw surname-substring hit between a tender winner's business name
    and a real voting councillor's surname. A hit is a candidate to
    investigate on provenance, not a confirmed conflict — see
    `decider_supplier_conflict`'s docstring for why."""
    firm: str
    amount: float
    councillor_id: int
    councillor_name: str
    surname: str


@dataclass
class DeciderSupplierConflict:
    tender_motions: int              # minutes motions matched as tender-award (Limb 1)
    votes_on_tender_motions: int
    declared_votes: int
    declared_pct: float
    base_declared_pct: float         # chamber-wide declared_interest rate, all minutes votes
    named_awards: int                # deduped named (non-Respondent, non-NULL) minutes tenders (Limb 2)
    surnames_tested: int
    collisions: list[SurnameCollision] = field(default_factory=list)


def decider_supplier_conflict(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    meeting_id: int | None = None,
) -> DeciderSupplierConflict:
    """
    Part 3.3 procurement-integrity test: does the decider<->winner join expose
    an undeclared conflict of interest between whoever votes on a tender award
    and whoever wins it?

    Two independent limbs. Neither touches `interest_declarations`, so the
    item_reference fan-out risk documented in Investigator_prompt.txt §0.4 /
    `_linked_declared_votes` (a same-numbered agenda item recurring across
    unrelated meetings, or more than one `interest_declarations` row for one
    real declaration) does not apply to this function at all:

    (1) Declaration rate on tender-award motions. Tender-award motions are
        identified by a keyword match for tender/RFT/contract-award language
        on `motions.title` / `motions.motion_text` (minutes only — agendas
        carry officer recommendations, not decided votes). The declaration
        signal is read DIRECTLY off `votes.declared_interest` for the votes
        cast on those motions, never via a join out to
        `interest_declarations` — `votes` carries
        UNIQUE(motion_id, councillor_id), so this limb cannot fan out no
        matter how `item_reference` is reused elsewhere in the corpus.
        Compared against the chamber-wide declaration rate across ALL minutes
        votes as the base rate.

    (2) Name-match. Does any tender WINNER (`tenders.awarded_to`) contain a
        real voting councillor's surname? This is a plain string match
        against `tenders.awarded_to` — there is no schema link from `tenders`
        to a `motions`/`votes`/`interest_declarations` row at all, so there is
        no join-safety risk here either; the only risk is a name-COLLISION
        false positive (a firm whose name happens to contain a councillor's
        surname), which is why every raw hit is data for a human to resolve
        on provenance, not itself evidence of a conflict.
        - Surnames tested are restricted to councillors who cast >=1 vote
          (`Councillor.id` present in `votes.councillor_id`) and whose
          `family_name` is >=4 characters. The vote-cast restriction is what
          excludes the ~197 zero-vote placeholder councillor records
          (Investigator_prompt.txt §0.4) — they carry no vote row to match
          on, so they're never selected; no separate filter is needed. The
          length floor cuts short-surname noise (a 3-letter surname collides
          with too many unrelated business names to be informative).
        - `awarded_to` NULL/blank rows are EXCLUDED from this limb outright,
          never treated as a redacted or concealed award (the [25] trap,
          §0.6) — a NULL winner here is an extraction gap, not evidence.
          "Respondent N" placeholders (confidential awards) are excluded for
          the same reason: there is no name to match against.
        - Named award rows are deduplicated by (normalised contractor,
          normalised reference number, amount) before matching — the same
          guard `tender_concentration()` needed after AUDIT_2026-08-14.md
          found it missing there. Confirmed live on this corpus: "G T Evans
          Weed Spraying Service" / ref TEN0008 / $70,000 is extracted as TWO
          minutes rows 16 days apart (ids 172, 1850) — one real 1995 award,
          not two. Without this guard a single real-world surname collision
          gets counted twice; this function counts it once.

    Both limbs filter to `Meeting.document_type == 'minutes'`.

    `collisions` lists whatever survives dedup; resolving whether a listed
    collision is a real relationship or a business-name coincidence (e.g. a
    firm trading under a common surname, or a product/manufacturer name that
    happens to match) requires reading the tender's own extraction_evidence
    quote — this function does not do that resolution itself, it only
    surfaces candidates.
    """
    # ---- Limb 1: declaration rate on tender-award motions ----------------
    tender_kw = (
        func.lower(Motion.title).like("%tender%")
        | func.lower(Motion.title).like("% rft %")
        | func.lower(Motion.title).like("rft %")
        | func.lower(Motion.title).like("%contract%award%")
        | func.lower(Motion.motion_text).like("%accept the tender%")
        | func.lower(Motion.motion_text).like("%awards%contract%")
        | func.lower(Motion.motion_text).like("%rft %")
    )
    tm_q = (
        session.query(Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            tender_kw,
        )
    )
    tm_q = _year_filter_query(tm_q, Meeting, from_year, to_year, meeting_id=meeting_id)
    tender_motion_ids = [mid for (mid,) in tm_q.all()]

    votes_on_tm = 0
    declared_on_tm = 0
    if tender_motion_ids:
        vote_rows = (
            session.query(Vote.declared_interest)
            .filter(Vote.motion_id.in_(tender_motion_ids))
            .all()
        )
        votes_on_tm = len(vote_rows)
        declared_on_tm = sum(1 for (d,) in vote_rows if d)

    base_q = (
        session.query(Vote.declared_interest)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
    )
    # NOT meeting-scoped even when meeting_id is set: this is the "normal"
    # baseline a single meeting's tender-motion declaration rate is compared
    # against (headline below) — scoping it to the same one meeting would
    # compare a number to itself instead of to a real baseline.
    base_q = _year_filter_query(base_q, Meeting, from_year, to_year)
    base_rows = base_q.all()
    base_pct = round(100 * sum(1 for (d,) in base_rows if d) / len(base_rows), 2) if base_rows else 0.0

    # ---- Limb 2: name-match tender winners against real councillor surnames
    surnames = (
        session.query(Councillor.id, Councillor.given_name, Councillor.family_name)
        .filter(
            Councillor.family_name.isnot(None),
            func.length(Councillor.family_name) >= 4,
            Councillor.id.in_(select(Vote.councillor_id).distinct()),
        )
        .all()
    )

    aw_q = (
        session.query(Tender.id, Tender.awarded_to, Tender.amount, Tender.reference_number)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Tender.awarded_to.isnot(None),
            func.trim(Tender.awarded_to) != "",
            ~func.lower(Tender.awarded_to).like("respondent%"),
        )
    )
    aw_q = _year_filter_query(aw_q, Meeting, from_year, to_year, meeting_id=meeting_id)

    # Dedup pass — see docstring: a real award can be extracted more than
    # once (agenda+minutes, or twice within minutes); collapse rows sharing
    # the same normalised contractor + normalised reference + amount before
    # matching, exactly like `tender_concentration()`'s fix.
    seen: dict[tuple[str, str, float], int] = {}
    named_rows: list[tuple[int, str, float]] = []
    for tid, awarded_to, amount, ref in aw_q.all():
        name = awarded_to.strip()
        amt = float(amount or 0)
        ck = _normalise_contractor(name)
        rk = _normalise_tender_ref(ref)
        if ck and rk:
            key = (ck, rk, amt)
            if key in seen:
                continue
            seen[key] = tid
        named_rows.append((tid, name, amt))

    import re as _re_dsc
    collisions: list[SurnameCollision] = []
    for _tid, firm, amt in named_rows:
        fl = firm.lower()
        for cid, given, family in surnames:
            s = family.lower().strip()
            if _re_dsc.search(r"\b" + _re_dsc.escape(s) + r"\b", fl):
                collisions.append(SurnameCollision(
                    firm=firm, amount=amt, councillor_id=cid,
                    councillor_name=f"{given or ''} {family or ''}".strip(),
                    surname=family,
                ))

    return DeciderSupplierConflict(
        tender_motions=len(tender_motion_ids),
        votes_on_tender_motions=votes_on_tm,
        declared_votes=declared_on_tm,
        declared_pct=round(100 * declared_on_tm / votes_on_tm, 2) if votes_on_tm else 0.0,
        base_declared_pct=base_pct,
        named_awards=len(named_rows),
        surnames_tested=len(surnames),
        collisions=collisions,
    )


# ---------------------------------------------------------------------------
# Delegate/board-member conflict — the mirror image of decider_supplier_conflict:
# does the DECIDER's OWN appointed role on an external body go undeclared when
# that body's business comes before Council? [41] in INVESTIGATIONS.md.
# ---------------------------------------------------------------------------

@dataclass
class DelegateBodyResult:
    label: str                      # display name for the body
    n_appointed_councillors: int    # distinct councillors ever appointed to this body
    n_appointment_windows: int      # appointment-tenure windows built (see function docstring)
    n_motions: int                  # minutes motions matching the body's keyword
    affiliated_votes: int           # votes cast by an appointee, inside their own tenure window
    affiliated_declared: int
    affiliated_declared_pct: float
    other_votes: int                # every other councillor's vote on the SAME motions
    other_declared: int
    other_declared_pct: float
    declarations_corpuswide: int    # interest_declarations rows anywhere mentioning the keyword


@dataclass
class DelegateBodyConflict:
    bodies: list[DelegateBodyResult] = field(default_factory=list)


# Cambridge-specific config, not a generic mechanism: the three external bodies
# with enough appointment + motion volume to test on THIS corpus (identified by
# the [41] Explorer session's Part-1 survey of the `appointments` table). A
# second council would need its own list of regional-council / outside-board
# appointments — there is no way to discover "which external bodies get their
# own councillors appointed to them" generically without a table of them, so
# (like the 2018-21 Authorised-Inquiry window hardcoded in `_recusal_era` and
# `public_question_responsiveness`, per REFINEMENT_PROTOCOL.md's dimension-4
# backlog) this is logged as a documented, council-specific literal rather than
# a blocking issue: `council_id`/`from_year`/`to_year` stay fully generic, only
# this table is Cambridge-specific, and a second council with no equivalent
# appointments simply yields an empty `bodies` list (see `data_ok` handling in
# the calling TestResult).
#
# `appt_like` / `appt_exclude` are case-insensitive substring matches against
# `appointments.body_name`, not exact-string matches. This is a deliberate fix
# over the original scratchpad script (scratchpad/h41_body_conflict.py), which
# matched `body_name` by an exact IN-list and — for Ocean Gardens specifically —
# undercounted appointment windows by ~45% (23 of 43 rows): the same real
# retirement-village board is extracted across meetings/years as "Ocean Gardens
# (Inc) Board of Management", "Ocean Gardens (Inc)", "Ocean Gardens (Inc)
# Board", "Ocean Gardens (Inc.) Board" and "Ocean Gardens Retirement Village"
# (confirmed same `role` values — Director / Director Appointment — across all
# five variants). This is the same free-text-inconsistency failure mode the
# STANDING CONFOUND CHECKLIST already documents for `appointments.role`
# (Explorer_prompt.txt, added the same session), just on `body_name` instead —
# not previously caught because [41] was the first session to touch this
# table. Fixing it changes Ocean Gardens from 17/3 (17.6%) declared affiliated
# votes to 21/5 (23.8%) — a materially different, MORE supportive number, not
# a smaller one; verified directly against council.db during refinement
# (2026-08-14).
_DELEGATE_BODIES: list[dict] = [
    {
        "label": "Mindarie Regional Council",
        "appt_like": ["Mindarie Regional Council"],
        # "Mindarie Regional Council Working Group" (1 appointment row, 2011)
        # is deliberately excluded: a working group is a distinct sub-body,
        # not the plenary regional council whose meeting reports/tenders are
        # the "Mindarie"-titled motions this test measures against.
        "appt_exclude": ["Working Group"],
        "motion_keyword": "Mindarie",
    },
    {
        "label": "Tamala Park Regional Council",
        "appt_like": ["Tamala Park"],
        "appt_exclude": [],
        "motion_keyword": "Tamala Park",
    },
    {
        "label": "Ocean Gardens (Inc) Board of Management",
        "appt_like": ["Ocean Gardens"],
        "appt_exclude": [],
        "motion_keyword": "Ocean Gardens",
    },
]


def delegate_body_conflict(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
) -> DelegateBodyConflict:
    """
    Part 3.3 integrity test, the mirror image of `decider_supplier_conflict`:
    when a councillor is Council's OWN appointed delegate / representative /
    board member on an external body, do they declare an interest before
    voting on THAT BODY's business — the same disclosure regime that would
    apply to a private supplier relationship?

    Per body in `_DELEGATE_BODIES` (a documented, Cambridge-specific config —
    see that constant's docstring for why council-agnosticism stops there):

      1. Build one appointment-tenure "window" per (councillor, appointment)
         row: [this appointment's meeting_date, the SAME councillor's next
         reappointment to the SAME body, or +4y if there is none). A
         councillor only counts as "affiliated" during their actual delegate
         tenure, not their whole career on Council — skipping this windowing
         gives a materially different, wrong answer (confirmed during
         refinement: a naive "ever appointed" match inflates the affiliated
         vote count by counting votes cast years before or after the actual
         appointment).
      2. Find every `document_type='minutes'` motion whose title or text
         contains the body's keyword (free-text match — inherits the same
         false-positive risk `decider_supplier_conflict` accepts for its
         tender-keyword match: one genuine false positive is documented in
         INVESTIGATIONS.md [41], a 2017 "thank three retiring councillors"
         motion that incidentally mentions "Mindarie"; disclosed as a
         precision limit, it does not change the direction of the result
         since it contributes zero declarations either way).
      3. Split every vote on those motions into "affiliated" (cast by a
         councillor inside their own tenure window for that body) vs "other"
         (every OTHER councillor's vote on the SAME motions — this controls
         for the motion's own declaration-worthiness, a cleaner comparison
         than a bare corpus-wide base rate).
      4. `declarations_corpuswide` is a separate, independent sanity count:
         how many `interest_declarations` rows anywhere in the whole corpus
         mention the body's keyword in free text. This is a plain
         `WHERE description LIKE ...` — it does NOT join
         `interest_declarations` out to `motions`/`votes` at all, so the
         §0.4 `item_reference` fan-out caveat (anchor on
         `votes.declared_interest=1` before treating a declaration as
         anything but an enrichment lookup — see `_linked_declared_votes`)
         does not apply here: there is no join to fan out. Steps 1–3's
         affiliated/other split is read directly off `votes.declared_interest`
         (`votes` carries UNIQUE(motion_id, councillor_id)), the same
         fan-out-safe pattern `decider_supplier_conflict`'s Limb 1 uses.

    `document_type='minutes'` is filtered on the appointment side and the
    motion side (agendas carry officer text but no decided vote outcomes).
    `from_year`/`to_year` filter which MOTIONS (and so which votes) are in
    scope; appointment history itself is read in full regardless of the year
    filter, because a window opened before `from_year` can still be open
    (and so still relevant) during it.
    """
    result = DelegateBodyConflict()

    for body in _DELEGATE_BODIES:
        appt_q = (
            session.query(Appointment.councillor_id, Meeting.meeting_date)
            .join(Meeting, Appointment.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Meeting.document_type == "minutes",
                Appointment.councillor_id.isnot(None),
            )
        )
        like_clause = None
        for kw in body["appt_like"]:
            c = Appointment.body_name.ilike(f"%{kw}%")
            like_clause = c if like_clause is None else (like_clause | c)
        appt_q = appt_q.filter(like_clause)
        for ex in body["appt_exclude"]:
            appt_q = appt_q.filter(~Appointment.body_name.ilike(f"%{ex}%"))

        by_cid: dict[int, list[date]] = defaultdict(list)
        for cid, mdate in appt_q.all():
            if mdate:
                by_cid[cid].append(mdate if isinstance(mdate, date) else date.fromisoformat(mdate))

        windows: list[tuple[int, date, date]] = []
        for cid, dates in by_cid.items():
            dates = sorted(set(dates))
            for i, d in enumerate(dates):
                end = dates[i + 1] if i + 1 < len(dates) else d + timedelta(days=365 * 4)
                windows.append((cid, d, end))

        motion_q = (
            session.query(Motion.id, Meeting.meeting_date)
            .join(Meeting, Motion.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Meeting.document_type == "minutes",
                (Motion.title.ilike(f"%{body['motion_keyword']}%"))
                | (Motion.motion_text.ilike(f"%{body['motion_keyword']}%")),
            )
        )
        motion_q = _year_filter_query(motion_q, Meeting, from_year, to_year)
        motion_date: dict[int, date] = {}
        for mid, mdate in motion_q.all():
            if mdate:
                motion_date[mid] = mdate if isinstance(mdate, date) else date.fromisoformat(mdate)

        aff_n = aff_decl = oth_n = oth_decl = 0
        if motion_date:
            vote_rows = (
                session.query(Vote.motion_id, Vote.councillor_id, Vote.declared_interest)
                .filter(Vote.motion_id.in_(list(motion_date.keys())))
                .all()
            )
            for mid, cid, declared in vote_rows:
                mdate = motion_date[mid]
                is_aff = any(
                    wcid == cid and start <= mdate < end for wcid, start, end in windows
                )
                if is_aff:
                    aff_n += 1
                    aff_decl += bool(declared)
                else:
                    oth_n += 1
                    oth_decl += bool(declared)

        decl_n = (
            session.query(func.count(InterestDeclaration.id))
            .join(Meeting, InterestDeclaration.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                InterestDeclaration.description.ilike(f"%{body['motion_keyword']}%"),
            )
            .scalar()
        ) or 0

        result.bodies.append(DelegateBodyResult(
            label=body["label"],
            n_appointed_councillors=len(by_cid),
            n_appointment_windows=len(windows),
            n_motions=len(motion_date),
            affiliated_votes=aff_n,
            affiliated_declared=aff_decl,
            affiliated_declared_pct=round(100 * aff_decl / aff_n, 1) if aff_n else 0.0,
            other_votes=oth_n,
            other_declared=oth_decl,
            other_declared_pct=round(100 * oth_decl / oth_n, 1) if oth_n else 0.0,
            declarations_corpuswide=decl_n,
        ))

    return result


# ---------------------------------------------------------------------------
# Oversight-body capture — [48] in INVESTIGATIONS.md: does membership on the
# council's own accountability bodies (Audit Committee, CEO Performance
# Review Committee) skew toward the chamber's habitual winners, or does it
# draw broadly? The "who controls the controls" mirror of
# `decider_supplier_conflict` (3.3), read as a Governance/3.2 AND Strength/E
# dual-domain test.
# ---------------------------------------------------------------------------

@dataclass
class OversightAppointeeProfile:
    councillor_id: int
    name: str
    n: int              # contested votes cast (cohort floor already applied)
    win_rate: float      # share on the winning side


@dataclass
class OversightBodyCaptureStats:
    n_appointees: int              # distinct councillors EVER appointed (no vote-count floor)
    appointee_n: int               # pooled contested votes, cohort appointees only
    appointee_won: int
    appointee_win_rate: float
    non_appointee_n: int
    non_appointee_won: int
    non_appointee_win_rate: float
    n_appointee_cohort: int        # appointees with >= min_votes contested votes
    n_non_appointee_cohort: int
    profiles: list[OversightAppointeeProfile] = field(default_factory=list)  # cohort appointees, by win_rate


def oversight_body_capture(
    session: Session,
    council_id: int,
    min_votes: int = 20,
) -> OversightBodyCaptureStats:
    """
    [48] Governance/3.2 ("who controls the controls") AND Strength/E: do the
    council's own accountability bodies — the Audit Committee (and its
    corpus renamings: Audit and Risk / Audit, Risk and Improvement / Audit
    Standing / Town's Audit Committee / Audit Committee interviewing panel)
    and the CEO/Chief Executive Officer Performance Review Committee — draw
    appointees from across the chamber's power spectrum, or only from its
    habitual winners?

    Appointee set: every distinct `councillor_id` EVER appointed to a body
    whose `appointments.body_name` case-insensitively contains "audit", or
    both "ceo"/"chief executive" AND "performance". Unlike
    `delegate_body_conflict`'s `_DELEGATE_BODIES` (a hand-maintained list of
    Cambridge-specific external-body names), these are generic committee-role
    keywords any English-speaking council's audit/CEO-review body is likely
    to be named with — so, unusually for an `appointments`-table query, this
    half needs no council-specific config to stay meaningful on a second
    corpus. No `document_type` filter on the appointments side: an
    appointment can be minuted via either document type, and this is a plain
    `DISTINCT councillor_id` over a single-anchor join (`appointments` →
    `meetings`), not a query that could fan out — filtering would only risk
    dropping a real appointee, not fixing a duplication that isn't there.

    Win-rate methodology reused verbatim from `voting_power()` / [18], for
    an apples-to-apples appointee-vs-non-appointee comparison:
    `document_type='minutes'`, `outcome IN (CARRIED, LOST)`, `votes_against
    > 0`, `choice IN (FOR, AGAINST)`, won = (FOR & CARRIED) or (AGAINST &
    LOST). `document_type='minutes'` is required here — without it, 2
    agenda-document motions with a CARRIED/LOST outcome (an extraction
    artifact; agendas aren't supposed to carry an outcome) leak into the
    contested-vote pool (see [48 REFINEMENT ATTEMPT] in INVESTIGATIONS.md).
    NOTE: `voting_power()` itself does not carry this filter yet
    (REFINEMENT_PROTOCOL.md dimension-2 backlog, logged but not fixed
    unilaterally there) — this function's pooled win rate is therefore NOT
    directly comparable to `voting_power()`'s published figures; both are
    internally consistent but on a slightly different vote pool.

    Cohort floor (`min_votes`, default 20) matches `councillor_tenure()`'s
    ([45]) threshold, for comparability across the two tests. `votes`
    carries `UNIQUE(motion_id, councillor_id)`, so grouping by
    `Vote.councillor_id` here cannot fan out.
    """
    appt_pattern = (
        Appointment.body_name.ilike("%audit%")
        | (
            (Appointment.body_name.ilike("%ceo%") | Appointment.body_name.ilike("%chief executive%"))
            & Appointment.body_name.ilike("%performance%")
        )
    )
    appointee_ids: set[int] = {
        cid for (cid,) in (
            session.query(Appointment.councillor_id)
            .join(Meeting, Appointment.meeting_id == Meeting.id)
            .filter(
                Meeting.council_id == council_id,
                Appointment.councillor_id.isnot(None),
                appt_pattern,
            )
            .distinct()
        )
    }

    rows = (
        session.query(
            Vote.councillor_id, Vote.choice, Motion.outcome,
            Councillor.given_name, Councillor.family_name,
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
            Motion.votes_against > 0,
            Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]),
        )
        .all()
    )

    per_cllr: dict[int, dict] = defaultdict(lambda: {"n": 0, "won": 0, "name": ""})
    for cid, choice, outcome, given, family in rows:
        won = (choice == VoteChoice.FOR and outcome == MotionOutcome.CARRIED) or \
              (choice == VoteChoice.AGAINST and outcome == MotionOutcome.LOST)
        d = per_cllr[cid]
        d["n"] += 1
        d["won"] += int(won)
        d["name"] = f"{given or ''} {family or ''}".strip()

    profiles: list[OversightAppointeeProfile] = []
    app_n = app_won = non_n = non_won = 0
    n_app_cohort = n_non_cohort = 0
    for cid, d in per_cllr.items():
        if d["n"] < min_votes:
            continue
        if cid in appointee_ids:
            app_n += d["n"]
            app_won += d["won"]
            n_app_cohort += 1
            profiles.append(OversightAppointeeProfile(
                councillor_id=cid, name=d["name"], n=d["n"],
                win_rate=round(100 * d["won"] / d["n"], 1),
            ))
        else:
            non_n += d["n"]
            non_won += d["won"]
            n_non_cohort += 1

    profiles.sort(key=lambda p: p.win_rate)

    return OversightBodyCaptureStats(
        n_appointees=len(appointee_ids),
        appointee_n=app_n,
        appointee_won=app_won,
        appointee_win_rate=round(100 * app_won / app_n, 2) if app_n else 0.0,
        non_appointee_n=non_n,
        non_appointee_won=non_won,
        non_appointee_win_rate=round(100 * non_won / non_n, 2) if non_n else 0.0,
        n_appointee_cohort=n_app_cohort,
        n_non_appointee_cohort=n_non_cohort,
        profiles=profiles,
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


def objection_dose_response(session: Session, council_id: int,
                            meeting_id: int | None = None) -> ObjectionDoseStats:
    """
    Refusal rate as a function of *how many* community objections an application
    drew. The existing objection panel treats objection as binary; this asks
    whether there is a threshold where neighbour opposition starts to bite.

    Buckets: 0, 1, 2-4, 5+ objectors. Decided applications only (APPROVED /
    REFUSED). Objections = community_submissions with position='object'.

    `meeting_id`, when set, narrows to applications decided at that one
    meeting (docs/frontend/PRODUCT_ROADMAP.md F2's single-meeting digest) —
    only applications with a linked `motion_id` are reachable this way (see
    that same caveat noted against `_t_big_dollar_leniency`).
    """
    q = (
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
    )
    if meeting_id is not None:
        q = q.filter(Meeting.id == meeting_id)
    rows = q.group_by(PlanningApplication.id).all()

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


def transparency_by_year(session: Session, council_id: int,
                         meeting_id: int | None = None) -> TransparencyStats:
    """
    Share of decided council items recorded as confidential, per year.

    Pools four item types that carry an is_confidential flag — tenders,
    'other items', delegated decisions and budget items — over minutes (not
    agendas). Surfaces whether the proportion of business taken behind closed
    doors has shifted over the 30-year record.

    `meeting_id`, when set, narrows every subquery to that one meeting
    (docs/frontend/PRODUCT_ROADMAP.md F2's single-meeting digest) — the
    `:mid IS NULL OR m.id = :mid` form keeps one SQL string for both modes.

    The `other_items` branch excludes rows whose description is a standing
    "Nil items" placeholder heading (e.g. "Confidential Reports - Nil items")
    — a section header meaning nothing was listed under it, not a decided
    item, and not confidential just because the section it stands in for
    would be (digest design plan, fact 5: meeting 258's "1 of 34 items
    closed" was entirely this one placeholder row). SQLite's LIKE is
    case-insensitive on ASCII, so one pattern covers "Nil"/"nil". Confirmed
    2026-08-27 against live data: only 2 of 529 corpus-wide confidential
    other_items rows match, so this doesn't move the corpus-wide baseline
    `transparency.confidential_share` publishes — a per-meeting fix, not a
    whole-corpus correction.
    """
    from sqlalchemy import text as sql_text

    sql = sql_text(
        """
        WITH allitems AS (
            SELECT m.meeting_date d, t.is_confidential c, 'tenders' AS cat
              FROM tenders t JOIN meetings m ON t.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
               AND (:mid IS NULL OR m.id = :mid)
            UNION ALL
            SELECT m.meeting_date, o.is_confidential, 'other'
              FROM other_items o JOIN meetings m ON o.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
               AND (:mid IS NULL OR m.id = :mid)
               AND o.description NOT LIKE '%nil item%'
            UNION ALL
            SELECT m.meeting_date, dd.is_confidential, 'delegated'
              FROM delegated_decisions dd JOIN meetings m ON dd.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
               AND (:mid IS NULL OR m.id = :mid)
            UNION ALL
            SELECT m.meeting_date, b.is_confidential, 'budget'
              FROM budget_items b JOIN meetings m ON b.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes'
               AND (:mid IS NULL OR m.id = :mid)
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
    rows = session.execute(sql, {"cid": council_id, "mid": meeting_id}).fetchall()

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
    # Peak by % among years with a meaningful sample (>= 50 items). No years
    # at all is a real case for a meeting_id-scoped call (a single meeting
    # can easily have zero rows across all four category tables) — not just
    # a hypothetical the corpus-wide call never hits.
    eligible = [y for y in years if y.total >= 50]
    peak = max(eligible, key=lambda y: y.confidential_pct) if eligible else (years[-1] if years else None)

    return TransparencyStats(
        years=years,
        pre_era_pct=pre_pct,
        peak_year=peak.year if peak else 0,
        peak_pct=peak.confidential_pct if peak else 0.0,
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
# Linkage is item-level and vote-driven, via the shared `_linked_declared_votes`
# helper (see its docstring): interest_declarations.item_reference ==
# motions.item_number at the same meeting, then that councillor's vote on that
# motion. Anchoring on votes.declared_interest = 1 (not on interest_declarations
# rows joined outward) avoids both the meeting-level cross-contamination where a
# councillor declaring several interest types at one meeting would otherwise have
# every type attributed to every vote, AND the fan-out a declaration-driven join
# produces when a meeting has duplicate declaration rows or multiple motions
# sharing one item_number — see `LinkedDeclaredVote`'s docstring for the concrete
# fabricated-claim case (naming a real councillor) this replaced.

_RECUSAL_ERAS = [
    ("pre", "Before Inquiry (pre-2018)", None, 2017),
    ("inquiry", "Authorised Inquiry (2018–2021)", 2018, 2021),
    ("post", "After Inquiry (2022+)", 2022, None),
]

def _recusal_era(year: int) -> str:
    if year < 2018:
        return "pre"
    if year <= 2021:
        return "inquiry"
    return "post"


def _ministerial_approved(what: str | None, quote: str | None) -> bool:
    """True if a must-leave declaration cites s.5.69 LGA 1995 Ministerial
    approval to participate despite the interest — a lawful, disclosed
    exception, not a compliance lapse. Every other must-leave declaration in
    this corpus cites the standard disclose-and-leave provision, s.5.65,
    instead — the section number alone reliably tells the two apart (see
    docs/review, BLOCKING flag "Most frequent stay-and-vote", 2026-08-22
    pass 1: four councillors' single post-2022 stay-and-vote, all on the
    same s.5.69-approved item, were being ranked as an individual
    compliance-lapse pattern)."""
    return "5.69" in f"{what or ''} {quote or ''}"


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
    # post-2022 must-leave stays excluded from `drivers` because the
    # declaration itself cites s.5.69 Ministerial approval — a distinct,
    # non-adverse category, not a compliance lapse (see `_ministerial_approved`)
    #
    # Shipped to recusal.json ahead of any frontend consumer: pass 1's
    # (2026-08-22) BLOCKING fix removed RecusalTrendPanel's top-driver
    # rendering entirely rather than making it Ministerial-approval-aware, so
    # this field is currently unread. Its intended consumer is a future
    # tie-aware, Ministerial-approval-aware driver callout in that panel
    # (frontend track) — the plumbing was kept because recomputing it later
    # would mean re-deriving the same s.5.69 split, not because it's expected
    # to stay unused (see docs/review, pass 2 ADVISORY flag, 2026-08-22).
    ministerial_approved_post_n: int = 0


def recusal_compliance_trend(
    session: Session,
    council_id: int,
    min_year_n: int = 4,
) -> RecusalTrendStats:
    """Recusal compliance over time, split by the legal type of interest.

    Built on `_linked_declared_votes` — the same vote-driven, fan-out-safe
    linkage `conflict_recusal_stats`/`declared.json` uses — rather than a
    second, independently-computed item-level join. The two must never be
    able to disagree on "how many declared-interest votes did X cast"; see
    `LinkedDeclaredVote`'s docstring for what went wrong when this query
    maintained its own join.
    """
    from sqlalchemy import text

    linked = _linked_declared_votes(session, council_id)

    # by type x era
    te: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])  # [declared, recused]
    # must-leave by year
    ml_year: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    # post-2022 must-leave drivers (stayed and voted, excluding s.5.69
    # Ministerial-approved participation — see `_ministerial_approved`)
    drv: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [stayed, total]
    ministerial_approved_post_n = 0
    # raw declaration rows behind each (type, era) cell, for the drill-down
    te_rows: dict[tuple[str, str], list[tuple]] = defaultdict(list)

    for row in linked:
        if row.year is None:
            continue
        t = row.interest_type or "other"
        era = _recusal_era(row.year)
        rec = _actually_stepped_out(row.choice, row.quote)
        te[(t, era)][0] += 1
        if rec:
            te[(t, era)][1] += 1
        te_rows[(t, era)].append((row.declaration_id, row.item, row.name, rec, row.what, row.date))
        if t in ("financial", "proximity"):
            ml_year[row.year][0] += 1
            if rec:
                ml_year[row.year][1] += 1
            if row.year >= 2022:
                if _ministerial_approved(row.what, row.quote):
                    ministerial_approved_post_n += 1
                else:
                    drv[row.name][1] += 1
                    if not rec:
                        drv[row.name][0] += 1

    # All minute quotes per declaration behind a cell, concatenated — see the
    # matching fix and comment in `_linked_declared_votes`.
    _CELL_CAP = 60
    all_dids = [r[0] for rows in te_rows.values() for r in sorted(
        rows, key=lambda x: x[5] or "", reverse=True)[:_CELL_CAP] if r[0] is not None]
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
            quote_by_decl[did] = f"{quote_by_decl[did]} {q}" if did in quote_by_decl else q

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
        ministerial_approved_post_n=ministerial_approved_post_n,
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
    meeting_id: int | None = None,
) -> PQResponsivenessStats:
    """Are public questions answered in the meeting, or 'taken on notice'?

    `meeting_id`, when set, narrows to that one meeting's questions
    (docs/frontend/PRODUCT_ROADMAP.md F2's single-meeting digest) — the
    era/year breakdown fields become degenerate (a single meeting sits in
    one era, one year); a caller wanting this meeting's numbers next to a
    real baseline should also call this unscoped and compare, the same way
    `_t_question_responsiveness`'s single-meeting variant does.
    """
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
          AND (:mid IS NULL OR mt.id = :mid)
    """), {"cid": council_id, "mid": meeting_id}).all()

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
