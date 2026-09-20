"""
Tests for src/analysis/cross_panel.py — C-06, the cross-panel critic,
mechanized as batch checks over a whole build's claims.
"""
from src.analysis.claims import (
    GRADE_NEUTRAL,
    Claim,
    Individual,
    NumeratorDenominator,
    Population,
)
from src.analysis.cross_panel import run_cross_panel


def _claim(id, population_definition="pop", denom_n=100, individuals=(), names_individuals=False, **overrides):
    defaults = dict(
        id=id,
        hypothesis="Test hypothesis",
        population=Population(grain="(application)", definition=population_definition, base_table="application_fact"),
        numerator=NumeratorDenominator(definition="n", n=10),
        denominator=NumeratorDenominator(definition="d", n=denom_n),
        grade=GRADE_NEUTRAL,
        grade_justification="because",
        individuals=individuals,
        names_individuals=names_individuals,
    )
    defaults.update(overrides)
    return Claim(**defaults)


def test_cp01_flags_shared_definition_different_denominators():
    a = _claim("a", population_definition="shared pop", denom_n=100)
    b = _claim("b", population_definition="shared pop", denom_n=200)
    findings = run_cross_panel([a, b])
    cp01 = [f for f in findings if f.id.startswith("CP-01")]
    assert len(cp01) == 2
    assert {f.claim_id for f in cp01} == {"a", "b"}


def test_cp01_silent_when_denominators_agree():
    a = _claim("a", population_definition="shared pop", denom_n=100)
    b = _claim("b", population_definition="shared pop", denom_n=100)
    findings = run_cross_panel([a, b])
    assert [f for f in findings if f.id.startswith("CP-01")] == []


def test_cp01_silent_for_unrelated_populations():
    a = _claim("a", population_definition="pop one", denom_n=100)
    b = _claim("b", population_definition="pop two", denom_n=200)
    findings = run_cross_panel([a, b])
    assert [f for f in findings if f.id.startswith("CP-01")] == []


def test_cp02_flags_whitespace_inconsistent_name():
    a = _claim("a", names_individuals=True, individuals=(Individual(name="Jo McAllister", n_for_this_person=5),))
    b = _claim("b", names_individuals=True, individuals=(Individual(name="Jo  McAllister", n_for_this_person=3),))
    findings = run_cross_panel([a, b])
    cp02 = [f for f in findings if f.id.startswith("CP-02")]
    assert len(cp02) == 1
    assert "Jo McAllister" in cp02[0].statement or "Jo  McAllister" in cp02[0].statement


def test_cp02_flags_case_inconsistent_name():
    a = _claim("a", names_individuals=True, individuals=(Individual(name="jo mcallister", n_for_this_person=5),))
    b = _claim("b", names_individuals=True, individuals=(Individual(name="Jo McAllister", n_for_this_person=3),))
    findings = run_cross_panel([a, b])
    assert len([f for f in findings if f.id.startswith("CP-02")]) == 1


def test_cp02_silent_when_names_are_consistent():
    a = _claim("a", names_individuals=True, individuals=(Individual(name="Jo McAllister", n_for_this_person=5),))
    b = _claim("b", names_individuals=True, individuals=(Individual(name="Jo McAllister", n_for_this_person=3),))
    findings = run_cross_panel([a, b])
    assert [f for f in findings if f.id.startswith("CP-02")] == []


def test_cp02_silent_when_no_individuals_named():
    a = _claim("a")
    b = _claim("b")
    assert run_cross_panel([a, b]) == []


def test_run_cross_panel_empty_batch_is_empty():
    assert run_cross_panel([]) == []
