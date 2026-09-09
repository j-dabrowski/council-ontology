"""
FastAPI backend for the Council Ontology frontend.

Exposes the analysis query functions as JSON REST endpoints.
Run with:
    uvicorn api.main:app --reload --port 8000

`/api/evidence/{test_id}` (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 2) is
not reachable from the published site — no Cloud Run deploy exists for this
API (EVIDENCE_CHAIN_PLAN.md A.4). The frontend reads the exported
`evidence/<test_id>.json` snapshot instead (Step 3); this endpoint is for
local development and the day the API does deploy. Do not wire the
frontend to it.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# Resolve DB path relative to project root
_PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = os.environ.get("DB_PATH", str(_PROJECT_ROOT / "data" / "council.db"))
COUNCIL_SHORT_NAME = "Cambridge"

# ── DB session ─────────────────────────────────────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def _make_engine():
    url = f"sqlite:///{DB_PATH}"
    return create_engine(url, connect_args={"check_same_thread": False})

_engine = None
_SessionLocal = None


def get_session() -> Session:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _make_engine()
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


# ── App ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up the engine on startup
    get_session().close()
    yield


app = FastAPI(title="Council Ontology API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _get_council_id(session: Session) -> int:
    from src.analysis.queries import get_council_by_name
    council = get_council_by_name(session, COUNCIL_SHORT_NAME)
    if not council:
        raise HTTPException(status_code=404, detail="Council not found")
    return council.id


def _dc(obj) -> dict:
    """Dataclass to dict, converting date objects to ISO strings."""
    d = asdict(obj)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/api/interests")
def interests(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
) -> list[dict]:
    """Per-councillor interest declaration counts by type."""
    from src.analysis.queries import interest_declarations_summary
    session = get_session()
    try:
        council_id = _get_council_id(session)
        summaries = interest_declarations_summary(session, council_id, from_year, to_year)
        return [_dc(s) for s in summaries]
    finally:
        session.close()


@app.get("/api/divergence")
def divergence(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
) -> dict:
    """Officer recommendation vs. council decision divergence rate and exceptions."""
    from src.analysis.divergence import officer_divergence
    session = get_session()
    try:
        council_id = _get_council_id(session)
        pairs = officer_divergence(session, council_id, from_year, to_year)
        diverged = [p for p in pairs if p.diverged]
        followed = [p for p in pairs if not p.diverged]
        total = len(pairs)
        return {
            "total_matched": total,
            "diverged_count": len(diverged),
            "followed_count": len(followed),
            "compliance_rate": round(len(followed) / total, 4) if total else None,
            "exceptions": [
                {
                    "meeting_date": p.meeting_date.isoformat(),
                    "item_number": p.item_number,
                    "title": p.title,
                    "officer_recommendation": p.officer_recommendation,
                    "council_outcome": p.council_outcome,
                    "match_confidence": round(p.match_confidence, 2),
                }
                for p in diverged
            ],
        }
    finally:
        session.close()


@app.get("/api/co-movers")
def co_movers(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
    min_count: int = Query(default=5),
    active_only: bool = Query(default=True),
) -> dict:
    """Most frequent mover+seconder pairs, formatted for a network graph."""
    from src.analysis.queries import co_mover_pairs
    session = get_session()
    try:
        council_id = _get_council_id(session)
        pairs = co_mover_pairs(
            session, council_id, from_year, to_year,
            min_count=min_count, active_only=active_only,
        )

        # Build node/edge lists for force graph
        names: set[str] = set()
        for p in pairs:
            names.add(p.mover_name)
            names.add(p.seconder_name)

        nodes = [{"id": name} for name in sorted(names)]
        links = [
            {"source": p.mover_name, "target": p.seconder_name, "value": p.count}
            for p in pairs
        ]
        return {"nodes": nodes, "links": links, "pairs": [_dc(p) for p in pairs]}
    finally:
        session.close()


@app.get("/api/alignment")
def alignment(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
    min_shared: int = Query(default=10),
    limit: int = Query(default=50),
) -> dict:
    """Pairwise voting alignment matrix."""
    from src.analysis.queries import voting_alignment_matrix
    ALLY_THRESHOLD, OPPONENT_THRESHOLD = 0.85, 0.40
    session = get_session()
    try:
        council_id = _get_council_id(session)
        rows = voting_alignment_matrix(
            session, council_id,
            from_year=from_year, to_year=to_year,
        )
        # filter min_shared and cap limit
        filtered = [r for r in rows if r.total_shared_votes >= min_shared][:limit]
        pairs = [
            {
                "name_a": r.councillor_a.strip(),
                "name_b": r.councillor_b.strip(),
                "agreement_rate": round(r.agreement_rate, 4),
                "shared_votes": r.total_shared_votes,
                "is_ally": r.agreement_rate >= ALLY_THRESHOLD,
                "is_opponent": r.agreement_rate <= OPPONENT_THRESHOLD,
            }
            for r in filtered
        ]
        return {"pairs": pairs}
    finally:
        session.close()


@app.get("/api/trends")
def trends(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
) -> dict:
    """Contestation rate and topic distribution by year."""
    from src.analysis.queries import contestation_by_year, topic_distribution_by_year
    session = get_session()
    try:
        council_id = _get_council_id(session)
        contestation = contestation_by_year(session, council_id, from_year, to_year)
        topics = topic_distribution_by_year(session, council_id, from_year, to_year)
        return {
            "contestation": [
                {
                    "year": r.year,
                    "total_carried": r.total_carried,
                    "total_with_dissent": r.contested,
                    "contestation_rate": round(r.contestation_rate, 4),
                    "most_contested": [title for title, _ in (r.most_contested[:3] if r.most_contested else [])],
                }
                for r in contestation
            ],
            "topics": {str(k): v for k, v in topics.items()},
        }
    finally:
        session.close()


@app.get("/api/engagement")
def engagement(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
) -> list[dict]:
    """Public questions, deputations, and petitions per year."""
    from src.analysis.queries import public_engagement_by_year
    session = get_session()
    try:
        council_id = _get_council_id(session)
        rows = public_engagement_by_year(session, council_id, from_year, to_year)
        return [
            {
                "year": r.year,
                "public_questions": r.public_questions,
                "deputations": r.deputations,
                "petitions": r.petitions,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/api/activity")
def activity(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
    min_votes: int = Query(default=10),
) -> list[dict]:
    """Per-councillor activity summary."""
    from src.analysis.queries import councillor_activity_ranges
    session = get_session()
    try:
        council_id = _get_council_id(session)
        rows = councillor_activity_ranges(session, council_id, from_year, to_year, min_votes)
        return [_dc(r) for r in rows]
    finally:
        session.close()


@app.get("/api/planning")
def planning(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Planning application outcomes and top sites."""
    from src.analysis.queries import planning_outcomes
    session = get_session()
    try:
        council_id = _get_council_id(session)
        o = planning_outcomes(session, council_id, from_year, to_year, limit)
        return {
            "total": o.total,
            "approved": o.approved,
            "refused": o.refused,
            "deferred": o.deferred,
            "pending": o.pending,
            "approval_rate": round(o.approval_rate, 4),
            "top_sites": [{"address": addr, "count": n} for addr, n in o.top_sites],
            "top_applicants": [{"name": name, "count": n} for name, n in o.top_applicants],
        }
    finally:
        session.close()


_EVIDENCE_BUILDERS = {
    # evidence_query (config/test_registry.json) -> resolver
    # (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 6).
    "officer_divergence": "evidence_for_officer_ratification",
    "objection_dose_response": "evidence_for_objection_responsiveness",
    "transparency_by_year": "evidence_for_transparency",
    "mayoral_agenda_setting": "evidence_for_chair_capture",
    "tests._t_threshold_gaming": "evidence_for_threshold_gaming",
    "tests._t_eoy_spending": "evidence_for_eoy_spending",
    "tests._t_big_dollar_leniency": "evidence_for_big_dollar_leniency",
    "tests._t_repeat_applicant": "evidence_for_repeat_applicant",
    "tests._t_unanimity_trend": "evidence_for_unanimity_trend",
    "tests._t_confidential_tender_size": "evidence_for_confidential_tender_size",
    "tests._t_confidential_topics": "evidence_for_confidential_topics",
    "tests._t_procurement_incumbency": "evidence_for_incumbency",
    "tests._t_deputation_dissent": "evidence_for_deputation_dissent",
    "tests._t_freshman": "evidence_for_freshman_effect",
    "tests._t_election_cycle": "evidence_for_election_cycle",
    "tests._t_attendance": "evidence_for_attendance",
    "decider_supplier_conflict": "evidence_for_decider_supplier_conflict",
    "delegate_body_conflict": "evidence_for_delegate_body_conflict",
    "oversight_body_capture": "evidence_for_oversight_body_capture",
    "conflict_recusal_stats": "evidence_for_recusal_management",
    "recusal_compliance_trend": "evidence_for_recusal_trend",
    "voting_power": "evidence_for_power_spread",
}
_EVIDENCE_SUPPORTED_FILTERS: dict[str, set[str]] = {
    # evidence_query -> filters its underlying query actually supports.
    # Anything absent here supports none (objection_dose_response's
    # resolver takes no filters at all yet) — checked below before calling
    # the builder, so a filter name never reaches a builder that can't
    # accept it as a kwarg.
    "officer_divergence": {"year"},
}


@app.get("/api/evidence/{test_id}")
def evidence(
    test_id: str,
    year: int | None = Query(default=None),
    councillor: str | None = Query(default=None),
    contractor: str | None = Query(default=None),
) -> dict:
    """Evidence chain for one test: every entity behind its figure, each
    quote classified into the four match tiers of docs/frontend/
    EVIDENCE_CHAIN_PLAN.md B.2 (exact/normalised/stripped/paraphrase),
    computed at request time — never from `char_offset`.
    """
    from src.analysis import evidence as evidence_module
    from src.test_registry import load_test_registry

    registry = {row.id: row for row in load_test_registry()}
    row = registry.get(test_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown test_id {test_id!r}. See config/test_registry.json for valid ids.",
        )

    builder_name = _EVIDENCE_BUILDERS.get(row.evidence_query)
    if builder_name is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"{test_id!r} has no evidence resolver yet "
                f"(evidence_query={row.evidence_query!r} isn't wired up — "
                "Phase 2, docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 6)."
            ),
        )
    builder = getattr(evidence_module, builder_name)

    supported = _EVIDENCE_SUPPORTED_FILTERS.get(row.evidence_query, set())
    requested = {
        name for name, value in
        (("year", year), ("councillor", councillor), ("contractor", contractor))
        if value is not None
    }
    unsupported = requested - supported
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{test_id!r} supports only these filters: {sorted(supported) or 'none'}. "
                f"Got unsupported: {sorted(unsupported)}."
            ),
        )

    session = get_session()
    try:
        council_id = _get_council_id(session)
        # Only pass a filter the builder actually declared support for —
        # not every resolver takes a `year` kwarg (objection_dose_response's
        # doesn't take one at all yet).
        kwargs = {"year": year} if "year" in supported else {}
        return builder(session, council_id, **kwargs)
    finally:
        session.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "db": DB_PATH}


# ── Static files (production: serve built frontend) ────────────────────────────

_STATIC_DIR = _PROJECT_ROOT / "frontend" / "dist"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
