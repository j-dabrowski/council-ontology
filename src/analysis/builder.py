"""
The Builder (docs/uplift/02-claim-layer.md's own term for this role;
docs/uplift/03-critic-agents.md: "critics operate on claim objects plus
rendered panels, not on prose reports" — this module is what produces
that rendered panel). Deterministic: turns a `Claim`'s structured fields
into panel data and a chart, with zero interpretive latitude. No prose is
authored here.

This closes the gap the target spec names directly: "Today the analyst
emits a report and the builder interprets it into a panel. That single
step fuses four separable decisions." Every one of this project's claim-
emitting functions (`src/analysis/tests.py`'s `_t_*_claim` generators)
currently hand-writes its own `narrative.headline`/`body` alongside the
statistic — the analyst authoring final prose directly, exactly the fused
step the target architecture wants split apart. This module is the other
half of that split: everything a genuinely mechanical builder CAN produce
without writing a word of prose. `NarrativeBrief` is deliberately
structured data, not text — generating the actual headline/body from it
is a separate, later step. This project already has two components for
that step, neither built out yet: the S10 Renderer
(`docs/render/Renderer_prompt.txt`, written, never run) and the critic-
agent review loop (`docs/uplift/03-critic-agents.md`, not built) for
iterating a draft until it clears review. Reusing an already-hand-authored
`Claim.narrative.headline` here would just be re-importing the same fused
analyst-writes-prose pattern one level down — deliberately not done.

Not wired into `council draft` or any live output path — additive, proving
the seam works, same as every other step in this migration. See
`scripts/render_claim_panels_preview.py` for a standalone demonstration
against real data.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analysis.claim_linter import LintStatus, lint_claim
from src.analysis.claims import Claim


@dataclass(frozen=True)
class ChartSpec:
    """A single value-with-confidence-interval marker — the one chart
    shape every claim's `statistic` can support generically, regardless of
    which of the many different statistical shapes produced it (a
    proportion, a difference, a hypergeometric count, an OLS slope...).
    Claims without a computed CI (e.g. a `herfindahl_index`-based one)
    simply carry `ci_low=ci_high=None`; the chart degrades to a bare point
    marker, not an error — a caller renders whatever is present."""
    kind: str  # always "value_ci" — the one generic shape built so far
    value: float | None
    ci_low: float | None
    ci_high: float | None
    method: str


@dataclass(frozen=True)
class NarrativeBrief:
    """Every fact a prose-writing step needs, structured — never
    assembled into a sentence here. Mirrors the claim's own fields rather
    than reshaping them, so a later Renderer/critic pass can trace any
    word it writes back to exactly one of these, per `02-claim-layer.md`'s
    own requirement that narrative be generated FROM the structured
    fields, not alongside them."""
    hypothesis: str
    population_grain: str
    population_definition: str
    numerator_definition: str
    numerator_n: int
    denominator_definition: str
    denominator_n: int
    comparison_type: str
    comparison_reference_definition: str
    comparison_reference_is_same_event: bool
    statistic_value: float | None
    statistic_ci_low: float | None
    statistic_ci_high: float | None
    statistic_method: str
    grade: str
    grade_justification: str
    caveats: tuple[str, ...]
    names_individuals: bool
    individual_names: tuple[str, ...]


@dataclass(frozen=True)
class PanelData:
    """The deterministic "most of the panel" this build's scope covers —
    everything except prose. `lint_clean` is False whenever a fresh lint
    pass (run here, not trusted from an earlier call a caller might have
    made against a since-modified claim) finds any FAIL; a panel built
    from a claim with an open FAIL is flagged, not silently built anyway —
    a caller deciding whether to actually publish this should check it."""
    claim_id: str
    grade: str
    chart: ChartSpec
    brief: NarrativeBrief
    lint_clean: bool
    lint_failures: tuple[str, ...]  # "RULE: message", for whatever failed


def build_panel(claim: Claim) -> PanelData:
    """The Builder itself: `Claim` -> `PanelData`, no prose written. A
    pure function of the claim's own fields plus a fresh lint pass."""
    results = lint_claim(claim)
    failures = tuple(f"{r.rule_id}: {r.message}" for r in results if r.status == LintStatus.FAIL)

    chart = ChartSpec(
        kind="value_ci",
        value=claim.statistic.value,
        ci_low=claim.statistic.ci_low,
        ci_high=claim.statistic.ci_high,
        method=claim.statistic.method,
    )
    brief = NarrativeBrief(
        hypothesis=claim.hypothesis,
        population_grain=claim.population.grain,
        population_definition=claim.population.definition,
        numerator_definition=claim.numerator.definition,
        numerator_n=claim.numerator.n,
        denominator_definition=claim.denominator.definition,
        denominator_n=claim.denominator.n,
        comparison_type=claim.comparison.type,
        comparison_reference_definition=claim.comparison.reference_definition,
        comparison_reference_is_same_event=claim.comparison.reference_is_same_event,
        statistic_value=claim.statistic.value,
        statistic_ci_low=claim.statistic.ci_low,
        statistic_ci_high=claim.statistic.ci_high,
        statistic_method=claim.statistic.method,
        grade=claim.grade,
        grade_justification=claim.grade_justification,
        caveats=claim.narrative.caveats,
        names_individuals=claim.names_individuals,
        individual_names=tuple(i.name for i in claim.individuals),
    )
    return PanelData(
        claim_id=claim.id, grade=claim.grade, chart=chart, brief=brief,
        lint_clean=not failures, lint_failures=failures,
    )


def build_panels(claims: dict[str, Claim]) -> dict[str, PanelData]:
    """The batch counterpart, mirroring `run_claim_battery()`'s own
    `{test_id: Claim}` shape."""
    return {test_id: build_panel(claim) for test_id, claim in claims.items()}
