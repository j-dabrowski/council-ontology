"""
The coverage register (docs/AGENT_DESIGN.md §3 Q5, C7): the audit grid as
data instead of prose.

`docs/investigator/coverage_register.json` is the source file — one row per
dimension from `docs/investigator/COVERAGE_AUDIT_2026-08-23.md`'s grid,
each carrying the `test_id`s that cover it and a density verdict
(DENSE/MODERATE/THIN/EMPTY, plus `data_blocked`/`out_of_scope` flags).

`verify_register()` is the "CI script" Q5 calls for: it cross-checks the
register against the shipped battery's *real* test_ids, catching drift in
both directions —

  - a dimension claims a test_id that no longer exists (renamed/removed
    without updating the register)
  - a shipped test_id isn't claimed by any dimension (an orphan generator
    the register hasn't caught up with)

`extract_shipped_test_ids()` gets those real test_ids by statically parsing
`src/analysis/tests.py`'s source (AST, not execution) — no database, no
`run_test_battery` call. That keeps the check hermetic and safe for the
required CI path (docs/TESTING.md's no-DB/no-LLM rule), which matters
because no formal "generator declaration block" exists yet to read instead
(Refiner emitting one is docs/AGENT_DESIGN.md §6 Step 5, not built here).
`tests/test_coverage_register.py` runs `verify_register` against the real
register and the real battery on every test run, so this is the always-on
check — no separate manual command was built (see Step 4's Build log entry
in docs/AGENT_DESIGN.md for that scoping call).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

TESTS_SOURCE_PATH = Path(__file__).resolve().parent / "tests.py"
DEFAULT_REGISTER_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "investigator" / "coverage_register.json"
)


def extract_shipped_test_ids(source_path: Path = TESTS_SOURCE_PATH) -> set[str]:
    """The test_id every `_BATTERY` function actually declares, found by
    walking each function's body for the two call shapes tests.py uses:
    a `TestResult(test_id="...")` keyword, and a `_nodata("...", ...)`
    fallback's first positional string (used by tests with a
    `data_ok=False` early-return branch, and by the two permanently
    not-computable placeholder generators that only ever call `_nodata`).
    """
    tree = ast.parse(source_path.read_text())

    battery_names: list[str] = []
    functions: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = node
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_BATTERY" for t in node.targets
        ):
            for elt in node.value.elts:
                if isinstance(elt, ast.Name):
                    battery_names.append(elt.id)

    ids: set[str] = set()
    for name in battery_names:
        fn = functions.get(name)
        if fn is None:
            continue
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            if call.func.id == "TestResult":
                for kw in call.keywords:
                    if kw.arg == "test_id" and isinstance(kw.value, ast.Constant):
                        ids.add(kw.value.value)
            elif call.func.id == "_nodata":
                if call.args and isinstance(call.args[0], ast.Constant):
                    ids.add(call.args[0].value)
    return ids


@dataclass
class RegisterProblem:
    dimension_id: int | None  # None for an orphan-generator problem
    kind: str  # "unknown-test-id" | "orphan-generator"
    detail: str


def load_register(path: Path = DEFAULT_REGISTER_PATH) -> dict:
    return json.loads(path.read_text())


def verify_register(register: dict, shipped_ids: set[str]) -> list[RegisterProblem]:
    """Both directions of drift, per the module docstring. Empty list means
    the register and the real battery agree completely.
    """
    problems: list[RegisterProblem] = []
    claimed: set[str] = set()
    for dim in register["dimensions"]:
        for tid in dim.get("tests", []):
            claimed.add(tid)
            if tid not in shipped_ids:
                problems.append(RegisterProblem(
                    dimension_id=dim["id"],
                    kind="unknown-test-id",
                    detail=(
                        f"dimension {dim['id']} ({dim['name']}) lists {tid!r}, which is not "
                        "a currently shipped test_id"
                    ),
                ))
    for tid in sorted(shipped_ids - claimed):
        problems.append(RegisterProblem(
            dimension_id=None,
            kind="orphan-generator",
            detail=f"{tid!r} is a shipped test_id but no register dimension claims it",
        ))
    return problems
