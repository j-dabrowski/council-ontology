"""
Parity checks for config/test_registry.json (docs/frontend/
TEST_REGISTRY_PLAN.md Step 4) — the registry is now the one place that
states which tests exist; these tests catch it silently drifting from the
three things that must agree with it: `_GENERATORS` (src/analysis/tests.py),
`BESPOKE_PANELS` (frontend/src/bespokePanels.tsx), and the real
queries.py/divergence.py/tests.py functions its `evidence_query` values
name. All hermetic: source/JSON reads only, no DB, no network.

Deliberately NOT asserted here: question_public / title_public / method /
objection non-empty — those are filled in a later pass (B.8); asserting them
now would fail on every intermediate commit before that pass lands.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.analysis.tests import _GENERATORS
from src.test_registry import load_test_registry

ROOT = Path(__file__).resolve().parent.parent
BESPOKE_PANELS_PATH = ROOT / "frontend" / "src" / "bespokePanels.tsx"
QUERIES_SOURCE = ROOT / "src" / "analysis" / "queries.py"
DIVERGENCE_SOURCE = ROOT / "src" / "analysis" / "divergence.py"
TESTS_SOURCE = ROOT / "src" / "analysis" / "tests.py"

_VALID_CATEGORIES = {
    "integrity_procurement",
    "governance_culture",
    "transparency_engagement",
    "financial",
}


def _bespoke_panel_ids() -> set[str]:
    """BESPOKE_PANELS is one flat `Record<string, ComponentType>` literal
    (see frontend/src/bespokePanels.tsx) — its keys are every test_id with a
    bespoke deep-dive panel today."""
    text = BESPOKE_PANELS_PATH.read_text()
    return set(re.findall(r'"([a-z_]+\.[a-z_]+)":\s*\w+,', text))


def _defined_function_names(path: Path) -> set[str]:
    return set(re.findall(r"^def (\w+)\(", path.read_text(), re.MULTILINE))


def test_every_registry_id_has_a_generator_and_vice_versa():
    registry_ids = {row.id for row in load_test_registry()}
    generator_ids = set(_GENERATORS)
    only_registry = registry_ids - generator_ids
    only_generators = generator_ids - registry_ids
    assert not only_registry and not only_generators, (
        f"registry rows with no _GENERATORS entry: {sorted(only_registry)}; "
        f"_GENERATORS entries with no registry row: {sorted(only_generators)}"
    )


def test_has_deep_dive_matches_bespoke_panels_both_directions():
    registry_deep_ids = {row.id for row in load_test_registry() if row.has_deep_dive}
    bespoke_ids = _bespoke_panel_ids()
    only_registry = registry_deep_ids - bespoke_ids
    only_bespoke = bespoke_ids - registry_deep_ids
    assert not only_registry and not only_bespoke, (
        f"has_deep_dive=true with no BESPOKE_PANELS entry: {sorted(only_registry)}; "
        f"BESPOKE_PANELS entry with has_deep_dive=false (or missing): {sorted(only_bespoke)}"
    )


def test_order_is_exactly_1_through_29_and_unique():
    orders = sorted(row.order for row in load_test_registry())
    assert orders == list(range(1, 30)), f"expected order values 1..29, got {orders}"


def test_every_category_is_one_of_the_four():
    bad = {row.id: row.category for row in load_test_registry() if row.category not in _VALID_CATEGORIES}
    assert not bad, f"rows with an unrecognised category: {bad}"


def test_detail_panel_is_unique_and_non_empty():
    registry = load_test_registry()
    empty = [row.id for row in registry if not row.detail_panel]
    assert not empty, f"rows with an empty detail_panel: {empty}"
    panels = [row.detail_panel for row in registry]
    assert len(panels) == len(set(panels)), "detail_panel values must be unique"


def test_evidence_query_names_a_real_function():
    queries_fns = _defined_function_names(QUERIES_SOURCE)
    divergence_fns = _defined_function_names(DIVERGENCE_SOURCE)
    tests_fns = _defined_function_names(TESTS_SOURCE)

    bad = []
    for row in load_test_registry():
        eq = row.evidence_query
        if eq.startswith("tests."):
            if eq.removeprefix("tests.") not in tests_fns:
                bad.append(row.id)
        elif eq not in queries_fns and eq not in divergence_fns:
            bad.append(row.id)
    assert not bad, f"evidence_query doesn't name a real function for: {bad}"
