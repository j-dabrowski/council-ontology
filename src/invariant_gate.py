"""
S7: the invariant gate (docs/INFORMATION_ARCHITECTURE.md §3, C2).

Scripted, no LLM — runs inside `council draft` after the standard test
battery (`src/analysis/tests.py`'s `TestResult` list, the claim objects for
this stage of the redesign) is computed, and before a draft is treated as
reviewable output. A failure blocks the draft mechanically: no Editor call,
no review chain, no pass count (docs/AGENT_DESIGN.md §3 Q3) — fix the
generator that produced the violating claim and re-draft.

Four checks, each traceable to a real Editor pass-1 finding
(docs/investigator/COVERAGE_AUDIT_2026-08-23.md; C2 in
`INFORMATION_ARCHITECTURE.md`):

- **name-free institutional schema** — an `institutional`-unit claim (the
  only unit the institutional/public product may ever carry — §4 tier
  derivation) must carry zero `named_entities`. This is what makes "nothing
  tagged public yet" resolve structurally once tier derivation lands,
  instead of depending on hand-discipline in a query or a panel.
- **name-free text** — the same claim's rendered strings (title, headline,
  verdict, chart labels) must not contain a real person's name either.
  `named_entities` is a declaration a generator can simply fail to set, and
  tier derivation trusts it; without this check "provably name-free" would
  mean "declared name-free" (see `find_names_in_text`).
- **MIN_N** — an `individual` or `individual_implicating` claim at or below
  MIN_N underlying records is unshippable regardless of how carefully it's
  framed. Calibrated to Editor's own pass-1 line: a named-individual claim
  resting on n ≤ 3 is a BLOCKING flag "regardless of how well it's framed"
  (`docs/review/editor/Editor_prompt.txt`) — MIN_N=3 in `config/invariants.json`
  reproduces that threshold as a script instead of an LLM judgment call.
- **identity-resolution clean bill** — an `individual` claim needs
  `entity_resolution == "clean"`; an open split means the person behind the
  claim isn't reliably one person yet (the flag-7 class).

Also owns **tier derivation** (§4/§7): the pure function of a claim batch
that decides whether the snapshot built from it may ship at the
institutional/public tier, replacing the hand-assigned `SNAPSHOT_TIER`
map in `src/cli.py` for claim-bearing snapshots. `derive_claim_tier` is
deliberately whole-batch, not per-claim: a batch is `"public"` only if
*every* claim in it is `institutional`-unit (already guaranteed name-free
by the gate above); one `individual`/`individual_implicating` claim drops
the whole batch to `"full"` rather than shipping a partial, redacted
version of it. Per-claim redaction (the `individual_implicating`
"reduced form" described in `INFORMATION_ARCHITECTURE.md` §4 — e.g. a
distribution without its per-person bars) is real future work, not built
here: nothing in the current battery needs it yet, and designing that
mechanism against zero real examples would be speculative (see the
2026-08-23 Step 2 Build log entry in `docs/AGENT_DESIGN.md`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

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
    check: str  # "name-free-schema" | "name-free-text" | "min-n" | "entity-resolution"
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


def _claim_text(c: TestResult) -> str:
    """Every rendered string a reader could see for this claim, including
    chart labels — the surfaces a name can actually leak through.
    """
    parts = [c.title, c.headline, c.verdict, c.question, c.base_rate or "", c.era or ""]
    chart = c.chart or {}
    parts += [str(b.get("label", "")) for b in chart.get("bars", [])]
    parts += [str(p.get("x", "")) for p in chart.get("points", [])]
    parts += [str(v) for point in c.series for v in point.values()]
    return " ".join(parts)


# Roster artefacts that would match ordinary prose. The corpus's councillor
# table carries extraction/dedup debris alongside real people — rows with an
# empty given name, officer titles parsed as names — and matching on those
# blocks every draft on words like "The". Real names with apostrophes,
# hyphens, and spaces (Le Page, O'Callghan, Wood-Gush) must survive this.
_NON_NAME_WORDS = {"the", "and", "of", "cr", "mayor", "councillor", "council", "director", "ceo"}


def usable_roster_names(known_names: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Roster entries specific enough to match on without false positives.

    Both parts must be at least two characters and contain a letter, and the
    family name must not be an ordinary word. A real person dropped here is
    still reachable through the titled-surname pattern, so the cost of being
    strict is low; the cost of being loose is a gate nobody can pass.
    """
    usable = set()
    for given, family in known_names:
        g, f = given.strip(), family.strip()
        if len(g) < 2 or len(f) < 2:
            continue
        if not any(ch.isalpha() for ch in g) or not any(ch.isalpha() for ch in f):
            continue
        if f.lower() in _NON_NAME_WORDS or g.lower() in _NON_NAME_WORDS:
            continue
        usable.add((g, f))
    return usable


def find_names_in_text(c: TestResult, known_names: set[tuple[str, str]]) -> list[str]:
    """Real people from the corpus whose name appears in a claim's own text.

    `named_entities` is a *declaration*, and the gate's schema check can only
    verify a declaration against itself: a generator that interpolates a name
    into a headline while leaving the declaration at its default would pass
    it. Since public-tier promotion is derived from that same declaration,
    the text is what has to be checked to make "provably name-free" true
    rather than merely asserted (the 2026-08-06 hardcoded-names incident is
    this failure mode, caught late).

    Matches a full "Given Family" name, or a family name carrying a civic
    title ("Cr Smith", "Councillor Smith", "Mayor Smith") — the realistic
    leak shapes. A bare family name is deliberately not matched: surnames
    like Park or Green collide with ordinary words, and a gate that blocks
    constantly gets worked around rather than trusted.
    """
    text = _claim_text(c)
    hits = []
    for given, family in usable_roster_names(known_names):
        full = rf"\b{re.escape(given)}\s+{re.escape(family)}\b"
        titled = rf"\b(?:Cr|Cr\.|Councillor|Mayor|Deputy Mayor)\s+{re.escape(family)}\b"
        if re.search(full, text, re.IGNORECASE) or re.search(titled, text, re.IGNORECASE):
            hits.append(f"{given} {family}")
    return sorted(set(hits))


def run_invariant_gate(
    claims: list[TestResult], min_n: int, known_names: set[tuple[str, str]] | None = None
) -> GateResult:
    """The gate itself. `claims` is the battery a `council draft` run just
    computed. A claim with `data_ok=False` carries no statistic to check —
    it already failed to compute, a different and already-visible condition,
    not a gate violation — so it's skipped.

    `known_names` is the corpus's real (given, family) pairs, used for the
    text-level name scan. Omitting it runs the schema checks only, which is
    strictly weaker — callers that can reach the DB should always pass it.
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
            leaked = find_names_in_text(c, known_names) if known_names else []
            if leaked:
                violations.append(Violation(
                    test_id=c.test_id,
                    check="name-free-text",
                    detail=(
                        f"institutional claim's own text names {leaked!r} — it declares "
                        "no named_entities, so tier derivation would promote it to the "
                        "public product with the name in it"
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


def derive_claim_tier(claims: list[TestResult]) -> str:
    """`"public"` iff every claim in the batch is `institutional`-unit (a
    claim with `data_ok=False` carries no statistic and doesn't count
    against this, same as the gate above); `"full"` otherwise. Never an
    authorial choice — a pure function of the claims themselves, called
    once the S7 gate has already passed (so any `institutional` claim here
    is already provably name-free).
    """
    for c in claims:
        if not c.data_ok:
            continue
        if c.unit_of_analysis != UNIT_INSTITUTIONAL:
            return "full"
    return "public"


# ─────────────────────────────────────────────────────────────────────────
# Per-claim tier derivation + institutional "reduced form" projections
# (digest design plan §2/§3): the whole-batch rule above is deliberately
# all-or-nothing (docs/INFORMATION_ARCHITECTURE.md §4) — right for a corpus
# snapshot's handful of claims, wrong for a period digest, where a single
# named-individual claim (an unexplained absence, a declared conflict) would
# otherwise drop an entire period's candidate pool to full-tier. These
# functions let each claim in a digest batch carry its own tier instead.
# ─────────────────────────────────────────────────────────────────────────

# The three SCOPE_SINGLE_MEETING generators that can emit a named claim
# today (src/analysis/tests.py): `_t_recusal_overall_meeting` and
# `_t_attendance_meeting` name people directly; `_t_decider_supplier_conflict_
# meeting` names a councillor when a raw surname collision fires. Each
# reduction below only strips what its own generator can put in named_entities
# — it does not re-derive the claim from the DB, so it can only project what
# the claim object already carries.
def _reduce_recusal_management(c: TestResult) -> TestResult:
    """conflict.recusal_management: the headline is already count-only
    ("N conflict(s) of interest declared this meeting, by K councillor(s)")
    — only `verdict` (the per-councillor action breakdown) and
    `named_entities` carry names."""
    n_names = len(c.named_entities)
    return replace(
        c,
        verdict=(
            f"{c.n or 0} conflict(s) of interest were declared this meeting, by {n_names} "
            "councillor(s); see the full record for who declared and how each was managed."
        ),
        unit_of_analysis=UNIT_INSTITUTIONAL,
        named_entities=[],
    )


def _reduce_attendance(c: TestResult) -> TestResult:
    """governance.attendance: both `headline` and `verdict` name the absent
    councillor(s) directly, so both need rewriting to a count-only form."""
    n_names = len(c.named_entities)
    text = (
        f"{n_names} councillor(s) had at least one unexplained absence this meeting"
        if n_names else "No unexplained absences this meeting"
    )
    return replace(c, headline=text, verdict=text + ".", unit_of_analysis=UNIT_INSTITUTIONAL,
                    named_entities=[])


def _reduce_decider_supplier_conflict(c: TestResult) -> TestResult:
    """procurement.decider_supplier_conflict: the headline is already
    count-only ("N surname collision(s) found... — unconfirmed"); `verdict`
    names the councillor(s) and the winning firm(s)."""
    n = len(c.named_entities)
    return replace(
        c,
        verdict=(
            f"{n} surname collision(s) were found between a tender winner and a voting "
            "councillor this meeting — unconfirmed, provenance not checked; see the full "
            "record for names and firms."
        ),
        unit_of_analysis=UNIT_INSTITUTIONAL,
        named_entities=[],
    )


INSTITUTIONAL_PROJECTIONS: dict[str, Callable[[TestResult], TestResult]] = {
    "conflict.recusal_management": _reduce_recusal_management,
    "governance.attendance": _reduce_attendance,
    "procurement.decider_supplier_conflict": _reduce_decider_supplier_conflict,
}


def project_to_institutional(c: TestResult) -> TestResult | None:
    """The public-tier candidate for one claim, or `None` if none exists.

    An already-institutional claim is its own candidate. An individual/
    individual_implicating claim only has one if its test_id has a
    registered reduction (`INSTITUTIONAL_PROJECTIONS`) — nothing today
    reduces an `individual_implicating` claim (no generator produces one
    yet), so this always returns `None` for that unit, matching
    `derive_claim_tier`'s module docstring on why per-claim redaction isn't
    built for it.
    """
    if c.unit_of_analysis == UNIT_INSTITUTIONAL:
        return c
    reducer = INSTITUTIONAL_PROJECTIONS.get(c.test_id)
    if reducer is None:
        return None
    return reducer(c)


def derive_claim_tiers(
    claims: list[TestResult], min_n: int, known_names: set[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """The per-claim sibling of `derive_claim_tier`: `test_id -> "public" |
    "full"`, one entry per claim (by `test_id`, which is unique within a
    single meeting's digest battery).

    A claim is `"public"` iff its institutional candidate (itself, or its
    `project_to_institutional` reduction) exists and clears the same S7
    checks `run_invariant_gate` runs — reusing that function's own logic via
    a one-claim gate call, rather than re-implementing the checks, so the two
    can never drift apart. `data_ok=False` claims are `"full"`: they carry no
    statistic, so there's nothing to safely publish.
    """
    tiers: dict[str, str] = {}
    for c in claims:
        if not c.data_ok:
            tiers[c.test_id] = "full"
            continue
        candidate = project_to_institutional(c)
        if candidate is None:
            tiers[c.test_id] = "full"
            continue
        result = run_invariant_gate([candidate], min_n=min_n, known_names=known_names)
        tiers[c.test_id] = "public" if result.passed else "full"
    return tiers
