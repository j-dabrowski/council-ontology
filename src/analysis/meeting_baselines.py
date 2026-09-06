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

from src.analysis.tests import ENTITY_RESOLUTION_CLEAN, UNIT_INSTITUTIONAL, TestResult, run_meeting_digest
from src.invariant_gate import GateResult, derive_claim_tiers, project_to_institutional, run_invariant_gate
from src.models import Councillor, Meeting, Motion
from src.provenance import meeting_provenance
from src.test_registry import RegistryRow, load_test_registry

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


def _all_minutes_meetings(session: Session, council_id: int) -> list[Meeting]:
    """Every minutes meeting, content-bearing or not — unlike
    `_content_bearing_minutes_meetings` above (which exists to keep a
    stub/placeholder row out of the *baseline distributions*), the watch
    feed shows one row per minutes meeting regardless (docs/frontend/
    WATCH_FEED_PLAN.md B.4: 506 rows for Cambridge, not 460)."""
    return (
        session.query(Meeting)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .order_by(Meeting.meeting_date.desc())
        .all()
    )


def compute_watch_feed(
    session: Session, council_id: int, council_key: str, generated_at: str,
    baselines: MeetingBaselines, min_n: int,
    meeting_bodies: dict[str, str] | None = None,
    registry: list[RegistryRow] | None = None,
    validation_dir: Path | None = None,
    batch_jobs_dir: Path | None = None,
) -> dict:
    """Part C.2's per-meeting watch record, over every minutes meeting
    (docs/frontend/WATCH_FEED_PLAN.md B.4) — the same corpus-wide pass this
    module already runs for the baseline distributions, extended to also
    emit the record `/watch` needs. Reuses `run_meeting_digest()` (one
    source of truth for what a meeting's claims are, same as
    `compute_meeting_baselines` above) and `deviates()`
    (`src.analysis.digest`, B.1/B.2) for the per-test exception check.

    Each exception carries both a `deep` and a `public` view of its
    rendered fields (mirroring `compose_period_digest()`'s own deep/public
    split per candidate, B.3) — `public` is `None` when this claim's tier is
    `"full"`. Step 5 decides which view the published snapshot actually
    carries; this function keeps both so that decision doesn't have to be
    made here.
    """
    # Local import: src.analysis.digest imports this module at top level
    # (MeetingBaselines/body_class_of/load_meeting_bodies), so a module-level
    # import here would be circular.
    from src.analysis.digest import deviates, meeting_inventory

    meeting_bodies = meeting_bodies if meeting_bodies is not None else load_meeting_bodies()
    registry = registry if registry is not None else load_test_registry()
    registry_by_id = {row.id: row for row in registry if row.meeting_scope}

    meetings = _all_minutes_meetings(session, council_id)
    meeting_ids = [m.id for m in meetings]
    provenance_kwargs = {}
    if validation_dir is not None:
        provenance_kwargs["validation_dir"] = validation_dir
    if batch_jobs_dir is not None:
        provenance_kwargs["batch_jobs_dir"] = batch_jobs_dir
    provenance_by_meeting = meeting_provenance(session, meeting_ids, **provenance_kwargs)
    known_names = {(c.given_name, c.family_name) for c in session.query(Councillor).all()}
    _null_provenance = {
        "pdf_filename": None, "pdf_url": None, "extracted_at": None,
        "run_id": None, "run_id_count": 0, "model": None,
        "validation_status": None, "coverage_ratio": None,
    }

    rows: list[dict] = []
    for m in meetings:
        body_class = body_class_of(m.meeting_type, meeting_bodies)
        claims = run_meeting_digest(session, council_id, m.id)
        tiers = derive_claim_tiers(claims, min_n=min_n, known_names=known_names)

        inv = meeting_inventory(session, council_id, m.id)
        n_motions = len(inv["motions"])
        n_other = sum(len(v) for v in inv["other_items_by_type"].values())

        exceptions: list[dict] = []
        for c in claims:
            entry = registry_by_id.get(c.test_id)
            if entry is None:  # a broken generator's error result carries no row
                continue
            result = deviates(c, baselines, body_class, entry)
            if not result["is_exception"]:
                continue
            public_c = project_to_institutional(c) if tiers.get(c.test_id) == "public" else None
            exceptions.append({
                "test_id": c.test_id,
                "threshold_kind": result["threshold_kind"],
                "baseline_median": result["baseline_median"],
                "why": result["why"],
                "stat": c.stat,
                "deep": {
                    "finding": c.headline, "verdict": c.verdict,
                    "valence": c.valence, "severity": c.grade,
                },
                "public": (
                    {
                        "finding": public_c.headline, "verdict": public_c.verdict,
                        "valence": public_c.valence, "severity": public_c.grade,
                    } if public_c is not None else None
                ),
            })

        rows.append({
            "meeting_id": m.id,
            "meeting_date": m.meeting_date.isoformat(),
            "meeting_type": m.meeting_type,
            "body_class": body_class,
            "counts": {"items": n_motions + n_other, "motions": n_motions, "other_items": n_other},
            "tests": {
                "run": len(claims),
                "exceptions": len(exceptions),
                "within_baseline": len(claims) - len(exceptions),
            },
            "exceptions": exceptions,
            "provenance": provenance_by_meeting.get(m.id, _null_provenance),
        })

    return {
        "council": council_key,
        "generated_at": generated_at,
        "n_meetings": len(rows),
        "meetings": rows,
    }


def project_watch_feed_to_public(
    feed: dict, min_n: int, known_names: set[tuple[str, str]] | None = None,
) -> tuple[dict, GateResult]:
    """The B.3 filter: from `compute_watch_feed()`'s full deep/public feed,
    build the shape that actually ships — public-tier exceptions only, each
    row carrying `exceptions_withheld` for the ones dropped (WATCH_FEED_PLAN.md
    B.3: "a dropped claim is recorded, not silently absent").

    Then re-verifies: reconstructs a minimal claim per surviving exception
    from exactly the text about to ship (nothing else — no title/question,
    since C.2's exception shape carries neither) and runs
    `run_invariant_gate` over all of them at once. This is independent of
    the per-claim tier check `derive_claim_tiers` already did (which decided
    what to *keep*) — it instead checks what's actually in the *output*, so
    it can only fail from a bug in this function's own filtering, not from
    the per-claim gate call it's re-running.
    """
    published_meetings = []
    synthetic_claims: list[TestResult] = []
    for row in feed["meetings"]:
        published_exceptions = []
        withheld = 0
        for exc in row["exceptions"]:
            if exc["public"] is None:
                withheld += 1
                continue
            published = {
                "test_id": exc["test_id"],
                "threshold_kind": exc["threshold_kind"],
                "baseline_median": exc["baseline_median"],
                "why": exc["why"],
                "stat": exc["stat"],
                **exc["public"],
            }
            published_exceptions.append(published)
            synthetic_claims.append(TestResult(
                test_id=published["test_id"], title="", genre="", principle="", question="",
                valence=published["valence"], grade=published["severity"],
                headline=published["finding"], verdict=published["verdict"],
                unit_of_analysis=UNIT_INSTITUTIONAL, named_entities=[],
                entity_resolution=ENTITY_RESOLUTION_CLEAN,
            ))
        published_meetings.append({
            **{k: v for k, v in row.items() if k != "exceptions"},
            "exceptions": published_exceptions,
            "exceptions_withheld": withheld,
        })

    published_feed = {**feed, "meetings": published_meetings}
    gate = run_invariant_gate(synthetic_claims, min_n=min_n, known_names=known_names)
    return published_feed, gate


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
