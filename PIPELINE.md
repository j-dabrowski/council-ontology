# Council-Ontology Extraction Pipeline: Master Plan

## Overview

This document defines the multi-level extraction pipeline for processing council meeting minutes PDFs into structured, auditable data. The core principle is **recursive refinement**: cheap broad passes feed expensive deep passes, and every pass validates the one after it. No blind extraction. By the time a document hits the full LLM call, we already know what it contains, what we expect to get back, and how to verify it.

Current state: 537 downloaded PDFs for Town of Cambridge (1995-2026). 196 ingested. 341 pending.

---

## Pipeline Status

| Level | Description | Status |
|-------|-------------|--------|
| 0 | Census: text extraction + keyword scan | **Done** (2026-05-28) |
| 1 | Cheap LLM inventory (Haiku, $4.83 actual) | **Done** (2026-05-28) |
| 2 | Schema and prompt revision | **Done** (2026-05-29) |
| 3a | Sample selection (`council sample`) | **Done** (2026-05-30) |
| 3b | Sample extraction (`council extract-sample`) | **Done** (2026-05-30) |
| 3c | Sample validation (`council validate-sample`) | **Done** (2026-05-30) — all metrics within target |
| 4 | Confidence metrics and validation script | **Done** (2026-05-31) |
| 5 | Batch extraction (~$7-20) | Pending |
| 6 | Human audit | Pending |

---

## Level 0: Free Pass (no LLM, no cost) ✅ COMPLETE

Run once across ALL documents. Pure text extraction and regex analysis.

### Tasks
- Extract text from every PDF via pypdf. Log: filename, success/failure, character count.
- Run keyword detection across extracted text. Target keywords:
  - Motions: MOVED, SECONDED, RESOLVED, AMENDMENT, MOTION
  - Votes: CARRIED, LOST, WITHDRAWN, DEFERRED, LAPSED, FOR, AGAINST, DIVISION
  - Planning: DA, DEVELOPMENT APPLICATION, PLANNING APPLICATION, LOT, SITE ADDRESS
  - Interests: DECLARATION OF INTEREST, FINANCIAL INTEREST, IMPARTIALITY INTEREST, CONFLICT
  - Community: PETITION, SUBMISSION, OBJECTION, DEPUTATION, PUBLIC QUESTION
  - Budget: BUDGET, EXPENDITURE, REVENUE, RATE, LEVY
  - Procedural: MINUTES CONFIRMED, APOLOGIES, LEAVE OF ABSENCE, PRESIDING MEMBER
- Detect section headers (look for numbered items, uppercase headings, common patterns like "ITEM X.X", "XX. TITLE").
- Count expected entities per document: estimated motion count (from MOVED/CARRIED occurrences), estimated planning items (from DA references), estimated interest declarations.
- Bucket documents by: size (tiny <10k, small 10-50k, medium 50-200k, large 200k+, failed), decade, meeting type.
- Flag outliers: empty extractions, corrupted PDFs, documents with zero keyword hits, extremely large documents.

### Output
- `data/census.json`: per-document metadata (filename, char_count, size_bucket, decade, meeting_type, keyword_counts, expected_entity_counts, flags).
- `data/census_summary.txt`: aggregate stats and outlier list.
- This data persists and is used by all subsequent levels for validation.

### Actual results (Cambridge, 2026-05-28)
- 537 PDFs scanned; 536 extractable, 1 empty, 0 errors
- 175M total chars; avg 327k chars/doc
- Size distribution: tiny 90 / small 85 / medium 42 / large 319 / failed 1
- Estimated entity totals: ~29,000 motions, ~5,700 planning items, ~1,650 interest declarations
- Flagged: 18 docs with no motion keywords, 1 with zero keyword hits, 43 with high DA count (>20)
- Command: `council census cambridge` (parallel workers, ~4 minutes for 537 PDFs)

---

## Level 1: Cheap LLM Inventory ($4.83 actual) ✅ COMPLETE

Run once (then iterate) across ALL documents. One small Haiku call per document. NOT full extraction. Document inventory only.

**Purpose:** The inventory isn't trying to count every motion in the document. It's trying to answer: what kind of document is this, and roughly what does it contain?

**The inventory prompt is iterated to convergence before any Level 2 schema work begins.** The quality signal is `other_content_rate` — the percentage of documents where the free-text `other_content` field is substantive (> 30 chars). This field captures anything the inventory schema didn't have a dedicated slot for. A high rate means the schema has gaps. The goal is ≤ 20%.

### Tasks
- For each document, build a text window from the first 20,000 characters + the last 10,000 characters. For documents under 30,000 chars, the full text is used. A separator marks where the middle was omitted: `[... middle section omitted ...]`.
- Send the text window to Haiku with a lightweight inventory-only prompt (`src/extraction/inventory_prompt.txt`).
- Prompt asks ONLY for a structural inventory:
  - List of section headings found
  - Count of motions/resolutions identified
  - Count of planning applications identified
  - Count of declared interests identified
  - Count of public questions, deputations, petitions, appointments, tenders, confidential items
  - Count of budget/financial items
  - Meeting date and type as identified by the model
  - Any content types present that don't fit the above categories (free text field: `other_content`)
- Cache raw LLM responses in `.cache/llm_responses/` keyed by document hash + prompt version. Bumping `PROMPT_VERSION` in `scripts/inventory.py` invalidates all cached responses, forcing a fresh call on the next run.
- Store per-document output as `data/inventories/{stem}.json`.

### Iteration loop (repeat until other_content_rate ≤ 20%)
1. `council inventory cambridge` — run inventory across all docs (or `--limit N --force` for a sample)
2. `council typology cambridge` (or `--limit N`) — aggregates inventories, computes `other_content_rate`, writes full report to `data/cambridge_typology_review.txt`, prints prompt box
3. Paste the prompt into Claude Code — updates `src/extraction/inventory_prompt.txt` and `DocumentInventory` Pydantic model; bumps `PROMPT_VERSION`
4. `council inventory cambridge --force --limit 20` — re-run on sample with new prompt
5. `council typology cambridge --limit 20` — did `other_content` shrink?
6. If still > 20%, repeat from step 3. Once ≤ 20%, do a full re-run, then proceed to Level 2.

Quality scores are saved to `data/inventory_quality/` for trend tracking (`council typology cambridge --history`).

### Output
- Per-document inventory with expected entity counts from the LLM's perspective.
- Cross-reference with Level 0 keyword counts. Flag documents where Level 0 and Level 1 disagree significantly (e.g. Level 0 found 12 MOVED keywords but Level 1 says 6 motions).
- A corpus-wide typology: which information types appear in which meeting types, how structure varies across eras.
- `other_content_rate` quality metric gating progression to Level 2.

### Actual results (Cambridge, 2026-05-28)
- 537 PDFs inventoried; 536 ok, 1 error (c1cdc1fa.pdf — known empty PDF from Level 0)
- 375 truncated (69%) — only 30k of text sent; 161 full window (doc fit within 30k)
- 1 flagged: d2af2d23.pdf (l1_mismatch_full_doc — Special Meeting, L1 counted 5 motions vs L0 estimate of 13)
- Meeting type distribution: 331 Ordinary / 124 Special / 22 Committee / 18 Special Council / 14 AGM / 13 AGM of Electors / 7 Special Electors / 5 Development Committee / 2 Briefing Forum
- Average per-doc: 9.6 motions / 9.5 planning / 1.0 interests / 0.6 petitions / 4.3 budget items
- Cost: $4.83 (537 docs × ~30k chars window, Haiku standard API)
- Current prompt version: `inventory-v2` (added public_question_count, deputation_count, petition_count, appointment_count, tender_count, confidential_item_count)
- `other_content_rate`: 100% on v1 (iteration in progress)

---

## Level 2: Schema and Prompt Revision (no cost)

Use Level 0 and Level 1 outputs to revise the extraction schema and prompt BEFORE running full extraction.

**Gated by Level 1 quality.** Do not begin Level 2 until `other_content_rate ≤ 20%` across the full corpus. The extraction schema should reflect what has been validated to exist in the corpus — not what was guessed upfront. Once the inventory prompt converges, `council typology` automatically switches its prompt box from inventory improvement instructions to extraction schema instructions.

**Run `council typology <council>` to get the schema update prompt.** This reads the typology report and generates instructions for updating `schemas.py`, `system_prompt.txt`, `ontology.py`, `extractor.py`, and `__init__.py` based on what the inventory has confirmed. The generated prompt explicitly requires: `source_quotes: list[str]` on every new entity model, `source_quotes` in the OUTPUT SCHEMA block of the extraction prompt, a new SQLAlchemy table per entity type, and provenance wiring in `save_extraction()` using the `_ev()` + `session.flush()` pattern. (Updated 2026-05-29 — prior version omitted `extractor.py` and said nothing about provenance.)

### Tasks
- Review Level 1 typology against current Pydantic schema (`src/extraction/schemas.py`). Identify gaps:
  - Entity types observed in documents but not in schema
  - Fields that exist in schema but are never populated
  - Structural patterns the schema doesn't capture
- Revise schema:
  - Add missing entity types or an `other_items` catch-all
  - Add provenance layer: every extracted entity carries a `source_quotes` field (list of short verbatim quotes from source text, 10-50 words each)
  - Ensure all Optional fields have sensible defaults
- Revise extraction prompt:
  - Informed by the full typology, not just the first few test documents
  - Explicitly request source quotes for every extracted fact
  - Include instruction: "If the document contains substantive items that don't fit the schema, list them in the other_items field. Do not silently discard content."
- Update database model (`src/models/ontology.py`) to match schema changes.
- Add `extraction_evidence` table: links extracted entities to source quotes with character offsets.

### Actual results (Cambridge, 2026-05-29) ✅ COMPLETE

All 13 inventory fields exceed 10% of corpus (lowest: deputation_count at 25%), so all
received dedicated Pydantic models.

`src/extraction/schemas.py`: 10 new entity models, each with `source_quotes: list[str]`.
  `ExtractedPublicQuestion`, `ExtractedDeputation`, `ExtractedPetition`,
  `ExtractedAppointment`, `ExtractedCommitteeReport`, `ExtractedBudgetItem`,
  `ExtractedInterestDeclaration`, `ExtractedTender`, `ExtractedDelegatedDecision`,
  `ExtractedBuildingPermit`. Also added `source_quotes` to `ExtractedMotion` and
  `ExtractedPlanningApplication`. Not added to nested sub-models.

`src/extraction/system_prompt.txt`: PROVENANCE RULE instruction added; `source_quotes`
field added to every entity in the OUTPUT SCHEMA block; extraction rules for all new types;
seven `other_items` type values removed (now have dedicated fields).

`src/models/ontology.py`: 11 new DB tables (one per entity type including `other_items`),
2 new enums (`InterestDeclarationType`, `PermitStatus`), `ExtractionEvidence` table.

`src/extraction/extractor.py`: `_resolve_offset()`, `_ev()` closure in `save_extraction()`,
`extract_from_pdf()` returns `(ExtractedMeeting, str)`, `save_extraction()` accepts `text=`.
All entity saves flush before inserting evidence rows. Call sites in `batch_extract.py` and
`cli.py` updated to pass raw text through.
`DEFAULT_MAX_CHARS = 80_000` added as single source of truth for the extraction window.
`extract()` / `extract_from_pdf()` accept `max_chars`: default 80k (single-chunk); `None`
enables multi-chunk full-document extraction with result merging.

### Output
- `schemas.py`, `system_prompt.txt`, `ontology.py`, `extractor.py` all updated.
- `extraction_evidence` table: one row per source quote per entity, with `char_offset`
  (best-effort verbatim position, stored as a UI convenience — not used for validation).

---

## Level 3: Prompt Validation Against Sample (~$1-2)

Test the revised prompt against a stratified sample before running at scale.
Level 3 is split into three substages with dedicated CLI commands.

### Level 3a: Sample Selection ✅ COMPLETE (2026-05-30)

`council sample cambridge [--count N]`

- Selects 15-20 documents from the corpus. Stratified by:
  - Era (at least 2 per decade from 1990s-2020s)
  - Size bucket (at least 2 from each: tiny, small, medium, large)
  - Meeting type (Ordinary, Special, AGM, Committee, Electors)
  - At least 3 documents flagged as outliers by Level 0/1
- Always persists the selection to `data/{council}_sample.json` (canonical file).
  Both 3b and 3c read from this file — the same document set is guaranteed across
  all substages.
- Also prints filenames to stdout (usable in subshell if needed).

### Level 3b: Sample Extraction ✅ COMPLETE (2026-05-30)

`council extract-sample cambridge`

- Reads `data/{council}_sample.json`.
- Always runs with `--force` (re-extracts regardless of existing DB records) — the
  point of this stage is to validate the *current* prompt and schema, not to reuse
  stale extractions. The user is notified at runtime.
- Populates `extraction_evidence` rows for all sample documents.

### Level 3c: Sample Validation ✅ COMPLETE (2026-05-30)

`council validate-sample cambridge`

- Reads `data/{council}_sample.json` (same document set as 3b).
- Re-extracts PDF source text at query time, strips page headers, then applies
  three-tier normalised matching to determine whether each model quote can be located
  in the source:
  0. **Page header stripping** — removes lines containing `H:\` Windows file paths from
     raw pypdf text before any matching. Council minute PDFs embed a page header (meeting
     title, date, file path) on every page; pypdf extracts these inline between content.
     Stripping them allows quotes spanning page breaks to match and contribute to coverage.
  1. **Whitespace normalisation** — collapse all whitespace runs to a single space.
     Handles pypdf line-break newlines inserted at every PDF line boundary.
  2. **Stripped matching** — remove all non-alphanumeric characters from both sides.
     Handles pypdf word-split artefacts in older PDFs (`"no ise"` → `"noise"`).
     Character span is recovered via a position-mapping array so these quotes
     contribute correctly to coverage. Only attempted for quotes ≥15 stripped chars.
  3. **Paraphrase** — content genuinely differs; collected for the paraphrase report.
- Four metrics per document:
  - **Paraphrase rate**: quotes unmatched after all three tiers / total quotes.
  - **Coverage ratio**: fraction of the extraction window covered by matched quotes.
    Denominator is `min(max_chars, total_chars)` so large documents are not penalised
    for content outside the extraction window. Pass `--max-chars full` to both
    `extract-sample` and `validate-sample` for full-document measurement.
    Unique char positions counted; overlapping quotes not double-counted.
  - **Inventory agreement**: extracted entity counts vs L1 inventory counts per field.
    Flagged if ratio <0.4 or >2.5.
  - **Keyword gap rate**: MOVED/CARRIED/DA/DECLARATION OF INTEREST/DEPUTATION/PETITION
    occurrences in normalised source text not spanned by any matched quote.
- Determines PASS/REVIEW/FAIL per doc; prints rich table to stdout.
- Writes `data/sample_validation/{stem}.json` per doc, `data/sample_validation/report.txt`
  (aggregate summary + interpretation), and `data/sample_validation/paraphrase_report.txt`
  (per-quote paraphrase detail with partial-match context for human or AI inspection).
- **Note on `char_offset` in DB**: `extraction_evidence.char_offset` is a best-effort
  convenience stored at save time via verbatim `text.find()`. It is not used here.
  All matching is recomputed from the live PDF text at validation time.

### Actual results (Cambridge, 2026-05-31, 18 docs) — final baselines after --max-chars full
- Quote completeness: **95.0%** (target >80%) ✓
- Paraphrase rate: **4.3%** (target <30%) ✓
- Coverage ratio:  **22.89%** (target >5%) ✓
- Keyword gap rate: **9.3%** (target <25%) ✓
- Status: 14 PASS / 4 REVIEW / 0 FAIL
- Quote completeness metric added: catches entities extracted with source_quotes=[]
  (invisible to paraphrase rate). Motions were the main offender; PROVENANCE RULE
  narrowed and explicit per-motion rule added.
  All 4 REVIEW docs re-extracted with --max-chars full. 4 remain REVIEW:
  008af827 (Public Art Committee, 74% completeness — non-standard language, known edge
  case), 060c4c87 (1995, 79.9% completeness — borderline), 0064743e (90% completeness,
  1 kwgap hit), 0a12261e (97.8% completeness, 68% kwgap persists across 6 chunks).

### Output
- `data/{council}_sample.json` — canonical sample (written by 3a, read by 3b and 3c).
- `data/sample_validation/` — per-doc JSON + `report.txt` + `paraphrase_report.txt`.
- Calibrated baseline metrics for Level 4 threshold configuration.

---

## Level 4: Confidence Metrics and Validation Script ✅ COMPLETE (2026-05-31)

`council validate cambridge [--limit N] [--files ...] [--from-year YYYY] [--force]`

Seven metrics per document — five inherited from Level 3c, two new:
- **Quote completeness** — fraction of entities with ≥1 source quote
- **Paraphrase rate** — quotes not matchable in normalised source text
- **Coverage ratio** — fraction of extraction window covered by matched quotes
- **Inventory agreement** — extracted counts vs Level 1 inventory counts
- **Keyword gap rate** — MOVED/CARRIED/DA etc. not covered by any quote span
- **Entity density** *(new)* — motions per 10k chars; flags large Ordinary meetings with suspiciously few motions
- **Schema completeness** *(new)* — Ordinary meetings must have ≥1 motion; all motions must have a non-null outcome

Composite status: PASS / REVIEW / FAIL per document.

Shared validation logic lives in `src/validation/core.py` — imported by both
`validate_sample.py` (Level 3c) and `validate_extraction.py` (Level 4).

`council validate` is a **separate step** from `council extract`, run explicitly after each batch.

### Output
- `data/validation/{stem}.json` per doc
- `data/validation/summary.json` aggregate (pass/review/fail counts, average metrics)

---

## Level 5: Batch Extraction (main cost, ~$7-20 on Haiku)

Full extraction across entire corpus in progressive batches.

### Workflow
```bash
council extract cambridge --limit 20 --dry-run  # preview cost before committing
council extract cambridge --limit 20   # extract a batch
council validate cambridge             # score the newly extracted docs
# triage REVIEW/FAIL results, fix errors, repeat
council extract cambridge --limit 50
council validate cambridge
# ...scale up to full corpus
```

### Tasks
- Run in batches of 20 documents on Haiku (standard API, not batch, for fast iteration).
- Use `--dry-run` to preview cost before each batch; use `council costs` for a full corpus breakdown.
- After each batch run `council validate cambridge` and triage:
  - PASS → continue
  - REVIEW → spot-check 2-3 per batch; adjust thresholds if false positives
  - FAIL → identify error class in `data/extraction_errors.json`, fix prompt/schema/parsing, re-extract
- Progressive scaling: 20, 50, 100, full remaining corpus.
- After every 100 documents: re-run Level 0 keyword detection with any new keywords discovered. Check for new flags on already-processed documents.
- Cache ALL raw LLM responses.
- Note: pre-Level-2b extractions already in DB (196 docs) will fail Level 4 (no extraction_evidence). Re-extract with `--force` to populate provenance.

### Output
- All documents extracted with per-document confidence scores.
- `data/extraction_errors.json`: structured error log grouped by error class.
- Full cache of raw LLM responses in `.cache/llm_responses/`.

---

## Level 6: Audit (no cost, human time only)

Final human verification on a random sample from the fully extracted corpus.

### Tasks
- Select 10-15 documents at random. NOT from the Level 3 sample. Stratify by era and size.
- For each: open the PDF and the extraction side by side. Go section by section.
- Record:
  - Precision: what % of extracted facts are correct?
  - Recall: what % of facts in the document were extracted?
  - Error rate: what % of extracted facts are wrong?
  - Provenance accuracy: do source quotes correctly support their associated facts?
- Document findings in `data/audit_report.md`.

### Output
- Audit report with quantified precision/recall/error metrics.
- This is the project's quality statement: "Across N audited documents, extraction captured X% of motions, Y% of votes, Z% of planning applications. Most common gap: ... Most common error: ..."

---

## Level 7: Production Run (optional, ~$10-40 on Sonnet batch)

If Haiku extraction quality was insufficient, re-extract on a stronger model.

### Tasks
- Run 10 documents on Sonnet (standard API) to check for new edge cases from richer output.
- If clean, submit full corpus to Sonnet via batch API (50% cost reduction, up to 24h latency).
- Re-run validation script on all results.
- Re-run audit on a fresh random sample.

### Output
- Production-quality extractions across full corpus.
- Updated audit report.

---

## Key Principles

1. **Every level validates the next.** Level 0 keyword counts validate Level 1 inventories. Level 1 inventories validate Level 2 extractions. Disagreements are flags, not failures.
2. **Schema reflects what's been validated, not what was guessed.** The extraction schema is not written until the inventory prompt has converged (other_content_rate ≤ 20%). Building the schema from a reliable inventory means it matches what's actually in the corpus.
3. **Cheap passes cover the full corpus. Expensive passes are informed by cheap ones.** Never do blind extraction.
4. **Cache everything.** Raw LLM responses, extracted text, inventories, validation results. Prompt changes invalidate LLM cache. Parsing changes don't.
5. **Provenance is non-negotiable.** Every fact links back to a source quote in the original text. No fact exists without evidence.
6. **Fix classes, not instances.** When extraction fails, identify the error class and fix the pattern. Don't patch individual documents.
7. **Human time goes where the system points.** Don't randomly sample for audit. Audit the documents the validation script flagged, plus a random sample for calibration.
8. **The system gets smarter as it runs.** New keywords, new patterns, and new edge cases discovered during extraction feed back into earlier levels. Re-run cheap passes with updated knowledge.

---

## File Structure

```
data/
  census.json                  # Level 0: per-document metadata
  census_summary.txt           # Level 0: aggregate stats
  inventories/                 # Level 1: per-document LLM inventory
    {filename}.json
  inventory_quality/           # Level 1: other_content_rate quality scores over time
    quality_{council}_{ts}.json
    latest_{council}.json
  {council}_typology_review.txt  # Level 1→2: typology report (council typology)
  validation/                  # Level 4: per-document confidence reports
    {filename}.json
  extraction_errors.json       # Level 5: error log by class
  audit_report.md              # Level 6: human audit findings

.cache/
  llm_responses/               # Cached raw LLM responses
    {hash}.json                # Keyed by doc_hash + prompt_version

scripts/
  census.py                    # Level 0
  inventory.py                 # Level 1
  inventory_typology.py        # Level 1→2 (council typology)
  stratified_sample.py         # Level 3a
  validate_sample.py           # Level 3c
  validate_extraction.py       # Level 4

src/validation/
  core.py                      # Shared validation logic (Levels 3c and 4)
```

---

## Current Model Configuration

- Development / iteration: claude-haiku-4-5-20251001 (standard API)
- Production: claude-sonnet-4-6 (batch API)
- Prompt version tracked in extraction cache key
- max_tokens: 64,000
- thinking: {"type": "adaptive"}
