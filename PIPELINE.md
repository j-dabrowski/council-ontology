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
| 2 | Schema and prompt revision | Pending |
| 3 | Prompt validation against sample (~$1-2) | Pending |
| 4 | Confidence metrics and validation script | Pending |
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

Run once across ALL documents. One small Haiku call per document. NOT full extraction. Document inventory only.

**Purpose:** The inventory isn't trying to count every motion in the document. It's trying to answer: what kind of document is this, and roughly what does it contain?

### Tasks
- For each document, build a text window from the first 20,000 characters + the last 10,000 characters. For documents under 30,000 chars, the full text is used. A separator marks where the middle was omitted: `[... middle section omitted ...]`.
- Send the text window to Haiku with a lightweight inventory-only prompt (`src/extraction/inventory_prompt.txt`).
- Prompt asks ONLY for a structural inventory:
  - List of section headings found
  - Count of motions/resolutions identified
  - Count of planning applications identified
  - Count of declared interests identified
  - Count of petitions/deputations/submissions
  - Count of budget/financial items
  - Meeting date and type as identified by the model
  - Any content types present that don't fit the above categories (free text field)
- Cache raw LLM responses in `.cache/llm_responses/` keyed by document hash + prompt version. Re-running the same prompt version costs nothing for already-cached documents.
- Store per-document output as `data/inventories/{stem}.json`.

### Output
- Per-document inventory with expected entity counts from the LLM's perspective.
- Cross-reference with Level 0 keyword counts. Flag documents where Level 0 and Level 1 disagree significantly (e.g. Level 0 found 12 MOVED keywords but Level 1 says 6 motions).
- A corpus-wide typology: which information types appear in which meeting types, how structure varies across eras.
- Updated keyword list: if Level 1 identifies content types or patterns Level 0 missed, feed new keywords back into Level 0 and re-run.

### Actual results (Cambridge, 2026-05-28)
- 537 PDFs inventoried; 536 ok, 1 error (c1cdc1fa.pdf — known empty PDF from Level 0)
- 375 truncated (69%) — only 30k of text sent; 161 full window (doc fit within 30k)
- 1 flagged: d2af2d23.pdf (l1_mismatch_full_doc — Special Meeting, L1 counted 5 motions vs L0 estimate of 13)
- Meeting type distribution: 331 Ordinary / 124 Special / 22 Committee / 18 Special Council / 14 AGM / 13 AGM of Electors / 7 Special Electors / 5 Development Committee / 2 Briefing Forum
- Average per-doc: 9.6 motions / 9.5 planning / 1.0 interests / 0.6 petitions / 4.3 budget items
- Cost: $4.83 (537 docs × ~30k chars window, Haiku standard API)
- Command: `council inventory cambridge` (max 20 concurrent Haiku calls)

---

## Level 2: Schema and Prompt Revision (no cost)

Use Level 0 and Level 1 outputs to revise the extraction schema and prompt BEFORE running full extraction.

**Before making any schema changes, run `council typology <council>` to review the Level 1 corpus typology report.** This surfaces content types, `other_content` patterns, and section heading frequencies across the full corpus — so schema gaps are identified before committing to a prompt revision.

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

### Output
- Revised `schemas.py`, `ontology.py`, extraction prompt.
- Documented rationale for what was added/changed and why.

---

## Level 3: Prompt Validation Against Sample (~$1-2)

Test the revised prompt against a stratified sample before running at scale.

### Tasks
- Select 15-20 documents from the corpus. Stratify by:
  - Era (at least 2 per decade from 1990s-2020s)
  - Size bucket (at least 2 from each: tiny, small, medium, large)
  - Meeting type (Ordinary, Special, AGM, Committee, Electors)
  - Include at least 3 documents flagged as outliers by Level 0/1
- Run full Haiku extraction on sample with revised prompt.
- For each document, validate:
  - Compare extracted entity counts to Level 1 inventory. Flag significant discrepancies.
  - Check source quotes: do they exist in the source text? Do they support the extracted values?
  - Run keyword gap detection: are there MOVED/CARRIED/etc. keywords in spans NOT referenced by any source quote?
  - Compute coverage ratio: characters referenced by source quotes / total characters.
- Iterate prompt until sample results meet expectations.
- Cache ALL raw LLM responses keyed by document hash + prompt version.

### Output
- Validated prompt with documented performance against sample.
- Calibrated confidence metric thresholds (baseline coverage ratio, entity density, acceptable keyword gap rate).
- Cached responses for sample documents (re-runnable without cost).

---

## Level 4: Confidence Metrics and Validation Script (no cost)

Build automated validation before running at scale.

### Tasks
- Implement validation script (`scripts/validate_extraction.py`) that takes a document and its extraction and returns:
  - **Coverage ratio**: chars referenced by source quotes / total document chars. Threshold from Level 3 calibration.
  - **Entity density**: motions per 10k chars. Flag documents significantly below baseline.
  - **Keyword gap score**: count of extraction-relevant keywords (MOVED, CARRIED, DA, DECLARATION, etc.) in spans NOT covered by any source quote. Zero is ideal; flag above threshold.
  - **Inventory agreement**: compare Level 2 extracted counts to Level 1 inventory counts per document. Flag significant disagreement.
  - **Schema completeness**: does every Ordinary Council Meeting have at least one motion? Does every motion with an outcome have a valid enum value? Flag structural anomalies.
  - **Cross-document consistency**: if meeting N references minutes of meeting N-1, does N-1 exist? Do councillors appear consistently across adjacent meetings in the same term?
  - **Overall confidence score**: composite of above metrics. Categorise as PASS / REVIEW / FAIL.
- The script runs automatically after each extraction batch.

### Output
- `scripts/validate_extraction.py` producing per-document confidence reports.
- `data/validation/` directory with per-document JSON reports.
- Summary output after each batch: X passed, Y review, Z failed, with error class breakdown.

---

## Level 5: Batch Extraction (main cost, ~$7-20 on Haiku)

Full extraction across entire corpus in progressive batches.

### Tasks
- Run in batches of 20 documents on Haiku (standard API, not batch, for fast iteration).
- After each batch:
  - Run validation script on all newly extracted documents.
  - Triage results: PASS (continue), REVIEW (spot-check a sample), FAIL (diagnose and fix).
  - For FAIL documents: identify error class, fix prompt/schema/parsing, re-run failed batch.
  - For REVIEW documents: manually inspect 2-3 per batch. Adjust thresholds if flags are false positives. Fix extraction if flags are real.
- Progressive scaling: 20, 50, 100, full remaining corpus.
- After every 100 documents: re-run Level 0 keyword detection with any new keywords discovered during extraction. Check for new flags on already-processed documents.
- Cache ALL raw LLM responses.

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
2. **Cheap passes cover the full corpus. Expensive passes are informed by cheap ones.** Never do blind extraction.
3. **Cache everything.** Raw LLM responses, extracted text, inventories, validation results. Prompt changes invalidate LLM cache. Parsing changes don't.
4. **Provenance is non-negotiable.** Every fact links back to a source quote in the original text. No fact exists without evidence.
5. **Fix classes, not instances.** When extraction fails, identify the error class and fix the pattern. Don't patch individual documents.
6. **Human time goes where the system points.** Don't randomly sample for audit. Audit the documents the validation script flagged, plus a random sample for calibration.
7. **The system gets smarter as it runs.** New keywords, new patterns, and new edge cases discovered during extraction feed back into earlier levels. Re-run cheap passes with updated knowledge.

---

## File Structure

```
data/
  census.json                  # Level 0: per-document metadata
  census_summary.txt           # Level 0: aggregate stats
  inventories/                 # Level 1: per-document LLM inventory
    {filename}.json
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
  validate_extraction.py       # Level 4
  batch_extract.py             # Level 5
```

---

## Current Model Configuration

- Development / iteration: claude-haiku-4-5-20251001 (standard API)
- Production: claude-sonnet-4-6 (batch API)
- Prompt version tracked in extraction cache key
- max_tokens: 64,000
- thinking: {"type": "adaptive"}
