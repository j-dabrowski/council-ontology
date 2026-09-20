"""
The claim object (docs/uplift/migration/02-claim-layer.md Step 1; target
schema docs/uplift/02-claim-layer.md).

Mirrors the target YAML field-for-field, including placeholder sub-objects
for sections no current generator populates yet (`power`, `extraction_error`,
`confounds`, `provenance.query_hash`/`gold_table_versions`) — per that
file's own "done when": the schema exists as an importable Python type with
every field from the target YAML present, even where nothing populates it
yet.

`TestResult` (`src/analysis/tests.py`) is the existing analogue this sits
alongside additively — nothing here replaces it, and no `_t_*` generator
emits a `Claim` yet. That wiring is Step 6, one test at a time, gated on
Steps 2-5 (gold tables, population/filter-chain, CI/power machinery, the
linter) existing first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── grain dimensions ────────────────────────────────────────────────────────
# The known dimension names a `population.grain` tuple may be built from —
# 02-claim-layer.md's design notes: "grain is mandatory and free-text is
# not acceptable — validate it parses as a tuple of known dimension names."
# Sourced from the 7 gold-table grains that same file declares (Step 2's
# `src/analysis/gold.py`), plus "firm"/"person" for claims whose grain is a
# derived aggregate rather than a gold-table row itself.
GRAIN_DIMENSIONS = frozenset({
    "meeting", "item", "councillor", "interest_type", "award",
    "application", "question", "body", "term", "firm", "person",
})


def parse_grain(grain: str) -> tuple[str, ...]:
    """Parse `"(meeting, item, councillor)"` into `("meeting", "item",
    "councillor")`. Raises `ValueError` if any dimension isn't a known
    name — this is the mandatory validation the target schema requires;
    a `population.grain` that doesn't parse is a build-time error, not a
    linter finding, because nothing downstream can reason about an
    unparseable grain at all.
    """
    inner = grain.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    dims = tuple(d.strip() for d in inner.split(",") if d.strip())
    if not dims:
        raise ValueError(f"grain must name at least one dimension, got {grain!r}")
    unknown = [d for d in dims if d not in GRAIN_DIMENSIONS]
    if unknown:
        raise ValueError(
            f"grain {grain!r} names unknown dimension(s) {unknown!r}; "
            f"known dimensions are {sorted(GRAIN_DIMENSIONS)}"
        )
    return dims


@dataclass(frozen=True)
class FrameworkRef:
    """One `{instrument, section}` citation. `instrument` is a key into
    `config/frameworks.json`'s `primary_instruments` (`src/frameworks.py`)
    — resolving it against that config is L-09, stubbed until this file's
    Step 5 (04-jurisdiction.md already ships the config; the resolve-check
    itself is new)."""
    instrument: str
    section: str


@dataclass(frozen=True)
class Exclusion:
    rule: str
    n_excluded: int
    reason: str


@dataclass(frozen=True)
class Population:
    """`population.grain`/`definition`/`filter_chain`/`exclusions` —
    G-03's object. `filter_chain` must be sufficient to reproduce
    `denominator.n` by replay (L-08); that replay is implemented in
    `src/analysis/gold.py` (`build_population()`/`replay_population_n()`,
    Step 3), not here — this stays a plain data object so a `Claim` remains
    serializable per "regeneration semantics" (docs/uplift/02-claim-layer.md)."""
    grain: str
    definition: str
    base_table: str
    filter_chain: tuple[str, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()

    def __post_init__(self) -> None:
        parse_grain(self.grain)


@dataclass(frozen=True)
class NumeratorDenominator:
    definition: str
    n: int


COMPARISON_WITHIN_SUBJECT = "within_subject"
COMPARISON_BETWEEN_SUBJECT = "between_subject"
COMPARISON_TEMPORAL = "temporal"
COMPARISON_NONE = "none"
_COMPARISON_TYPES = frozenset({
    COMPARISON_WITHIN_SUBJECT, COMPARISON_BETWEEN_SUBJECT, COMPARISON_TEMPORAL, COMPARISON_NONE,
})


@dataclass(frozen=True)
class Comparison:
    """`reference_is_same_event=False` must be flagged (L-07) — G-04's
    field; this is what the invalid 83x ratio and the unrestated win-rate
    baseline both were instances of a comparison nothing required to be
    declared."""
    type: str = COMPARISON_NONE
    reference_definition: str = ""
    reference_is_same_event: bool = True

    def __post_init__(self) -> None:
        if self.type not in _COMPARISON_TYPES:
            raise ValueError(
                f"comparison.type must be one of {sorted(_COMPARISON_TYPES)}, got {self.type!r}"
            )


CORRECTION_NONE = "none"
CORRECTION_BONFERRONI = "bonferroni"
CORRECTION_BH = "bh"
CORRECTION_PERMUTATION = "permutation"
_CORRECTIONS = frozenset({
    CORRECTION_NONE, CORRECTION_BONFERRONI, CORRECTION_BH, CORRECTION_PERMUTATION,
})


@dataclass(frozen=True)
class MultipleComparison:
    """`family_size > 1` requires a correction and a non-null
    `survives_correction` (L-10) — fed by the hypothesis registry (Step 8),
    not computed here."""
    family_size: int = 1
    correction: str = CORRECTION_NONE
    survives_correction: bool | None = None

    def __post_init__(self) -> None:
        if self.correction not in _CORRECTIONS:
            raise ValueError(
                f"multiple_comparison.correction must be one of {sorted(_CORRECTIONS)}, "
                f"got {self.correction!r}"
            )


@dataclass(frozen=True)
class Statistic:
    """The single largest gap the migration plan names: no CI, clustering,
    or multiple-comparison machinery exists anywhere in `src/analysis/`
    today (G-02). `value`/`ci_low`/`ci_high` populated by
    `src/analysis/inference.py` (Step 4), not here."""
    value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    method: str = ""
    clustering_unit: str | None = None  # "councillor" | "meeting" | "item" | None
    multiple_comparison: MultipleComparison = field(default_factory=MultipleComparison)


@dataclass(frozen=True)
class Power:
    mde: float | None = None
    achieved_power: float | None = None


@dataclass(frozen=True)
class ExtractionErrorField:
    field: str
    era: str
    precision: float
    recall_floor: float


@dataclass(frozen=True)
class ExtractionError:
    """G-08: `/method`'s `_build_validation()` already computes
    corpus-wide quote-completeness/paraphrase-rate but not broken down by
    era, and no `_t_*` function reads it. This field is where a per-era
    breakdown would land once computed; nothing populates it yet."""
    fields: tuple[ExtractionErrorField, ...] = ()
    source: str = ""


@dataclass(frozen=True)
class Confounds:
    addressed: tuple[tuple[str, str], ...] = ()  # (name, how)
    unaddressed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provenance:
    """Source-span provenance is genuinely strong already
    (`src/analysis/evidence.py`'s `resolve_evidence()`); `query_hash` and
    `gold_table_versions` have no current equivalent — there is no
    migration framework or gold-table versioning to draw them from yet."""
    source_spans: tuple[str, ...] = ()
    query_hash: str = ""
    gold_table_versions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Individual:
    name: str
    n_for_this_person: int
    ci_low: float | None = None
    ci_high: float | None = None


GRADE_CRITICAL = "critical"
GRADE_CONCERN = "concern"
GRADE_NEUTRAL = "neutral"
GRADE_SUPPORTIVE = "supportive"
_GRADES = frozenset({GRADE_CRITICAL, GRADE_CONCERN, GRADE_NEUTRAL, GRADE_SUPPORTIVE})


@dataclass(frozen=True)
class Narrative:
    """The only place the builder may write prose, generated from the
    structured fields above rather than authored alongside them.
    `caveats` render on the panel face — not a footnote the headline may
    contradict (G-06)."""
    headline: str = ""
    body: str = ""
    objection: str = ""
    response: str = ""
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True)
class Claim:
    """One structured claim object. `id` is stable and survives
    regeneration (the `TestResult.test_id` analogue). `population`,
    `numerator`, and `denominator` are mandatory — a claim with no
    declared population is exactly G-01's defect restated as a
    constructor call that would fail. Every other section defaults to an
    empty placeholder so the type is fully constructible today even
    though nothing currently populates `power`/`extraction_error`/
    `confounds`/most of `provenance`.
    """
    id: str
    hypothesis: str
    population: Population
    numerator: NumeratorDenominator
    denominator: NumeratorDenominator
    grade: str
    grade_justification: str

    hypothesis_registry_id: str = ""
    framework_refs: tuple[FrameworkRef, ...] = ()
    comparison: Comparison = field(default_factory=Comparison)
    statistic: Statistic = field(default_factory=Statistic)
    power: Power = field(default_factory=Power)
    extraction_error: ExtractionError = field(default_factory=ExtractionError)
    confounds: Confounds = field(default_factory=Confounds)
    provenance: Provenance = field(default_factory=Provenance)
    names_individuals: bool = False
    individuals: tuple[Individual, ...] = ()
    narrative: Narrative = field(default_factory=Narrative)

    def __post_init__(self) -> None:
        if self.grade not in _GRADES:
            raise ValueError(f"grade must be one of {sorted(_GRADES)}, got {self.grade!r}")
        if self.names_individuals and not self.individuals:
            raise ValueError("names_individuals=True requires at least one entry in individuals")
        if not self.names_individuals and self.individuals:
            raise ValueError("individuals is non-empty but names_individuals=False")
