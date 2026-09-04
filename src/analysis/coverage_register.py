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

`extract_shipped_test_ids()` gets those real test_ids from
`config/test_registry.json` (docs/frontend/TEST_REGISTRY_PLAN.md B.3) — a
plain read of the one file that states which tests the battery runs, no
database, no `run_test_battery` call. That keeps the check hermetic and safe
for the required CI path (docs/TESTING.md's no-DB/no-LLM rule). Before the
registry existed this statically parsed `src/analysis/tests.py`'s `_BATTERY`
list (AST, not execution); `_BATTERY` is gone (TEST_REGISTRY_PLAN.md Step 3),
the registry is now the one place this reads.
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
is computed at read time from real data: `extract_meeting_scope_test_ids()`
mirrors `extract_shipped_test_ids()` but keeps only rows with
`meeting_scope: true`, and `granularity_report()` cross-references that set
against each row's `tests[]` to produce a `meeting_verdict` alongside the
row's existing (corpus-scope) `verdict` — computed, never stored, so
there's nothing to go stale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEST_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "test_registry.json"
)
DEFAULT_REGISTER_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "investigator" / "coverage_register.json"
)


def _load_registry_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No test registry at {path}")
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of rows")
    return rows


def extract_shipped_test_ids(path: Path = DEFAULT_TEST_REGISTRY_PATH) -> set[str]:
    """Every `id` the test registry declares — what the battery actually
    ships."""
    return {row["id"] for row in _load_registry_rows(path)}


def extract_meeting_scope_test_ids(path: Path = DEFAULT_TEST_REGISTRY_PATH) -> set[str]:
    """The subset of `extract_shipped_test_ids()` whose registry row has
    `meeting_scope: true` — the real, current answer to "which dimensions'
    generators ship a `_meeting` variant a digest can call," used by
    `granularity_report()`'s `meeting_verdict` instead of a hand-maintained
    register field (see the module docstring's "granularity axis" note)."""
    return {row["id"] for row in _load_registry_rows(path) if row["meeting_scope"]}


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
