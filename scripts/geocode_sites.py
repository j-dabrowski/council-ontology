"""
Geocode planning application sites using the Nominatim API (OpenStreetMap).

Reads sites with address but no lat/lng from the DB and writes coordinates back.
Rate-limited to 1 request/second per Nominatim usage policy.

Usage:
    council geocode cambridge [--force] [--dry-run]
    python scripts/geocode_sites.py cambridge [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import time
import urllib.parse
import urllib.request
import json

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "council-ontology/1.0 (josef.dabrowski@gmail.com)"
RATE_LIMIT_SECS = 1.1  # Nominatim: max 1 req/sec


def _geocode_address(address: str, city_context: str = "City of Cambridge WA Australia") -> tuple[float, float] | None:
    """Query Nominatim for a single address. Returns (lat, lng) or None."""
    query = f"{address}, {city_context}"
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "au",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.warning("Geocode failed for %r: %s", address, exc)
    return None


def run(args) -> None:
    from src.models import Site
    from src.storage.database import init_db, make_session_factory
    from src.analysis.queries import get_council_by_name

    engine = init_db()
    session = make_session_factory(engine)()
    council = get_council_by_name(session, args.council)
    if not council:
        print(f"Council '{args.council}' not found in DB.")
        raise SystemExit(1)

    q = session.query(Site).filter(Site.council_id == council.id)
    if not args.force:
        q = q.filter(Site.latitude.is_(None))

    sites = q.all()
    if not sites:
        print("No sites to geocode.")
        return

    print(f"Geocoding {len(sites)} site(s){'  [dry-run]' if args.dry_run else ''}...")

    ok = failed = skipped = 0
    for i, site in enumerate(sites, 1):
        if not site.address or site.address.strip() in ("", "Unknown", "N/A"):
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [{i}/{len(sites)}] Would geocode: {site.address}")
            continue

        print(f"  [{i}/{len(sites)}] {site.address} ... ", end="", flush=True)
        result = _geocode_address(site.address)
        if result:
            site.latitude, site.longitude = result
            session.add(site)
            print(f"({result[0]:.4f}, {result[1]:.4f})")
            ok += 1
        else:
            print("FAILED")
            failed += 1

        time.sleep(RATE_LIMIT_SECS)

    if not args.dry_run:
        session.commit()
        print(f"\nDone: {ok} geocoded, {failed} failed, {skipped} skipped (no address).")
    session.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Geocode planning sites via Nominatim")
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument("--force", action="store_true",
                        help="Re-geocode sites that already have coordinates")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Show what would be geocoded without making any API calls")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
