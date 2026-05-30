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

## Level 1: Cheap LLM Inventory ✅ COMPLETE (2026-05-28)

**What was built:**
- `src/extraction/inventory_prompt.txt` — lightweight inventory-only prompt. Asks for meeting_date, meeting_type, section_headings, and approximate counts of motions, planning items, interests, petitions, and budget items. Output is a small JSON object (~1k tokens).
- `scripts/inventory.py` — per-document inventory script with:
  - Text window: first 20,000 chars + last 10,000 chars (separator if truncated). Full text for docs ≤30k chars. The 20k+10k window was chosen over 20k-front-only to improve coverage of large documents (319/537 Cambridge docs exceed 200k chars).
  - LLM response cache in `.cache/llm_responses/` keyed by `sha256(pdf_bytes)[:16]_inventory-v1`. Cache is checked before every API call; re-running with the same prompt version costs nothing for cached docs.
  - `DocumentInventory` Pydantic schema with lenient int/list coercions.
  - Census cross-reference: flags `l1_overcounts_motions` (L1 count > 2× L0 estimate) and `l1_mismatch_full_doc` (significant mismatch on non-truncated docs). Undercounting on large docs is expected and not flagged.
  - ThreadPoolExecutor (max 20 concurrent) for parallel API calls.
  - Incremental mode: skips docs with existing `status: "ok"` inventory files unless `--force`.
- `council inventory cambridge [--limit N] [--force] [--quiet]` — CLI entrypoint.
- Outputs: `data/inventories/{stem}.json` per doc + `data/inventories/summary.json`.
- `scripts/inventory_typology.py` — post-inventory typology analysis. Reads all inventory files and produces a corpus typology report covering meeting type distribution, entity averages by decade, `other_content` patterns, section heading frequencies (rare headings = potential schema gaps), and census cross-reference flags. CLI: `council typology cambridge [--quiet]`. Output: `data/{council}_typology_review.txt`. Run this after Level 1 and before making any Level 2 schema decisions.

**Purpose:** The inventory isn't trying to count every motion in the document. It's trying to answer: what kind of document is this, and roughly what does it contain?

---

## Level 2: Schema and Prompt Revision ✅ COMPLETE

**Schema/prompt step: DONE (2026-05-29)**

Applied the inventory field prevalence table from `council typology cambridge` to identify
what deserves a dedicated field vs `other_items`. All 13 inventory fields exceed 10% of
corpus (lowest: deputation_count 25%), so all received dedicated Pydantic models.

What was built:
- 10 new Pydantic sub-models in `src/extraction/schemas.py`:
  `ExtractedPublicQuestion`, `ExtractedDeputation`, `ExtractedPetition`,
  `ExtractedAppointment`, `ExtractedCommitteeReport`, `ExtractedBudgetItem`,
  `ExtractedInterestDeclaration`, `ExtractedTender`, `ExtractedDelegatedDecision`,
  `ExtractedBuildingPermit`.
  All have lenient validators (coerce amounts, signatory counts, status strings).
- 10 new list fields on `ExtractedMeeting` (one per model above).
- `unwrap_envelope` validator updated to score new field names.
- `src/extraction/system_prompt.txt` rewritten: new OUTPUT SCHEMA block with all new
  fields; dedicated extraction rules for each type; `other_items` item_type list pruned
  (removed 7 types now covered by dedicated fields).
- `src/models/ontology.py` — not changed; new fields are captured in extracted JSON only.

**DB tables + persistence (done 2026-05-29):**
- 11 new SQLAlchemy table classes in `src/models/ontology.py`:
  `PublicQuestion`, `Deputation`, `Petition`, `Appointment`, `CommitteeReport`,
  `BudgetItem`, `InterestDeclaration`, `Tender`, `DelegatedDecision`,
  `BuildingPermit`, `OtherItem`.
- 2 new enums: `InterestDeclarationType`, `PermitStatus`.
- `save_extraction()` updated with save loops for all 11 new field types.
  `Appointment` and `InterestDeclaration` resolve councillors via `_get_or_create_councillor()`.
- Tables created automatically by `Base.metadata.create_all()` on next `init_db()` call.

**Provenance step: DONE (2026-05-29)**

What was built:
- `source_quotes: list[str]` added to 13 Pydantic models in `schemas.py`:
  `ExtractedMotion`, `ExtractedPlanningApplication`, `ExtractedPublicQuestion`,
  `ExtractedDeputation`, `ExtractedPetition`, `ExtractedAppointment`,
  `ExtractedCommitteeReport`, `ExtractedBudgetItem`, `ExtractedInterestDeclaration`,
  `ExtractedTender`, `ExtractedDelegatedDecision`, `ExtractedBuildingPermit`,
  `ExtractedOtherItem`. Not added to nested sub-models (`ExtractedCouncillor`,
  `ExtractedVote`, `ExtractedCommunitySubmission`) — parent quotes cover these.
- PROVENANCE RULE instruction added to `system_prompt.txt`; `source_quotes` field
  added to every entity in the OUTPUT SCHEMA block.
- `ExtractionEvidence` table added to `ontology.py` and exported from `__init__.py`.
  `entity_table` + `entity_id` form a logical FK (not enforced) to the entity row.
  `char_offset=None` flags quotes not found verbatim in source text (hallucination).
- `_resolve_offset(text, quote)` added to `extractor.py` — finds first verbatim
  occurrence of quote in text, returns `(offset, length)` or `(None, None)`.
- `extract_from_pdf()` now returns `(ExtractedMeeting, str)` — the result plus raw text.
- `save_extraction()` accepts `text: str | None = None`. Defines an `_ev()` closure
  after the meeting flush that inserts evidence rows. Every entity save now calls
  `session.flush()` before `_ev()` to ensure the entity ID is available.
- `scripts/batch_extract.py` and `src/cli.py` (both call sites) updated to unpack
  `extracted, raw_text = extractor.extract_from_pdf(...)` and pass `text=raw_text`.

---

## Level 3: Prompt Validation Against Sample

Level 3 is split into three substages, each with its own CLI command.
The canonical sample is persisted to `data/{council}_sample.json` by 3a and read
by both 3b and 3c, guaranteeing all substages operate on the same document set.

### Level 3a: Sample Selection ✅ COMPLETE (2026-05-30)

**What was built:**
- `scripts/stratified_sample.py` — greedy stratified selection from census + L1 flags.
  Stratifies by era (decade), size bucket, meeting type, and outliers.
  Slots: L1-flagged (cap 3) → L0 outliers (cap 3 total) → era×size grid → decade balance
  (≥2/decade) → minority meeting types → pad to target.
- Always writes `data/{council}_sample.json`: `{council, selected_at, count, files[]}`.
  This is the canonical reference for 3b and 3c.
- Still prints filenames to stdout (usable in subshell).
- `council sample cambridge [--count N] [--output-file PATH]`

**Results (Cambridge, 2026-05-30):** 18 docs — all 7 meeting types, all 4 decades,
all 4 size buckets, 3 outliers (1 L1-flagged, 3 L0-flagged).

### Level 3b: Sample Extraction ✅ COMPLETE (2026-05-30)

**What was built:**
- `council extract-sample cambridge` — dedicated CLI command. Reads
  `data/{council}_sample.json`, always extracts with `--force` (warns user),
  delegates to `cmd_extract()`. No extra flags needed.
- Replaced the manual subshell pattern `council extract cambridge --force --files
  $(council sample cambridge)`.

**Results:** 18/18 extracted, 0 failed. `extraction_evidence` populated for all docs.

### Level 3c: Sample Validation ✅ COMPLETE (2026-05-30) — prompt iteration needed

**What was built:**
- `scripts/validate_sample.py` + `council validate-sample cambridge`.
- Reads `data/{council}_sample.json`, queries `extraction_evidence`, re-extracts PDF
  text for keyword gap detection, loads L1 inventories for agreement comparison.
- Four metrics per doc: hallucination rate, coverage ratio, inventory agreement, keyword gap rate.
- Determines PASS/REVIEW/FAIL per doc; writes per-doc JSON + `data/sample_validation/report.txt`.
- Prints rich table to stdout with colour-coded metrics; report.txt includes interpretation
  and next-step instructions.

**Results (Cambridge, 2026-05-30, 18 docs):**
- Hallucination rate: **78.3%** (target <30%) — model is paraphrasing, not quoting verbatim
- Coverage ratio: **0.82%** (target >5%) — consequence of hallucination (paraphrases → NULL offsets)
- Keyword gap rate: **22.1%** (target <25%) ✓ — entities ARE being found, just without verbatim quotes
- Status: 1 PASS / 9 REVIEW / 8 FAIL

**Key insight:** Keyword gap rate is within target, meaning the extractor is locating
entities correctly. The problem is provenance only: the model writes paraphrased
`source_quotes` instead of verbatim extracts. The PROVENANCE RULE in `system_prompt.txt`
needs strengthening before proceeding to Level 4.

**Next step (still in Level 3 iteration loop):**
1. Strengthen PROVENANCE RULE in `src/extraction/system_prompt.txt`.
2. `council extract-sample cambridge` (re-run 3b with force).
3. `council validate-sample cambridge` (re-run 3c).
4. Repeat until hallucination <30%, coverage >5%.
5. Then proceed to Level 4.

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

**Effort: Medium-Large.** Many individual checks, each simple, but the validation framework itself is new. All Level 2 dependencies (provenance, DB tables) are now in place.

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
| 2 | LLM response caching + Level 1 inventory script | Level 0 | Medium | **Done** |
| 3 | Level 2a: schema/prompt update from inventory typology | Level 1 | Medium | **Done** |
| 4 | Level 2b: provenance (source_quotes in schema, prompt, DB, persistence) | Level 2a | Large | **Done** (2026-05-29) |
| 5 | New DB tables + `save_extraction()` for 10 new field types | Level 2a | Medium | **Done** (2026-05-29) |
| 6 | Level 3a: stratified sample selection script | Levels 0, 1 | Small | **Done** (2026-05-30) |
| 7 | Level 3b: `council extract-sample` CLI command | Level 3a | Small | **Done** (2026-05-30) |
| 8 | Level 3c: `council validate-sample` + `scripts/validate_sample.py` | Level 3b | Medium | **Done** (2026-05-30) |
| 9 | Level 4: `scripts/validate_extraction.py` (per-doc confidence scorer) | Level 3c | Medium | Pending |
| 10 | Level 5: validation integration into batch loop | Level 4 | Small | Pending |
| 11 | Level 6: audit report generator | Level 5 | Small | Pending |

**Levels 0–2 and Level 3a/3b/3c are complete.** The critical path now requires a
provenance prompt iteration (3b→3c loop) before Level 4. Hallucination rate 78% is
the blocker; keyword gap rate 22% is within target. Once hallucination <30%, proceed
to Level 4 (`scripts/validate_extraction.py`), which unblocks Level 5 (full batch).

---

## Parallelisable Work

These can be done independently of the main pipeline sequence:

- Populate `minutes_pdf_url` from manifest into meetings table (trivial — URL is in manifest.json, never written to DB)
- Populate `extracted_at` timestamp on meetings (trivial — set datetime.utcnow() in save_extraction)
- Store `minutes_text` in meetings table (small — raw text is now passed to save_extraction via `text=`; just write it to `meeting.minutes_text`)
