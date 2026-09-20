"""
Tests for src/analysis/critic_routing.py (docs/uplift/03-critic-agents.md
"Routing"; Step 5).
"""
from src.analysis.claims import (
    GRADE_CONCERN,
    GRADE_CRITICAL,
    GRADE_NEUTRAL,
    GRADE_SUPPORTIVE,
    Claim,
    ExtractionError,
    ExtractionErrorField,
    FrameworkRef,
    Individual,
    NumeratorDenominator,
    Population,
)
from src.analysis.critic_routing import (
    C01_AUDITOR,
    C02_STATISTICIAN,
    C03_JURISDICTION,
    C04_DEFENCE_COUNSEL,
    C05_EXTRACTION_SCEPTIC,
    C06_CROSS_PANEL,
    C07_SUBJECT_FAIRNESS,
    C08_VISUAL_QA,
    C09_GOODHART,
    C10_LAYMAN,
    C11_EDITOR_IN_CHIEF,
    route_claim,
    route_cross_panel,
)


def _claim(**overrides):
    defaults = dict(
        id="test-claim",
        hypothesis="Test hypothesis",
        population=Population(grain="(application)", definition="pop", base_table="application_fact"),
        numerator=NumeratorDenominator(definition="n", n=10),
        denominator=NumeratorDenominator(definition="d", n=100),
        grade=GRADE_NEUTRAL,
        grade_justification="because",
    )
    defaults.update(overrides)
    return Claim(**defaults)


def test_neutral_unremarkable_claim_gets_only_always_critics():
    result = route_claim(_claim())
    assert result == (C08_VISUAL_QA, C10_LAYMAN, C11_EDITOR_IN_CHIEF)


def test_critical_grade_adds_statistician_and_defence_counsel():
    result = route_claim(_claim(grade=GRADE_CRITICAL))
    assert C02_STATISTICIAN in result
    assert C04_DEFENCE_COUNSEL in result


def test_concern_grade_also_triggers_the_same_pair():
    result = route_claim(_claim(grade=GRADE_CONCERN))
    assert C02_STATISTICIAN in result
    assert C04_DEFENCE_COUNSEL in result


def test_supportive_grade_does_not_trigger_statistician():
    result = route_claim(_claim(grade=GRADE_SUPPORTIVE))
    assert C02_STATISTICIAN not in result
    assert C04_DEFENCE_COUNSEL not in result


def test_named_individuals_triggers_subject_and_auditor():
    claim = _claim(names_individuals=True, individuals=(Individual(name="A One", n_for_this_person=5),))
    result = route_claim(claim)
    assert C07_SUBJECT_FAIRNESS in result
    assert C01_AUDITOR in result


def test_framework_refs_triggers_jurisdiction():
    claim = _claim(framework_refs=(FrameworkRef(instrument="LGA_1995", section="s5.65"),))
    result = route_claim(claim)
    assert C03_JURISDICTION in result


def test_no_framework_refs_does_not_trigger_jurisdiction():
    result = route_claim(_claim())
    assert C03_JURISDICTION not in result


def test_low_era_precision_triggers_extraction_sceptic():
    claim = _claim(extraction_error=ExtractionError(
        fields=(ExtractionErrorField(field="x", era="pre-2024", precision=0.5, recall_floor=0.5),),
    ))
    result = route_claim(claim)
    assert C05_EXTRACTION_SCEPTIC in result


def test_high_era_precision_does_not_trigger_extraction_sceptic():
    claim = _claim(extraction_error=ExtractionError(
        fields=(ExtractionErrorField(field="x", era="2024+", precision=0.99, recall_floor=0.9),),
    ))
    result = route_claim(claim)
    assert C05_EXTRACTION_SCEPTIC not in result


def test_gameable_test_ids_triggers_goodhart():
    claim = _claim(id="conflict.recusal_management")
    result = route_claim(claim, gameable_test_ids={"conflict.recusal_management"})
    assert C09_GOODHART in result


def test_not_in_gameable_list_does_not_trigger_goodhart():
    claim = _claim(id="some.other.test")
    result = route_claim(claim, gameable_test_ids={"conflict.recusal_management"})
    assert C09_GOODHART not in result


def test_multiple_triggers_compose_without_duplicates():
    claim = _claim(
        grade=GRADE_CRITICAL, names_individuals=True,
        individuals=(Individual(name="A One", n_for_this_person=5),),
        framework_refs=(FrameworkRef(instrument="LGA_1995", section="s5.65"),),
    )
    result = route_claim(claim)
    assert len(result) == len(set(result))
    for c in (C08_VISUAL_QA, C10_LAYMAN, C11_EDITOR_IN_CHIEF, C02_STATISTICIAN,
              C04_DEFENCE_COUNSEL, C07_SUBJECT_FAIRNESS, C01_AUDITOR, C03_JURISDICTION):
        assert c in result


def test_route_cross_panel_is_always_just_c06():
    assert route_cross_panel() == (C06_CROSS_PANEL,)
