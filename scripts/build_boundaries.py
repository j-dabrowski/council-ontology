"""
Council + backdrop boundary builder (docs/frontend/MAP_PAGE_PLAN.md Phase 3).
Two jobs from one ABS source, at two different simplification epsilons —
B.3's measurement found no single epsilon serves both: epsilon=0.002 (right
for 137 WA shires as a coarse backdrop) collapses Cambridge from 549
vertices to 27, unusable for a council roughly 9km across.

    council boundary <key> [--source PATH-OR-URL] [--lga-name NAME]
        writes config/council_boundaries/<key>.geojson — a single Feature,
        near-full fidelity, validated against that council's already-
        geocoded sites (the 3.2 point-in-polygon floor) before it's
        written.

    council boundary --backdrop [--source PATH-OR-URL]
        writes config/wa_lga_backdrop.geojson — every real WA LGA (the two
        null-geometry pseudo-LGAs dropped, not lost — see B.3), simplified,
        coordinates rounded to 4 decimals, name-only properties.

Folds scripts/download_wa_lga.sh's ABS query in as the fetch step here —
one way to get the file, not two.

Usage:
    council boundary cambridge
    council boundary --backdrop
    python scripts/build_boundaries.py cambridge
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, mapping, shape

# Same ABS ASGS 2021 query scripts/download_wa_lga.sh used directly. WA
# state code = 5. resultRecordCount=-1 requests all features (no
# server-side pagination).
ABS_WA_LGA_URL = (
    "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/LGA/FeatureServer/0/query"
    "?where=STATE_CODE_2021%3D'5'&outFields=LGA_CODE_2021%2CLGA_NAME_2021"
    "&f=geojson&returnGeometry=true&geometryPrecision=4&resultRecordCount=-1"
)
SOURCE_LICENCE = "CC BY 4.0 — ABS ASGS Edition 3 (2021)"

COUNCIL_BOUNDARY_DIR = Path("config/council_boundaries")
BACKDROP_PATH = Path("config/wa_lga_backdrop.geojson")


# The council layer is written at full fidelity, not simplified — measured
# empirically (MAP_PAGE_PLAN.md B.3): Cambridge's raw ABS polygon is 549
# vertices / ~12 KB, and even a light ε=0.0002 touch (~20m at this
# latitude) collapses it to 55 vertices, because the ABS source itself is
# already generalised to 4 decimal places (~11m) server-side — there's very
# little redundant precision left to remove without visibly changing the
# outline. A single council's full-fidelity file is negligible either way
# (~12 KB), which is the whole argument for the two-layer split (B.3).
COUNCIL_EPSILON = 0
BACKDROP_EPSILON = 0.002
IN_POLYGON_FLOOR = 0.90


def fetch_wa_lga(source: str | None = None) -> dict:
    """The raw ABS WA-LGA FeatureCollection — from `source` (a local path or
    an alternate URL) if given, else the live ABS query."""
    src = source or ABS_WA_LGA_URL
    if src.startswith("http://") or src.startswith("https://"):
        with urllib.request.urlopen(src, timeout=60) as resp:  # noqa: S310 — fixed ABS host, or an operator-supplied --source
            return json.loads(resp.read())
    return json.loads(Path(src).read_text())


def _feature_name(feature: dict) -> str | None:
    # The ABS endpoint has been seen casing this both LGA_NAME_2021 and
    # lga_name_2021 depending on the exact query — check both rather than
    # assume one.
    props = feature.get("properties") or {}
    return props.get("lga_name_2021") or props.get("LGA_NAME_2021")


def _round_coords(geom: dict, ndigits: int) -> dict:
    def _round(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], ndigits), round(c[1], ndigits)]
        return [_round(x) for x in c]
    geom = dict(geom)
    geom["coordinates"] = _round(geom["coordinates"])
    return geom


def _count_vertices(geom: dict) -> int:
    def _count(c):
        if isinstance(c[0], (int, float)):
            return 1
        return sum(_count(x) for x in c)
    return _count(geom["coordinates"])


def find_council_feature(fc: dict, lga_name: str) -> dict:
    matches = [
        f for f in fc["features"]
        if f.get("geometry") and (_feature_name(f) or "").lower() == lga_name.lower()
    ]
    if not matches:
        available = sorted({n for f in fc["features"] if (n := _feature_name(f))})
        raise ValueError(f"No LGA named {lga_name!r} in the source — available: {available}")
    if len(matches) > 1:
        raise ValueError(f"{len(matches)} LGAs named {lga_name!r} — ambiguous, pass --source to disambiguate")
    return matches[0]


def build_council_feature(key: str, lga_name: str, source: str | None, fc: dict | None = None) -> dict:
    """Provenance travels with the polygon (properties), same discipline
    /method applies to every other public figure on the site."""
    fc = fc if fc is not None else fetch_wa_lga(source)
    raw = find_council_feature(fc, lga_name)
    geom_shape = shape(raw["geometry"])
    if COUNCIL_EPSILON > 0:
        geom_shape = geom_shape.simplify(COUNCIL_EPSILON, preserve_topology=True)
    geom = _round_coords(mapping(geom_shape), 6)
    return {
        "type": "Feature",
        "properties": {
            "council_key": key,
            "lga_name": lga_name,
            "source": source or ABS_WA_LGA_URL,
            "source_licence": SOURCE_LICENCE,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "simplify_epsilon": COUNCIL_EPSILON,
            "n_vertices": _count_vertices(geom),
        },
        "geometry": geom,
    }


def in_polygon_share(feature: dict, sites: list[tuple[float, float]]) -> float | None:
    """None — not 0.0 or 1.0 — when `sites` is empty, so a council with no
    geocoded sites reads as "check skipped," never as "check passed"."""
    if not sites:
        return None
    poly = shape(feature["geometry"])
    inside = sum(1 for lon, lat in sites if poly.contains(Point(lon, lat)))
    return inside / len(sites)


def build_backdrop(source: str | None = None, fc: dict | None = None) -> dict:
    fc = fc if fc is not None else fetch_wa_lga(source)
    features = []
    for f in fc["features"]:
        if not f.get("geometry"):
            continue  # the two null-geometry pseudo-LGAs (B.3) — dropped, not lost
        simplified = shape(f["geometry"]).simplify(BACKDROP_EPSILON, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"lga_name": _feature_name(f)},
            "geometry": _round_coords(mapping(simplified), 4),
        })
    return {"type": "FeatureCollection", "features": features}


def run(args) -> None:
    """CLI entry point for both `council boundary <key>` and
    `council boundary --backdrop` — src/cli.py's subparser validates the
    council key against COUNCILS and the --backdrop/council mutual
    exclusion before calling this."""
    if args.backdrop:
        fc_out = build_backdrop(args.source)
        BACKDROP_PATH.parent.mkdir(parents=True, exist_ok=True)
        BACKDROP_PATH.write_text(json.dumps(fc_out, separators=(",", ":")))
        size_kb = BACKDROP_PATH.stat().st_size / 1024
        print(f"Wrote {BACKDROP_PATH} — {len(fc_out['features'])} feature(s), {size_kb:.0f} KB")
        return

    key = args.council
    # Same convention scripts/geocode_sites.py already uses for a council
    # key -> DB display name — no COUNCILS import here (src/cli.py already
    # imports this module, so importing back would be circular).
    lga_name = args.lga_name or key.capitalize()

    feature = build_council_feature(key, lga_name, args.source)

    from src.analysis.queries import get_council_by_name
    from src.models import Site
    from src.storage.database import init_db, make_session_factory

    engine = init_db()
    session = make_session_factory(engine)()
    council = get_council_by_name(session, key.capitalize())
    sites: list[tuple[float, float]] = []
    if council:
        sites = [
            (lng, lat) for lat, lng in session.query(Site.latitude, Site.longitude)
            .filter(Site.council_id == council.id, Site.latitude.isnot(None), Site.longitude.isnot(None))
            .all()
        ]

    share = in_polygon_share(feature, sites)
    if share is None:
        print(f"No geocoded sites for {key!r} — skipping the point-in-polygon check.")
    else:
        pct = share * 100
        print(f"{pct:.1f}% of {len(sites)} geocoded site(s) fall inside the boundary just built.")
        if share < IN_POLYGON_FLOOR:
            print(
                f"REFUSING to write: {pct:.1f}% is below the {IN_POLYGON_FLOOR:.0%} floor — "
                "this looks like the wrong polygon (wrong --lga-name? wrong --source?)."
            )
            raise SystemExit(1)

    COUNCIL_BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = COUNCIL_BOUNDARY_DIR / f"{key}.geojson"
    # Compact, not indent=2: this is a coordinate array, not structured data
    # meant to be hand-read — pretty-printing nearly triples a boundary
    # file's size for no readability gain (32 KB vs 12 KB on Cambridge).
    out_path.write_text(json.dumps(feature, separators=(",", ":")))
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} — {feature['properties']['n_vertices']} vertices, {size_kb:.1f} KB")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("council", nargs="?", help="Council key — omit when using --backdrop")
    p.add_argument("--backdrop", action="store_true",
                    help="Build config/wa_lga_backdrop.geojson instead of one council's boundary")
    p.add_argument("--source", help="Local path or URL to use instead of the live ABS ASGS query")
    p.add_argument("--lga-name", dest="lga_name", help="ABS LGA name to match, if it differs from the council key")
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    if not args.backdrop and not args.council:
        print("Pass a council key, or --backdrop.")
        sys.exit(1)
    run(args)
