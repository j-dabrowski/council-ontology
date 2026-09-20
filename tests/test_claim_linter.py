"""
Tests for src/analysis/claim_linter.py (docs/uplift/migration/02-claim-
layer.md Step 5): one passing and one failing case per rule (L-01..L-18),
per that step's own "Done when".
"""
from src.analysis.claim_linter import (
    RULES,
    LintContext,
    LintStatus,
    check_l01,
    check_l02,
    check_l03,
    check_l04,
    check_l05,
    check_l06_shared_denominator,
    check_l07,
    check_l08,
    check_l09,
    check_l10,
    check_l11,
    check_l12,
    check_l13,
    check_l14,
    check_l15,
    check_l16,
    check_l17,
    check_l18,
    has_blocking_failure,
    lint_batch,
    lint_claim,
)
from src.analysis.claims import (
    COMPARISON_BETWEEN_SUBJECT,
    COMPARISON_WITHIN_SUBJECT,
    CORRECTION_BONFERRONI,
    CORRECTION_NONE,
    GRADE_CRITICAL,
    GRADE_NEUTRAL,
    GRADE_SUPPORTIVE,
    Claim,
    Comparison,
    ExtractionError,
    ExtractionErrorField,
    FrameworkRef,
    Individual,
    MultipleComparison,
    Narrative,
    NumeratorDenominator,
    Population,
    Power,
    Provenance,
    Statistic,
)


def _claim(**overrides) -> Claim:
    defaults = dict(
        id="test-claim",
        hypothesis="Test hypothesis",
        population=Population(
            grain="(meeting, item, councillor)", definition="test population", base_table="vote_fact",
        ),
        numerator=NumeratorDenominator(definition="positive cases", n=10),
        denominator=NumeratorDenominator(definition="all cases", n=100),
        grade=GRADE_NEUTRAL,
        grade_justification="because",
    )
    defaults.update(overrides)
    return Claim(**defaults)


CTX = LintContext()


# ── L-01 ─────────────────────────────────────────────────────────────────

def test_l01_not_applicable_when_not_critical():
    assert check_l01(_claim(grade=GRADE_NEUTRAL), CTX).status == LintStatus.NOT_APPLICABLE


def test_l01_fails_when_ci_contains_null_value():
    claim = _claim(grade=GRADE_CRITICAL, statistic=Statistic(value=0.667, ci_low=0.35, ci_high=0.90))
    ctx = LintContext(null_value=0.871)
    assert check_l01(claim, ctx).status == LintStatus.FAIL


def test_l01_passes_when_ci_excludes_null_value():
    claim = _claim(grade=GRADE_CRITICAL, statistic=Statistic(value=0.15, ci_low=0.10, ci_high=0.20))
    ctx = LintContext(null_value=0.871)
    assert check_l01(claim, ctx).status == LintStatus.PASS


# ── L-02 ─────────────────────────────────────────────────────────────────

def test_l02_not_applicable_when_not_supportive():
    assert check_l02(_claim(grade=GRADE_NEUTRAL), CTX).status == LintStatus.NOT_APPLICABLE


def test_l02_fails_underpowered():
    claim = _claim(grade=GRADE_SUPPORTIVE, power=Power(achieved_power=0.3))
    assert check_l02(claim, CTX).status == LintStatus.FAIL


def test_l02_passes_adequately_powered():
    claim = _claim(grade=GRADE_SUPPORTIVE, power=Power(achieved_power=0.9))
    assert check_l02(claim, CTX).status == LintStatus.PASS


# ── L-03 ─────────────────────────────────────────────────────────────────

def test_l03_fails_excess_precision():
    claim = _claim(
        statistic=Statistic(value=0.753, ci_low=0.60, ci_high=0.90),
        narrative=Narrative(headline="Members recuse 75.3% of the time"),
    )
    assert check_l03(claim, CTX).status == LintStatus.FAIL


def test_l03_passes_precision_within_ci_width():
    claim = _claim(
        statistic=Statistic(value=0.75, ci_low=0.60, ci_high=0.90),
        narrative=Narrative(headline="Members recuse 75% of the time"),
    )
    assert check_l03(claim, CTX).status == LintStatus.PASS


def test_l03_unverifiable_without_ci():
    assert check_l03(_claim(), CTX).status == LintStatus.UNVERIFIABLE


# ── L-04 ─────────────────────────────────────────────────────────────────

def test_l04_not_applicable_when_grain_not_finer_than_entity():
    claim = _claim(population=Population(grain="(application)", definition="d", base_table="application_fact"))
    assert check_l04(claim, CTX).status == LintStatus.NOT_APPLICABLE


def test_l04_fails_without_clustering_unit():
    claim = _claim(statistic=Statistic(clustering_unit=None))
    assert check_l04(claim, CTX).status == LintStatus.FAIL


def test_l04_passes_with_clustering_unit():
    claim = _claim(statistic=Statistic(clustering_unit="councillor"))
    assert check_l04(claim, CTX).status == LintStatus.PASS


# ── L-05 ─────────────────────────────────────────────────────────────────

def test_l05_not_applicable_when_no_individuals_named():
    assert check_l05(_claim(names_individuals=False), CTX).status == LintStatus.NOT_APPLICABLE


def test_l05_fails_missing_safeguards():
    claim = _claim(
        names_individuals=True,
        individuals=(Individual(name="Carr", n_for_this_person=2),),
    )
    assert check_l05(claim, CTX).status == LintStatus.FAIL


def test_l05_passes_all_safeguards_present():
    claim = _claim(
        names_individuals=True,
        individuals=(Individual(name="Carr", n_for_this_person=5, ci_low=0.1, ci_high=0.9),),
        provenance=Provenance(source_spans=("span-1",)),
        narrative=Narrative(response="The council responded on 1 January."),
    )
    assert check_l05(claim, CTX).status == LintStatus.PASS


# ── L-06 (batch) ─────────────────────────────────────────────────────────

def test_l06_fails_when_shared_definition_has_different_denominators():
    a = _claim(id="a", population=Population(grain="(meeting, item, councillor)", definition="shared pop", base_table="vote_fact"),
               denominator=NumeratorDenominator(definition="d", n=100))
    b = _claim(id="b", population=Population(grain="(meeting, item, councillor)", definition="shared pop", base_table="vote_fact"),
               denominator=NumeratorDenominator(definition="d", n=200))
    results = check_l06_shared_denominator([a, b])
    assert results["a"].status == LintStatus.FAIL
    assert results["b"].status == LintStatus.FAIL


def test_l06_passes_when_shared_definition_has_same_denominator():
    a = _claim(id="a", population=Population(grain="(meeting, item, councillor)", definition="shared pop", base_table="vote_fact"),
               denominator=NumeratorDenominator(definition="d", n=100))
    b = _claim(id="b", population=Population(grain="(meeting, item, councillor)", definition="shared pop", base_table="vote_fact"),
               denominator=NumeratorDenominator(definition="d", n=100))
    results = check_l06_shared_denominator([a, b])
    assert results["a"].status == LintStatus.PASS
    assert results["b"].status == LintStatus.PASS


# ── L-07 ─────────────────────────────────────────────────────────────────

def test_l07_not_applicable_when_same_event():
    assert check_l07(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l07_fails_unjustified_non_same_event():
    claim = _claim(comparison=Comparison(reference_is_same_event=False))
    assert check_l07(claim, CTX).status == LintStatus.FAIL


def test_l07_passes_justified_and_surfaced():
    claim = _claim(
        comparison=Comparison(reference_is_same_event=False, reference_definition="non-attendance for illness"),
        narrative=Narrative(caveats=("This compares two different event types.",)),
    )
    assert check_l07(claim, CTX).status == LintStatus.PASS


# ── L-08 ─────────────────────────────────────────────────────────────────

def test_l08_unverifiable_without_replay():
    assert check_l08(_claim(), CTX).status == LintStatus.UNVERIFIABLE


def test_l08_fails_on_mismatch():
    claim = _claim(denominator=NumeratorDenominator(definition="d", n=100))
    ctx = LintContext(replayed_denominator_n=50)
    assert check_l08(claim, ctx).status == LintStatus.FAIL


def test_l08_passes_on_match():
    claim = _claim(denominator=NumeratorDenominator(definition="d", n=100))
    ctx = LintContext(replayed_denominator_n=100)
    assert check_l08(claim, ctx).status == LintStatus.PASS


# ── L-09 ─────────────────────────────────────────────────────────────────

def test_l09_not_applicable_without_framework_refs():
    assert check_l09(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l09_fails_unresolved_instrument():
    claim = _claim(framework_refs=(FrameworkRef(instrument="NOLAN", section="selflessness"),))
    assert check_l09(claim, CTX).status == LintStatus.FAIL


def test_l09_passes_resolved_instrument():
    claim = _claim(framework_refs=(FrameworkRef(instrument="LGA_1995", section="s5.65"),))
    assert check_l09(claim, CTX).status == LintStatus.PASS


# ── L-10 ─────────────────────────────────────────────────────────────────

def test_l10_not_applicable_family_size_one():
    assert check_l10(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l10_fails_no_correction():
    claim = _claim(statistic=Statistic(multiple_comparison=MultipleComparison(family_size=12, correction=CORRECTION_NONE)))
    assert check_l10(claim, CTX).status == LintStatus.FAIL


def test_l10_fails_correction_but_unresolved():
    claim = _claim(statistic=Statistic(multiple_comparison=MultipleComparison(
        family_size=12, correction=CORRECTION_BONFERRONI, survives_correction=None)))
    assert check_l10(claim, CTX).status == LintStatus.FAIL


def test_l10_passes_corrected_and_resolved():
    claim = _claim(statistic=Statistic(multiple_comparison=MultipleComparison(
        family_size=12, correction=CORRECTION_BONFERRONI, survives_correction=True)))
    assert check_l10(claim, CTX).status == LintStatus.PASS


# ── L-11 ─────────────────────────────────────────────────────────────────

def test_l11_passes_headline_figure_matches_statistic():
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=8),
        denominator=NumeratorDenominator(definition="d", n=12),
        statistic=Statistic(value=8 / 12),
        narrative=Narrative(headline="Council recused 66.7% of the time"),
    )
    assert check_l11(claim, CTX).status == LintStatus.PASS


def test_l11_fails_headline_only_number():
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=8),
        denominator=NumeratorDenominator(definition="d", n=12),
        statistic=Statistic(value=8 / 12),
        narrative=Narrative(headline="Council recused 90% of the time"),
    )
    assert check_l11(claim, CTX).status == LintStatus.FAIL


def test_l11_does_not_misread_a_hyphenated_compound_as_negative():
    # "top-10" must read as the positive number 10, not -10 - found by
    # running this rule against a real generated claim.
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=10),
        denominator=NumeratorDenominator(definition="d", n=100),
        statistic=Statistic(value=0.10),
        narrative=Narrative(headline="10 firms are in the top-10 dollar-recipient list"),
    )
    assert check_l11(claim, CTX).status == LintStatus.PASS


def test_l11_does_not_misread_a_range_hyphen_as_negative():
    # "41-92%" must read as 41 and 92, not 41 and -92.
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=41),
        denominator=NumeratorDenominator(definition="d", n=100),
        statistic=Statistic(value=0.92),
        narrative=Narrative(headline="Rates span 41-92% between councillors"),
    )
    assert check_l11(claim, CTX).status == LintStatus.PASS


def test_l11_handles_comma_formatted_thousands():
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=4993),
        denominator=NumeratorDenominator(definition="d", n=4993),
        statistic=Statistic(value=1.0),
        narrative=Narrative(headline="4,993 recorded public engagements"),
    )
    assert check_l11(claim, CTX).status == LintStatus.PASS


def test_l11_does_not_truncate_a_bare_four_digit_year():
    # A year like "2003" has no comma grouping - the comma-thousands fix
    # must not truncate it to "200" via a bare {1,3} digit cap. Found by
    # running this rule against a real generated claim whose headline
    # named two era labels ("2003-2007").
    claim = _claim(
        numerator=NumeratorDenominator(definition="n", n=2003),
        denominator=NumeratorDenominator(definition="d", n=2007),
        statistic=Statistic(value=2003 / 2007),
        narrative=Narrative(headline="2003 of 2007 recorded"),
    )
    assert check_l11(claim, CTX).status == LintStatus.PASS


# ── L-12 ─────────────────────────────────────────────────────────────────

def test_l12_not_applicable_when_narrative_empty():
    assert check_l12(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l12_passes_shared_denominator_reference():
    claim = _claim(
        denominator=NumeratorDenominator(definition="must-leave declarations", n=12),
        narrative=Narrative(
            headline="Must-leave recusal fell to 66.7%",
            body="Based on must-leave declarations, this fell from the prior period.",
        ),
    )
    assert check_l12(claim, CTX).status == LintStatus.PASS


def test_l12_fails_inconsistent_denominator_reference():
    claim = _claim(
        denominator=NumeratorDenominator(definition="must-leave declarations", n=12),
        narrative=Narrative(
            headline="Members stay and vote 75.0% of the time (blended rate)",
            body="This panel is graded on must-leave declarations only.",
        ),
    )
    assert check_l12(claim, CTX).status == LintStatus.FAIL


# ── L-13 ─────────────────────────────────────────────────────────────────

def test_l13_not_applicable_without_flat_wording():
    assert check_l13(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l13_fails_flat_wording_ci_excludes_zero():
    claim = _claim(
        statistic=Statistic(ci_low=0.10, ci_high=0.20),
        power=Power(achieved_power=0.9),
        narrative=Narrative(body="Applicant frequency is flat across bucket sizes."),
    )
    assert check_l13(claim, CTX).status == LintStatus.FAIL


def test_l13_passes_flat_wording_supported():
    claim = _claim(
        statistic=Statistic(ci_low=-0.05, ci_high=0.05),
        power=Power(achieved_power=0.9),
        narrative=Narrative(body="Applicant frequency is flat across bucket sizes."),
    )
    assert check_l13(claim, CTX).status == LintStatus.PASS


# ── L-14 ─────────────────────────────────────────────────────────────────

def test_l14_not_applicable_without_causal_verb():
    assert check_l14(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l14_passes_within_subject():
    claim = _claim(
        comparison=Comparison(type=COMPARISON_WITHIN_SUBJECT),
        narrative=Narrative(headline="Attending the same meeting twice causes no change."),
    )
    assert check_l14(claim, CTX).status == LintStatus.PASS


def test_l14_fails_causal_language_unjustified():
    claim = _claim(
        comparison=Comparison(type=COMPARISON_BETWEEN_SUBJECT),
        narrative=Narrative(headline="A declared-interest vote leans toward letting the matter through."),
    )
    assert check_l14(claim, CTX).status == LintStatus.FAIL


def test_l14_passes_causal_language_with_justification():
    claim = _claim(
        comparison=Comparison(type=COMPARISON_BETWEEN_SUBJECT),
        grade_justification="Observational only; see caveat on base-rate confound.",
        narrative=Narrative(
            headline="A declared-interest vote leans toward letting the matter through.",
            caveats=("Declared-interest items skew to categories with different base approval rates.",),
        ),
    )
    assert check_l14(claim, CTX).status == LintStatus.PASS


# ── L-15 ─────────────────────────────────────────────────────────────────

def test_l15_unverifiable_without_extraction_error():
    assert check_l15(_claim(), CTX).status == LintStatus.UNVERIFIABLE


def test_l15_fails_low_precision_graded_above_neutral():
    claim = _claim(
        grade=GRADE_CRITICAL,
        extraction_error=ExtractionError(fields=(ExtractionErrorField(field="x", era="pre-2024", precision=0.81, recall_floor=0.7),)),
    )
    assert check_l15(claim, CTX).status == LintStatus.FAIL


def test_l15_passes_low_precision_graded_neutral():
    claim = _claim(
        grade=GRADE_NEUTRAL,
        extraction_error=ExtractionError(fields=(ExtractionErrorField(field="x", era="pre-2024", precision=0.81, recall_floor=0.7),)),
    )
    assert check_l15(claim, CTX).status == LintStatus.PASS


def test_l15_passes_high_precision_any_grade():
    claim = _claim(
        grade=GRADE_CRITICAL,
        extraction_error=ExtractionError(fields=(ExtractionErrorField(field="x", era="2024+", precision=0.98, recall_floor=0.9),)),
    )
    assert check_l15(claim, CTX).status == LintStatus.PASS


# ── L-16 ─────────────────────────────────────────────────────────────────

def test_l16_not_applicable_without_fiscal_keyword():
    assert check_l16(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l16_fails_literal_month_without_config():
    claim = _claim(population=Population(
        grain="(meeting, item, councillor)", definition="fiscal year spend", base_table="tender_fact",
        filter_chain=("month == December",),
    ))
    assert check_l16(claim, CTX).status == LintStatus.FAIL


def test_l16_passes_month_referenced_via_config():
    claim = _claim(population=Population(
        grain="(meeting, item, councillor)", definition="fiscal year spend", base_table="tender_fact",
        filter_chain=("July per config/fiscal_year.json fiscal_year_start_month",),
    ))
    assert check_l16(claim, CTX).status == LintStatus.PASS


# ── L-17 ─────────────────────────────────────────────────────────────────

def test_l17_not_applicable_without_named_individuals():
    assert check_l17(_claim(), CTX).status == LintStatus.NOT_APPLICABLE


def test_l17_unverifiable_without_registry():
    claim = _claim(names_individuals=True, individuals=(Individual(name="Carr", n_for_this_person=5),))
    assert check_l17(claim, CTX).status == LintStatus.UNVERIFIABLE


def test_l17_fails_unresolved_name():
    claim = _claim(names_individuals=True, individuals=(Individual(name="Carr", n_for_this_person=5),))
    ctx = LintContext(canonical_entity_names=frozenset({"J. Carr"}))
    assert check_l17(claim, ctx).status == LintStatus.FAIL


def test_l17_passes_resolved_name():
    claim = _claim(names_individuals=True, individuals=(Individual(name="Carr", n_for_this_person=5),))
    ctx = LintContext(canonical_entity_names=frozenset({"Carr"}))
    assert check_l17(claim, ctx).status == LintStatus.PASS


# ── L-18 ─────────────────────────────────────────────────────────────────

def test_l18_unverifiable_without_counts():
    assert check_l18(_claim(), CTX).status == LintStatus.UNVERIFIABLE


def test_l18_fails_mismatched_series_count():
    ctx = LintContext(declared_category_count=12, rendered_series_count=11)
    assert check_l18(_claim(), ctx).status == LintStatus.FAIL


def test_l18_passes_matching_series_count():
    ctx = LintContext(declared_category_count=12, rendered_series_count=12)
    assert check_l18(_claim(), ctx).status == LintStatus.PASS


# ── entry points ─────────────────────────────────────────────────────────

def test_lint_claim_runs_every_single_claim_rule():
    results = lint_claim(_claim())
    assert {r.rule_id for r in results} == set(RULES.keys())


def test_lint_batch_includes_l06_and_keys_by_claim_id():
    a = _claim(id="a")
    b = _claim(id="b", population=Population(grain="(application)", definition="other pop", base_table="application_fact"))
    results = lint_batch([a, b])
    assert set(results.keys()) == {"a", "b"}
    assert {r.rule_id for r in results["a"]} == set(RULES.keys()) | {"L-06"}


def test_has_blocking_failure_true_on_any_fail():
    a = _claim(id="a", grade=GRADE_SUPPORTIVE, power=Power(achieved_power=0.1))
    results = lint_batch([a])
    assert has_blocking_failure(results) is True


def test_has_blocking_failure_false_when_clean():
    # grain deliberately not finer than one row per entity, so L-04 (which
    # would otherwise fail on the default claim's missing clustering_unit)
    # is NOT_APPLICABLE rather than FAIL — this test is about the aggregate
    # has_blocking_failure() wiring, not L-04 specifically.
    a = _claim(id="a", population=Population(grain="(application)", definition="test population", base_table="application_fact"))
    results = lint_batch([a])
    assert has_blocking_failure(results) is False
