"""
Geocode planning application sites using the Nominatim API (OpenStreetMap).

Reads sites with address but no lat/lng from the DB and writes coordinates back.
Rate-limited to 1 request/second per Nominatim usage policy — a cache (4.5)
means only genuinely new addresses ever pay that cost on a re-run.

docs/frontend/MAP_PAGE_PLAN.md Phase 4 — B.4 measured 626 of 2,454 Cambridge
sites (25.5%) failing to geocode, all falling into a handful of address
shapes `_clean_address()` didn't handle. This module now handles the
measured shapes (4.1), splits multi-site rows instead of misattributing one
site's coordinates to several (4.2), derives `suburb` (4.3), records
provenance (4.4), caches hits *and* misses (4.5), and can write a
classified failure report (4.6). It does not force precinct names,
intersections or road reserves through a street geocoder — those are
recorded `unaddressable` and left alone (4.7): the target is >=90% of
address-shaped rows, not 100% of all rows.

Usage:
    council geocode cambridge [--force] [--dry-run] [--report]
    python scripts/geocode_sites.py cambridge [--force] [--dry-run] [--report]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "council.db"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "council-ontology/1.0 (josef.dabrowski@gmail.com)"
RATE_LIMIT_SECS = 1.1  # Nominatim: max 1 req/sec

# ── address cleaning (4.1) — one real B.4 example per class ────────────────

# Trailing plan notation: "20 Norbury Crescent, City Beach (Lot 5 on
# Deposited Plan 27017)" -> "20 Norbury Crescent, City Beach". Stripped
# first, unconditionally — it can trail a "Lot N (No. M) ..." address too.
_TRAILING_PLAN_RE = re.compile(r"\s*\(Lot\s+\d+\s+on\s+Deposited\s+Plan\s+\d+\)\s*$", re.IGNORECASE)

# Reversed lot/number order: "No 15 (Lot 301) Bernard Street, Leederville"
# -> "15 Bernard Street, Leederville" (the No. comes before "(Lot N)", the
# opposite of every other shape below).
_REVERSED_LOT_RE = re.compile(r"^No\.?\s*(\d+[A-Za-z]?)\s+\(Lot\s+\d+\)\s+(.+)$", re.IGNORECASE)

# "Lot N (No./Nos. ...) rest" — one pattern for the parenthetical's shape,
# a second pass over its *contents* below extracts the first number. This
# is what covers both the pre-existing single-number case ("(No. 25)") and
# the two new ones B.4 measured: ranged ("Nos 346-350") and compound
# ("No. 77A and 77B", "No. 94/5") — same fix, since all three just need
# "the first number in the parens".
_LOT_PAREN_NO_RE = re.compile(r"^Lot\s+\d+\s+\((Nos?\.?\s*[^)]+)\)\s+(.+)$", re.IGNORECASE)
_FIRST_NUMBER_RE = re.compile(r"(\d+[A-Za-z]?)")

# "Lot N rest" with no parenthetical at all.
_LOT_PLAIN_RE = re.compile(r"^Lot\s+\d+\s+(.+)$", re.IGNORECASE)

_CLASS_TRAILING_PLAN = "trailing_plan_notation"
_CLASS_REVERSED = "reversed_lot_order"
_CLASS_PAREN_NUMBER = "lot_paren_number"  # covers the single/ranged/compound cases together
_CLASS_LOT_PLAIN = "lot_plain"


def _clean_address(address: str) -> tuple[str, list[str]]:
    """Strip council lot/plan notation so Nominatim can find the street
    address. Returns (cleaned, classes_applied) — classes_applied feeds the
    --report breakdown (4.6), never displayed to a resident.

    'Lot 82 (No. 25) Brighton Street, West Leederville' -> '25 Brighton Street, West Leederville'
    'Lot 395 Brighton Street, West Leederville'         -> 'Brighton Street, West Leederville'
    'Lot 4 (Nos 346-350) Cambridge Street, Wembley'     -> '346 Cambridge Street, Wembley'
    'Lot 37 (No. 77A and 77B) Lake Monger Drive'        -> '77A Lake Monger Drive'
    'No 15 (Lot 301) Bernard Street, Leederville'       -> '15 Bernard Street, Leederville'
    '20 Norbury Crescent, City Beach (Lot 5 on Deposited Plan 27017)' -> '20 Norbury Crescent, City Beach'
    """
    applied: list[str] = []

    if _TRAILING_PLAN_RE.search(address):
        address = _TRAILING_PLAN_RE.sub("", address)
        applied.append(_CLASS_TRAILING_PLAN)

    m = _REVERSED_LOT_RE.match(address)
    if m:
        applied.append(_CLASS_REVERSED)
        return f"{m.group(1)} {m.group(2)}", applied

    m = _LOT_PAREN_NO_RE.match(address)
    if m:
        applied.append(_CLASS_PAREN_NUMBER)
        paren_content, rest = m.groups()
        num = _FIRST_NUMBER_RE.search(paren_content)
        return (f"{num.group(1)} {rest}" if num else rest), applied

    m = _LOT_PLAIN_RE.match(address)
    if m:
        applied.append(_CLASS_LOT_PLAIN)
        return m.group(1), applied

    return address, applied


# ── unaddressable classification (4.7) — never forced through a geocoder ──

_INTERSECTION_RE = re.compile(r"\bintersection\b", re.IGNORECASE)
_ROAD_RESERVE_RE = re.compile(r"\broad reserve\b", re.IGNORECASE)


def classify_unaddressable(address: str) -> str | None:
    """A reason string if `address` is a precinct name, an intersection, or
    a road reserve — not a street address a geocoder should ever be
    pointed at (B.4) — else None. 'No street number anywhere' is the
    catch-all for precinct/place names like 'Floreat Activity Centre'."""
    if _INTERSECTION_RE.search(address):
        return "intersection"
    if _ROAD_RESERVE_RE.search(address):
        return "road_reserve"
    if not re.search(r"\d", _TRAILING_PLAN_RE.sub("", address)):
        return "no_street_number"
    return None


# ── multi-site splitting (4.2) ──────────────────────────────────────────────


def split_multi_site(address: str) -> list[str]:
    """Split an address joined by ';' or ' & ' into its component sites —
    but never inside a (...) parenthetical, where '&'/'and' is part of a
    compound lot number (see _LOT_PAREN_NO_RE above), not a second site.
    Deliberately does NOT split on bare 'and' outside parens either — too
    easy to false-positive on an ordinary street/place name; B.4's '162
    contain &/and' is dominated by the in-parens compound-number case,
    which this never touches.

    '104 Branksome Gardens, City Beach; 2 Adina Way, City Beach'
        -> ['104 Branksome Gardens, City Beach', '2 Adina Way, City Beach']
    """
    depth = 0
    parts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(address)
    while i < n:
        ch = address[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and ch == ";":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        if depth == 0 and address[i:i + 3] == " & ":
            parts.append("".join(buf))
            buf = []
            i += 3
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def is_multi_site(address: str) -> bool:
    return len(split_multi_site(address)) > 1


# ── suburb derivation (4.3) ─────────────────────────────────────────────────


def derive_suburb(cleaned_address: str) -> str | None:
    """Best-effort suburb from the address tail — 'X Street, Suburb' ->
    'Suburb'. None if there's no comma to split on (nothing reliable to
    take)."""
    if "," not in cleaned_address:
        return None
    tail = cleaned_address.rsplit(",", 1)[-1].strip()
    return tail or None


# ── Nominatim ────────────────────────────────────────────────────────────────


def _geocode_address(query: str, suburb: str | None) -> tuple[float, float] | None:
    """Query Nominatim for a single, already-cleaned query string. Returns
    (lat, lng) or None. `suburb`, when known, replaces the old fixed 'WA
    Australia' context with something Nominatim can actually narrow on."""
    context = f"{suburb}, WA Australia" if suburb else "WA Australia"
    full_query = f"{query}, {context}"
    params = urllib.parse.urlencode({
        "q": full_query,
        "format": "json",
        "limit": 1,
        "countrycodes": "au",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.warning("Geocode failed for %r: %s", full_query, exc)
    return None


# ── cache (4.5) — keyed by the cleaned query, hits AND misses ─────────────


def _cache_path(council_key: str) -> Path:
    return Path("data") / council_key / "geocode_cache.json"


def _load_cache(council_key: str) -> dict:
    path = _cache_path(council_key)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(council_key: str, cache: dict) -> None:
    path = _cache_path(council_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True))


# ── DB provenance columns (4.4) — no migration framework here ──────────────


def _ensure_site_columns(db_path: Path) -> None:
    """Ad-hoc ALTER-on-startup — same pattern scripts/import_terms.py's
    _ensure_columns() already uses for councillor_terms.source/notes (the
    MAP_PAGE_PLAN.md text pointed at src/storage/database.py for this
    precedent; the real one lives here instead)."""
    conn = sqlite3.connect(db_path)
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(sites)")}
        for col in ("latitude_source", "geocoded_at", "geocode_note"):
            if col not in existing:
                conn.execute(f"ALTER TABLE sites ADD COLUMN {col} TEXT")
        conn.commit()
    finally:
        conn.close()


# ── main run ─────────────────────────────────────────────────────────────


def run(args) -> None:
    from src.analysis.queries import get_council_by_name
    from src.models import Site
    from src.storage.database import init_db, make_session_factory

    # Schema prep, not a data mutation — runs even under --dry-run, since
    # the Site ORM model now declares these columns and every query
    # (dry-run included) selects them.
    _ensure_site_columns(DB_PATH)

    engine = init_db()
    session = make_session_factory(engine)()
    council = get_council_by_name(session, args.council.capitalize())
    if not council:
        print(f"Council '{args.council}' not found in DB.")
        raise SystemExit(1)

    q = session.query(Site).filter(Site.council_id == council.id)
    if not args.force:
        q = q.filter(Site.latitude.is_(None))

    sites = q.all()
    if not sites:
        print("No sites to geocode.")
        if args.report:
            _write_report(args.council, session, council.id, class_counts=Counter(), n_scanned=0)
        return

    print(f"Geocoding {len(sites)} site(s){'  [dry-run]' if args.dry_run else ''}...")

    cache = {} if args.dry_run else _load_cache(args.council)
    class_counts: Counter[str] = Counter()
    ok = failed = skipped = unaddressable = 0
    now = datetime.now(timezone.utc)

    for i, site in enumerate(sites, 1):
        if not site.address or site.address.strip() in ("", "Unknown", "N/A"):
            skipped += 1
            continue

        reason = classify_unaddressable(site.address)
        if reason:
            unaddressable += 1
            class_counts[reason] += 1
            if not args.dry_run:
                site.geocode_note = f"unaddressable: {reason}"
            print(f"  [{i}/{len(sites)}] SKIP (unaddressable: {reason}): {site.address}")
            continue

        components = split_multi_site(site.address)
        split_note = None
        if len(components) > 1:
            class_counts["multi_site_split"] += 1
            split_note = f"multi-site row split into {len(components)}; geocoded the first"
            query_source = components[0]
        else:
            query_source = site.address

        cleaned, applied = _clean_address(query_source)
        for cls in applied:
            class_counts[cls] += 1
        suburb = derive_suburb(cleaned)

        if args.dry_run:
            print(f"  [{i}/{len(sites)}] Would geocode: {cleaned!r} (suburb={suburb!r})")
            continue

        if suburb:
            site.suburb = suburb

        cache_key = cleaned
        if cache_key in cache:
            result = tuple(cache[cache_key]["result"]) if cache[cache_key]["result"] else None
            print(f"  [{i}/{len(sites)}] {cleaned} ... [cached] ", end="")
        else:
            print(f"  [{i}/{len(sites)}] {cleaned} ... ", end="", flush=True)
            result = _geocode_address(cleaned, suburb)
            cache[cache_key] = {
                "result": list(result) if result else None,
                "cached_at": now.isoformat(),
            }
            _save_cache(args.council, cache)
            time.sleep(RATE_LIMIT_SECS)

        note_parts = [p for p in (split_note,) if p]
        if result:
            site.latitude, site.longitude = result
            site.latitude_source = "nominatim"
            site.geocoded_at = now
            if note_parts:
                site.geocode_note = "; ".join(note_parts)
            print(f"({result[0]:.4f}, {result[1]:.4f})")
            ok += 1
        else:
            class_counts["nominatim_no_match"] += 1
            note_parts.append("nominatim: no match")
            site.geocode_note = "; ".join(note_parts)
            print("FAILED")
            failed += 1

    if not args.dry_run:
        session.commit()
        print(
            f"\nDone: {ok} geocoded, {failed} failed, {unaddressable} unaddressable, "
            f"{skipped} skipped (no address)."
        )
        if args.report:
            _write_report(args.council, session, council.id, class_counts, n_scanned=len(sites))
    session.close()


def _write_report(council_key: str, session, council_id: int, class_counts: Counter, n_scanned: int) -> None:
    """data/<key>/geocode_report.json (4.6) — coverage, failures grouped by
    the classes above, and the point-in-polygon result against the
    council's own committed boundary (3.2 reuses the same check)."""
    from src.models import Site

    all_sites = session.query(Site).filter(Site.council_id == council_id).all()
    total = len(all_sites)
    geocoded = [s for s in all_sites if s.latitude is not None and s.longitude is not None]
    unaddressable_now = [s for s in all_sites if (s.geocode_note or "").startswith("unaddressable:")]
    address_shaped = total - len(unaddressable_now)

    in_polygon = None
    boundary_path = Path("config/council_boundaries") / f"{council_key}.geojson"
    if boundary_path.exists() and geocoded:
        from scripts.build_boundaries import in_polygon_share

        feature = json.loads(boundary_path.read_text())
        pts = [(s.longitude, s.latitude) for s in geocoded]
        in_polygon = in_polygon_share(feature, pts)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "council": council_key,
        "n_scanned_this_run": n_scanned,
        "n_total_sites": total,
        "n_geocoded": len(geocoded),
        "n_unaddressable": len(unaddressable_now),
        "n_address_shaped": address_shaped,
        "coverage_of_address_shaped": (len(geocoded) / address_shaped) if address_shaped else None,
        "in_polygon_share": in_polygon,
        "failure_classes_this_run": dict(class_counts),
    }
    out_path = Path("data") / council_key / "geocode_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out_path}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Geocode planning sites via Nominatim")
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument("--force", action="store_true",
                        help="Re-geocode sites that already have coordinates")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Show what would be geocoded without making any API calls")
    parser.add_argument("--report", action="store_true",
                        help="Write data/<council>/geocode_report.json after the run")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
