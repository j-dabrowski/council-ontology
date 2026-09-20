"""
The claim linter (docs/uplift/migration/02-claim-layer.md Step 5; target
spec docs/uplift/02-claim-layer.md "The linter"). Deterministic, no model.
18 rules (L-01..L-18), each a pure function over a `Claim`
(`src/analysis/claims.py`) plus an optional `LintContext` for the handful
of rules that need something beyond the claim itself (a replayed row count,
the set of all claims in a run, the jurisdiction config).

Grounded directly against the concrete defects in `docs/uplift/01-known-
defects.md` (D-01..D-39) rather than the abstract rule table alone, since
several rules are underspecified by the target YAML schema on their own —
notably L-01 ("excludes the null value"): D-10's worked example compares a
*post-period rate against a pre-period rate*, not against zero, so the
"null value" a critical grade's CI must exclude is the comparison's
reference point, not always 0.0. Where the schema has no field to carry
that reference value, this module accepts it via `LintContext.null_value`
and falls back to 0.0 (documented per-rule below) rather than silently
assuming every claim is a zero-null test.

`RULES` maps every rule id to its single-claim function, except L-06,
which is inherently cross-claim (`docs/uplift/02-claim-layer.md`: "All
claims sharing a population.definition must share denominator.n") and is
exposed separately as `check_l06_shared_denominator`. `lint_claim()` and
`lint_batch()` are the two entry points; Step 7 wires `lint_batch()` into
`council draft`.

Status model: `PASS` / `FAIL` are the two statuses the target schema means
by "failures are blocking." `NOT_APPLICABLE` covers a rule whose
precondition the claim doesn't meet (e.g. L-01 on a non-critical claim) —
vacuously satisfied, never blocking. `UNVERIFIABLE` is this module's own
addition: several rules (L-08, L-09's fallback, L-15, L-17, L-18) need
information no `_t_*` function populates yet (extraction_error, per-claim
provenance to a canonical id set, a rendered chart's actual series count).
Reporting UNVERIFIABLE instead of a fabricated PASS is this project's
established convention (honest incompleteness over false confidence);
Step 7 should NOT block a draft on UNVERIFIABLE, only on FAIL.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from src.analysis.claims import (
    COMPARISON_WITHIN_SUBJECT,
    CORRECTION_NONE,
    GRADE_CRITICAL,
    GRADE_NEUTRAL,
    GRADE_SUPPORTIVE,
    Claim,
    parse_grain,
)
from src.frameworks import primary_instruments
from src.invariant_gate import load_min_n

DEFAULT_NULL_VALUE = 0.0
DEFAULT_MIN_ACHIEVED_POWER = 0.8
# README: tuned (2024+) corpus quote completeness 98.1%, untuned (1995-2023)
# 81.1% — 0.90 sits between the two, closer to the tuned-era floor than a
# round number chosen without reference to real corpus numbers.
DEFAULT_EXTRACTION_PRECISION_THRESHOLD = 0.90
# A headline commonly rounds a percentage to the nearest whole number,
# which can be up to 0.5 percentage points off the underlying figure
# (e.g. 66.67% rendered as "67%") — 0.05 (found by exercising this rule
# against a real generated claim, src/analysis/tests.py's
# _t_recusal_overall_claim) rejected that legitimate rounding as a
# mismatch. 0.6 tolerates whole-number rounding on the percentage scale
# without going so loose it stops catching a genuinely wrong figure.
FIGURE_MATCH_TOLERANCE = 0.6

# (?<!\w) before the optional sign: a "-" directly preceded by a letter or
# digit is a hyphen inside a compound word ("top-10") or a range
# ("41-92%"), not a negative sign — found by running this rule against a
# real generated claim ("top-10 dollar-recipient" was misread as "-10").
# The optional (?:,\d{3})* group matches comma-grouped thousands ("4,993")
# as one token instead of splitting at the comma into "4" and "993" — same
# real-data discovery.
_NUMBER_RE = re.compile(r"(?<!\w)-?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?")
_CAUSAL_RE = re.compile(
    r"\b(causes?|drives?|moves?)\b|\bleans? toward\b|\bmakes?\b[^.]{0,40}\bmore likely\b",
    re.IGNORECASE,
)
_FLAT_RE = re.compile(r"\bflat\b|\bno difference\b|\bno effect\b", re.IGNORECASE)
_MONTH_RE = re.compile(
    r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|"
    r"sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b",
    re.IGNORECASE,
)
_FISCAL_KEYWORD_RE = re.compile(r"\bfiscal\b|\bfinancial year\b|\bFY\d|\bbudget year\b", re.IGNORECASE)


class LintStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class LintResult:
    rule_id: str
    status: LintStatus
    message: str


@dataclass(frozen=True)
class LintContext:
    """Everything a rule might need beyond the `Claim` itself. Every field
    defaults to empty/None so a rule can always be checked with zero
    context — it just reports `UNVERIFIABLE` honestly instead of guessing."""
    all_claims: Sequence[Claim] = ()
    null_value: float | None = None  # L-01: the comparison's reference point, if not 0.0
    replayed_denominator_n: int | None = None  # L-08: gold.replay_population_n()'s result
    canonical_entity_names: frozenset[str] | None = None  # L-17
    declared_category_count: int | None = None  # L-18
    rendered_series_count: int | None = None  # L-18
    extraction_precision_threshold: float = DEFAULT_EXTRACTION_PRECISION_THRESHOLD


def _narrative_text(claim: Claim) -> str:
    return f"{claim.narrative.headline} {claim.narrative.body}"


# ── L-01..L-05 ───────────────────────────────────────────────────────────

def check_l01(claim: Claim, ctx: LintContext) -> LintResult:
    """`grade == critical` requires a CI excluding the null value (D-10:
    post-period 66.7% on n=12, CI ~35-90%, contains the pre-period 87.1% —
    not distinguishable from the baseline it's being compared against).
    `ctx.null_value` supplies that baseline when the comparison isn't
    against zero; falls back to 0.0 when not given, which only exercises
    the D-10 shape correctly if the caller passes the real reference."""
    if claim.grade != GRADE_CRITICAL:
        return LintResult("L-01", LintStatus.NOT_APPLICABLE, "grade is not critical")
    s = claim.statistic
    if s.ci_low is None or s.ci_high is None:
        return LintResult("L-01", LintStatus.FAIL, "statistic.ci_low/ci_high not populated")
    null_value = ctx.null_value if ctx.null_value is not None else DEFAULT_NULL_VALUE
    if s.ci_low <= null_value <= s.ci_high:
        return LintResult(
            "L-01", LintStatus.FAIL,
            f"statistic CI [{s.ci_low}, {s.ci_high}] contains the null value {null_value} "
            "— not distinguishable from it",
        )
    return LintResult("L-01", LintStatus.PASS, "CI excludes the null value")


def check_l02(claim: Claim, ctx: LintContext) -> LintResult:
    """`grade == supportive` requires `achieved_power >= 0.8` (D-11: n=69,
    n=2, n=15 nulls graded Supportive — absence of evidence is not evidence
    of absence)."""
    if claim.grade != GRADE_SUPPORTIVE:
        return LintResult("L-02", LintStatus.NOT_APPLICABLE, "grade is not supportive")
    power = claim.power.achieved_power
    if power is None:
        return LintResult("L-02", LintStatus.FAIL, "power.achieved_power not populated")
    if power < DEFAULT_MIN_ACHIEVED_POWER:
        return LintResult(
            "L-02", LintStatus.FAIL,
            f"achieved_power={power} < {DEFAULT_MIN_ACHIEVED_POWER}",
        )
    return LintResult("L-02", LintStatus.PASS, "achieved_power meets threshold")


def _max_decimals_for_ci_width(ci_low: float, ci_high: float) -> int:
    """D-14's rule as a number: a CI half-width of X percentage points
    supports roughly log10(1/X) decimal digits on a 0-1 proportion. Same
    heuristic shape as the existing `_capped_pct()` (`tests.py`) — 0dp for
    a wide interval, more only once the interval is tight enough to
    justify it."""
    half_width = abs(ci_high - ci_low) / 2
    if half_width == 0:
        return 3
    if half_width >= 0.05:
        return 0
    if half_width >= 0.005:
        return 1
    return 2


def check_l03(claim: Claim, ctx: LintContext) -> LintResult:
    """Reported significant figures must not exceed what the CI width
    supports (D-14: "75.0%" on a ~7pp-wide CI; "100.0%" on n=1; "73.28%"
    vs "73.13%" implying a real difference the interval can't support)."""
    s = claim.statistic
    if s.ci_low is None or s.ci_high is None:
        return LintResult("L-03", LintStatus.UNVERIFIABLE, "statistic.ci_low/ci_high not populated")
    max_decimals = _max_decimals_for_ci_width(s.ci_low, s.ci_high)
    offenders = []
    for match in _NUMBER_RE.finditer(_narrative_text(claim)):
        token = match.group().rstrip("%")
        if "." in token and len(token.split(".")[1]) > max_decimals:
            offenders.append(match.group())
    if offenders:
        return LintResult(
            "L-03", LintStatus.FAIL,
            f"narrative reports {offenders} to more decimals than the CI width "
            f"supports (max {max_decimals}dp)",
        )
    return LintResult("L-03", LintStatus.PASS, "reported precision within CI-supported digits")


def check_l04(claim: Claim, ctx: LintContext) -> LintResult:
    """`clustering_unit` must be set wherever the population grain is finer
    than the true inference unit — heuristically, wherever the grain
    includes an entity dimension (councillor/firm/person) alongside at
    least one other dimension, meaning rows repeat per entity (D-13:
    12,839 vote-rows reported as if independent; the real n is 31
    councillors)."""
    entity_dims = {"councillor", "firm", "person"}
    dims = set(parse_grain(claim.population.grain))
    if not (dims & entity_dims) or len(dims) < 2:
        return LintResult("L-04", LintStatus.NOT_APPLICABLE, "grain is not finer than one row per entity")
    if claim.statistic.clustering_unit is None:
        return LintResult(
            "L-04", LintStatus.FAIL,
            f"grain {claim.population.grain!r} repeats per entity but clustering_unit is not set",
        )
    return LintResult("L-04", LintStatus.PASS, "clustering_unit is set for a finer-than-entity grain")


def check_l05(claim: Claim, ctx: LintContext) -> LintResult:
    """`names_individuals` requires, per named person: n >= MIN_N (reusing
    `src/invariant_gate.py`'s existing threshold rather than a second,
    unsynced one), a per-person CI, non-empty source_spans on the claim,
    and a right-of-reply field populated (`narrative.response` is this
    schema's closest equivalent — the target YAML has no separate
    right-of-reply field) (D-31: named individuals on an unconfirmed
    surname match, no chance baseline, no provenance)."""
    if not claim.names_individuals:
        return LintResult("L-05", LintStatus.NOT_APPLICABLE, "claim does not name individuals")
    min_n = load_min_n()
    problems = []
    for person in claim.individuals:
        if person.n_for_this_person < min_n:
            problems.append(f"{person.name}: n={person.n_for_this_person} < MIN_N={min_n}")
        if person.ci_low is None or person.ci_high is None:
            problems.append(f"{person.name}: missing per-person CI")
    if not claim.provenance.source_spans:
        problems.append("provenance.source_spans is empty")
    if not claim.narrative.response.strip():
        problems.append("narrative.response (right-of-reply field) is empty")
    if problems:
        return LintResult("L-05", LintStatus.FAIL, "; ".join(problems))
    return LintResult("L-05", LintStatus.PASS, "named-individual safeguards all present")


# ── L-06 (cross-claim) ───────────────────────────────────────────────────

def check_l06_shared_denominator(claims: Sequence[Claim]) -> dict[str, LintResult]:
    """All claims sharing a `population.definition` must share
    `denominator.n` (D-04: the same population described seven different
    ways producing seven different denominators, none declared on the
    panel face). Cross-claim by nature — not exposed via `RULES` /
    `lint_claim()`, called separately by `lint_batch()`. Keyed by
    `claim.id` rather than returned in input order, since results are
    naturally computed per population-definition group, not per input
    position."""
    by_definition: dict[str, list[Claim]] = {}
    for c in claims:
        by_definition.setdefault(c.population.definition, []).append(c)
    results: dict[str, LintResult] = {}
    for definition, group in by_definition.items():
        ns = {c.denominator.n for c in group}
        for c in group:
            if len(ns) > 1:
                results[c.id] = LintResult(
                    "L-06", LintStatus.FAIL,
                    f"population.definition {definition!r} shared by claims with "
                    f"denominator.n in {sorted(ns)}, not one shared value",
                )
            else:
                results[c.id] = LintResult(
                    "L-06", LintStatus.PASS, "denominator.n consistent for this population.definition"
                )
    return results


# ── L-07..L-10 ───────────────────────────────────────────────────────────

def check_l07(claim: Claim, ctx: LintContext) -> LintResult:
    """`comparison.reference_is_same_event == False` is blocking unless
    the reference group is explicitly described and surfaced as a caveat
    (D-12: the 83x ratio's two numerators were different events by
    construction, with nothing declaring that)."""
    if claim.comparison.reference_is_same_event:
        return LintResult("L-07", LintStatus.NOT_APPLICABLE, "comparison.reference_is_same_event is True")
    if not claim.comparison.reference_definition.strip():
        return LintResult("L-07", LintStatus.FAIL, "reference_is_same_event=False but reference_definition is empty")
    if not claim.narrative.caveats:
        return LintResult("L-07", LintStatus.FAIL, "reference_is_same_event=False but no caveat surfaces it")
    return LintResult("L-07", LintStatus.PASS, "non-same-event comparison is justified and surfaced")


def check_l08(claim: Claim, ctx: LintContext) -> LintResult:
    """`filter_chain` replayed against gold must reproduce `denominator.n`
    exactly (D-03/D-04). This module is pure and has no DB access — the
    caller must actually replay (`src/analysis/gold.py`'s
    `replay_population_n()`) and pass the result via
    `ctx.replayed_denominator_n`. Without it, this rule is honestly
    `UNVERIFIABLE`, not a silent pass — matches Step 5's own note that L-08
    can only be wired for real once a test's `steps` exist to replay
    (Step 6)."""
    if ctx.replayed_denominator_n is None:
        return LintResult("L-08", LintStatus.UNVERIFIABLE, "no replayed row count supplied via LintContext")
    if ctx.replayed_denominator_n != claim.denominator.n:
        return LintResult(
            "L-08", LintStatus.FAIL,
            f"replay produced n={ctx.replayed_denominator_n}, claim declares denominator.n={claim.denominator.n}",
        )
    return LintResult("L-08", LintStatus.PASS, "filter_chain replay reproduces denominator.n")


def check_l09(claim: Claim, ctx: LintContext) -> LintResult:
    """`framework_refs` must resolve against the jurisdiction config
    (D-28: Nolan/CIPFA cited for a WA council). Not stubbed — Phase 1
    already built `config/frameworks.json` / `src/frameworks.py`, ahead of
    this rule, so it resolves for real against `primary_instruments()`."""
    if not claim.framework_refs:
        return LintResult("L-09", LintStatus.NOT_APPLICABLE, "claim declares no framework_refs")
    known = set(primary_instruments().keys())
    if not known:
        return LintResult("L-09", LintStatus.UNVERIFIABLE, "config/frameworks.json has no primary_instruments")
    unresolved = [ref.instrument for ref in claim.framework_refs if ref.instrument not in known]
    if unresolved:
        return LintResult(
            "L-09", LintStatus.FAIL,
            f"framework_refs cite unresolved instrument(s) {unresolved} — known: {sorted(known)}",
        )
    return LintResult("L-09", LintStatus.PASS, "all framework_refs resolve against jurisdiction config")


def check_l10(claim: Claim, ctx: LintContext) -> LintResult:
    """`multiple_comparison.family_size > 1` requires a correction and a
    non-null `survives_correction` (D-15: ~1,000 sponsorship pairs, top 12
    published with no permutation-null check)."""
    mc = claim.statistic.multiple_comparison
    if mc.family_size <= 1:
        return LintResult("L-10", LintStatus.NOT_APPLICABLE, "family_size is 1")
    if mc.correction == CORRECTION_NONE:
        return LintResult("L-10", LintStatus.FAIL, f"family_size={mc.family_size} but correction is 'none'")
    if mc.survives_correction is None:
        return LintResult("L-10", LintStatus.FAIL, "survives_correction is null")
    return LintResult("L-10", LintStatus.PASS, "multiple-comparison correction applied and resolved")


# ── L-11..L-14 ───────────────────────────────────────────────────────────

def _known_figures(claim: Claim) -> list[float]:
    s, num, den = claim.statistic, claim.numerator, claim.denominator
    figures: list[float] = []
    for v in (s.value, s.ci_low, s.ci_high):
        if v is not None:
            figures.append(v)
            figures.append(v * 100)
    figures.extend([float(num.n), float(den.n)])
    if den.n:
        figures.append(num.n / den.n * 100)
    return figures


def check_l11(claim: Claim, ctx: LintContext) -> LintResult:
    """Every figure in `narrative.headline` must exist as a field in
    `statistic`/`numerator`/`denominator` — no headline-only numbers
    (D-22/D-24). Matches with a small tolerance since narrative text
    rounds (e.g. "83%" for a raw 0.8324)."""
    figures = _known_figures(claim)
    offenders = []
    for match in _NUMBER_RE.finditer(claim.narrative.headline):
        token = match.group().rstrip("%").replace(",", "")
        try:
            value = float(token)
        except ValueError:
            continue
        if not any(abs(value - f) <= FIGURE_MATCH_TOLERANCE for f in figures):
            offenders.append(match.group())
    if offenders:
        return LintResult(
            "L-11", LintStatus.FAIL,
            f"headline figures {offenders} do not match any statistic/numerator/denominator field",
        )
    return LintResult("L-11", LintStatus.PASS, "all headline figures trace to a structured field")


_L12_STOPWORDS = frozenset({"about", "these", "those", "their", "where", "which", "there"})


def _content_words(text: str) -> set[str]:
    """Words of at least 5 letters, lowercased, excluding a small stopword
    list — used by L-12 as a paraphrase-tolerant proxy for "same topic,"
    rather than requiring the exact definition string or its first word
    verbatim (that stricter check produced false positives against
    naturally-worded prose that legitimately paraphrases the denominator —
    found by running this rule against claims built from real data,
    src/analysis/tests.py's Step 6 migration)."""
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in _L12_STOPWORDS}


def _shares_content_word(a_words: set[str], b_words: set[str]) -> bool:
    """True if any word in `a_words` is a prefix of, or shares a prefix
    with, any word in `b_words` — a cheap stand-in for stemming that
    tolerates plurals and common suffixes (award/awards, declare/declared)
    without pulling in a real stemmer dependency."""
    return any(w1 == w2 or w1.startswith(w2) or w2.startswith(w1) for w1 in a_words for w2 in b_words)


def check_l12(claim: Claim, ctx: LintContext) -> LintResult:
    """`narrative.headline` and `narrative.body` must reference the same
    denominator definition (D-22: headline quotes the blended rate, the
    panel's own footnote disowns it for a different, must-leave-only
    denominator). Heuristic: at least one significant (>=5-letter) word
    from the denominator's definition must appear (allowing plural/suffix
    variation) in both headline and body — tolerant of paraphrasing, but
    still catches a genuinely different denominator being smuggled in
    (D-22/D-24's actual shape: "blended" vs "must-leave" share no such
    word)."""
    headline, body = claim.narrative.headline.strip(), claim.narrative.body.strip()
    if not headline or not body:
        return LintResult("L-12", LintStatus.NOT_APPLICABLE, "headline or body not yet populated")
    def_words = _content_words(claim.denominator.definition)
    if not def_words:
        return LintResult("L-12", LintStatus.UNVERIFIABLE, "denominator.definition has no matchable content words")
    in_headline = _shares_content_word(def_words, _content_words(headline))
    in_body = _shares_content_word(def_words, _content_words(body))
    if not (in_headline and in_body):
        return LintResult(
            "L-12", LintStatus.FAIL,
            f"denominator.definition {claim.denominator.definition!r} not referenced consistently "
            "in both headline and body",
        )
    return LintResult("L-12", LintStatus.PASS, "headline and body reference the same denominator")


def check_l13(claim: Claim, ctx: LintContext) -> LintResult:
    """"flat"/"no difference"/"no effect" require a CI containing zero
    *and* adequate power (D-18: 82/72/84/83 called "flat" despite a 12pp
    range and no monotonic-trend check)."""
    if not _FLAT_RE.search(_narrative_text(claim)):
        return LintResult("L-13", LintStatus.NOT_APPLICABLE, "no flat/no-difference wording present")
    s, power = claim.statistic, claim.power.achieved_power
    if s.ci_low is None or s.ci_high is None:
        return LintResult("L-13", LintStatus.FAIL, "flat/no-difference wording used but no CI populated")
    ci_contains_zero = s.ci_low <= 0 <= s.ci_high
    adequate_power = power is not None and power >= DEFAULT_MIN_ACHIEVED_POWER
    if not (ci_contains_zero and adequate_power):
        return LintResult(
            "L-13", LintStatus.FAIL,
            f"flat/no-difference wording requires CI containing zero (got [{s.ci_low}, {s.ci_high}]) "
            f"and achieved_power >= {DEFAULT_MIN_ACHIEVED_POWER} (got {power})",
        )
    return LintResult("L-13", LintStatus.PASS, "flat/no-difference wording is statistically supported")


def check_l14(claim: Claim, ctx: LintContext) -> LintResult:
    """Causal verbs are blocked unless `comparison.type == within_subject`
    or a design justification is on record (D-19: "a declared-interest
    vote leans toward letting the matter through" on an observational,
    between-subject comparison). This schema has no dedicated "design
    justification" field, so a populated `grade_justification` plus at
    least one `narrative.caveats` entry is treated as that justification —
    an interpretation, not a literal schema field, documented here rather
    than left implicit."""
    if not _CAUSAL_RE.search(_narrative_text(claim)):
        return LintResult("L-14", LintStatus.NOT_APPLICABLE, "no causal verb present")
    if claim.comparison.type == COMPARISON_WITHIN_SUBJECT:
        return LintResult("L-14", LintStatus.PASS, "causal language used on a within_subject comparison")
    justified = bool(claim.grade_justification.strip()) and bool(claim.narrative.caveats)
    if not justified:
        return LintResult(
            "L-14", LintStatus.FAIL,
            "causal verb used on a non-within_subject comparison with no design justification "
            "(grade_justification + a caveat)",
        )
    return LintResult("L-14", LintStatus.PASS, "causal language used with a recorded design justification")


# ── L-15..L-18 ───────────────────────────────────────────────────────────

def check_l15(claim: Claim, ctx: LintContext) -> LintResult:
    """A claim whose era-stratum extraction precision is below threshold
    cannot be graded above `neutral` (D-33: no accuracy statement at all;
    every named adverse finding is downstream of extraction quality).
    `UNVERIFIABLE` when `extraction_error.fields` is empty — true for
    every claim today, since nothing populates it until `05-verification.md`
    lands (G-08)."""
    fields = claim.extraction_error.fields
    if not fields:
        return LintResult("L-15", LintStatus.UNVERIFIABLE, "extraction_error.fields is empty")
    worst = min(f.precision for f in fields)
    if worst < ctx.extraction_precision_threshold and claim.grade != GRADE_NEUTRAL:
        return LintResult(
            "L-15", LintStatus.FAIL,
            f"era-stratum precision {worst} < {ctx.extraction_precision_threshold} but grade={claim.grade!r}, not neutral",
        )
    return LintResult("L-15", LintStatus.PASS, "grade consistent with era-stratum extraction precision")


def check_l16(claim: Claim, ctx: LintContext) -> LintResult:
    """Fiscal-period claims must reference the jurisdiction's FY boundary
    from config, never a literal month (D-01: a January-anchored panel on
    a council whose financial year runs July-June). Detects a
    fiscal-period claim by keyword in `population.definition`/
    `filter_chain`/narrative, then fails if a literal month name appears
    anywhere in that same text without also citing config."""
    haystack_parts = [claim.population.definition, *claim.population.filter_chain, _narrative_text(claim)]
    haystack = " ".join(haystack_parts)
    if not _FISCAL_KEYWORD_RE.search(haystack):
        return LintResult("L-16", LintStatus.NOT_APPLICABLE, "not a fiscal-period claim")
    cites_config = "config" in haystack.lower()
    if _MONTH_RE.search(haystack) and not cites_config:
        return LintResult(
            "L-16", LintStatus.FAIL,
            "fiscal-period claim names a literal month with no reference to the FY-boundary config",
        )
    return LintResult("L-16", LintStatus.PASS, "fiscal-period claim references config, not a literal month")


def check_l17(claim: Claim, ctx: LintContext) -> LintResult:
    """Entity names must resolve to a canonical id in the silver entity
    tables (D-05/D-06/D-07: two unsynced contractor normalisers, a bucket
    ranked among named firms, "Carr" appearing as two unresolved entities).
    Checked against `claim.individuals[].name` — the only entity-name
    field this schema exposes. `UNVERIFIABLE` without
    `ctx.canonical_entity_names`, since no shared silver-table id registry
    exists to check against yet (G-10)."""
    if not claim.names_individuals:
        return LintResult("L-17", LintStatus.NOT_APPLICABLE, "claim does not name individuals")
    if ctx.canonical_entity_names is None:
        return LintResult("L-17", LintStatus.UNVERIFIABLE, "no canonical entity registry supplied via LintContext")
    unresolved = [p.name for p in claim.individuals if p.name not in ctx.canonical_entity_names]
    if unresolved:
        return LintResult("L-17", LintStatus.FAIL, f"names {unresolved} do not resolve to a canonical entity id")
    return LintResult("L-17", LintStatus.PASS, "all named individuals resolve to a canonical entity id")


def check_l18(claim: Claim, ctx: LintContext) -> LintResult:
    """Rendered chart series count must equal declared category count
    (D-02: a twelve-month chart rendering eleven values). Needs both
    counts from the caller — a `Claim` alone doesn't carry "how many bars
    did the frontend actually draw"; `UNVERIFIABLE` without them."""
    if ctx.declared_category_count is None or ctx.rendered_series_count is None:
        return LintResult("L-18", LintStatus.UNVERIFIABLE, "declared_category_count/rendered_series_count not supplied")
    if ctx.declared_category_count != ctx.rendered_series_count:
        return LintResult(
            "L-18", LintStatus.FAIL,
            f"declared {ctx.declared_category_count} categories, rendered {ctx.rendered_series_count} series",
        )
    return LintResult("L-18", LintStatus.PASS, "rendered series count matches declared category count")


RULES: dict[str, Callable[[Claim, LintContext], LintResult]] = {
    "L-01": check_l01, "L-02": check_l02, "L-03": check_l03, "L-04": check_l04,
    "L-05": check_l05, "L-07": check_l07, "L-08": check_l08, "L-09": check_l09,
    "L-10": check_l10, "L-11": check_l11, "L-12": check_l12, "L-13": check_l13,
    "L-14": check_l14, "L-15": check_l15, "L-16": check_l16, "L-17": check_l17,
    "L-18": check_l18,
}


def lint_claim(claim: Claim, ctx: LintContext | None = None) -> list[LintResult]:
    """Run every single-claim rule (all but L-06) against one claim."""
    ctx = ctx or LintContext()
    return [rule(claim, ctx) for rule in RULES.values()]


def lint_batch(claims: Sequence[Claim], ctx: LintContext | None = None) -> dict[str, list[LintResult]]:
    """Run the full 18-rule linter across a run's claims: every
    single-claim rule per claim, plus L-06 across the whole set. Keyed by
    `claim.id`. Step 7 blocks a draft on any `FAIL` in here, and only on
    `FAIL` — `UNVERIFIABLE`/`NOT_APPLICABLE` are not blocking."""
    ctx = ctx or LintContext(all_claims=tuple(claims))
    results: dict[str, list[LintResult]] = {c.id: lint_claim(c, ctx) for c in claims}
    for claim_id, l06_result in check_l06_shared_denominator(claims).items():
        results[claim_id].append(l06_result)
    return results


def has_blocking_failure(results: dict[str, list[LintResult]]) -> bool:
    return any(r.status == LintStatus.FAIL for claim_results in results.values() for r in claim_results)
