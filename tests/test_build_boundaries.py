"""
Unit tests for scripts/build_boundaries.py's pure logic (docs/frontend/
MAP_PAGE_PLAN.md Phase 3) — synthetic inputs only, no network, no DB, per
docs/TESTING.md's "Adding coverage" convention for parsing/scoring/matching
logic. `run()` itself (DB + network) isn't covered here — it's a thin CLI
wrapper around these functions.
"""

from __future__ import annotations

import pytest

from scripts.build_boundaries import (
    _count_vertices,
    _round_coords,
    build_backdrop,
    build_council_feature,
    find_council_feature,
    in_polygon_share,
)

# A simple 1deg square, [0,0]-[1,0]-[1,1]-[0,1]-[0,0] — easy to reason about
# for point-in-polygon and vertex-count checks.
_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
}


def _fc(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def _feature(name: str | None, geometry: dict | None) -> dict:
    return {"type": "Feature", "properties": {"lga_name_2021": name}, "geometry": geometry}


# ── find_council_feature ───────────────────────────────────────────────────


def test_find_council_feature_matches_case_insensitively():
    fc = _fc(_feature("Cambridge", _SQUARE), _feature("Perth", _SQUARE))
    found = find_council_feature(fc, "cambridge")
    assert found["properties"]["lga_name_2021"] == "Cambridge"


def test_find_council_feature_raises_when_missing():
    fc = _fc(_feature("Perth", _SQUARE))
    with pytest.raises(ValueError, match="No LGA named"):
        find_council_feature(fc, "cambridge")


def test_find_council_feature_ignores_null_geometry_rows():
    fc = _fc(_feature(None, None), _feature("Cambridge", _SQUARE))
    found = find_council_feature(fc, "cambridge")
    assert found["geometry"] is not None


def test_find_council_feature_raises_on_ambiguous_name():
    fc = _fc(_feature("Cambridge", _SQUARE), _feature("Cambridge", _SQUARE))
    with pytest.raises(ValueError, match="ambiguous"):
        find_council_feature(fc, "cambridge")


# ── in_polygon_share ────────────────────────────────────────────────────────


def test_in_polygon_share_none_when_no_sites():
    feature = {"geometry": _SQUARE}
    assert in_polygon_share(feature, []) is None


def test_in_polygon_share_counts_correctly():
    feature = {"geometry": _SQUARE}
    # 3 inside the unit square, 1 outside (lon, lat order, matching GeoJSON).
    sites = [(0.5, 0.5), (0.1, 0.9), (0.9, 0.1), (5.0, 5.0)]
    assert in_polygon_share(feature, sites) == pytest.approx(0.75)


# ── build_council_feature ───────────────────────────────────────────────────


def test_build_council_feature_carries_provenance():
    fc = _fc(_feature("Cambridge", _SQUARE))
    feature = build_council_feature("cambridge", "Cambridge", "local-test.geojson", fc=fc)
    props = feature["properties"]
    assert props["council_key"] == "cambridge"
    assert props["lga_name"] == "Cambridge"
    assert props["source"] == "local-test.geojson"
    assert props["n_vertices"] == 5  # the square's closed ring


# ── build_backdrop ──────────────────────────────────────────────────────────


def test_build_backdrop_drops_null_geometry_features():
    fc = _fc(_feature("Cambridge", _SQUARE), _feature(None, None))
    out = build_backdrop(fc=fc)
    assert len(out["features"]) == 1
    assert out["features"][0]["properties"]["lga_name"] == "Cambridge"


def test_build_backdrop_properties_are_name_only():
    fc = _fc(_feature("Cambridge", _SQUARE))
    out = build_backdrop(fc=fc)
    assert set(out["features"][0]["properties"]) == {"lga_name"}


# ── coordinate helpers ──────────────────────────────────────────────────────


def test_round_coords_rounds_nested_rings():
    geom = {"type": "Polygon", "coordinates": [[[1.123456, 2.987654]]]}
    rounded = _round_coords(geom, 4)
    assert rounded["coordinates"] == [[[1.1235, 2.9877]]]


def test_count_vertices_on_a_closed_square_ring():
    assert _count_vertices(_SQUARE) == 5
