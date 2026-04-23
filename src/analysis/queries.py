"""
Query helpers for the council ontology.

These functions operate at the boundary between the three ontology layers:
  Semantic  — who are the actors?
  Kinetic   — what did they do?
  Dynamic   — what patterns emerge?
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models import (
    Council,
    Councillor,
    Meeting,
    Motion,
    MotionOutcome,
    Vote,
    VoteChoice,
)


# ---------------------------------------------------------------------------
# Semantic layer queries
# ---------------------------------------------------------------------------


def get_council_by_name(session: Session, short_name: str) -> Council | None:
    return session.query(Council).filter_by(short_name=short_name).first()


def list_councillors(session: Session, council_id: int) -> list[Councillor]:
    """All councillors who have ever appeared in a vote for the given council."""
    return (
        session.query(Councillor)
        .join(Vote)
        .join(Motion)
        .join(Meeting)
        .filter(Meeting.council_id == council_id)
        .distinct()
        .all()
    )


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


def motions_by_tag(session: Session, council_id: int, tag: str) -> list[Motion]:
    """Find motions whose tag list contains the given tag (case-insensitive)."""
    return (
        session.query(Motion)
        .join(Meeting)
        .filter(
            Meeting.council_id == council_id,
            Motion.tags.ilike(f"%{tag}%"),
        )
        .order_by(Meeting.meeting_date.desc())
        .all()
    )


def planning_motions(session: Session, council_id: int) -> list[Motion]:
    return motions_by_tag(session, council_id, "planning")


def contested_motions(session: Session, council_id: int, min_against: int = 2) -> list[Motion]:
    """Motions that passed but had meaningful opposition."""
    return (
        session.query(Motion)
        .join(Meeting)
        .filter(
            Meeting.council_id == council_id,
            Motion.outcome == MotionOutcome.CARRIED,
            Motion.votes_against >= min_against,
        )
        .order_by(Motion.votes_against.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Dynamic layer queries — voting alignment patterns
# ---------------------------------------------------------------------------


@dataclass
class VotingAlignment:
    councillor_a: str
    councillor_b: str
    total_shared_votes: int
    agreements: int
    agreement_rate: float


def voting_alignment_matrix(
    session: Session, council_id: int
) -> list[VotingAlignment]:
    """
    Compute pairwise voting agreement between all councillors.

    Returns a list of VotingAlignment records sorted by agreement_rate descending.
    Useful for detecting blocs/coalitions (dynamic layer).
    """
    # Get all votes for this council with councillor names
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
    session: Session, councillor_id: int, council_id: int
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
    session: Session, council_id: int, limit: int = 20
) -> list[tuple[str, int]]:
    """Sites with the most planning applications, ordered by count."""
    from src.models import PlanningApplication, Site

    rows = (
        session.query(Site.address, func.count(PlanningApplication.id).label("n"))
        .join(PlanningApplication, PlanningApplication.site_id == Site.id)
        .filter(Site.council_id == council_id)
        .group_by(Site.id)
        .order_by(func.count(PlanningApplication.id).desc())
        .limit(limit)
        .all()
    )
    return [(address, n) for address, n in rows]
