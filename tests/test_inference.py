"""
Tests for src/analysis/inference.py (docs/uplift/migration/02-claim-layer.md
Step 4): CI, clustering, and permutation-test machinery.
"""
import pytest

from src.analysis.inference import (
    clustered_proportion,
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
