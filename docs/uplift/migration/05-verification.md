# Verification and Accuracy Measurement — Migration Plan

Traces the target verification pyramid (V-1 through V-10) in
`docs/uplift/05-verification.md` against current code. Feeds
`extraction_error` into `02-claim-layer.md`'s claim object and supplies
`03-critic-agents.md`'s C-05 extraction sceptic. Overlaps `00-codebase-map.md`
§2 (extraction layer) and `06-medallion-pipeline-SCOPE.md`'s territory at
the edges — cross-referenced below rather than re-derived, per this file's
own instruction not to duplicate that investigation.

**Headline finding.** The document-derived anchor checks (V-1, V-2, V-3) —
the ones the source doc calls "zero models, unambiguous" and wants built
*before* anything model-based — are almost entirely buildable **today**,
with **zero new extraction**, because the raw ingredients already sit in
the database unused for this purpose:

- V-1's ground truth (a stated tally, "carried 5/2") is already extracted
  and persisted: `Motion.votes_for`/`votes_against`/`votes_abstain`
  (`src/models/ontology.py:231-233`, written by `extractor.py:892-894`
  from `ExtractedMotion`'s same-named fields, `schemas.py`). **Nothing
  anywhere reconciles these against a `COUNT()` of the motion's individual
  `Vote` rows** — confirmed by grep; the fields are used only for
  display/filtering (`queries.py`'s contested-vote thresholds, margin
  calculations), never as a check.
- V-2's ingredients (attendance/vote consistency, term-date bounds,
  mover/seconder-in-attendance) are likewise present in the schema
  (`votes`, `councillor_terms`, `motions.moved_by_id`/`seconded_by_id`)
  but no contradiction sweep of any kind runs over them — confirmed:
  `scripts/audit_report.py` (the Level-6 tooling) is a stratified-sample
  report generator for *human* review, not an automated sweep, and no
  `contradictions` table exists anywhere in the schema (`00-codebase-map.md`
  §3's full 20-table inventory has no such table).
- V-3's cross-document checks are partially already-computed in spirit
  (`officer_divergence()` already does agenda-item-numbering-to-minutes
  matching for the officer-recommendation panel) but not persisted as a
  general-purpose reconciliation output.

This means the highest-value, lowest-cost part of this whole category
— the "load-bearing sentence" the target's own published-method-text
example leads with — could ship well before any of the harder,
model-based layers (V-4 through V-10) are built at all.

---

## Current state inventory

| Target capability | Current equivalent | Path | Status | Notes |
|---|---|---|---|---|
| V-1 Stated tally reconciliation | `Motion.votes_for`/`votes_against`/`votes_abstain` extracted and persisted; never reconciled against `Vote` row counts | `src/models/ontology.py:231-233`, `src/extraction/extractor.py:892-894` | PARTIAL (data exists; check doesn't) | The single cheapest win in this file — see G-01 |
| V-2 Internal contradiction sweep | No `contradictions` table exists; no code checks any of the five listed contradiction classes (double-recorded ABSENT+vote, orphan declarations, out-of-term votes, absent mover/seconder, tally exceeding chamber size) | — | MISSING (as a check); PARTIAL (ingredients present: `votes`, `councillor_terms`, `motions.moved_by_id`) | `councillor_terms` has only 125 rows against 423 councillors (`00-codebase-map.md` §3) — thin enough that an out-of-term-vote check will have real gaps in its own coverage, worth stating as a caveat on the check itself |
| V-3 Cross-document arithmetic | `officer_divergence()` already does agenda↔minutes item-number matching for one purpose (`src/analysis/divergence.py`); nothing generalises this into a standing reconciliation output; tender-value-vs-aggregate and councillor-name-vs-terms checks don't exist | `src/analysis/divergence.py` | PARTIAL | One instance of this class of check exists, narrowly scoped to one panel's needs, not built as reusable verification infrastructure |
| V-4 Page rasterisation, addressable by `(source_pdf, page)` | Confirmed absent — no image-capture or page-rasterisation code anywhere (`00-codebase-map.md` §5); the closest analogue is `src/analysis/evidence.py`'s live re-parse of PDF text per page for quote-to-page matching, which never rasterises, only re-extracts text | `src/analysis/evidence.py` | MISSING | Text-level page-matching exists and works today; image-level does not — these are different capabilities that happen to share a `(pdf, page)` addressing concept |
| V-5 Precision pass (stratified sample, vision, different model family, closed adjudication) | `council validate-sample`/`council extraction-loop` already do a stratified sample (era × format) at n≈18-20 and a three-tier quote-matching check (`src/validation/core.py`) — but same-model-family, text-only, and it's a completeness/paraphrase check, not a closed supported/contradicted/not-determinable adjudication | `src/validation/core.py`, `scripts/validate_sample.py` | PARTIAL | The stratified-sampling *infrastructure* and *cadence* (an existing iteration loop) are real and reusable; the *verification method* itself doesn't yet meet the target's three-axis-independence bar (same model family, same input representation — text, not images) |
| V-6 Three-way adjudication + `contested` table | No adjudication mechanism exists; no `contested` table in the schema | — | MISSING | `council validate`'s PASS/REVIEW/FAIL (`src/validation/core.py`'s `determine_status()`) is a related but different concept — a per-document confidence score, not a per-record three-way adjudication with an excluded-from-silver outcome |
| V-7 Capture–recapture for recall | No such mechanism; no independent second-pass extraction of any kind exists | — | MISSING | — |
| V-8 Adversarial injection | No such mechanism; `scripts/compare_models.py` (`council compare`) is the closest analogue — runs 3 models on one real PDF for dev comparison, but never injects synthetic content or measures detection | `scripts/compare_models.py` | MISSING (injection); PARTIAL (a model-comparison harness exists as reusable scaffolding) |
| V-9 Census verification of every named-claim source span | `src/analysis/evidence.py`'s `resolve_evidence()` already resolves and tiers (exact/normalised/stripped/paraphrase) every quote behind every entity in a claim, corpus-wide, not sampled — a genuinely strong existing mechanism (`00-codebase-map.md` §2) — but it checks whether the quote *appears in the source text*, not whether an independent model *adjudicates the claim as supported* | `src/analysis/evidence.py` | PARTIAL | The text-matching half of "verify every span" already runs on every draft; the independent-model-adjudication half doesn't exist |
| V-10 s5.68 census sweep | MISSING — see `04-jurisdiction.md` G-03/Step 4; the sibling s5.69 sweep runs corpus-wide today via substring match, no vision needed for that one | `src/analysis/queries.py:3429-3438` | MISSING (for s5.68); PARTIAL (proven pattern for the sibling provision) | Cross-referenced, not duplicated, per `04-jurisdiction.md` |
| Per-field, per-era error table (`field, era, format, precision, precision_ci, recall_floor, n_sampled, verification_run_id`) | `/method`'s `_build_validation()` computes corpus-wide (not per-era) `quote_completeness`/`paraphrase_rate`/`coverage_ratio`/`inventory_agreement`, each with its own `generated_at` | `src/analysis/method.py:368-463` | PARTIAL | Real numbers exist and are already public (`01-known-defects.md` G-33); the era/format breakdown and the `verification_run_id`/CI columns the target schema wants don't |
| Error term folded into claim CIs | No CI exists on any claim yet (`02-claim-layer.md` G-02); nothing today widens any interval for extraction uncertainty because no interval exists to widen | — | MISSING | Directly downstream of `02-claim-layer.md`'s Step 4 landing first |
| Published method text with the target's worked example shape | `/method` page exists and is live/public, but its narrative is closer to "here are four separate metrics" than the target's single fluent paragraph anchored on the document-derived reconciliation figure as the load-bearing sentence | `src/analysis/method.py`, `frontend/src/pages/MethodPage.tsx` | PARTIAL | The data to write this paragraph from partially exists (validation metrics) and partially doesn't yet (V-1's reconciliation rate, since V-1 itself doesn't run yet) |
| Model version, extraction date recorded per record | `Meeting.extracted_at` exists and is populated; model identity is recoverable only for batch-extracted meetings via `data/batch_jobs/*.json` (per-batch, not per-record) — confirmed 130 sync-extracted meetings have no recoverable model identity at query time | `src/models/ontology.py:208`, `src/provenance.py` | PARTIAL | Restated from `00-codebase-map.md` §2, directly relevant here since the target's method-text example opens with "[model, version, date]" |
| Per-field provenance (source PDF, page, character span) | `char_offset` stored at extraction time; page is *not* stored, only reconstructed live at draft time by re-parsing the PDF (`src/analysis/evidence.py`) | `src/models/ontology.py` (`ExtractionEvidence`), `src/analysis/evidence.py` | PARTIAL | Restated from `00-codebase-map.md` §2 — directly answers this file's own "Investigation prompts" question about per-field provenance |
| Source PDFs retained and page-addressable | Retained on disk (`data/raw/<council>/*.pdf`, gitignored, not deleted); **not** page-addressable in storage — two independent PDF-to-text codepaths both flatten to one string with no page-boundary metadata kept | `src/extraction/extractor.py:93-116`, `src/cli.py:40-64` | PARTIAL | Restated from `00-codebase-map.md` §2/§9 — page-addressability is reconstructed on demand (`evidence.py`), not stored, which is sufficient for V-9's text-matching half but not for V-4's rasterisation, which needs the actual page images, not just text |
| Validation running between extraction and DB insert | `save_extraction()` flags a hallucination risk via `_resolve_offset()`'s null-on-no-match (`extractor.py`); `council validate`/`council validate-sample` run as separate, later, batchable steps, not inline at insert time | `src/extraction/extractor.py`, `src/validation/core.py` | PARTIAL | A narrow inline check exists (offset resolution); the fuller five-metric validation is a deliberately separate, rerunnable stage, not blocking insert |

---

## Gaps

### G-01: Stated-tally reconciliation (V-1) is buildable today with zero new extraction
Target: reconcile every stated tally against extracted vote rows, corpus-wide, as the anchor, load-bearing method-text sentence.
Current: both sides of the comparison already exist in the database (`Motion.votes_for`/`votes_against` and the `votes` table's per-motion `COUNT()`); nothing computes the reconciliation.
Delta: this is a pure analysis-layer addition — no schema change, no re-extraction, no new pipeline stage. It is the single cheapest, highest-value step in this entire migration plan.
Risk if unfixed: the report continues to have no document-derived accuracy anchor at all, despite already storing everything needed to compute one — the exact "no precision, no recall... no audited sample" gap (D-33) persists for the one metric that costs nothing to fix.

### G-02: No internal-contradiction sweep despite the ingredients existing
Target: five classes of self-contradiction detected corpus-wide, persisted as a `contradictions` table, feeding C-05.
Current: MISSING as a mechanism; the underlying tables (`votes`, `councillor_terms`, `motions`) exist but `councillor_terms` is thin (125 rows / 423 councillors per `00-codebase-map.md` §3), which will limit the out-of-term-vote check's own coverage.
Delta: needs a new script/module and a new table; the term-date check specifically needs to report its own denominator honestly (how many votes even have a determinable term to check against) rather than silently skipping the gaps.
Risk if unfixed: five classes of free, zero-model, unambiguous errors go uncounted, and C-05 (`03-critic-agents.md`) has no `contradictions` table to read as one of its stated inputs.

### G-03: No page rasterisation exists; V-4 is a hard prerequisite for V-5 through V-10 and V-9's own drill-down/reply requirement
Target: every PDF page rendered to an addressable image.
Current: confirmed absent; text-level page-matching (`evidence.py`) is a different, already-working capability that doesn't substitute for it.
Delta: net-new infrastructure — this single step gates five of the ten target verification layers (V-5, V-6, V-8, V-9's image half, V-10) plus `03-critic-agents.md`'s C-08 visual critic's need for a rendering path in the other direction (panels, not source pages) — two related but distinct rasterisation needs in this plan, worth building with shared tooling where possible (both are "headless render → addressable image").
Risk if unfixed: none of the vision-based verification layers can start; the plan's own explicit ordering ("V-4 — page rasterisation" as step 2, before any precision/recall work) reflects exactly this dependency.

### G-04: Existing sample-validation infrastructure doesn't meet the three-axis-independence bar
Target: verification differs from extraction in task shape (closed vs. open), input representation (image vs. text), and model.
Current: `council validate-sample`'s three-tier quote-matching (`src/validation/core.py`) is a real, working, iterated-on capability — but it's text-on-text, same general model family, and measures quote-findability, not closed adjudication of a specific claim.
Delta: the *infrastructure* (stratified sampling, an iteration loop with a convergence target, a report format) is directly reusable; the *method* needs to change on all three axes to produce information the current approach structurally cannot ("if verification uses the same model, same task shape, and same input representation as extraction, it measures nothing," per the source doc).
Risk if unfixed: continuing to publish the current validation metrics without the three-axis change would let the same circularity trap the source doc explicitly warns against ship under respectable-sounding language ("83.7% quote completeness") that doesn't actually rule out correlated model error.

### G-05: No contested/adjudication mechanism; disagreements have nowhere to go
Target: extractor/verifier/arbiter three-way adjudication, disagreements written to a `contested` table and excluded from silver, the count itself published.
Current: `council validate`'s PASS/REVIEW/FAIL is a per-document confidence score assigned by one process reading its own output, not a genuine second opinion, and there is no `contested` table or silver-exclusion concept anywhere.
Delta: this requires V-4 (images) and a second, independent verification pass (V-5) to exist first — it's the adjudication layer sitting on top of both, not a standalone build.
Risk if unfixed: uncertain records continue to sit in the database indistinguishable from confident ones, with no structural way to say "we don't know" rather than silently guessing.

### G-06: No recall measurement of any kind
Target: capture–recapture over an independent second pass estimates what extraction missed, reported as a floor.
Current: MISSING entirely — every existing validation/verification concept in the codebase measures precision-adjacent properties (is what was extracted correct/findable), never recall (was everything there extracted).
Delta: net-new, and structurally the hardest layer to build well (needs genuine pass-two independence — different prompt lineage, no sight of pass one).
Risk if unfixed: D-08's under-counted objectors and any other silent omission class remains permanently invisible to every other check in this file, since all of them assume what's in the database is the universe to check, not a sample of it.

### G-07: No adversarial injection capability
Target: synthetic period-appropriate content injected into real pages, re-extracted, detection measured directly.
Current: `scripts/compare_models.py`'s multi-model harness on real PDFs is genuine, reusable scaffolding for the "run extraction and compare" half; it has no injection or synthetic-content capability at all.
Delta: needs a synthetic-content generator (period-appropriate phrasing is explicitly called out as mattering) and a held-out-set discipline to keep injected records from ever reaching silver.
Risk if unfixed: recall failure classes the other checks can't reach (because they only look at real, already-extracted content) remain unmeasured.

### G-08: Named-claim census verification has a working text half and a missing model-adjudication half
Target: every source span behind every named adverse claim is verified, not sampled, order 300 spans.
Current: `resolve_evidence()` already does exactly this at the corpus scale for text-matching (tiering every quote behind every entity, on every draft) — a real strength, not a gap, for the "does the quote appear" question.
Delta: the target's actual ask — an independent model adjudicating *supported/contradicted/not-determinable*, not just "text present" — needs V-4/V-5's infrastructure; `resolve_evidence()`'s tiering is necessary but not sufficient.
Risk if unfixed: a quote can be present verbatim in the source and still be a misleading or out-of-context read of what actually happened — text-matching alone can't catch that, only adjudication can.

### G-09: Extraction accuracy has no era/format breakdown and isn't folded into any interval
Target: a per-field, per-era, per-format precision table; extraction error widens claim CIs, not sits in a footnote.
Current: `/method` computes real, public, corpus-wide (not stratified) validation metrics; nothing feeds them into a per-claim interval because no per-claim interval exists yet.
Delta: two sequenced sub-gaps — stratify the existing metric by era/format first (cheap, uses existing data differently), then wire the result into `02-claim-layer.md`'s `statistic.ci_*` once that field exists.
Risk if unfixed: a single blended accuracy number continues to imply uniform reliability across a corpus the project's own README already documents as ranging from 81.1% (untuned, 1995–2023) to 98.1% (tuned, 2024+) quote completeness — a 17-point swing hidden inside one headline figure.

---

## Implementation steps

Sequenced per the source doc's own instruction: census checks first (cheapest, most likely to reshape priorities), then rasterisation, then the model-based layers, then folding results back into the claim layer.

### Step 1: Build V-1, stated-tally reconciliation
Files touched: new `src/analysis/verification.py` (`reconcile_stated_tallies()` — join `motions` to a `COUNT()` over `votes` grouped by `choice`, compare against `votes_for`/`votes_against`/`votes_abstain`), a new CLI command or a section of `council validate`'s output
Depends on: none
Done when: a reconciliation rate exists, per era, per document format, computed from data already in the database — no re-extraction, no new pipeline stage.

### Step 2: Build V-2, the internal contradiction sweep
Files touched: `src/analysis/verification.py` (five contradiction-class checks per the target's list), new `contradictions` table (`src/models/ontology.py`, additive)
Depends on: none
Done when: every contradiction class is counted corpus-wide; the out-of-term-vote check's own coverage denominator (how many votes have a determinable term to check) is reported alongside its result, not silently assumed complete.

### Step 3: Generalise V-3's cross-document checks
Files touched: `src/analysis/verification.py` (extract and generalise the agenda↔minutes matching pattern already proven in `src/analysis/divergence.py`; add tender-value-vs-aggregate and councillor-name-vs-terms checks)
Depends on: Step 2 (shares infrastructure)
Done when: V-1 through V-3's outputs together form the "load-bearing sentence" — a real, document-derived, model-free accuracy figure ready to publish before any other step in this file completes.

### Step 4: Build page rasterisation (V-4)
Files touched: new `src/verification/rasterize.py` or similar (per-page image export from each meeting's PDF, using `fitz`/PyMuPDF — already a project dependency), storage convention `(source_pdf, page) -> image path`
Depends on: none (can run in parallel with Steps 1–3)
Done when: any page of any retained PDF can be retrieved as an image by a stable key; this also supplies `03-critic-agents.md`'s Step 3 (C-08's rendering need is for panels, not source pages, but the tooling and addressing convention should be shared where practical).

### Step 5: Build the vision-based precision pass (V-5) and adjudication (V-6)
Files touched: new `src/verification/precision_pass.py` (stratified sample by era × format, vision-model closed adjudication against a cited span: supported/contradicted/not_determinable), new `contested` table for unresolved three-way splits, wiring to exclude contested records from whatever `02-claim-layer.md` treats as gold
Depends on: Step 4; a second model (different family from the extractor) and a third (arbiter) — a cost/API-usage decision for the project owner, not a design question this plan resolves
Done when: n≈500 stratified sample is adjudicated; the contested count is itself a published number.

### Step 6: Capture–recapture recall floor (V-7)
Files touched: new `src/verification/recall.py` (independent second-pass extraction over a page sample, vision path, no sight of pass one; A×B/C population estimate)
Depends on: Step 4; independent prompt lineage from the main extraction prompt (a deliberate design choice, not a reuse of `system_prompt.txt`)
Done when: a recall floor is published with the independence-violation caveat stated in the method text, per the source doc's own instruction to report it as a strength, not hide it.

### Step 7: Named-claim census verification (V-9) and the s5.68 sweep (V-10)
Files touched: `src/analysis/evidence.py` (extend `resolve_evidence()`'s output to flag which entries feed a `names_individuals==true` claim, prioritising those ~300 spans for Step 5's adjudication pass specifically, not just the general sample); `04-jurisdiction.md` Step 4 for V-10 specifically
Depends on: Step 5 (needs the adjudication mechanism to exist); `04-jurisdiction.md`'s Step 4 (s5.68 detector) for V-10
Done when: every source span behind every named adverse claim has been adjudicated, not sampled — order 300 spans total per the source doc's own estimate.

### Step 8: Adversarial injection (V-8)
Files touched: new `src/verification/injection.py`, a held-out synthetic-record set that never reaches any gold/silver table
Depends on: Step 4 (needs page images to inject synthetic content into) and a period-appropriate content generator (a genuinely new capability, not a reuse of extraction machinery)
Done when: injected declarations/tenders/objections across multiple document-era formats are detected at a measured rate, reported directly as recall for the classes free checks can't reach.

### Step 9: Build the per-field, per-era error table and fold it into claim CIs
Files touched: `src/analysis/method.py` (`_build_validation()` — add era/format stratification to the existing corpus-wide metrics), new schema `field, era, format, precision, precision_ci, recall_floor, n_sampled, verification_run_id`, wiring into `02-claim-layer.md`'s `claim.extraction_error` field
Depends on: Steps 1–8 (this is the table that aggregates all of them); `02-claim-layer.md` Step 1 (the field to populate)
Done when: a claim resting on a low-precision stratum is structurally prevented from grading above neutral (linter rule L-15, `02-claim-layer.md`), and `03-critic-agents.md`'s C-05 has real per-era numbers to read instead of none.

### Step 10: Write the published method text
Files touched: `src/analysis/method.py`, `frontend/src/pages/MethodPage.tsx`
Depends on: Steps 1, 5, 6 at minimum (the target's own worked example cites a reconciliation rate, a precision CI, a recall floor, and a contested count — all four need to exist first)
Done when: `/method` reads as the source doc's worked example — one fluent paragraph anchored on the document-derived reconciliation figure as its load-bearing, non-model-dependent sentence.

### Cross-category dependency notes
- Step 9 is what `02-claim-layer.md`'s `extraction_error` field and linter rule L-15 depend on for real values — that file's Step 1 defines the field's *shape*; this file's Step 9 supplies the *data*, exactly the two-way relationship the reading order already anticipates ("05 feeds error terms into 02").
- Step 7 depends on `04-jurisdiction.md`'s s5.68 detector (that file's Step 4) for V-10 specifically — sequence Step 7's V-9 half independently if the s5.68 detector isn't ready yet; don't block all of V-9 on V-10.
- Step 4's rasterisation tooling should be built once and shared with `03-critic-agents.md`'s C-08 (Step 3 there) rather than duplicated — two different addressing needs (source pages vs. rendered panels) but the same underlying headless-render capability.
- Cross-reference `00-codebase-map.md` §2 and `06-medallion-pipeline-SCOPE.md` before building Step 1–3 in detail, per this file's own instruction not to duplicate the extraction-layer investigation — this file's inventory table already reflects that investigation's findings rather than re-deriving them.
