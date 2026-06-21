"""
FastAPI backend for the Council Ontology frontend.

Exposes the analysis query functions as JSON REST endpoints.
Run with:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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
    from_year: int | None = Query(default=2024),
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "db": DB_PATH}


# ── Static files (production: serve built frontend) ────────────────────────────

_STATIC_DIR = _PROJECT_ROOT / "frontend" / "dist"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
