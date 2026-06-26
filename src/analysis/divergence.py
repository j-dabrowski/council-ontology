"""
Officer recommendation vs. council decision matching.

Matches agenda motions (officer_recommendation) to their corresponding minutes
motions (outcome) for the same meeting date. Reports which motions diverged from
the officer's recommendation.

Matching strategy:
  1. Meeting-level: agenda.meeting_date == minutes.meeting_date
  2. Motion-level: exact item_number match, then title fuzzy match (SequenceMatcher ≥ 0.5)

Divergence definition (conservative):
  FOLLOWED  — council CARRIED the motion (it carried what was before them, which
               was the officer recommendation in an agenda context).
  DIVERGED  — council LOST or DEFERRED a motion that had an officer recommendation.
              This is the clearest signal that council rejected what officers proposed.
  INDETERMINATE — outcome is null or outcome is WITHDRAWN/LAPSED.

Limitation: this does not detect "council amended the motion text before carrying it."
That requires motion-text diff, which is deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from src.models import Meeting, Motion, MotionOutcome


@dataclass
class DivergencePair:
    meeting_date: date
    item_number: str | None
    title: str
    officer_recommendation: str | None
    council_outcome: str | None
    diverged: bool
    match_confidence: float
    minutes_motion_id: int | None = None   # row id of the matched minutes motion
    motion_text: str | None = None         # full text of the council motion


def officer_divergence(
    session: Session,
    council_id: int,
    from_year: int | None = None,
    to_year: int | None = None,
    min_confidence: float = 0.5,
) -> list[DivergencePair]:
    """
    For every meeting date that has both an agenda and a minutes document,
    match agenda motions (with officer_recommendation) to minutes motions (with outcome)
    and flag divergences.
    """
    from sqlalchemy import extract as sql_extract

    # All meeting dates that have both an agenda and minutes
    agenda_q = session.query(Meeting.meeting_date).filter(
        Meeting.council_id == council_id,
        Meeting.document_type == "agenda",
    )
    minutes_q = session.query(Meeting.meeting_date).filter(
        Meeting.council_id == council_id,
        Meeting.document_type == "minutes",
    )
    if from_year:
        agenda_q = agenda_q.filter(sql_extract("year", Meeting.meeting_date) >= from_year)
        minutes_q = minutes_q.filter(sql_extract("year", Meeting.meeting_date) >= from_year)
    if to_year:
        agenda_q = agenda_q.filter(sql_extract("year", Meeting.meeting_date) <= to_year)
        minutes_q = minutes_q.filter(sql_extract("year", Meeting.meeting_date) <= to_year)

    agenda_dates = {d for (d,) in agenda_q.all()}
    minutes_dates = {d for (d,) in minutes_q.all()}
    paired_dates = sorted(agenda_dates & minutes_dates)

    results: list[DivergencePair] = []

    for meeting_date in paired_dates:
        # Fetch agenda motions with officer recommendations
        agenda_mtg = (
            session.query(Meeting)
            .filter(
                Meeting.council_id == council_id,
                Meeting.meeting_date == meeting_date,
                Meeting.document_type == "agenda",
            )
            .first()
        )
        minutes_mtg = (
            session.query(Meeting)
            .filter(
                Meeting.council_id == council_id,
                Meeting.meeting_date == meeting_date,
                Meeting.document_type == "minutes",
            )
            .first()
        )
        if not agenda_mtg or not minutes_mtg:
            continue

        agenda_motions = (
            session.query(Motion)
            .filter(
                Motion.meeting_id == agenda_mtg.id,
                Motion.officer_recommendation.isnot(None),
            )
            .all()
        )
        minutes_motions = (
            session.query(Motion)
            .filter(Motion.meeting_id == minutes_mtg.id)
            .all()
        )

        if not agenda_motions or not minutes_motions:
            continue

        # Index minutes motions by item_number for fast lookup
        by_item: dict[str, Motion] = {}
        for mm in minutes_motions:
            if mm.item_number:
                by_item[mm.item_number.strip()] = mm

        for am in agenda_motions:
            matched_mm: Motion | None = None
            confidence: float = 0.0

            # Try exact item number match first
            if am.item_number and am.item_number.strip() in by_item:
                matched_mm = by_item[am.item_number.strip()]
                confidence = 1.0
            else:
                # Fall back to title fuzzy match
                best_score = 0.0
                for mm in minutes_motions:
                    if not mm.title or not am.title:
                        continue
                    score = SequenceMatcher(
                        None,
                        am.title.lower().strip(),
                        mm.title.lower().strip(),
                    ).ratio()
                    if score > best_score:
                        best_score = score
                        matched_mm = mm
                confidence = best_score

            if confidence < min_confidence or matched_mm is None:
                continue

            outcome = matched_mm.outcome
            if outcome == MotionOutcome.CARRIED:
                diverged = False
            elif outcome in (MotionOutcome.LOST, MotionOutcome.DEFERRED):
                diverged = True
            else:
                continue  # WITHDRAWN, LAPSED, null — skip

            results.append(
                DivergencePair(
                    meeting_date=meeting_date,
                    item_number=am.item_number,
                    title=am.title,
                    officer_recommendation=am.officer_recommendation,
                    council_outcome=outcome.value if outcome else None,
                    diverged=diverged,
                    match_confidence=confidence,
                    minutes_motion_id=matched_mm.id,
                    motion_text=matched_mm.motion_text,
                )
            )

    return results
