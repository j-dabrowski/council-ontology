"""
S7: the invariant gate (docs/INFORMATION_ARCHITECTURE.md §3, C2).

Scripted, no LLM — runs inside `council draft` after the standard test
battery (`src/analysis/tests.py`'s `TestResult` list, the claim objects for
this stage of the redesign) is computed, and before a draft is treated as
reviewable output. A failure blocks the draft mechanically: no Editor call,
no review chain, no pass count (docs/AGENT_DESIGN.md §3 Q3) — fix the
generator that produced the violating claim and re-draft.

Three checks, each traceable to a real Editor pass-1 finding
(docs/investigator/COVERAGE_AUDIT_2026-08-23.md; C2 in
`INFORMATION_ARCHITECTURE.md`):

- **name-free institutional schema** — an `institutional`-unit claim (the
  only unit the institutional/public product may ever carry — §4 tier
  derivation) must carry zero `named_entities`. This is what makes "nothing
  tagged public yet" resolve structurally once tier derivation lands,
  instead of depending on hand-discipline in a query or a panel.
- **MIN_N** — an `individual` or `individual_implicating` claim at or below
  MIN_N underlying records is unshippable regardless of how carefully it's
  framed. Calibrated to Editor's own pass-1 line: a named-individual claim
  resting on n ≤ 3 is a BLOCKING flag "regardless of how well it's framed"
  (`docs/review/editor/Editor_prompt.txt`) — MIN_N=3 in `config/invariants.json`
  reproduces that threshold as a script instead of an LLM judgment call.
- **identity-resolution clean bill** — an `individual` claim needs
  `entity_resolution == "clean"`; an open split means the person behind the
  claim isn't reliably one person yet (the flag-7 class).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.analysis.tests import (
    ENTITY_RESOLUTION_CLEAN,
    TestResult,
    UNIT_INDIVIDUAL,
    UNIT_INSTITUTIONAL,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "invariants.json"


@dataclass
class Violation:
    test_id: str
    check: str  # "name-free-schema" | "min-n" | "entity-resolution"
    detail: str


@dataclass
class GateResult:
    passed: bool
    violations: list[Violation]


def load_min_n(path: Path = DEFAULT_CONFIG_PATH) -> int:
    """MIN_N: the smallest n an `individual`/`individual_implicating` claim
    may ship on (a claim with exactly MIN_N records still fails — n must
    exceed it). Config, not a magic number, per the redesign's hard rule.
    """
    if not path.exists():
        raise FileNotFoundError(f"No invariant config at {path}")
    data = json.loads(path.read_text())
    min_n = data.get("min_n")
    if not isinstance(min_n, int) or min_n < 0:
        raise ValueError(f"min_n must be a non-negative integer, got {min_n!r}")
    return min_n


def run_invariant_gate(claims: list[TestResult], min_n: int) -> GateResult:
    """The gate itself. `claims` is the battery a `council draft` run just
    computed. A claim with `data_ok=False` carries no statistic to check —
    it already failed to compute, a different and already-visible condition,
    not a gate violation — so it's skipped.
    """
    violations: list[Violation] = []
    for c in claims:
        if not c.data_ok:
            continue

        if c.unit_of_analysis == UNIT_INSTITUTIONAL:
            if c.named_entities:
                violations.append(Violation(
                    test_id=c.test_id,
                    check="name-free-schema",
                    detail=(
                        f"institutional claim carries named_entities={c.named_entities!r} — "
                        "an institutional-unit claim must be provably name-free"
                    ),
                ))
            continue

        # individual_implicating or individual: MIN_N applies to both
        if c.n is None or c.n <= min_n:
            violations.append(Violation(
                test_id=c.test_id,
                check="min-n",
                detail=f"{c.unit_of_analysis} claim has n={c.n}, at or below MIN_N={min_n}",
            ))

        if c.unit_of_analysis == UNIT_INDIVIDUAL and c.entity_resolution != ENTITY_RESOLUTION_CLEAN:
            violations.append(Violation(
                test_id=c.test_id,
                check="entity-resolution",
                detail=(
                    f"individual claim has entity_resolution={c.entity_resolution!r}, not "
                    f"{ENTITY_RESOLUTION_CLEAN!r} — the named person(s) aren't reliably "
                    "resolved to one identity yet"
                ),
            ))

    return GateResult(passed=not violations, violations=violations)
