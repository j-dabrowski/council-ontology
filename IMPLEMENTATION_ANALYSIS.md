# Council-Ontology Pipeline: Implementation Analysis

## Purpose

Maps each pipeline level (from PIPELINE.md) against the current project state (from PROJECT_OVERVIEW) to identify what can be composed from existing CLI commands, what needs new work, and the dependency order for building it.

---

## Level 0: Census ✅ COMPLETE

**Completed 2026-05-28.** `scripts/census.py` + `council census cambridge`.

**What was built:**
- `scripts/census.py` — parallel pypdf extraction + keyword/regex scan across all PDFs.
  ProcessPoolExecutor with configurable workers (default: min(8, cpu_count)).
  Incremental mode (skips already-scanned PDFs unless --force).
- `council census cambridge [--force] [--quiet] [--workers N]` — CLI entrypoint.
- Outputs `data/census.json` (537 records) and `data/census_summary.txt`.

**Actual results from Cambridge corpus (537 PDFs):**
- 536 extractable, 1 empty (`c1cdc1fa.pdf`), 0 errors
- 175M total chars, avg 327k chars/doc
- Size buckets: tiny 90, small 85, medium 42, large 319, failed 1
- Estimated motions: ~29,000; planning items: ~5,700; interest declarations: ~1,650
- Flags: 18 docs with no motion keywords, 1 with zero keyword hits (`46698696.pdf`), 43 with high DA count

**Still not built (from original Level 0 spec):**
- `data/census_summary.txt` aggregate stats: done.
- Keyword detection: done. Section header detection: done.
- The census does NOT yet detect meeting type from PDF text (uses manifest only).

---

## Level 1: Cheap LLM Inventory

**Already exists:**
- `council batch` and `council extract` both call the LLM, but they run the FULL extraction prompt with 64k max output tokens. No lightweight inventory mode exists.
- `council compare` runs multiple models on one PDF but again uses the full prompt.
- The caching infrastructure does NOT exist. Raw LLM responses are not cached to disk.

**Can be composed now:**
- Nothing. There's no way to run a cheap inventory-only prompt through existing CLI commands.

**Needs new work:**
- A new prompt (small, inventory-only) and a corresponding Pydantic schema for the inventory output.
- A new script (`scripts/inventory.py`) or CLI command (`council inventory cambridge`) that sends only the first ~20k chars to Haiku with the inventory prompt and stores results per document.
- LLM response caching. This is needed here and pays off massively in Level 5. Key by document hash + prompt version. Check cache before calling API.
- Cross-referencing logic: compare Level 0 keyword counts to Level 1 inventory counts, flag disagreements.

**Effort: Medium.** New prompt, new schema, new script, new cache layer. But each piece is small.

---

## Level 2: Schema and Prompt Revision

**Already exists:**
- `schemas.py` has lenient validators with coercion for common LLM output variants.
- `system_prompt.txt` is the extraction prompt (externalised from the code).
- `other_items` catch-all field was added to the schema on 2026-05-27 but is NOT persisted to the database (`save_extraction()` ignores it).
- The overview notes the prompt eval score is 100/100 (benchmark saturated).

**Can be composed now:**
- Schema review can be done manually by comparing Level 0/1 outputs to the current schema. No automation needed.

**Needs new work:**
- Provenance layer. This is the biggest schema change. Every extracted entity needs a `source_quotes` field. The Pydantic schemas, the extraction prompt, the database model, and `save_extraction()` all need to be updated.
- New database table: `extraction_evidence` linking entities to source quotes with character offsets.
- `other_items` persistence. The overview explicitly flags this as unfinished. Needs either a new DB table or a JSON sidecar.
- Post-processing step: take source quotes returned by the LLM and resolve them to character offsets in the source text via string matching.

**Effort: Large.** Provenance touches every layer of the stack: schema, prompt, database, persistence, and adds a new post-processing step. This is the hardest level.

---

## Level 3: Prompt Validation Against Sample

**Already exists:**
- `council eval` runs extraction against benchmark PDFs and scores quality. Currently uses 4 PDFs x 2 models.
- `council compare <pdf>` runs all three models on one PDF for side-by-side comparison.
- `council extract --files a.pdf b.pdf` targets specific PDFs.

**Can be composed now:**
- Select 15-20 PDFs manually, run `council extract --files <list>`, then inspect results. This is roughly what eval does already but with a fixed benchmark set.
- `council compare` on individual sample documents gives multi-model comparison.
- Level 0 census data now enables stratified sampling: pick by size bucket, decade, meeting type, and flagged outliers.

**Needs new work:**
- Expanding the eval benchmark from 4 PDFs to a properly stratified 15-20 document sample (selected using Level 0/1 data to cover all size buckets, decades, meeting types).
- Validation comparison: automated diff of Level 5 extraction counts against Level 1 inventory counts per document. `eval_prompt.py` scores against a fixed rubric; it doesn't compare against a per-document inventory.
- Source quote validation: check that every returned source quote actually exists in the source text. New post-processing logic.
- Coverage ratio computation: chars referenced by quotes / total chars. New metric.

**Effort: Medium.** The eval infrastructure exists but needs extending to use Level 1 inventories as ground truth and to validate provenance.

---

## Level 4: Confidence Metrics and Validation Script

**Already exists:**
- `data/extraction_errors.json` captures errors from batch runs, grouped by class.
- The batch script already triages into success/failure.
- `council analyse` queries can surface some anomalies (e.g. councillors with zero votes, motions with no outcome).

**Can be composed now:**
- Basic anomaly detection using existing analysis queries. But this is manual, not automated per-document validation.

**Needs new work:**
- `scripts/validate_extraction.py` as a new script. Nothing like this exists. Needs to compute:
  - Coverage ratio (requires provenance from Level 2)
  - Entity density (motions per 10k chars, computable from existing data + Level 0 char counts)
  - Keyword gap score (requires Level 0 keyword positions + Level 2 source quote positions)
  - Inventory agreement (requires Level 1 inventories)
  - Schema completeness checks (queryable from existing DB but not automated)
  - Cross-document consistency (new logic)
  - Composite confidence score per document
- CLI integration: `council validate cambridge` or similar.
- Output format: `data/validation/{filename}.json`.

**Effort: Medium-Large.** Many individual checks, each simple, but the validation framework itself is new. Partially blocked by Level 2 (provenance needed for coverage ratio and keyword gap).

---

## Level 5: Batch Extraction

**Already exists:**
- `council batch cambridge --limit N` does exactly this. Processes N pending PDFs, writes errors to `data/extraction_errors.json`, prints success/failure summary with error class breakdown.
- Resume logic works: already-extracted documents are skipped.
- `--from-year` / `--to-year` / `--files` flags allow targeting specific subsets.
- `--model` flag allows switching between Haiku/Sonnet/Opus.
- `--force` allows re-extraction of already-ingested documents.

**Can be composed now:**
- `council batch cambridge --limit 20` repeated in a loop IS the progressive batch extraction workflow. It already skips completed docs and reports errors.

**Needs new work:**
- Auto-run validation script after each batch (integrate Level 4 into the batch loop).
- Triage output: currently errors are just logged. Needs PASS/REVIEW/FAIL categorisation per document based on confidence scores.
- Feedback loop: after every ~100 documents, re-run Level 0 keyword scan with updated keyword list. Not automated.
- LLM response caching (same as Level 1; needed to avoid re-paying for failed parsing).

**Effort: Small-Medium.** The core loop exists. The additions are validation integration and caching.

---

## Level 6: Audit

**Already exists:**
- `council compare <pdf>` gives multi-model comparison for individual PDFs.
- `council eval --show` displays the latest evaluation.

**Can be composed now:**
- Manual audit using `council extract --files <list>` on a random sample, then hand-comparing PDFs to DB records.

**Needs new work:**
- Audit report generator: select N random documents from the extracted set (excluding eval benchmarks), pull their extractions, format for human review.
- Precision/recall computation framework (semi-automated: human marks correct/incorrect/missing, script computes stats).
- Output: `data/audit_report.md`.

**Effort: Small.** Mostly a reporting script wrapping existing data.

---

## Build Order: Dependency Graph

| Priority | Component | Blocked by | Effort | Status |
|----------|-----------|------------|--------|--------|
| 1 | Level 0: keyword scanner + census output | Nothing | Small | **Done** |
| 2 | LLM response caching layer | Nothing | Small | Pending |
| 3 | Level 1: inventory prompt + script | Level 0 | Medium | Pending |
| 4 | Level 2: provenance (source quotes in schema, prompt, DB, persistence) | Level 1 | Large | Pending |
| 5 | `other_items` persistence | Nothing (already flagged) | Small | Pending |
| 6 | Level 4: validation script | Levels 0, 1, 2 | Medium | Pending |
| 7 | Level 5: validation integration into batch loop | Level 4 | Small | Pending |
| 8 | Level 6: audit report generator | Level 5 | Small | Pending |

**The critical path is Level 2 (provenance).** Everything downstream that involves confidence metrics depends on source quotes existing. Level 1 is next and is now unblocked by the completed Level 0.

---

## Parallelisable Work

These can be done independently of the main pipeline sequence:

- `other_items` persistence (small, unblocked, already flagged in project overview)
- Populate `minutes_pdf_url` from manifest into meetings table (trivial, already flagged)
- Populate `extracted_at` timestamp on meetings (trivial, already flagged)
- Store `minutes_text` in meetings table for future provenance lookups (small)
- LLM response caching layer (small, unblocked, saves money immediately)
