"""
The period digest (digest design plan §1/§3 item 8): scored, salience-ranked
claims across a window of meetings, composed purely over already-computed
meeting records — never recomputed per cadence, per the plan's "smallest
unit, composed upward" decision (the meeting is the stored atom; week /
fortnight / month are pure compositions over it, selected by
`config/digest_policy.json`'s `interval`).

Three surfaces:
- `score_salience()` — `max(novelty, digest_floor)`, fully scripted (the LLM
  never scores). Novelty is a two-sided percentile of a claim's `stat`
  against its own `(test_id, body_class)` baseline
  (`src/analysis/meeting_baselines.py`); `digest_floor` is the per-generator
  floor declared on the claim itself (`src/analysis/tests.py`).
- `meeting_inventory()` — the scripted, evidence-linked "what this meeting
  decided" summary (motions/outcomes/vote-splits/officer-rec departures,
  `other_items` grouped by type) that the battery's own dedicated queries
  can miss (fact 3: 17 parking submissions filed as
  `other_items.item_type='correspondence'`, invisible to
  `engagement.participation`'s dedicated query).
- `compose_period_digest()` — unions the candidate pools of every meeting in
  the window, re-ranks by salience, and — because the gate + per-claim tier
  derivation already ran per meeting — carries both a `deep` (raw, may name
  individuals) and `public` (S7-checked institutional/projected, or `None`)
  view of every candidate, so a later rendering role can build either
  product from the same artifact without re-deriving tiers itself.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.analysis.divergence import officer_divergence
from src.analysis.meeting_baselines import MeetingBaselines, body_class_of, load_meeting_bodies
from src.analysis.tests import TestResult, run_meeting_digest
from src.invariant_gate import derive_claim_tiers, project_to_institutional
from src.models import Councillor, Meeting, Motion, OtherItem

VALID_INTERVALS = ("meeting", "week", "fortnight", "month")

_INTERVAL_DAYS = {"week": 7, "fortnight": 14, "month": 30}


def _two_sided_percentile(value: float, distribution: list[float]) -> float:
    """Rank of `value` within `distribution`, folded so the median reads 0
    and either extreme approaches 1 — "8 of 67 motions dissented" ranks
    above "0 of 55" automatically, whichever side of the baseline it falls."""
    if not distribution:
        return 0.0
    n = len(distribution)
    below = sum(1 for v in distribution if v < value)
    at = sum(1 for v in distribution if v == value)
    percentile = (below + 0.5 * at) / n
    return round(2 * abs(percentile - 0.5), 4)


def score_salience(
    claim: TestResult, baselines: MeetingBaselines, body_class: str, policy: dict,
) -> float:
    """`max(novelty, digest_floor)`. Novelty is disabled (0.0) — the floor is
    the only thing that can make the claim salient — when the claim carries
    no comparable statistic, or this `(test_id, body_class)` has fewer than
    `policy["min_baseline_meetings"]` prior meetings (a 4-member committee's
    3 meetings can't support a percentile — fact 4 of the design plan)."""
    value = claim.stat["value"] if claim.stat is not None else claim.n
    if value is None:
        return claim.digest_floor
    by_body = baselines.baselines.get(claim.test_id, {})
    tb = by_body.get(body_class)
    min_baseline = policy.get("min_baseline_meetings", 8)
    if tb is None or tb.n_meetings < min_baseline:
        novelty = 0.0
    else:
        novelty = _two_sided_percentile(value, tb.values)
    return max(novelty, claim.digest_floor)


def meeting_inventory(session: Session, council_id: int, meeting_id: int) -> dict:
    """The scripted "what this meeting decided" summary — deep view (names
    who moved/seconded each motion). Use `public_inventory_projection()` for
    the name-free version."""
    meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
    motions = (
        session.query(Motion)
        .filter(Motion.meeting_id == meeting_id)
        .order_by(Motion.item_number)
        .all()
    )
    councillor_ids = {m.moved_by_id for m in motions if m.moved_by_id} | {
        m.seconded_by_id for m in motions if m.seconded_by_id
    }
    names_by_id = {
        c.id: f"{c.given_name} {c.family_name}"
        for c in session.query(Councillor).filter(Councillor.id.in_(councillor_ids)).all()
    } if councillor_ids else {}

    # item_id: a stable citation anchor for the Renderer digest mode
    # (RENDERER_PROTOCOL.md dimension 8) — "meeting:motion:<item_number>",
    # falling back to a positional index when item_number is missing so
    # every motion is still citable.
    items = [
        {
            "item_id": f"{meeting_id}:motion:{m.item_number or idx}",
            "item_number": m.item_number,
            "title": m.title,
            "outcome": m.outcome.value if m.outcome else None,
            "votes_for": m.votes_for,
            "votes_against": m.votes_against,
            "votes_abstain": m.votes_abstain,
            "moved_by": names_by_id.get(m.moved_by_id),
            "seconded_by": names_by_id.get(m.seconded_by_id),
        }
        for idx, m in enumerate(motions)
    ]

    departures = [
        {"item_number": p.item_number, "title": p.title}
        for p in officer_divergence(session, council_id, meeting_id=meeting_id)
        if p.diverged
    ]

    # "Nil items" standing-agenda placeholder headings aren't decided items
    # (same exclusion as the transparency_by_year fix — src/analysis/queries.py).
    # item_id here is positional within its item_type bucket — other_items
    # carries no natural per-row citation key the way a motion's item_number is.
    other_items_by_type: dict[str, list[dict]] = {}
    for oi in session.query(OtherItem).filter(OtherItem.meeting_id == meeting_id).all():
        if "nil item" in (oi.description or "").lower():
            continue
        bucket = other_items_by_type.setdefault(oi.item_type, [])
        bucket.append({
            "item_id": f"{meeting_id}:other:{oi.item_type}:{len(bucket)}",
            "description": oi.description,
            "is_confidential": oi.is_confidential,
        })

    return {
        "meeting_id": meeting_id,
        "meeting_date": meeting.meeting_date.isoformat() if meeting and meeting.meeting_date else None,
        "meeting_type": meeting.meeting_type if meeting else None,
        "motions": items,
        "officer_rec_departures": departures,
        "other_items_by_type": other_items_by_type,
    }


def public_inventory_projection(inventory: dict) -> dict:
    """Name-free by construction (digest design plan §3 item 6): drops
    `moved_by`/`seconded_by` from every motion. Everything else in the
    inventory (outcomes, vote splits, item descriptions) already names no
    one — only the mover/seconder fields carry a person."""
    return {
        **inventory,
        "motions": [
            {k: v for k, v in item.items() if k not in ("moved_by", "seconded_by")}
            for item in inventory["motions"]
        ],
    }


def _content_bearing_minutes_meetings_in_window(
    session: Session, council_id: int, window_start: date | None, window_end: date,
) -> list[Meeting]:
    q = (
        session.query(Meeting)
        .join(Motion, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            Meeting.document_type == "minutes",
            Meeting.meeting_date <= window_end,
        )
        .distinct()
    )
    if window_start is not None:
        q = q.filter(Meeting.meeting_date >= window_start)
    return q.order_by(Meeting.meeting_date.desc()).all()


def _most_recent_content_bearing_meeting(session: Session, council_id: int) -> Meeting | None:
    return next(
        (
            m for m in (
                session.query(Meeting)
                .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
                .order_by(Meeting.meeting_date.desc())
                .all()
            )
            if session.query(Motion).filter(Motion.meeting_id == m.id).count() > 0
        ),
        None,
    )


def compose_period_digest(
    session: Session,
    council_id: int,
    interval: str,
    period_end: date,
    baselines: MeetingBaselines,
    policy: dict,
    min_n: int,
) -> dict:
    """Pure composition over the window's meeting records — every claim from
    every content-bearing minutes meeting in range, scored and tiered, never
    recomputed differently by cadence (only the window changes)."""
    if interval not in VALID_INTERVALS:
        raise ValueError(f"interval must be one of {VALID_INTERVALS}, got {interval!r}")

    meeting_bodies = load_meeting_bodies()
    known_names = {
        (c.given_name, c.family_name) for c in session.query(Councillor).all()
    }

    if interval == "meeting":
        latest = _most_recent_content_bearing_meeting(session, council_id)
        meetings = [latest] if latest else []
    else:
        window_start = period_end - timedelta(days=_INTERVAL_DAYS[interval])
        meetings = _content_bearing_minutes_meetings_in_window(
            session, council_id, window_start, period_end,
        )

    if not meetings:
        if policy.get("empty_period_behaviour") != "emit_quiet_record":
            raise ValueError(
                f"empty_period_behaviour={policy.get('empty_period_behaviour')!r} not "
                "supported — only 'emit_quiet_record' is implemented"
            )
        most_recent = _most_recent_content_bearing_meeting(session, council_id)
        return {
            "council_id": council_id,
            "interval": interval,
            "period_end": period_end.isoformat(),
            "quiet": True,
            "most_recent_meeting": (
                {"meeting_id": most_recent.id, "meeting_date": most_recent.meeting_date.isoformat(),
                 "meeting_type": most_recent.meeting_type}
                if most_recent else None
            ),
            "meetings_covered": [],
            "candidates": [],
            "highlights": [],
        }

    candidates: list[dict] = []
    meetings_covered: list[dict] = []
    inventories: dict[int, dict] = {}
    for m in meetings:
        body_class = body_class_of(m.meeting_type, meeting_bodies)
        claims = run_meeting_digest(session, council_id, m.id)
        tiers = derive_claim_tiers(claims, min_n=min_n, known_names=known_names)
        meetings_covered.append({
            "meeting_id": m.id, "meeting_date": m.meeting_date.isoformat(),
            "meeting_type": m.meeting_type, "body_class": body_class,
        })
        inv = meeting_inventory(session, council_id, m.id)
        inventories[m.id] = {"deep": inv, "public": public_inventory_projection(inv)}
        for c in claims:
            if not c.data_ok:
                continue
            salience = score_salience(c, baselines, body_class, policy)
            tier = tiers.get(c.test_id, "full")
            public_candidate = project_to_institutional(c) if tier == "public" else None
            candidates.append({
                # Stable citation anchor for the Renderer digest mode
                # (RENDERER_PROTOCOL.md dimension 8) — unique within a period
                # digest since it's meeting-qualified, unlike test_id alone.
                "claim_id": f"{m.id}:{c.test_id}",
                "meeting_id": m.id,
                "meeting_date": m.meeting_date.isoformat(),
                "body_class": body_class,
                "salience": salience,
                "tier": tier,
                "deep": asdict(c),
                "public": asdict(public_candidate) if public_candidate is not None else None,
            })

    candidates.sort(key=lambda x: x["salience"], reverse=True)
    min_salience = policy.get("min_salience", 0.7)
    max_highlights = policy.get("max_highlights", 4)
    highlights = [c for c in candidates if c["salience"] >= min_salience][:max_highlights]

    return {
        "council_id": council_id,
        "interval": interval,
        "period_end": period_end.isoformat(),
        "quiet": False,
        "meetings_covered": meetings_covered,
        "inventories": inventories,
        "candidates": candidates,
        "highlights": highlights,
    }
