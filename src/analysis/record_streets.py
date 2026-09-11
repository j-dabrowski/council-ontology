"""Builds record_streets.json (docs/frontend/RECORD_PAGE_PLAN.md Step 3,
Part C.2) -- the street -> sites -> applications index /record's address
lookup (feature 1) reads. Every figure comes from `sites` +
`planning_applications` + the evidence document reference; nothing here
is a new analysis, only a regrouping of data that already exists
(RECORD_PAGE_PLAN.md "Deliberately not in this plan").

Two privacy rules apply to this file specifically (RECORD_PAGE_PLAN.md
B.1), enforced by tests/test_record_streets.py, not by care:
- `applicant_name` is never read off PlanningApplication, let alone
  projected -- there is no code path in this module that touches it.
- `description` is free text and genuinely can carry a private name --
  four real rows in this corpus read "Landowner: C N Torre" or similar,
  found while building this step -- so it always passes through
  `src.privacy.redact_private_names()` before being written out.
"""

from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.analysis.evidence import EntityRef, resolve_evidence
from src.models import CommunitySubmission, Meeting, Motion, PlanningApplication, Site
from src.privacy import redact_private_names

# Data-driven from every distinct trailing word of a site address's first
# comma-segment across the live corpus (2,454 sites) -- see
# RECORD_PAGE_PLAN.md A.3. Deliberately a plain suffix list, not a
# gazetteer: this is the "crude street-type regex" the plan names, not a
# claim of completeness (measured: 2,425/2,454 sites, 98.8%, on this list).
STREET_TYPES = [
    "Street", "Streets", "Road", "Roads", "Avenue", "Ave", "Way", "Drive",
    "Crescent", "Cresent", "Gardens", "Place", "Parade", "Boulevard",
    "Terrace", "Court", "Close", "Vista", "Grove", "Lane", "Square",
]
_TYPE_ALT = "|".join(re.escape(t) for t in sorted(STREET_TYPES, key=len, reverse=True))
# Up to 4 consecutive capitalised words ending in a recognised street
# type -- "The Boulevard", "St Leonards Avenue", "Cambridge Street".
_STREET_RE = re.compile(
    rf"\b((?:The\s+)?[A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){{0,3}}\s+(?:{_TYPE_ALT}))\b"
)


def extract_street_name(address: str | None) -> str | None:
    """The primary street name from a site address, or None if the crude
    regex can't find one (RECORD_PAGE_PLAN.md A.3/B.5 -- ~1.2% of sites,
    remeasured at build time below, not trusted from the plan's figure).

    Searches every comma-segment except the last (which is usually the
    suburb) and takes the *first* street-type match -- a "corner X Road"
    cross-street, when present, is always a later segment, so this
    naturally prefers the primary street over it.
    """
    if not address:
        return None
    parts = address.split(",")
    search_text = ",".join(parts[:-1]) if len(parts) > 1 else address
    match = _STREET_RE.search(search_text)
    return match.group(1).strip() if match else None


def extract_suburb(address: str | None) -> str | None:
    """The trailing comma-separated token of `address` (A.3 -- sites.suburb
    is 100% NULL in this corpus, so it has to be parsed, not read)."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(",")]
    if len(parts) < 2 or not parts[-1]:
        return None
    return parts[-1]


def _evidence_reference(entry: dict) -> dict:
    """Reshape one resolve_evidence() entry down to the document reference
    C.2 wants: {filename, url, meeting_date, page} -- no quotes, no tier.
    The quote itself is fetched through the full evidence chain at click
    time (C.2), redacted per B.1; this file only ever carries where to
    look, never the quote text."""
    document = entry.get("document") or {}
    return {
        "filename": document.get("filename"),
        "url": document.get("url"),
        "meeting_date": entry.get("meeting_date"),
        "page": document.get("page"),
    }


def build_record_streets(
    session: Session,
    council_id: int,
    generated_at: str,
    source_cache: dict | None = None,
) -> dict:
    """Build the full record_streets.json payload (Part C.2's shape).

    `source_cache`: see resolve_evidence() -- pass the same dict
    `_generate_snapshots` already threads through its other evidence_for_*
    calls so a meeting's PDF is parsed once per draft run, not once per
    snapshot that happens to reference it.
    """
    sites = session.query(Site).filter(Site.council_id == council_id).all()
    n_sites = len(sites)

    street_by_site: dict[int, str | None] = {}
    suburb_by_site: dict[int, str | None] = {}
    for site in sites:
        street_by_site[site.id] = extract_street_name(site.address)
        suburb_by_site[site.id] = extract_suburb(site.address)
    n_sites_with_street = sum(1 for name in street_by_site.values() if name)

    n_applications, n_applications_with_site = (
        session.query(
            func.count(PlanningApplication.id),
            func.count(PlanningApplication.site_id),
        )
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id)
        .one()
    )

    # Scoped by Meeting.council_id via Motion, not Site.council_id --
    # matching objection_dose_response()/evidence_for_objection_
    # responsiveness()'s existing convention, and deliberately the same
    # scoping the coverage counts above use. A site-scoped query would
    # disagree with them: 12 applications in the live corpus carry a
    # motion_id with no matching motion row (a pre-existing data-quality
    # gap, not introduced here), so they have a site but no reachable
    # meeting/evidence -- excluding them here keeps every site's
    # application list summing back to `applications_with_site` exactly.
    apps = (
        session.query(PlanningApplication)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, PlanningApplication.site_id.isnot(None))
        .all()
    )

    objector_counts = dict(
        session.query(CommunitySubmission.application_id, func.count(CommunitySubmission.id))
        .filter(func.lower(CommunitySubmission.position) == "object")
        .group_by(CommunitySubmission.application_id)
        .all()
    )

    refs: list[EntityRef] = [("planning_applications", app.id, "application") for app in apps]
    evidence_entries = resolve_evidence(session, refs, council_id, source_cache)
    evidence_by_app_id = {e["entity_id"]: _evidence_reference(e) for e in evidence_entries}

    _no_evidence = {"filename": None, "url": None, "meeting_date": None, "page": None}
    apps_by_site: dict[int, list[dict]] = {}
    for app in apps:
        evidence = evidence_by_app_id.get(app.id, _no_evidence)
        # PlanningApplication.application_date/decision_date are 100% NULL
        # in this corpus (checked directly against the live DB) -- the
        # meeting date the application was considered at is the only date
        # this record actually has.
        apps_by_site.setdefault(app.site_id, []).append({
            "date": evidence["meeting_date"],
            "reference": app.reference_number,
            "description": redact_private_names(app.description),
            "n_objectors": int(objector_counts.get(app.id, 0)),
            "outcome": app.status.value if app.status else None,
            "evidence": evidence,
        })

    sites_by_street: dict[str, list[Site]] = {}
    for site in sites:
        name = street_by_site[site.id]
        if name:
            sites_by_street.setdefault(name, []).append(site)

    streets = []
    for name in sorted(sites_by_street):
        street_sites = sites_by_street[name]
        suburbs = sorted({suburb_by_site[s.id] for s in street_sites if suburb_by_site[s.id]})
        site_entries = [
            {
                "address": s.address,
                "lot_number": s.lot_number,
                "applications": sorted(
                    apps_by_site.get(s.id, []),
                    key=lambda a: a["date"] or "",
                    reverse=True,
                ),
            }
            for s in street_sites
        ]
        n_applications_on_street = sum(len(e["applications"]) for e in site_entries)
        streets.append({
            "name": name,
            "suburbs": suburbs,
            "n_sites": len(street_sites),
            "n_applications": n_applications_on_street,
            "sites": site_entries,
        })

    return {
        "generated_at": generated_at,
        "source": "data/council.db",
        "coverage": {
            "sites": n_sites,
            "sites_with_street": n_sites_with_street,
            "applications": int(n_applications),
            "applications_with_site": int(n_applications_with_site),
            "note": (
                f"{n_sites - n_sites_with_street} of {n_sites} sites have an address "
                "this lookup can't parse into a street name -- reachable only by "
                f"knowing the full address. {int(n_applications) - int(n_applications_with_site)} "
                "applications have no linked site and appear under no street at all."
            ),
        },
        "streets": streets,
    }
