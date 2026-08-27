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

**The granularity axis** (digest design plan, Explorer v3.1): a dimension's
whole-corpus density and its meeting-scope density are different
questions — a dimension can be DENSE at corpus scope while contributing
almost nothing to a per-meeting digest. Rather than hand-maintain a second
verdict field on every register row (which would recreate the exact drift
risk `verify_register()` exists to catch, doubled), meeting-scope coverage
is computed at read time from real code: `extract_meeting_scope_test_ids()`
mirrors `extract_shipped_test_ids()` but parses `_MEETING_BATTERY` instead
of `_BATTERY`, and `granularity_report()` cross-references that set against
each row's `tests[]` to produce a `meeting_verdict` alongside the row's
existing (corpus-scope) `verdict` — computed, never stored, so there's
nothing to go stale.
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


def _extract_test_ids_for_battery(source_path: Path, battery_var_name: str) -> set[str]:
    """The test_id every member of the named battery list actually declares,
    found by walking each function's body for the two call shapes tests.py
    uses: a `TestResult(test_id="...")` keyword, and a `_nodata("...", ...)`
    fallback's first positional string (used by tests with a
    `data_ok=False` early-return branch, and by the two permanently
    not-computable placeholder generators that only ever call `_nodata`).

    Shared by `extract_shipped_test_ids()` (`_BATTERY`) and
    `extract_meeting_scope_test_ids()` (`_MEETING_BATTERY`) — both lists
    hold the same *dispatcher* function names (e.g. `_t_recusal_overall`,
    never `_t_recusal_overall_meeting` directly), and a dispatcher's own
    AST body always carries a literal whole-corpus `TestResult(test_id=...)`
    call even when it also dispatches to a `_meeting` sibling for
    `meeting_id is not None` — `ast.walk` doesn't recurse into that sibling
    call, but doesn't need to: the test_id string is identical in both
    scopes for every real generator (verified against `src/analysis/
    tests.py`'s 14 `_MEETING_BATTERY` members), so reading it off the
    dispatcher's own whole-corpus branch is sufficient either way.
    """
    tree = ast.parse(source_path.read_text())

    battery_names: list[str] = []
    functions: dict[str, ast.FunctionDef] = {}
    recognised = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = node
        # Both assignment forms: `_BATTERY = [...]` and `_BATTERY: list = [...]`.
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == battery_var_name for t in targets):
            # Only a literal list/tuple is walkable. An empty one is a real,
            # recognised battery that happens to have no generators; anything
            # else (e.g. `_CORE + _EXTRA`) is a shape this parser can't read.
            if isinstance(node.value, (ast.List, ast.Tuple)):
                recognised = True
                for elt in node.value.elts:
                    if isinstance(elt, ast.Name):
                        battery_names.append(elt.id)

    if not recognised:
        raise ValueError(
            f"No readable {battery_var_name} assignment in {source_path}. This "
            f"parser recognises `{battery_var_name} = [fn, ...]` (or an "
            "annotated assignment) of plain names; if it's now built some "
            "other way, update this function — otherwise every register "
            "entry would look like an unknown test_id and point the "
            "maintainer at the wrong file."
        )

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


def extract_shipped_test_ids(source_path: Path = TESTS_SOURCE_PATH) -> set[str]:
    """The test_id every `_BATTERY` (whole-corpus) function actually declares."""
    return _extract_test_ids_for_battery(source_path, "_BATTERY")


def extract_meeting_scope_test_ids(source_path: Path = TESTS_SOURCE_PATH) -> set[str]:
    """The test_id every `_MEETING_BATTERY` (single-meeting-eligible) function
    actually declares — the real, current answer to "which dimensions'
    generators ship a `_meeting` variant a digest can call," used by
    `granularity_report()`'s `meeting_verdict` instead of a hand-maintained
    register field (see the module docstring's "granularity axis" note)."""
    return _extract_test_ids_for_battery(source_path, "_MEETING_BATTERY")


_GRANULARITY_THRESHOLDS = (
    (0, "EMPTY"),
    (1, "THIN"),
    (3, "MODERATE"),
    # 4+ -> DENSE
)


def _mechanical_verdict(n_tests: int) -> str:
    """0 -> EMPTY, 1 -> THIN, 2-3 -> MODERATE, 4+ -> DENSE. A stated,
    documented proxy for Explorer to seed hypotheses from — not the same
    holistic human judgment the register's own (corpus-scope) `verdict`
    values carry, which weigh coverage quality as well as count."""
    if n_tests >= 4:
        return "DENSE"
    for max_n, verdict in _GRANULARITY_THRESHOLDS:
        if n_tests <= max_n:
            return verdict
    return "DENSE"  # unreachable given the >=4 check above; kept for clarity


@dataclass
class GranularityRow:
    dimension_id: int
    name: str
    corpus_verdict: str
    meeting_tests: list[str]
    meeting_verdict: str


def granularity_report(register: dict, meeting_scope_ids: set[str]) -> list[GranularityRow]:
    """Per-dimension meeting-scope density alongside the register's existing
    corpus-scope `verdict` — computed fresh every call, never persisted, so
    it can never drift the way a second hand-maintained field could.
    Excludes `data_blocked`/`out_of_scope` rows, matching how Stage 1
    (`Explorer_prompt.txt`) already excludes them from corpus-scope seeding
    — a row that can't be improved by any hypothesis, meeting-scoped or not,
    isn't a gap to seed from.
    """
    rows: list[GranularityRow] = []
    for dim in register["dimensions"]:
        if dim.get("data_blocked") or dim.get("out_of_scope"):
            continue
        meeting_tests = sorted(set(dim.get("tests", [])) & meeting_scope_ids)
        rows.append(GranularityRow(
            dimension_id=dim["id"],
            name=dim["name"],
            corpus_verdict=dim["verdict"],
            meeting_tests=meeting_tests,
            meeting_verdict=_mechanical_verdict(len(meeting_tests)),
        ))
    return rows


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
