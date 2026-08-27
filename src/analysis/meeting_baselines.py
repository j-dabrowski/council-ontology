"""
Per-meeting baselines for digest salience scoring (the digest design plan
§3 item 6; `src/analysis/digest.py`'s `score_salience()` is the consumer).

A period digest ranks a meeting's claims by how unusual they are — but "8 of
67 motions dissented" only means something next to the distribution of that
same statistic across every other meeting of the SAME body class (fact 4 of
the design plan: a 4-member committee's numbers aren't comparable to full
council's). This module computes that distribution once, corpus-wide, so
`council digest`/`council draft` never recompute it per run — the same
"a command, not a per-draft cost" split `council profile` already
establishes for `compute_corpus_profile`.

Reuses `run_meeting_digest()` (the same function `council meeting-digest`
and `cmd_draft`'s local digest already call) rather than re-implementing the
meeting-scoped battery — one source of truth for what a meeting's claims
are, whether you want one meeting's or every meeting's.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.analysis.tests import run_meeting_digest
from src.models import Meeting, Motion

DEFAULT_MEETING_BODIES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "meeting_bodies.json"

# Assigned to any meeting_type not present in config/meeting_bodies.json — a
# corpus with an unanticipated meeting_type degrades to a thin/empty
# baseline (novelty disabled, digest_floor still applies) rather than
# crashing (digest design plan, "points left open" #4).
UNKNOWN_BODY_CLASS = "unknown"


def load_meeting_bodies(path: Path = DEFAULT_MEETING_BODIES_PATH) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"No meeting_bodies config at {path}")
    return json.loads(path.read_text())


def body_class_of(meeting_type: str, meeting_bodies: dict[str, str]) -> str:
    return meeting_bodies.get(meeting_type, UNKNOWN_BODY_CLASS)


@dataclass
class TestBaseline:
    n_meetings: int
    values: list[float] = field(default_factory=list)


@dataclass
class MeetingBaselines:
    council: str
    generated_at: str
    n_meetings_considered: int
    # test_id -> body_class -> TestBaseline
    baselines: dict[str, dict[str, TestBaseline]] = field(default_factory=dict)


def _content_bearing_minutes_meetings(session: Session, council_id: int) -> list[Meeting]:
    """Every minutes meeting with real content — the same "has at least one
    motion" filter `cmd_draft` already uses to pick the local digest's
    latest meeting (src/cli.py), applied here to every meeting instead of
    just the newest one, so a stub/placeholder minutes row doesn't pollute
    the baseline distributions."""
    meeting_ids_with_motions = {
        mid for (mid,) in
        session.query(Motion.meeting_id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .group_by(Motion.meeting_id)
        .having(func.count(Motion.id) > 0)
        .all()
    }
    return (
        session.query(Meeting)
        .filter(Meeting.id.in_(meeting_ids_with_motions))
        .order_by(Meeting.meeting_date.asc())
        .all()
    )


def compute_meeting_baselines(
    session: Session, council_id: int, council_key: str, generated_at: str,
    meeting_bodies: dict[str, str] | None = None,
) -> MeetingBaselines:
    meeting_bodies = meeting_bodies if meeting_bodies is not None else load_meeting_bodies()
    meetings = _content_bearing_minutes_meetings(session, council_id)

    raw: dict[str, dict[str, list[float]]] = {}
    for m in meetings:
        body_class = body_class_of(m.meeting_type, meeting_bodies)
        for claim in run_meeting_digest(session, council_id, m.id):
            if not claim.data_ok:
                continue
            value = claim.stat["value"] if claim.stat is not None else claim.n
            if value is None:
                continue
            raw.setdefault(claim.test_id, {}).setdefault(body_class, []).append(float(value))

    baselines = {
        test_id: {
            body_class: TestBaseline(n_meetings=len(values), values=values)
            for body_class, values in by_body.items()
        }
        for test_id, by_body in raw.items()
    }
    return MeetingBaselines(
        council=council_key, generated_at=generated_at,
        n_meetings_considered=len(meetings), baselines=baselines,
    )


def meeting_baselines_to_dict(mb: MeetingBaselines) -> dict:
    return asdict(mb)


def load_meeting_baselines(path: Path) -> MeetingBaselines:
    """The reader side of the gitignored `data/<council>_meeting_baselines.json`
    artifact `council meeting-baselines` writes — mirrors `council profile`'s
    write-then-reread pattern (`compute_corpus_profile`/`profile_to_dict`)."""
    if not path.exists():
        raise FileNotFoundError(
            f"No meeting baselines at {path} — run `council meeting-baselines <council>` first"
        )
    data = json.loads(path.read_text())
    baselines = {
        test_id: {
            body_class: TestBaseline(**tb)
            for body_class, tb in by_body.items()
        }
        for test_id, by_body in data["baselines"].items()
    }
    return MeetingBaselines(
        council=data["council"], generated_at=data["generated_at"],
        n_meetings_considered=data["n_meetings_considered"], baselines=baselines,
    )
