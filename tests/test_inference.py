"""
Tests for src/analysis/inference.py (docs/uplift/migration/02-claim-layer.md
Step 4): CI, clustering, and permutation-test machinery.
"""
import pytest

from src.analysis.inference import (
    chi_square_independence,
    clustered_proportion,
    difference_in_proportions_ci,
    herfindahl_index,
    hypergeometric_overlap_test,
    linear_trend_ci,
    mann_whitney_test,
    median_ci,
    median_difference_ci,
    permutation_test_difference,
    proportion_ci,
)


# ── proportion_ci ────────────────────────────────────────────────────────

def test_proportion_ci_wilson_contains_point_estimate():
    est = proportion_ci(50, 100)
    assert est.value == pytest.approx(0.5)
    assert est.method == "wilson"
    assert est.ci_low < est.value < est.ci_high


def test_proportion_ci_narrows_with_larger_n():
    small = proportion_ci(5, 10)
    large = proportion_ci(500, 1000)
    assert (large.ci_high - large.ci_low) < (small.ci_high - small.ci_low)


def test_proportion_ci_exact_method_is_wider_than_wilson():
    wilson = proportion_ci(9, 10, method="wilson")
    exact = proportion_ci(9, 10, method="exact")
    assert (exact.ci_high - exact.ci_low) >= (wilson.ci_high - wilson.ci_low)


def test_proportion_ci_rejects_zero_n():
    with pytest.raises(ValueError, match="n=0"):
        proportion_ci(0, 0)


def test_proportion_ci_rejects_k_greater_than_n():
    with pytest.raises(ValueError, match="0 <= k <= n"):
        proportion_ci(5, 3)


# ── clustered_proportion ─────────────────────────────────────────────────

class _Row:
    def __init__(self, councillor_id, recused):
        self.councillor_id = councillor_id
        self.recused = recused


def test_clustered_proportion_averages_across_clusters_not_rows():
    # Councillor A: 1 vote, always recuses (prop=1.0). Councillor B: 9 votes,
    # never recuses (prop=0.0). Pooled row-level rate would be 1/10 = 0.1;
    # the cluster-mean rate should sit near the midpoint of the two
    # cluster-level proportions instead.
    rows = [_Row("A", True)] + [_Row("B", False) for _ in range(9)]
    est = clustered_proportion(
        rows, cluster_key=lambda r: r.councillor_id,
        is_positive=lambda r: r.recused, clustering_unit="councillor",
    )
    assert est.value == pytest.approx(0.5)
    assert est.n_clusters == 2
    assert est.n_rows == 10
    assert est.clustering_unit == "councillor"


def test_clustered_proportion_requires_at_least_two_clusters():
    rows = [_Row("A", True), _Row("A", False)]
    with pytest.raises(ValueError, match="at least 2 non-empty clusters"):
        clustered_proportion(
            rows, cluster_key=lambda r: r.councillor_id,
            is_positive=lambda r: r.recused, clustering_unit="councillor",
        )


def test_clustered_proportion_ci_collapses_when_clusters_agree():
    rows = [_Row("A", True), _Row("B", True), _Row("C", True)]
    est = clustered_proportion(
        rows, cluster_key=lambda r: r.councillor_id,
        is_positive=lambda r: r.recused, clustering_unit="councillor",
    )
    assert est.value == pytest.approx(1.0)
    assert est.ci_low == pytest.approx(1.0)
    assert est.ci_high == pytest.approx(1.0)


# ── difference_in_proportions_ci ─────────────────────────────────────────

def test_difference_in_proportions_ci_zero_when_equal():
    est = difference_in_proportions_ci(50, 100, 50, 100)
    assert est.value == pytest.approx(0.0)
    assert est.ci_low < 0 < est.ci_high


def test_difference_in_proportions_ci_detects_large_gap():
    est = difference_in_proportions_ci(10, 100, 90, 100)
    assert est.value == pytest.approx(0.8)
    assert est.ci_low > 0


def test_difference_in_proportions_ci_rejects_zero_n():
    with pytest.raises(ValueError, match="n1=0"):
        difference_in_proportions_ci(0, 0, 5, 10)


# ── permutation_test_difference ──────────────────────────────────────────

def test_permutation_test_detects_large_difference():
    group_a = [10.0] * 20
    group_b = [0.0] * 20
    result = permutation_test_difference(group_a, group_b, n_resamples=999, seed=0)
    assert result.observed_diff == pytest.approx(10.0)
    assert result.p_value < 0.01


def test_permutation_test_no_difference_is_not_significant():
    group_a = [5.0, 5.0, 5.0, 5.0]
    group_b = [5.0, 5.0, 5.0, 5.0]
    result = permutation_test_difference(group_a, group_b, n_resamples=999, seed=0)
    assert result.observed_diff == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0)


def test_permutation_test_rejects_empty_group():
    with pytest.raises(ValueError, match="at least one observation"):
        permutation_test_difference([], [1.0])


# ── median_ci ─────────────────────────────────────────────────────────────

def test_median_ci_contains_the_point_estimate():
    est = median_ci([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], seed=0)
    assert est.value == pytest.approx(5.5)
    assert est.ci_low < est.value < est.ci_high


def test_median_ci_rejects_single_observation():
    with pytest.raises(ValueError, match="at least 2 observations"):
        median_ci([1.0])


# ── median_difference_ci ─────────────────────────────────────────────────

def test_median_difference_ci_detects_large_gap():
    group_a = [1, 2, 3, 4, 5] * 5
    group_b = [100, 101, 102, 103, 104] * 5
    est = median_difference_ci(group_a, group_b, seed=0)
    assert est.value == pytest.approx(99.0)
    assert est.ci_low > 0


def test_median_difference_ci_rejects_tiny_group():
    with pytest.raises(ValueError, match="at least 2 observations per group"):
        median_difference_ci([1.0], [1.0, 2.0])


# ── mann_whitney_test ────────────────────────────────────────────────────

def test_mann_whitney_detects_large_difference():
    group_a = [1, 2, 3, 4, 5] * 5
    group_b = [100, 101, 102, 103, 104] * 5
    result = mann_whitney_test(group_a, group_b)
    assert result.p_value < 0.01


def test_mann_whitney_rejects_empty_group():
    with pytest.raises(ValueError, match="at least one observation"):
        mann_whitney_test([], [1.0])


# ── chi_square_independence ──────────────────────────────────────────────

def test_chi_square_detects_dependence():
    # Theme A closes 90/100, theme B closes 10/100 - clearly dependent.
    table = [[90, 10], [10, 90]]
    result = chi_square_independence(table)
    assert result.p_value < 0.01
    assert result.dof == 1


def test_chi_square_no_dependence_when_rates_match():
    table = [[50, 50], [50, 50]]
    result = chi_square_independence(table)
    assert result.p_value == pytest.approx(1.0)


def test_chi_square_rejects_undersized_table():
    with pytest.raises(ValueError, match="at least a 2x2 table"):
        chi_square_independence([[5]])


# ── herfindahl_index ─────────────────────────────────────────────────────

def test_herfindahl_index_single_firm_is_one():
    assert herfindahl_index([100.0]) == pytest.approx(1.0)


def test_herfindahl_index_equal_split():
    assert herfindahl_index([25.0, 25.0, 25.0, 25.0]) == pytest.approx(0.25)


def test_herfindahl_index_rejects_zero_total():
    with pytest.raises(ValueError, match="positive total amount"):
        herfindahl_index([0.0, 0.0])


# ── hypergeometric_overlap_test ──────────────────────────────────────────

def test_hypergeometric_overlap_full_overlap_is_surprising():
    # Population of 100 firms, two independent top-10 lists - all 10 overlapping is very unlikely by chance.
    result = hypergeometric_overlap_test(population_size=100, group_a_size=10, group_b_size=10, observed_overlap=10)
    assert result.observed_overlap == 10
    assert result.expected_overlap == pytest.approx(1.0)
    assert result.p_value_at_least_observed < 0.001


def test_hypergeometric_overlap_zero_overlap_is_plausible():
    result = hypergeometric_overlap_test(population_size=100, group_a_size=10, group_b_size=10, observed_overlap=0)
    assert result.p_value_at_least_observed > 0.1


def test_hypergeometric_overlap_rejects_invalid_sizes():
    with pytest.raises(ValueError, match="invalid sizes"):
        hypergeometric_overlap_test(population_size=10, group_a_size=20, group_b_size=5, observed_overlap=1)


# ── linear_trend_ci ──────────────────────────────────────────────────────

def test_linear_trend_ci_detects_rising_trend():
    x = list(range(10))
    y = [2 * i + 1 for i in x]
    est = linear_trend_ci(x, y)
    assert est.slope == pytest.approx(2.0, abs=0.01)
    assert est.ci_low > 0


def test_linear_trend_ci_flat_series_contains_zero():
    x = list(range(10))
    y = [5.0] * 10
    est = linear_trend_ci(x, y)
    assert est.slope == pytest.approx(0.0, abs=1e-9)


def test_linear_trend_ci_rejects_too_few_points():
    with pytest.raises(ValueError, match="at least 3 points"):
        linear_trend_ci([1, 2], [1, 2])
