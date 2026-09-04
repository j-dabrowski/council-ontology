"""One-off seeder for config/test_registry.json.

Run once, at docs/frontend/TEST_REGISTRY_PLAN.md's Step 2, to turn the
battery's current output into the registry's Phase 1 seed. This is NOT part
of any pipeline — nothing calls it, `council` doesn't wire it up — and it
must NEVER be re-run over a hand-edited config/test_registry.json: doing so
would silently discard every edit a human (or a later refinement pass) made
to question_public/title_public/method/caveats/objection/response, or to a
corrected order/category.

Reads:
  - the newest data/draft/cambridge/draft_*/scorecard.json — title/question/
    principle/detail_panel/genre for each test, and the _BATTERY execution
    order (scorecard.json's `tests` array is written straight from
    `run_test_battery`'s return list, in `_BATTERY` order, unsorted — see
    src/cli.py's draft export).
  - src/analysis/tests.py's `_BATTERY` / `_MEETING_BATTERY`, parsed
    statically rather than imported (same convention as
    src/analysis/coverage_register.py's `_extract_test_ids_for_battery` —
    this script has no DB session to give a real import of tests.py's
    dependency chain).
  - frontend/src/bespokePanels.tsx's `BESPOKE_PANELS` keys.

Writes config/test_registry.json: one row per test, in `_BATTERY` order.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_SOURCE = ROOT / "src" / "analysis" / "tests.py"
BESPOKE_PANELS_SOURCE = ROOT / "frontend" / "src" / "bespokePanels.tsx"
REGISTRY_OUT = ROOT / "config" / "test_registry.json"

# Part D's evidence_query / evidence_snapshot columns (docs/frontend/
# TEST_REGISTRY_PLAN.md) — not derivable from _BATTERY or scorecard.json,
# since which queries.py function backs a test (vs. inline ORM code inside
# tests.py) isn't recorded anywhere at runtime. Hand-sourced once, verbatim
# from the plan. `governance.unanimity_trend`'s evidence_snapshot is null
# here, not "trends" — Part D marks that value "(Phase 2)"; Step 11 is what
# sets it, once TrendsChart actually gets a BESPOKE_PANELS entry.
_EVIDENCE: dict[str, tuple[str, str | None]] = {
    "procurement.threshold_gaming": ("tests._t_threshold_gaming", None),
    "procurement.incumbency": ("tests._t_procurement_incumbency", None),
    "procurement.single_source": ("tests._t_single_source", None),
    "procurement.concentration": ("tender_concentration", "tenders"),
    "procurement.decider_supplier_conflict": ("decider_supplier_conflict", None),
    "conflict.recusal_management": ("conflict_recusal_stats", "declared"),
    "conflict.recusal_trend": ("recusal_compliance_trend", "recusal"),
    "conflict.delegate_body_conflict": ("delegate_body_conflict", None),
    "planning.repeat_applicant": ("tests._t_repeat_applicant", None),
    "planning.big_dollar_leniency": ("tests._t_big_dollar_leniency", None),
    "governance.officer_ratification": ("officer_divergence", "divergence"),
    "governance.power_spread": ("voting_power", "power"),
    "governance.oversight_body_capture": ("oversight_body_capture", None),
    "governance.unanimity_trend": ("tests._t_unanimity_trend", None),
    "governance.chair_capture": ("mayoral_agenda_setting", "mayoral"),
    "governance.durable_faction": ("sponsorship_network", "sponsorship"),
    "governance.incumbency": ("councillor_tenure", "tenure"),
    "governance.freshman_effect": ("tests._t_freshman", None),
    "governance.election_cycle": ("tests._t_election_cycle", None),
    "governance.attendance": ("tests._t_attendance", None),
    "planning.objection_responsiveness": ("objection_dose_response", "dose"),
    "transparency.confidential_share": ("transparency_by_year", "transparency"),
    "transparency.confidential_tender_size": ("tests._t_confidential_tender_size", None),
    "transparency.confidential_topics": ("tests._t_confidential_topics", None),
    "engagement.participation": ("public_engagement_by_year", "engagement"),
    "engagement.deputation_dissent": ("tests._t_deputation_dissent", None),
    "engagement.question_responsiveness": ("public_question_responsiveness", "question-responsiveness"),
    "finance.eoy_spending": ("tests._t_eoy_spending", None),
    "finance.reserve_trajectory": ("tests._t_reserve_trajectory", None),
}

# genre -> category, mirroring frontend/src/groupTestsByGenre.ts's `ORDER`
# exactly (first match wins), so `category` reproduces what the current
# frontend already renders. "Planning & fairness" is a real bucket there but
# matches zero genres in this battery (TEST_REGISTRY_PLAN.md A.3 point 3) —
# dropped from the registry's four-value enum (B.6), never assigned here.
_CATEGORY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("integrity_procurement", re.compile(r"procurement|conflict|integrity", re.I)),
    ("governance_culture", re.compile(r"governance|culture", re.I)),
    ("transparency_engagement", re.compile(r"transparency|engagement", re.I)),
    ("financial", re.compile(r"financial", re.I)),
]


def _newest_draft_scorecard() -> Path:
    base = ROOT / "data" / "draft" / "cambridge"
    runs = sorted(d for d in base.iterdir() if d.is_dir() and d.name.startswith("draft_"))
    if not runs:
        raise SystemExit(f"No draft_* runs under {base}")
    path = runs[-1] / "scorecard.json"
    if not path.exists():
        raise SystemExit(f"{path} does not exist")
    return path


def _battery_function_names(tree: ast.Module, battery_var_name: str) -> list[str]:
    """Ordered function names assigned to `_BATTERY` / `_MEETING_BATTERY`."""
    for node in ast.walk(tree):
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == battery_var_name for t in targets):
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                raise SystemExit(f"{battery_var_name} is not a literal list/tuple in {TESTS_SOURCE}")
            return [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
    raise SystemExit(f"No {battery_var_name} assignment found in {TESTS_SOURCE}")


def _function_test_id(functions: dict[str, ast.FunctionDef], name: str) -> str | None:
    fn = functions.get(name)
    if fn is None:
        return None
    for call in ast.walk(fn):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id == "TestResult":
            for kw in call.keywords:
                if kw.arg == "test_id" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
        elif call.func.id == "_nodata":
            if call.args and isinstance(call.args[0], ast.Constant):
                return call.args[0].value
    return None


def _category_for_genre(genre: str) -> str:
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(genre):
            return category
    raise SystemExit(f"Genre {genre!r} matches no known category pattern")


def _split_principles(principle: str) -> list[str]:
    return [p.strip() for p in principle.split("·") if p.strip()]


def _bespoke_panel_ids(source_path: Path) -> set[str]:
    text = source_path.read_text()
    return set(re.findall(r'"([a-z_]+\.[a-z_]+)":\s*\w+,', text))


def main() -> None:
    scorecard_path = _newest_draft_scorecard()
    scorecard_tests = json.loads(scorecard_path.read_text())["data"]["tests"]

    tree = ast.parse(TESTS_SOURCE.read_text())
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    battery_names = _battery_function_names(tree, "_BATTERY")
    meeting_names = _battery_function_names(tree, "_MEETING_BATTERY")
    battery_ids = [_function_test_id(functions, n) for n in battery_names]
    meeting_ids = {_function_test_id(functions, n) for n in meeting_names}

    if None in battery_ids:
        unresolved = [n for n, tid in zip(battery_names, battery_ids) if tid is None]
        raise SystemExit(f"Could not resolve a test_id for: {unresolved}")
    if len(battery_ids) != len(scorecard_tests):
        raise SystemExit(
            f"_BATTERY has {len(battery_ids)} entries but {scorecard_path} "
            f"has {len(scorecard_tests)} tests"
        )

    order_by_id = {tid: i + 1 for i, tid in enumerate(battery_ids)}
    bespoke_ids = _bespoke_panel_ids(BESPOKE_PANELS_SOURCE)

    rows = []
    for t in scorecard_tests:
        tid = t["test_id"]
        if tid not in order_by_id:
            raise SystemExit(f"{tid} is in {scorecard_path} but not in _BATTERY")
        if tid not in _EVIDENCE:
            raise SystemExit(f"{tid} has no _EVIDENCE entry — add one from Part D")
        evidence_query, evidence_snapshot = _EVIDENCE[tid]
        rows.append({
            "id": tid,
            "order": order_by_id[tid],
            "category": _category_for_genre(t["genre"]),
            "question_technical": t["question"],
            "question_public": "",
            "title_technical": t["title"],
            "title_public": "",
            "principles": _split_principles(t["principle"]),
            "method": "",
            "caveats": [],
            "objection": None,
            "response": None,
            "evidence_query": evidence_query,
            "evidence_snapshot": evidence_snapshot,
            "has_deep_dive": tid in bespoke_ids,
            "public_interest": False,
            "meeting_scope": tid in meeting_ids,
            "detail_panel": t["detail_panel"],
        })

    rows.sort(key=lambda r: r["order"])

    REGISTRY_OUT.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Wrote {len(rows)} rows to {REGISTRY_OUT} (source: {scorecard_path})")


if __name__ == "__main__":
    main()
