"""
CI/significance/clustering machinery (docs/uplift/migration/02-claim-layer.md
Step 4). This is G-02's fix: before this module, zero confidence-interval,
significance-test, or clustering-correction code existed anywhere in
`src/analysis/` (confirmed by an exhaustive grep for `confidence`,
`interval`, `wilson`, `p_value`, `scipy.stats`, run three times independently
across the audit that produced `docs/uplift/migration/02-claim-layer.md`).

Populates `Statistic.value/ci_low/ci_high/clustering_unit`
(`src/analysis/claims.py`) once wired into a test in Step 6 — nothing in
`src/analysis/tests.py` calls this module yet.

Honest limitation, stated once here rather than at every call site:
`clustered_proportion()` uses the simplest correct clustering correction —
collapse to one proportion per cluster, then a t-interval over those
cluster-level proportions — not a full sandwich/robust-SE estimator.
`statsmodels` would be needed for that; this project doesn't carry that
dependency, and the target schema only requires *a* clustering-aware
estimate distinct from the naive pooled one, not a specific method. The
`method` field on every returned object says exactly what was computed, so
a claim's `statistic.method` is never silently wrong about this.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class ProportionEstimate:
    value: float
    ci_low: float
    ci_high: float
    method: str
    k: int
    n: int


def proportion_ci(
    k: int,
    n: int,
    *,
    confidence: float = 0.95,
    method: str = "wilson",
) -> ProportionEstimate:
    """A proportion `k/n` with a confidence interval — L-01/L-02/L-03's
    prerequisite. `method` is one of scipy's `binomtest.proportion_ci`
    methods: `"wilson"` (default — the standard choice for a small-n
    council-level proportion) or `"exact"` (Clopper-Pearson, wider and more
    conservative). Raises `ValueError` on `n == 0` rather than returning a
    meaningless interval — there is no honest CI for zero observations.
    """
    if n <= 0:
        raise ValueError(f"cannot compute a proportion CI with n={n} observations")
    if not (0 <= k <= n):
        raise ValueError(f"k={k} must satisfy 0 <= k <= n={n}")
    result = stats.binomtest(k, n)
    ci = result.proportion_ci(confidence_level=confidence, method=method)
    return ProportionEstimate(
        value=k / n, ci_low=float(ci.low), ci_high=float(ci.high),
        method=method, k=k, n=n,
    )


@dataclass(frozen=True)
class ClusteredEstimate:
    value: float
    ci_low: float
    ci_high: float
    method: str
    clustering_unit: str
    n_clusters: int
    n_rows: int


def clustered_proportion(
    rows: Sequence[object],
    *,
    cluster_key: Callable[[object], Hashable],
    is_positive: Callable[[object], bool],
    clustering_unit: str,
    confidence: float = 0.95,
) -> ClusteredEstimate:
    """L-04: a rate whose denominator grain is finer than the inference
    unit (e.g. one row per vote, but the real independent unit is the
    councillor who cast many votes) must not be pooled as if every row were
    independent. Groups `rows` by `cluster_key`, computes each cluster's own
    proportion, then treats those cluster-level proportions as the sample —
    `value` is their mean, and the CI is a t-interval over them (df =
    n_clusters - 1), not the naive Wilson interval over the pooled row
    count. Needs at least 2 non-empty clusters; raises `ValueError`
    otherwise, since a between-cluster CI is not computable from one
    cluster.
    """
    clusters: dict[Hashable, list[bool]] = defaultdict(list)
    for row in rows:
        clusters[cluster_key(row)].append(bool(is_positive(row)))
    cluster_props = [sum(flags) / len(flags) for flags in clusters.values() if flags]
    n_clusters = len(cluster_props)
    if n_clusters < 2:
        raise ValueError(
            "clustered_proportion needs at least 2 non-empty clusters to estimate "
            f"a between-cluster CI, got {n_clusters}"
        )
    value = statistics.fmean(cluster_props)
    sd = statistics.stdev(cluster_props)
    se = sd / math.sqrt(n_clusters)
    t_crit = float(stats.t.ppf(1 - (1 - confidence) / 2, df=n_clusters - 1))
    margin = t_crit * se
    return ClusteredEstimate(
        value=value,
        ci_low=max(0.0, value - margin),
        ci_high=min(1.0, value + margin),
        method="cluster-mean t-interval",
        clustering_unit=clustering_unit,
        n_clusters=n_clusters,
        n_rows=len(rows),
    )


@dataclass(frozen=True)
class PermutationResult:
    observed_diff: float
    p_value: float
    n_resamples: int
    method: str = "permutation"


def permutation_test_difference(
    group_a: Sequence[float],
    group_b: Sequence[float],
    *,
    n_resamples: int = 9999,
    alternative: str = "two-sided",
    seed: int | None = None,
) -> PermutationResult:
    """A model-free significance test for a difference in means between two
    groups (e.g. the sponsorship-network case's ratio, `01-known-defects.md`
    G-12) — no distributional assumption, unlike a t-test. `seed` makes the
    resampling reproducible for a test's own regression suite; leave it
    `None` for a real run. Raises `ValueError` if either group is empty.
    """
    if len(group_a) == 0 or len(group_b) == 0:
        raise ValueError("permutation_test_difference needs at least one observation per group")

    def _mean_diff(x: np.ndarray, y: np.ndarray, axis: int) -> np.ndarray:
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    result = stats.permutation_test(
        (np.asarray(group_a, dtype=float), np.asarray(group_b, dtype=float)),
        _mean_diff,
        n_resamples=n_resamples,
        alternative=alternative,
        random_state=seed,
    )
    return PermutationResult(
        observed_diff=float(result.statistic),
        p_value=float(result.pvalue),
        n_resamples=n_resamples,
    )
