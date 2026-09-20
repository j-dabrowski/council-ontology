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
class DifferenceEstimate:
    value: float
    ci_low: float
    ci_high: float
    method: str


def difference_in_proportions_ci(
    k1: int, n1: int, k2: int, n2: int, *, confidence: float = 0.95,
) -> DifferenceEstimate:
    """`p2/n2 - p1/n1` with a Wald (normal-approximation) CI — the standard,
    simple choice for a two-proportion difference; Newcombe's method is more
    accurate at small n but isn't implemented here. Used to compare two
    subgroups' rates directly (e.g. repeat vs. one-shot applicants) rather
    than the single-sample `proportion_ci()`. Raises `ValueError` on
    `n1 == 0` or `n2 == 0`.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError(f"cannot compute a difference-in-proportions CI with n1={n1}, n2={n2}")
    p1, p2 = k1 / n1, k2 / n2
    diff = p2 - p1
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = float(stats.norm.ppf(1 - (1 - confidence) / 2))
    margin = z * se
    return DifferenceEstimate(
        value=diff, ci_low=diff - margin, ci_high=diff + margin, method="wald",
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


# ── machinery for the 10 not-yet-migrated battery tests (Step 6 continued) ──
# Added when building claim counterparts for the remaining tests whose
# statistic isn't a proportion or a proportion difference: a median
# comparison (confidential_tender_size), a categorical/contingency test
# (confidential_topics), a pure concentration measure (tender_concentration),
# a chance-overlap test (procurement_incumbency), and a trend-over-time
# estimate (engagement). Two of the ten (single_source, reserve_trajectory)
# have no underlying data at all on this corpus, and one (sponsorship) has a
# query that emits hardcoded prose rather than a computed statistic — no
# amount of inference machinery closes those; not attempted here.

@dataclass(frozen=True)
class MedianEstimate:
    value: float
    ci_low: float
    ci_high: float
    method: str


def median_ci(
    values: Sequence[float], *, confidence: float = 0.95, n_resamples: int = 9999, seed: int | None = None,
) -> MedianEstimate:
    """Bootstrap CI for a single sample's median — no closed-form CI exists
    for a median the way Wilson's does for a proportion. Uses the `"basic"`
    bootstrap method, not scipy's default `"BCa"`: BCa's bias-correction/
    acceleration terms are unstable for the median specifically when a
    real-world dollar-value sample has many repeated/rounded values (found
    while building this — scipy emits a `DegenerateDataWarning` and can
    return a degenerate interval under `"BCa"` on exactly that kind of
    data). Raises `ValueError` on fewer than 2 observations (nothing to
    resample)."""
    if len(values) < 2:
        raise ValueError("median_ci needs at least 2 observations to bootstrap a CI")
    arr = np.asarray(values, dtype=float)
    result = stats.bootstrap(
        (arr,), np.median, confidence_level=confidence, n_resamples=n_resamples,
        random_state=seed, method="basic",
    )
    return MedianEstimate(
        value=float(np.median(arr)), ci_low=float(result.confidence_interval.low),
        ci_high=float(result.confidence_interval.high), method="bootstrap",
    )


def median_difference_ci(
    group_a: Sequence[float], group_b: Sequence[float], *,
    confidence: float = 0.95, n_resamples: int = 9999, seed: int | None = None,
) -> DifferenceEstimate:
    """Bootstrap CI for `median(group_b) - median(group_a)` (e.g. confidential
    vs. open tender values, `01-known-defects.md` D-25's median-ratio
    comparison) — reuses `DifferenceEstimate`'s shape from the two-proportion
    case since the fields are identical. Uses `"basic"`, same reasoning as
    `median_ci()`. Raises `ValueError` on fewer than 2 observations per
    group."""
    if len(group_a) < 2 or len(group_b) < 2:
        raise ValueError("median_difference_ci needs at least 2 observations per group")
    a, b = np.asarray(group_a, dtype=float), np.asarray(group_b, dtype=float)

    def _diff(x: np.ndarray, y: np.ndarray, axis: int) -> np.ndarray:
        return np.median(y, axis=axis) - np.median(x, axis=axis)

    result = stats.bootstrap(
        (a, b), _diff, confidence_level=confidence, n_resamples=n_resamples,
        random_state=seed, method="basic",
    )
    return DifferenceEstimate(
        value=float(np.median(b) - np.median(a)), ci_low=float(result.confidence_interval.low),
        ci_high=float(result.confidence_interval.high), method="bootstrap",
    )


@dataclass(frozen=True)
class MannWhitneyResult:
    statistic: float
    p_value: float


def mann_whitney_test(
    group_a: Sequence[float], group_b: Sequence[float], *, alternative: str = "two-sided",
) -> MannWhitneyResult:
    """A rank-based significance test for whether two samples' distributions
    differ — no normality assumption, unlike a t-test, which suits a
    dollar-value distribution's long tail better. Complements
    `median_difference_ci()`'s effect size with a p-value."""
    if len(group_a) == 0 or len(group_b) == 0:
        raise ValueError("mann_whitney_test needs at least one observation per group")
    result = stats.mannwhitneyu(group_a, group_b, alternative=alternative)
    return MannWhitneyResult(statistic=float(result.statistic), p_value=float(result.pvalue))


@dataclass(frozen=True)
class ChiSquareResult:
    statistic: float
    p_value: float
    dof: int


def chi_square_independence(table: Sequence[Sequence[int]]) -> ChiSquareResult:
    """Omnibus test of independence over a contingency table (e.g. theme x
    confidential/open, `confidential_topics`'s 6-theme breakdown) — whether
    closure rates differ across categories at all, before asking which
    category in particular differs (that's a per-category `proportion_ci()`
    call, not this function's job). Raises `ValueError` on a table smaller
    than 2x2."""
    arr = np.asarray(table, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
        raise ValueError("chi_square_independence needs at least a 2x2 table")
    result = stats.chi2_contingency(arr)
    return ChiSquareResult(statistic=float(result.statistic), p_value=float(result.pvalue), dof=int(result.dof))


def herfindahl_index(amounts: Sequence[float]) -> float:
    """Sum of squared market shares (0-1 scale: 1/n for n equal firms, 1.0
    for a single firm taking everything). Purely descriptive — concentration
    has no inherent good/bad direction, so this returns a bare float, not an
    object with a CI/method: no null hypothesis attaches to it the way one
    does to every other function in this module. Raises `ValueError` if the
    amounts sum to zero or less (nothing to take a share of)."""
    total = sum(amounts)
    if total <= 0:
        raise ValueError(f"herfindahl_index needs a positive total amount, got {total}")
    return sum((a / total) ** 2 for a in amounts)


@dataclass(frozen=True)
class OverlapResult:
    observed_overlap: int
    expected_overlap: float
    p_value_at_least_observed: float


def hypergeometric_overlap_test(
    population_size: int, group_a_size: int, group_b_size: int, observed_overlap: int,
) -> OverlapResult:
    """`P(overlap >= observed)` under a hypergeometric null: `group_a` and
    `group_b` are two subsets of a `population_size`-item population, each
    drawn as if independently at random — how likely is an overlap this
    large by chance alone (e.g. `procurement_incumbency`'s "is any firm both
    a top-10 repeat-winner and a top-10 dollar-recipient" check)? Raises
    `ValueError` on an invalid population/group size."""
    if population_size <= 0 or group_a_size > population_size or group_b_size > population_size:
        raise ValueError(
            f"invalid sizes for hypergeometric_overlap_test: population={population_size}, "
            f"group_a={group_a_size}, group_b={group_b_size}"
        )
    expected = group_a_size * group_b_size / population_size
    p_value = float(stats.hypergeom.sf(observed_overlap - 1, population_size, group_a_size, group_b_size))
    return OverlapResult(observed_overlap=observed_overlap, expected_overlap=expected, p_value_at_least_observed=p_value)


@dataclass(frozen=True)
class TrendEstimate:
    slope: float
    ci_low: float
    ci_high: float
    method: str


def linear_trend_ci(x: Sequence[float], y: Sequence[float], *, confidence: float = 0.95) -> TrendEstimate:
    """An OLS trend slope with a CI (e.g. `engagement`'s participation-count
    series over years) — the simplest honest way to ask "is this rising or
    falling" for a raw count series with no natural denominator to compute a
    proportion from. Raises `ValueError` on fewer than 3 points (a line
    through 2 points has no residual to estimate a CI from)."""
    if len(x) < 3:
        raise ValueError("linear_trend_ci needs at least 3 points to fit a trend with a CI")
    result = stats.linregress(x, y)
    dof = len(x) - 2
    t_crit = float(stats.t.ppf(1 - (1 - confidence) / 2, df=dof))
    margin = t_crit * result.stderr
    return TrendEstimate(
        slope=float(result.slope), ci_low=float(result.slope - margin), ci_high=float(result.slope + margin),
        method="ols",
    )
