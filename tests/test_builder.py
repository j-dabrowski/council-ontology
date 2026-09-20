"""
Tests for src/analysis/builder.py — the Builder (docs/uplift/
02-claim-layer.md's term): deterministic Claim -> PanelData, no prose.
"""
import pytest

from src.analysis.builder import build_panel, build_panels
from src.analysis.claims import (
    GRADE_CRITICAL,
    GRADE_NEUTRAL,
    Claim,
    Comparison,
    Individual,
    NumeratorDenominator,
    Population,
    Statistic,
)


def _claim(**overrides) -> Claim:
    defaults = dict(
        id="test-claim",
        hypothesis="Test hypothesis",
        population=Population(
            grain="(application)", definition="test population", base_table="application_fact",
        ),
        numerator=NumeratorDenominator(definition="positive cases", n=10),
        denominator=NumeratorDenominator(definition="all cases", n=100),
        grade=GRADE_NEUTRAL,
        grade_justification="because",
    )
    defaults.update(overrides)
    return Claim(**defaults)


def test_build_panel_carries_no_prose_fields():
    panel = build_panel(_claim())
    # PanelData/NarrativeBrief have no headline/body/verdict field at all -
    # the whole point of the split. Confirmed structurally, not just by
    # convention: neither dataclass declares one.
    from dataclasses import fields
    field_names = {f.name for f in fields(panel)} | {f.name for f in fields(panel.brief)}
    assert "headline" not in field_names
    assert "body" not in field_names
    assert "verdict" not in field_names


def test_build_panel_chart_reflects_statistic():
    claim = _claim(statistic=Statistic(value=0.42, ci_low=0.3, ci_high=0.5, method="wilson"))
    panel = build_panel(claim)
    assert panel.chart.kind == "value_ci"
    assert panel.chart.value == pytest.approx(0.42)
    assert panel.chart.ci_low == pytest.approx(0.3)
    assert panel.chart.ci_high == pytest.approx(0.5)
    assert panel.chart.method == "wilson"


def test_build_panel_chart_degrades_gracefully_without_ci():
    claim = _claim(statistic=Statistic(value=0.2, method="hypergeometric"))
    panel = build_panel(claim)
    assert panel.chart.value == pytest.approx(0.2)
    assert panel.chart.ci_low is None
    assert panel.chart.ci_high is None


def test_build_panel_brief_mirrors_structured_fields():
    claim = _claim(
        hypothesis="Does X happen more than Y?",
        comparison=Comparison(type="between_subject", reference_definition="group Y", reference_is_same_event=True),
        grade=GRADE_CRITICAL,
        grade_justification="CI excludes the null",
    )
    panel = build_panel(claim)
    b = panel.brief
    assert b.hypothesis == "Does X happen more than Y?"
    assert b.population_definition == "test population"
    assert b.numerator_definition == "positive cases"
    assert b.numerator_n == 10
    assert b.denominator_definition == "all cases"
    assert b.denominator_n == 100
    assert b.comparison_type == "between_subject"
    assert b.comparison_reference_definition == "group Y"
    assert b.grade == GRADE_CRITICAL
    assert b.grade_justification == "CI excludes the null"


def test_build_panel_brief_carries_individual_names_when_named():
    claim = _claim(
        names_individuals=True,
        individuals=(Individual(name="A One", n_for_this_person=5), Individual(name="B Two", n_for_this_person=6)),
    )
    panel = build_panel(claim)
    assert panel.brief.names_individuals is True
    assert panel.brief.individual_names == ("A One", "B Two")


def test_build_panel_flags_lint_failures_not_silently():
    # GRADE_SUPPORTIVE with no achieved_power is a known, real L-02 FAIL.
    from src.analysis.claims import GRADE_SUPPORTIVE, Power
    claim = _claim(grade=GRADE_SUPPORTIVE, power=Power(achieved_power=None))
    panel = build_panel(claim)
    assert panel.lint_clean is False
    assert any(f.startswith("L-02") for f in panel.lint_failures)


def test_build_panel_lint_clean_when_no_failures():
    claim = _claim()  # neutral grade, no triggers - should be clean
    panel = build_panel(claim)
    assert panel.lint_clean is True
    assert panel.lint_failures == ()


def test_build_panels_batch_keys_by_claim_id():
    claims = {"a": _claim(id="a"), "b": _claim(id="b")}
    panels = build_panels(claims)
    assert set(panels.keys()) == {"a", "b"}
    assert panels["a"].claim_id == "a"
    assert panels["b"].claim_id == "b"
