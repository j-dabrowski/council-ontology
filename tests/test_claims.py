"""Step 1 of docs/uplift/migration/02-claim-layer.md: the claim object
exists as an importable Python type with every target-schema field present."""

import pytest

from src.analysis.claims import (
    Claim,
    Comparison,
    Exclusion,
    FrameworkRef,
    GRADE_SUPPORTIVE,
    Individual,
    MultipleComparison,
    Narrative,
    NumeratorDenominator,
    Population,
    Statistic,
    parse_grain,
)


def _minimal_claim(**overrides) -> Claim:
    kwargs = dict(
        id="procurement.threshold_gaming",
        hypothesis="Is there excess mass just below the competitive-tender threshold?",
        population=Population(
            grain="(meeting, award)",
            definition="Tenders awarded 2015 onward",
            base_table="tender_fact",
            filter_chain=("year >= 2015",),
        ),
        numerator=NumeratorDenominator(definition="tenders in [200k, 250k)", n=4),
        denominator=NumeratorDenominator(definition="tenders in [250k, 300k)", n=3),
        grade=GRADE_SUPPORTIVE,
        grade_justification="ratio 1.33 <= 1.6 threshold",
    )
    kwargs.update(overrides)
    return Claim(**kwargs)


def test_parse_grain_known_dimensions():
    assert parse_grain("(meeting, item, councillor)") == ("meeting", "item", "councillor")


def test_parse_grain_single_dimension_no_parens():
    assert parse_grain("councillor") == ("councillor",)


def test_parse_grain_rejects_unknown_dimension():
    with pytest.raises(ValueError, match="unknown dimension"):
        parse_grain("(meeting, widget)")


def test_parse_grain_rejects_empty():
    with pytest.raises(ValueError):
        parse_grain("()")


def test_population_validates_grain_on_construction():
    with pytest.raises(ValueError):
        Population(grain="(nonsense)", definition="x", base_table="y")


def test_minimal_claim_constructs():
    c = _minimal_claim()
    assert c.grade == GRADE_SUPPORTIVE
    # placeholder sections default to empty, not absent
    assert c.power.mde is None
    assert c.extraction_error.fields == ()
    assert c.confounds.unaddressed == ()
    assert c.provenance.query_hash == ""
    assert c.statistic.multiple_comparison.family_size == 1
    assert c.narrative == Narrative()
    assert c.comparison == Comparison()
    assert c.names_individuals is False
    assert c.individuals == ()


def test_claim_rejects_unknown_grade():
    with pytest.raises(ValueError, match="grade must be one of"):
        _minimal_claim(grade="terrible")


def test_claim_requires_individuals_when_names_individuals_true():
    with pytest.raises(ValueError, match="requires at least one entry"):
        _minimal_claim(names_individuals=True)


def test_claim_rejects_individuals_without_names_individuals_flag():
    with pytest.raises(ValueError, match="names_individuals=False"):
        _minimal_claim(
            individuals=(Individual(name="A B", n_for_this_person=5),),
        )


def test_claim_with_named_individual():
    c = _minimal_claim(
        names_individuals=True,
        individuals=(Individual(name="A B", n_for_this_person=5, ci_low=0.1, ci_high=0.4),),
    )
    assert c.individuals[0].name == "A B"


def test_comparison_rejects_unknown_type():
    with pytest.raises(ValueError, match="comparison.type"):
        Comparison(type="sideways")


def test_multiple_comparison_rejects_unknown_correction():
    with pytest.raises(ValueError, match="correction"):
        MultipleComparison(correction="astrology")


def test_framework_ref_and_exclusion_are_plain_value_objects():
    ref = FrameworkRef(instrument="LGA_1995", section="s5.65")
    excl = Exclusion(rule="no_recorded_vote", n_excluded=2, reason="tally-only motion")
    assert ref.instrument == "LGA_1995"
    assert excl.n_excluded == 2


def test_statistic_defaults_are_none_not_zero():
    s = Statistic()
    assert s.value is None and s.ci_low is None and s.ci_high is None
    assert s.clustering_unit is None
