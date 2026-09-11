"""One-off verification script, not part of any pipeline. Confirms
docs/frontend/RECORD_PAGE_PLAN.md Step 5's precondition for publishing
dose.json at public tier: that src/cli.py's redaction of apps[].quote,
apps[].description and headline_examples actually holds against the
live corpus, and reports the real numbers the objector calculator needs
(the four bucket refusal rates, the 5+ bucket's sample size, and whether
the most-opposed application on record was refused).

Mirrors src/cli.py's dose-export query and redaction exactly, rather
than importing it, because that logic is inline inside the (very large)
_generate_snapshots() function, not a standalone importable unit.

Needs a populated data/council.db (gitignored, local-only).

Usage: python scripts/verify_dose_redaction.py
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from src.analysis.queries import objection_dose_response
from src.models import (
    ApplicationStatus,
    CommunitySubmission,
    ExtractionEvidence,
    Meeting,
    Motion,
    PlanningApplication,
    Site,
)
from src.privacy import redact_private_names

COUNCIL_ID = 1


def _bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if n <= 4:
        return "2-4"
    return "5+"


def main() -> None:
    engine = create_engine("sqlite:///data/council.db")
    session = sessionmaker(bind=engine)()

    dose = objection_dose_response(session, COUNCIL_ID)

    print("Four bucket refusal rates (from objection_dose_response(), live corpus):")
    for b in dose.buckets:
        print(f"  {b.label:>4}  n={b.n:<5} refused={b.refused:<5} refusal_pct={b.refusal_pct}%")
    print(f"total_decided={dose.total_decided}  max_objections={dose.max_objections}")

    # Replicate src/cli.py's dose.json apps[] construction exactly.
    rows = (
        session.query(
            PlanningApplication.id,
            PlanningApplication.reference_number,
            PlanningApplication.description,
            PlanningApplication.status,
            func.count(CommunitySubmission.id).label("n_obj"),
            Site.address,
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .outerjoin(Site, PlanningApplication.site_id == Site.id)
        .outerjoin(
            CommunitySubmission,
            (CommunitySubmission.application_id == PlanningApplication.id)
            & (func.lower(CommunitySubmission.position) == "object"),
        )
        .filter(
            Meeting.council_id == COUNCIL_ID,
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        )
        .group_by(PlanningApplication.id)
        .order_by(func.count(CommunitySubmission.id).desc())
        .all()
    )

    apps_by_bucket: dict[str, list[dict]] = {"0": [], "1": [], "2-4": [], "5+": []}
    app_ids_needed: list[int] = []
    for pid, ref, desc, status, n_obj, addr in rows:
        n_obj = int(n_obj or 0)
        bk = _bucket(n_obj)
        if len(apps_by_bucket[bk]) < 30:
            apps_by_bucket[bk].append({
                "id": pid,
                "reference": ref,
                "description": (redact_private_names(desc) or "")[:200] or None,
                "address": addr,
                "n_objectors": n_obj,
                "outcome": status.value if status else None,
            })
            app_ids_needed.append(pid)

    dose_quote: dict[int, str] = {}
    if app_ids_needed:
        for pid, qt in session.query(ExtractionEvidence.entity_id, ExtractionEvidence.quote_text).filter(
            ExtractionEvidence.entity_table == "planning_applications",
            ExtractionEvidence.entity_id.in_(app_ids_needed),
            ExtractionEvidence.quote_text.isnot(None),
        ):
            dose_quote.setdefault(pid, qt)

    for bk, apps in apps_by_bucket.items():
        for app in apps:
            eid = app.pop("id")
            app["entity_id"] = eid
            app["quote"] = redact_private_names(dose_quote.get(eid))

    payload = {
        "total_decided": dose.total_decided,
        "max_objections": dose.max_objections,
        "headline_examples": [redact_private_names(h) for h in dose.headline_examples],
        "buckets": [
            {
                "label": b.label, "n": b.n, "refused": b.refused, "refusal_pct": b.refusal_pct,
                "n_shown": len(apps_by_bucket.get(b.label, [])),
                "apps": apps_by_bucket.get(b.label, []),
            }
            for b in dose.buckets
        ],
    }

    payload_json = json.dumps(payload)
    print()
    print("Private-name check against the full dose payload (all buckets, all apps/quotes):")
    print(f'  "applicant_name" present: {"applicant_name" in payload_json}')
    print(f'  "Owner:" present: {"Owner:" in payload_json}')
    print(f'  "Applicant:" present: {"Applicant:" in payload_json}')
    print(f'  "Landowner:" present: {"Landowner:" in payload_json}')

    bucket_5plus = next(b for b in payload["buckets"] if b["label"] == "5+")
    print()
    print(f"5+ bucket: n={bucket_5plus['n']} applications, refusal_pct={bucket_5plus['refusal_pct']}%")

    most_opposed = max(bucket_5plus["apps"], key=lambda a: a["n_objectors"], default=None)
    if most_opposed:
        print(
            f"Most-opposed application shown: {most_opposed['n_objectors']} objectors, "
            f"outcome={most_opposed['outcome']}, description={most_opposed['description']!r}"
        )
    print(f"headline_examples: {payload['headline_examples']}")


if __name__ == "__main__":
    main()
