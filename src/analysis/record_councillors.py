"""Builds record_councillors.json (docs/frontend/RECORD_PAGE_PLAN.md
Step 6, Part B.3) -- a REDUCED projection of councillor data for
/record's councillor cards (Phase 2), not councillors.json republished.

Only the five factual fields the brief allows: years served, motions
moved, votes cast, most frequent seconder, contested-vote counts -- the
last as raw won/lost counts, not a win_rate (B.3 explicitly rules out
publishing the rate). No dissent_rate, no dissent_effectiveness, no
recusal_rate, no declarations -- councillors.json carries those and
stays full-tier; this file is the only councillor data /record is
allowed to publish.

Cards sort alphabetically by surname (B.3 -- never by a performance
field; "first year served" was the plan's other allowed option).
"most frequent seconder" names a second councillor on the first one's
card -- a mild, symmetric, factual association claim B.3 says to keep.
"""

from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.analysis.queries import co_mover_pairs, councillor_tenure
from src.models import Councillor, Meeting, Motion, MotionOutcome, Vote, VoteChoice


def _most_frequent_seconders(session: Session, council_id: int) -> dict[str, dict]:
    """Per mover, their single most-common seconder.

    Uses the raw pair table (min_count=1), not co-movers.json's
    min_count=5 chart threshold (RECORD_PAGE_PLAN.md A.5): a quieter
    councillor's most-common seconder can fall below that chart's bar
    and must not silently vanish from their own card.
    """
    result: dict[str, dict] = {}
    for pair in co_mover_pairs(session, council_id, min_count=1):
        current = result.get(pair.mover_name)
        if current is None or pair.count > current["count"]:
            result[pair.mover_name] = {"name": pair.seconder_name, "count": pair.count}
    return result


def _contested_vote_counts(session: Session, council_id: int) -> dict[int, tuple[int, int]]:
    """councillor_id -> (total contested votes, won).

    Same population src.analysis.queries.voting_power() scores (motions
    with at least one AGAINST vote, CARRIED or LOST) -- computed
    independently here because voting_power() exposes only a rounded
    win_rate, and B.3 wants raw counts, not a rate.
    """
    rows = (
        session.query(
            Vote.councillor_id,
            func.count(Vote.id),
            func.sum(
                case(
                    (
                        ((Vote.choice == VoteChoice.FOR) & (Motion.outcome == MotionOutcome.CARRIED))
                        | ((Vote.choice == VoteChoice.AGAINST) & (Motion.outcome == MotionOutcome.LOST)),
                        1,
                    ),
                    else_=0,
                )
            ),
        )
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Motion.votes_against > 0,
            Motion.outcome.in_([MotionOutcome.CARRIED, MotionOutcome.LOST]),
            Vote.choice.in_([VoteChoice.FOR, VoteChoice.AGAINST]),
        )
        .group_by(Vote.councillor_id)
        .all()
    )
    return {cid: (int(n), int(won or 0)) for cid, n, won in rows}


def _motions_moved(session: Session, council_id: int) -> dict[str, int]:
    result: dict[str, int] = {}
    for given, family, count in (
        session.query(Councillor.given_name, Councillor.family_name, func.count(Motion.id))
        .join(Motion, Councillor.id == Motion.moved_by_id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .group_by(Councillor.id)
        .all()
    ):
        result[f"{given or ''} {family or ''}".strip()] = count
    return result


def build_record_councillors(session: Session, council_id: int, generated_at: str) -> dict:
    """Build the full record_councillors.json payload.

    Candidate names come from councillor_tenure() alone, not a union of
    several profile sources -- confirmed against the live corpus that
    every name voting_power()/conflict_recusal_stats() know about is
    already a subset of councillor_tenure()'s (tenure is vote-activity
    derived, so it doesn't have councillors.json's by_name projection's
    councillor_terms gap; see that snapshot's own comment for the
    incident this matters for).
    """
    tenure = councillor_tenure(session, council_id)
    moved = _motions_moved(session, council_id)
    most_frequent_seconder = _most_frequent_seconders(session, council_id)
    contested_by_id = _contested_vote_counts(session, council_id)

    name_parts: dict[str, tuple[str, str, int]] = {}
    for cid, given, family in session.query(
        Councillor.id, Councillor.given_name, Councillor.family_name
    ).all():
        name = f"{given or ''} {family or ''}".strip()
        name_parts.setdefault(name, (given or "", family or "", cid))

    slug_by_id = {c.id: c.slug for c in session.query(Councillor).all()}

    councillors = []
    for profile in tenure.profiles:
        given, family, cid = name_parts.get(profile.name, ("", "", None))
        n_contested, n_won = contested_by_id.get(cid, (0, 0))
        councillors.append({
            "name": profile.name,
            "given_name": given,
            "family_name": family,
            "slug": slug_by_id.get(cid),
            "years_served": profile.years,
            "first_vote": profile.first,
            "motions_moved": moved.get(profile.name, 0),
            "votes_cast": profile.n_votes,
            "most_frequent_seconder": most_frequent_seconder.get(profile.name),
            "contested_votes": {
                "total": n_contested,
                "won": n_won,
                "lost": n_contested - n_won,
            },
        })

    councillors.sort(key=lambda c: (c["family_name"], c["given_name"]))

    return {
        "generated_at": generated_at,
        "source": "data/council.db",
        "councillors": councillors,
    }
