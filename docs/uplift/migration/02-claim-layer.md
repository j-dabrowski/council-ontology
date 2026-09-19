# The Claim Layer — Migration Plan

Traces the target claim-object architecture in `docs/uplift/02-claim-layer.md`
against the current codebase. Per that file's own "Investigation prompts for
the receiving agent," most of the answers were already established in
`00-codebase-map.md` §4 (analysis layer) and `01-known-defects.md`'s
per-defect gaps — this file synthesizes those into the claim-layer design
gap rather than re-deriving them. Where a linter rule (L-01..L-18) maps
directly onto a defect already gapped in `01-known-defects.md`, that gap
(G-xx) is cited rather than restated.

**Framing note.** This category is explicitly the load-bearing one: 15 of
`01-known-defects.md`'s 39 defects (see the linter table below) exist
*because* no seam currently separates population definition, statistic,
grade, and narrative. Building the claim object doesn't just close its own
target-state items — it is the mechanism that makes most of `01`'s gaps
mechanically unshippable going forward, per `02-claim-layer.md`'s own
framing ("This is where most of `01-known-defects.md` becomes mechanically
impossible to reship").

---

## Current state inventory

### Claim schema, by section

| Target field group | Current equivalent | Path | Status | Notes |
|---|---|---|---|---|
| `id`, `hypothesis` | `TestResult.test_id`, `TestResult.question` | `src/analysis/tests.py:107-135` (dataclass fields) | PARTIAL | `test_id` is stable and unique; `question` is overwritten post-hoc from `config/test_registry.json`'s `question_technical` (`tests.py:2320-2321`) — the hypothesis as *originally posed* (pre-registered) isn't the same object as the question rendered, and there's no `hypothesis_registry_id` link at all |
| `hypothesis_registry_id` + hypothesis registry | `docs/investigator/INVESTIGATIONS.md` (3,068 lines, hand-maintained markdown) | — | PARTIAL | Already does the *discipline* — records every hypothesis including nulls that never became panels (e.g. entries [3]/[4]/[5]: weak/minor findings kept, not deleted) — but as unstructured prose with no machine-readable `id`/`pre_registered_at`/`outcome` fields, nothing links an entry to a `claim_id`, and nothing feeds a `family_size` count into any multiple-comparison correction |
| `framework_refs` | Hardcoded string literals, 3 unsynced copies (`config/test_registry.json`'s `principles`, `tests.py`'s `principle=` fields, `OverviewPanel.tsx:38-80`) | see `01-known-defects.md` G-28 | WRONG | No structured `{instrument, section}` object anywhere; framework identity is prose, not data |
| `population` (grain/definition/base_table/filter_chain/exclusions) | None — every `_t_*` function writes its own ad hoc SQLAlchemy filter chain | `src/analysis/tests.py` (29 functions), `src/analysis/queries.py` (4,254 lines) | MISSING | This is `01-known-defects.md` G-04's exact finding, restated at the architecture level: no population object exists to fill this field from |
| `numerator`/`denominator` | Present as raw `n`, `count`, etc. local variables inside each function, never as a structured, self-describing object | `tests.py` (throughout) | PARTIAL | The numbers exist; the definitions attached to them exist only as prose in headline/verdict strings, not as a separately-inspectable field |
| `comparison` (type/reference_definition/reference_is_same_event) | No such field or check anywhere | — | MISSING | This is exactly `01-known-defects.md` G-12 (the invalid 83× ratio) and G-16 (win-rate baseline never restated) — both are instances of an unlabelled `comparison` |
| `statistic` (value/ci_low/ci_high/method/clustering_unit/multiple_comparison) | `TestResult.n` only; confirmed by exhaustive grep (`00-codebase-map.md`, `01-known-defects.md` statistical-defects trace) that **zero** confidence-interval, significance-test, or clustering-correction machinery exists anywhere in `src/analysis/` | `tests.py`, `queries.py` | MISSING | The single largest gap in the whole file — see G-04 below |
| `power` (mde/achieved_power) | None | — | MISSING | No power calculation exists anywhere in the codebase |
| `extraction_error` (per-field/era precision/recall) | `/method`'s `_build_validation()` computes corpus-wide `quote_completeness`/`paraphrase_rate`/`coverage_ratio` (`src/analysis/method.py:368-463`) but **not broken down by era**, and **never read by any `_t_*` function** — no claim's grade is ever capped by extraction confidence | `src/analysis/method.py` | PARTIAL | The raw numbers exist and are public (`01-known-defects.md` G-33); the field this schema wants (per-claim, per-era, feeding a grade cap) doesn't |
| `confounds` (addressed/unaddressed) | Ad hoc, inconsistent: some functions self-declare a limitation in a code comment never surfaced to the reader (e.g. `divergence.py:17-19`'s amendment-blindness note); most don't | `src/analysis/divergence.py`, `tests.py` | PARTIAL | See `01-known-defects.md` G-25; no structured field exists, only scattered prose, present in some functions and absent in others |
| `provenance` (source_spans/query_hash/gold_table_versions) | `ExtractionEvidence` + `src/analysis/evidence.py`'s `resolve_evidence()` is a close analogue of `source_spans` (quote + char_offset + page, resolved at request time — `00-codebase-map.md` §2); no `query_hash` or table-versioning concept exists anywhere (`src/storage/database.py` has no migration framework — confirmed by its own code comment, "there is no migration framework here") | `src/analysis/evidence.py`, `src/models/ontology.py` | PARTIAL | Source-span provenance is genuinely strong (98%+ evidence coverage per README); the reproducibility half (hash the query, version the gold tables) doesn't exist because there's no gold layer to version |
| `names_individuals` + `individuals[]` | `TestResult.unit_of_analysis`, `TestResult.named_entities` (`tests.py:107-135`) | `src/invariant_gate.py` | PARTIAL | The boolean-equivalent and the name list exist and are enforced by the S7 gate; the per-person `n_for_this_person`/`ci_low`/`ci_high` breakdown does not — MIN_N is a single threshold on the whole claim, not per individual |
| `grade` + `grade_justification` | `TestResult.valence`/`TestResult.grade`, decided inline by a hardcoded Python ternary in the same function that computes the number (`tests.py`, confirmed for every function read in `01-known-defects.md`'s statistical-defects trace) | `tests.py` (29 functions) | WRONG | A grade is decided, but by an ungoverned per-function threshold literal, not by a rule any linter could check against a stated justification field |
| `narrative` (headline/body/objection/response/caveats) | `TestResult.headline`/`verdict`, written as f-strings in the *same* function as the grade and the number — confirmed the same code path, no serialization boundary (`00-codebase-map.md` §4) | `tests.py` | WRONG | This satisfies the target's "generated from the structured fields" requirement accidentally (same function, same locals) but has no `caveats` field that must render on the panel face — see G-06 below (D-22/D-24's headline/footnote contradiction) |

### The linter (L-01 through L-18)

No deterministic claim-linter exists in any form — confirmed by the same
statistics/CI grep used throughout `01-known-defects.md` (zero hits for
`confidence`, `interval`, `wilson`, `p_value`, `scipy.stats`, etc.,
anywhere in `src/analysis/`). Every rule below is **MISSING** as a
mechanism; the "Kills" column already shows which defect it would have
caught, all already gapped in `01-known-defects.md`:

| ID | Rule | Current state | Kills (see `01-known-defects.md`) |
|---|---|---|---|
| L-01 | Critical requires CI excluding null | No CI computed anywhere | G-10 |
| L-02 | Supportive requires power ≥ 0.8 | No power computed anywhere | G-11 |
| L-03 | Precision ≤ CI width | No CI to check against | G-14 |
| L-04 | Clustering required when grain is finer than inference unit | No clustering unit tracked | G-13 |
| L-05 | Named claims require per-person n/CI/spans/reply field | S7 gate checks MIN_N and name-freedom at the whole-claim level only, not per-person | G-31 (partial overlap) |
| L-06 | Shared population definition ⇒ shared denominator n | No population definition object exists to compare | G-04 |
| L-07 | Non-same-event comparison must be flagged | No `comparison` field exists | G-12 |
| L-08 | filter_chain replay must reproduce denominator.n | No filter_chain object exists | G-03, G-04 |
| L-09 | framework_refs must resolve against jurisdiction config | No structured framework_refs field; see `04-jurisdiction.md` | G-28 |
| L-10 | family_size > 1 requires correction | No hypothesis-family tracking wired to any statistic | G-15 |
| L-11 | Every headline figure must exist in statistic/numerator/denominator | No such check; headline strings are hand-written prose | G-22, G-24 |
| L-12 | Headline and body share a denominator definition | No such check | G-22, G-24 |
| L-13 | "flat"/"no difference" requires CI-contains-zero + power | No such check | G-18 |
| L-14 | Causal verbs blocked outside within-subject comparisons | No such check; confirmed causal language ships from both `tests.py` prose and, worse, frontend component source the gate never scans | G-19 |
| L-15 | Grade capped by era-stratum extraction precision | Extraction precision is computed (`/method`) but never read by any grading function | G-33 (adjacent — `/method` has the numbers, no claim reads them) |
| L-16 | Fiscal-period claims reference config FY boundary | Calendar-month literal hardcoded instead | G-01 |
| L-17 | Entity names resolve to a canonical silver-table id | Two independent, unsynced councillor-name normalisers (`src/extraction/extractor.py:675`, `scripts/dedup_councillors.py:227`); one contractor normaliser correctly reused in one place, bypassed in another (`00-codebase-map.md` §7, `01-known-defects.md` G-05) | G-05, G-06, G-07 |
| L-18 | Rendered series count = declared category count | No such check; the one instance flagged (D-02) is unverified against current data, not confirmed reproducible | G-02 |

### Hypothesis registry

Covered above under the schema table — `docs/investigator/INVESTIGATIONS.md`
is a real, disciplined practice (a genuine [1]-through-[N] numbered log
including kept null results) that satisfies the *spirit* of the target's
purposes 2 and 3, but none of the *mechanism*: no stable machine-readable
id, no `pre_registered_at` timestamp, no link to `claim_id`, and critically,
its entries are never counted anywhere to populate any claim's
`multiple_comparison.family_size`. Status: **PARTIAL**.

### Gold table grain declarations

| Target gold table | Current equivalent | Status | Notes |
|---|---|---|---|
| `vote_fact` (meeting, item, councillor) | `votes` table (`src/models/ontology.py`), grain enforced by `uq_vote` unique constraint on `(motion_id, councillor_id)` — genuinely clean per `00-codebase-map.md` §3 | PARTIAL | The grain is accidentally already correct (a real unique constraint exists) but is not *declared* anywhere as a fact-table contract, and ABSENT is not sub-typed (recusal/non-attendance/unknown) — that's exactly `01-known-defects.md` G-09/G-12 |
| `declaration_fact` (meeting, item, councillor, interest_type) | `interest_declarations` table — no unique constraint confirmed on this tuple, and no `s5_68_permission_granted` flag exists anywhere (`01-known-defects.md` G-29) | MISSING | Both the grain declaration and the s5.68 flag are absent |
| `tender_fact` (meeting, award) | `tenders` table — `awarded_to` is unnormalised free text with no canonical-contractor-id column, no `confidential`/`value_recorded` flags, and (per `01-known-defects.md` G-06) no multi-recipient handling | PARTIAL | The table exists at roughly the right grain; every derived attribute the target wants is computed ad hoc at query time instead of stored |
| `application_fact` (application) | `planning_applications` table — no canonical applicant id, no `value_recorded` flag (though `_t_big_dollar_leniency` self-declares this filter in its `era` field, per G-17) | PARTIAL | Grain is clean (one row per application); the declared attributes aren't columns, they're per-query filter logic |
| `question_fact` (meeting, question) | `public_questions` table — no `answered`/`deferred`/`unknown` status column found in `ontology.py` | MISSING (attribute); PARTIAL (table) | — |
| `membership_fact` (councillor, body, term) | `appointments` table — per `00-codebase-map.md` §3, populated but read only by `queries.py`/`evidence.py`/`profile.py`, never by `tests.py` or the frontend | PARTIAL | Table exists at the right conceptual grain, just underused, not absent |
| `motion_fact` (meeting, item) | `motions` table — has mover/seconder/outcome; officer recommendation and amendment-flag are not separate stored fields (per `01-known-defects.md` G-25, `officer_divergence()` cannot detect motion-text amendments at all) | PARTIAL | — |

No table in the current schema declares its grain as metadata; every grain
fact above was established in `00-codebase-map.md` §3 by manual inspection
(row-count + constraint check), not by reading a declaration. The target's
"gold tables must not be agent-designed" principle is not directly violated
today, because there is no separate gold layer at all — `tests.py`/`queries.py`
query the raw extraction schema (bronze/silver undifferentiated) directly,
which is a different problem than agent-designed gold, but one the target
architecture would also need to solve: **introducing** a gold layer is new
work, not a redesign of an existing one.

### Regeneration semantics

| Target property | Current state | Status |
|---|---|---|
| Swapping frameworks is a config change, not a regeneration | Framework identity is a Python string literal in 3 places (`tests.py`, `config/test_registry.json`, `OverviewPanel.tsx`) — changing it requires editing code and redeploying the frontend, not just config | WRONG |
| Re-grading after new error terms touches claims only, never bronze/silver | No error-term ingestion path exists at all (that's `05-verification.md`'s job); today, changing a grade means editing the threshold literal inside a `_t_*` function — a code change, and by construction the same change also touches the narrative text in the same edit, since they're one function | WRONG |
| A failed critic round regenerates the claim, not the pipeline | No critic round exists yet (`03-critic-agents.md`); today's closest analogue, the Editor/Fixer loop, operates on already-rendered draft *snapshots*, one level downstream of anything resembling a claim object | N/A — no current equivalent to evaluate against |

---

## Gaps

### G-01: No claim object exists as a distinct, structured artefact
Target: the analyst emits one structured object per claim, schema as specified.
Current: `TestResult` (`tests.py:107-135`) is the closest analogue — a flat dataclass with `n`, `valence`, `grade`, `headline`, `verdict`, `unit_of_analysis`, `named_entities` — computed and consumed entirely in-memory during one `council draft` run, never persisted independently of the final JSON snapshot (`00-codebase-map.md` §4).
Delta: `TestResult` has no `population`, `comparison`, `statistic.ci_*`, `power`, `provenance.query_hash`, or `narrative.caveats` fields — roughly a third of the target schema's top-level sections have zero representation today.
Risk if unfixed: every other gap below (and most of `01-known-defects.md`) has no seam to attach a fix to; fixes continue to be per-function patches that can drift apart again exactly as G-05/G-22 already have.

### G-02: No statistical-inference machinery anywhere in the analysis layer
Target: every claim's `statistic` block carries a CI, a method, a clustering unit, and multiple-comparison bookkeeping.
Current: confirmed zero hits for CI/significance/clustering machinery across `tests.py`/`queries.py`/`divergence.py` (the same grep run three times independently across this session's forks, always zero).
Delta: this single missing capability is what makes L-01, L-02, L-03, L-04, L-10, L-13 all unimplementable as anything but a hardcoded threshold — it's one gap, not six.
Risk if unfixed: every grade in the report continues to rest on a threshold literal a human chose once, with no way to tell whether it was ever statistically justified.

### G-03: No population/grain/filter-chain object
Target: `population.grain`/`definition`/`filter_chain`/`exclusions` make every denominator reproducible by replay.
Current: MISSING per `01-known-defects.md` G-04 — restated here as the schema gap it is, not just a symptom.
Delta: L-06 and L-08 cannot exist without this object first existing.
Risk if unfixed: identical to G-04's own risk statement — this is the same gap, viewed from the schema side rather than the defect side.

### G-04: `comparison` type/validity never declared or checked
Target: every stated comparison declares whether its reference group is the same event under different conditions.
Current: MISSING — `01-known-defects.md` G-12 (83× ratio) and G-16 (win-rate baseline) are both instances of a comparison whose validity was never checked because nothing requires it to be declared.
Delta: L-07 depends directly on this field existing.
Risk if unfixed: a new invalid comparison of this exact shape can ship again on any future test, on any future council, with nothing to catch it.

### G-05: Grade decided by ungoverned per-function threshold, not a rule with a justification field
Target: `grade` is accompanied by `grade_justification`, checkable against `statistic`.
Current: every `_t_*` function's threshold (e.g. `ratio <= 1.6`, `stay < 50.0`, `gap > 10`) is a bare literal with no accompanying justification field, confirmed for every function read across this session's four defect-tracing passes.
Delta: L-01/L-02/L-13's rules require a `grade_justification` and a `statistic` to check it against — neither exists.
Risk if unfixed: thresholds are arbitrary and unaudited; two reasonable people could disagree on `1.6` vs `2.0` with no record of why one was chosen.

### G-06: `narrative.caveats` has no equivalent, and headline/body already fuse with grade in one function
Target: caveats render on the panel face and are not a footnote the headline may contradict; narrative is generated *from* structured fields, never authored alongside them.
Current: `01-known-defects.md` G-22 and G-24 are both concrete instances of exactly this fusion producing a self-contradiction; there is no `caveats` field anywhere, so a caveat that exists at all lives in a footnote or a docstring, never load-bearing on the render.
Delta: the schema's `caveats: [str]` field, rendered mandatorily, is new; today caveat text (where it exists) is optional prose a reader can miss.
Risk if unfixed: G-22/G-24's exact failure mode (headline says one thing, a footnote elsewhere disowns it) recurs on any future test with a similar secondary caveat.

### G-07: Framework references are prose in 3 unsynced places, not structured config
Target: `framework_refs` is a list of `{instrument, section}` objects resolved against jurisdiction config.
Current: `01-known-defects.md` G-28 — three independent hardcoded copies.
Delta: this is the field `04-jurisdiction.md`'s WA-instrument config will populate; building the field here is a prerequisite, not a duplicate of that category's work.
Risk if unfixed: `04-jurisdiction.md`'s config swap has nothing to attach to without this field existing first.

### G-08: No `extraction_error` field read by any grading function
Target: a claim's grade is capped when the underlying field/era's extraction precision is below threshold.
Current: `/method` already computes corpus-wide quote-completeness/paraphrase-rate (`01-known-defects.md` G-33) but no `_t_*` function reads it, and it isn't broken down by era.
Delta: two sub-gaps — (a) the metric needs an era breakdown, which is new computation; (b) every grading function needs to read it, which is new wiring, not new data.
Risk if unfixed: a claim resting on a historically poorly-extracted era (e.g. the untuned 1995–2023 set, quote completeness 81.1% vs the tuned 2024+ set's 98.1%, per README) can still be graded CRITICAL with no acknowledgement that its underlying data is less trustworthy than a claim from the tuned era.

### G-09: Hypothesis registry exists as discipline, not as structured, linkable data
Target: every hypothesis is logged pre-registered, with a stable id linking to `claim_id`, feeding `multiple_comparison.family_size`.
Current: `docs/investigator/INVESTIGATIONS.md` already logs every hypothesis including kept nulls (3,068 lines, confirmed real entries with explicit weak/minor/null outcomes retained, not deleted) — the practice this target wants already exists in spirit.
Delta: no machine-readable schema, no `pre_registered_at` timestamp proving the hypothesis predated the result, no link from an entry to the `TestResult`/claim it produced, and nothing counts entries toward any correction.
Risk if unfixed: the exact thing G-15/L-10 wants (a real family size for multiple-comparison correction) can never be computed, because nothing counts how many hypotheses were actually tried before one was published — the raw material to compute it already exists in `INVESTIGATIONS.md`, uncounted.

### G-10: No gold-fact-table layer; grain established by inspection, not declaration
Target: 7 named gold tables, each with declared grain, sourced by claims instead of ad hoc queries against raw extraction tables.
Current: `tests.py`/`queries.py` query the raw extraction schema directly; every grain fact in the inventory table above was established this session by manual row-count/constraint inspection, not by reading a declaration anywhere.
Delta: this is new architecture, not a fix to an existing gold layer — there isn't one to fix. Three of the seven target tables (`vote_fact`, `application_fact`, `motion_fact`) map cleanly onto existing tables with mostly-correct grain already; the other four need new derived attributes or new tables.
Risk if unfixed: L-06/L-08/L-17 (population/filter-chain/entity-resolution checks) have nothing stable to validate against — a "gold table" that can be redefined by any future `_t_*` function's ad hoc filter is not a fixed point a linter can check reproducibility against.

### G-11: Framework/grading changes require code edits and redeploys, not config or claim regeneration
Target: swapping frameworks or re-grading after new error terms touches claims only.
Current: framework identity is a Python string literal in `tests.py` and a separate one in `frontend/src/components/OverviewPanel.tsx`; a grading threshold is a bare literal inside the same function that produces the narrative.
Delta: achieving this property requires G-01 (a claim object to regenerate), G-05 (a grade rule separable from a threshold literal), and G-07 (a config-driven framework reference) all to exist first — this is a consequence of the other gaps, not an independent one to fix directly.
Risk if unfixed: `04-jurisdiction.md`'s framework swap, if implemented against the current architecture, would require editing `tests.py` and redeploying the frontend — precisely the "if any of the above requires re-running extraction, the layering is wrong" failure this target explicitly warns against (re-running extraction isn't the risk here; re-deploying code for a config-shaped change is the analogous violation).

---

## Implementation steps

Additive throughout, per `00-README.md`'s constraint: the existing
`TestResult`/`tests.py` path keeps working and keeps shipping snapshots
while the claim layer is built alongside it; nothing here proposes deleting
`tests.py` or re-running extraction. Cutover (retiring `TestResult` in
favour of the claim object as the only path) is the last step, not an
early one.

### Step 1: Define the claim object as code
Files touched: new `src/analysis/claims.py` (a dataclass or Pydantic model mirroring `02-claim-layer.md`'s YAML schema in full, including empty/placeholder sub-objects for sections no current data feeds yet)
Depends on: none
Done when: the schema exists as an importable Python type with every field from the target YAML present, even where nothing populates it yet.

### Step 2: Stand up gold-fact-table views with declared grain
Files touched: new `src/analysis/gold.py` (SQL views or query functions over the existing raw tables — additive, no schema migration of `src/models/ontology.py` required yet), a `GRAIN` constant or docstring contract per table matching the inventory above
Depends on: Step 1 (the claim object's `population.base_table`/`grain` fields need something real to reference)
Done when: all 7 target gold tables exist as queryable views with a grain declared in code (not just inferred by inspection), and the 3 already-clean ones (`vote_fact`, roughly `application_fact`, roughly `motion_fact`) are wired first as the easy cases.

### Step 3: Build the population/filter-chain object and wire it into the gold views
Files touched: `src/analysis/gold.py` (each gold-table query returns its filter chain alongside its rows), `src/analysis/claims.py` (`population` field population)
Depends on: Step 2
Done when: querying any gold table returns both the rows and a `filter_chain` sufficient to reproduce the row count by replay — this is L-08's prerequisite.

### Step 4: Add CI/significance/clustering computation
Files touched: new `src/analysis/inference.py` (Wilson or exact binomial CI for proportions, a permutation-null helper for the sponsorship-network case, a clustering-aware rate calculator taking a `clustering_unit` argument), `pyproject.toml` (add `scipy`/`statsmodels` as a dependency — confirmed absent today)
Depends on: Step 3 (needs a population object to know what the clustering unit even is for a given claim)
Done when: a proportion computed via this module returns `(value, ci_low, ci_high)`; a rate computed with a `clustering_unit` argument returns a clustered, not pooled, estimate. Directly closes G-02/G-04's underlying capability gap, closing D-10, D-11, D-13, D-14 (`01-known-defects.md`) once wired into real tests in Step 6.

### Step 5: Build the linter as pure functions
Files touched: new `src/analysis/claim_linter.py`, implementing L-01 through L-18 against the `Claims` type from Step 1, each rule a pure function returning pass/fail + a readable diagnostic naming the rule and offending field, per the source doc's requirement
Depends on: Step 1 (needs the schema to validate against); Steps 3–4 for the rules that need `filter_chain`/`statistic.ci_*` to actually exist (L-01 through L-04, L-08); L-09 can only be stubbed until `04-jurisdiction.md`'s config format exists (build the rule now against a placeholder config shape, wire the real one when `04-jurisdiction.md` lands)
Done when: all 18 rules exist as pure functions with unit tests exercising both a passing and a failing claim per rule.

### Step 6: Migrate the battery one test at a time to emit claim objects alongside `TestResult`
Files touched: `src/analysis/tests.py` (each `_t_*` function gains a claim-object-producing counterpart, or is refactored to produce both), starting with the tests already flagged in `01-known-defects.md` as having the clearest fix (G-01 fiscal-year, G-18 flat-classification, G-12 invalid ratio) before the harder architectural ones (G-04's population reconciliation, which touches every test)
Depends on: Steps 2–5
Done when: every one of the 29 battery tests emits a claim object that passes the linter, or fails it with a named, readable reason (a controlled failure, not silence) — `council draft` continues to also write the legacy `TestResult`-derived snapshot in parallel until Step 9.

### Step 7: Run the linter in `council draft`, between battery computation and snapshot-writing
Files touched: `src/cli.py` (`_generate_snapshots()` / `cmd_draft`), alongside — not replacing — `src/invariant_gate.py`'s existing S7 checks (name-freedom, MIN_N, entity-resolution stay; they check a different thing than the new linter and both should run)
Depends on: Step 6
Done when: a claim that fails the linter blocks the draft with the same mechanical, no-LLM discipline the S7 gate already has, before any human or Editor sees it.

### Step 8: Structure the hypothesis registry
Files touched: new `investigator/hypothesis_registry.json` (or a small SQLite table) with the target schema (`id, question, pre_registered_at, gold_tables_used, outcome, claim_id, drop_reason`); a one-off backfill script parsing `docs/investigator/INVESTIGATIONS.md`'s existing ~entries into this structure (best-effort — `pre_registered_at` for backfilled entries is necessarily the backfill date, not the original investigation date, and must be marked as such, not fabricated)
Depends on: Step 1 (needs `claim_id` to link to)
Done when: every future `council explore` session appends a structured entry here in addition to `INVESTIGATIONS.md`'s prose (both kept — the prose remains the human-readable notebook; the structured entry is what `multiple_comparison.family_size` actually counts).

### Step 9: Run the linter in CI; retire `TestResult` as the primary path
Files touched: `.github/workflows/ci.yml` (add the linter test suite from Step 5), `src/analysis/tests.py` (once every test has a passing claim-object counterpart, the `TestResult`-only path is deleted, not before)
Depends on: Step 6 fully complete for all 29 tests
Done when: `TESTING.md` documents the linter as a required CI check; `TestResult` no longer exists as a separate, unlinted path a new test could accidentally use instead of the claim object.

### Cross-category dependency notes
- Step 5's L-09 and Step 6's `framework_refs` population are stubbed until `04-jurisdiction.md` defines the actual WA-instrument config format — build against a placeholder shape now rather than blocking on it.
- `03-critic-agents.md`'s critic roster reads claim objects, not `TestResult` — its design should assume Step 1's schema is the input contract, and its own steps should declare "Depends on: 02-claim-layer.md Step 1" explicitly when that file is written.
- `05-verification.md`'s error-term measurement is what should ultimately populate `extraction_error` (G-08) with real per-era numbers — Step 1 defines the field's shape; `05-verification.md` should declare "Depends on: 02-claim-layer.md Step 1 (extraction_error field shape)" and 02 depends on 05 for the *values*, a genuine two-way relationship the reading order's "05 feeds error terms into 02" note already anticipates.
