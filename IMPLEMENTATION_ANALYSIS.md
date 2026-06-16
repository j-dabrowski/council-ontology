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

### Level 3c: Sample Validation ✅ COMPLETE (2026-05-30)

**What was built:**
- `scripts/validate_sample.py` + `council validate-sample cambridge`.
- Reads `data/{council}_sample.json`, queries `extraction_evidence`, re-extracts PDF
  text for all matching and gap detection, loads L1 inventories for agreement comparison.
- Four metrics per doc: paraphrase rate, coverage ratio, inventory agreement, keyword gap rate.
- Determines PASS/REVIEW/FAIL per doc; writes per-doc JSON + `data/sample_validation/report.txt`
  + `data/sample_validation/paraphrase_report.txt` (per-quote detail for human/AI inspection).
- Prints rich table to stdout with colour-coded metrics.

**Quote matching — pre-processing + three tiers applied in order:**
All matching is done at validation time against the live PDF text; `char_offset` in the DB is not
used here (it is a best-effort UI convenience only, stored by `_resolve_offset()` via verbatim
`text.find()` at save time).
0. **Page header stripping** — `_strip_page_headers()` removes lines containing Windows file
   paths (`H:\...`) from raw pypdf text before any matching. Council minute PDFs (originally
   Word documents) embed a repeated header on every page (meeting title, date, file path) which
   pypdf extracts inline between page content. Stripping these lines allows quotes that span page
   breaks to match correctly and contributes their full span to coverage.
1. **Whitespace normalisation** — collapse all whitespace runs to a single space in both source
   and quote before comparing. Handles pypdf line-break newlines.
2. **Stripped matching** — remove all non-alphanumeric characters from both sides. Handles
   pypdf word-split artefacts in older PDFs where spaces are inserted mid-word
   (`"no ise"` → `"noise"`, `"provisi ons"` → `"provisions"`). Span in source is recovered
   precisely via a position-mapping array (`strip_to_norm`), so these contribute to coverage.
   Only attempted for quotes ≥15 stripped characters to avoid false positives.
3. **Paraphrase** — content genuinely differs. Collected with partial-match context
   (longest prefix of quote found in source + source text at that position) for the
   paraphrase report.

**Results (Cambridge, 2026-05-31, 18 docs) — final baselines after --max-chars full re-extraction:**
- Quote completeness: **95.0%** (target >80%) ✓
- Paraphrase rate: **4.3%** (target <30%) ✓
- Coverage ratio: **22.89%** (target >5%) ✓
- Keyword gap rate: **9.3%** (target <25%) ✓
- Status: 14 PASS / 4 REVIEW / 0 FAIL

Quote completeness metric added (2026-05-31): fraction of extracted entities with ≥1 evidence row.
Catches entities extracted with source_quotes=[] — invisible to paraphrase rate. Motions were the
main offender. PROVENANCE RULE narrowed (empty-list exception no longer applies to motions) and
explicit per-motion rule added: source_quotes must never be empty for a motion.
All 4 REVIEW docs re-extracted with `--max-chars full`; 4 remain REVIEW:
- `008af827.pdf` (2025-05-01, Public Art Committee): 74% completeness — non-standard procedural
  language (no MOVED/CARRIED), known edge case, not fixable by prompt alone.
- `060c4c87.pdf` (1995-07-25, Council Meeting): 79.9% completeness — borderline; oldest era,
  37 entities missing quotes (motions + budget_items + other_items).
- `0064743e.pdf` (2012-04-24, Council Meeting): 90% completeness, 100% kwgap (1 uncovered hit)
  — 5 chunks, 34 motions without quotes; structurally acceptable.
- `0a12261e.pdf` (2020-12-15, Ordinary Meeting): 97.8% completeness, 68% kwgap (45/66 hits
  uncovered) — 6 chunks, kwgap persists even with full extraction; likely a large doc with
  agenda items in uncovered regions between chunks.

**Next step: proceed to Level 4.**

---

## Level 4: Confidence Metrics and Validation Script ✅ COMPLETE (2026-05-31)

**What was built:**
- `src/validation/core.py` — shared validation library extracted from `validate_sample.py`.
  Contains all five Level 3c metric functions (quote completeness, paraphrase rate, coverage ratio,
  inventory agreement, keyword gap rate), the three-tier quote matching pipeline, DB helpers,
  data loaders, and `validate_doc()`. Imported by both `validate_sample.py` and
  `validate_extraction.py` — no code duplication.
- `src/validation/__init__.py` — package marker.
- `scripts/validate_extraction.py` — Level 4 per-doc confidence scorer. Extends Level 3c with:
  - **Entity density**: motions per 10k source chars. Flags Ordinary meetings with large docs
    (>50k chars) and density < 0.3 as REVIEW — likely an extraction gap.
  - **Schema completeness**: Ordinary meetings must have ≥1 motion; all motions must have
    a non-null outcome. Flags as REVIEW when violated.
  - `determine_status_l4()` combines base Level 3c status with the two new checks.
  - `validate_files(council, filenames)` — clean API used by `run()`. Returns (results, counts).
  - `get_extracted_filenames()` — queries DB for all extracted meetings for a council;
    supports `from_year`/`to_year` filtering via manifest.
  - Per-doc JSON to `data/validation/{stem}.json`. Summary to `data/validation/summary.json`.
- `council validate cambridge [--limit N] [--files ...] [--from-year YYYY] [--to-year YYYY]
  [--max-chars N|full] [--force]` — CLI entrypoint.

**Cross-document consistency** deferred — requires parsing minute confirmation text from
motion text and is disproportionate effort before batch extraction has run.

**validate_sample.py refactored** to import shared logic from `src/validation/core.py`.
Behaviour unchanged; all Level 3c output identical to pre-refactor.

**First run result (Cambridge, first 10 of 196 extracted docs):**
- 1 PASS / 3 REVIEW / 6 FAIL
- FAILs are expected: docs extracted before provenance was wired (Level 2b, 2026-05-29)
  have 0 extraction_evidence rows → completeness_rate = 0.0 → FAIL. These need re-extraction.
- Schema flags on 6 docs: 5× `_motions_null_outcome`, 1× `ordinary_meeting_no_motions`.

**Next step:** `council extract cambridge --limit 20` then `council validate cambridge` (Level 5).

---

## Level 5: Batch Extraction

**What exists:**
- `council extract cambridge --limit N` — synchronous extraction: processes N pending PDFs, writes grouped error report to `data/extraction_errors.json`, skips already-extracted docs. Supports `--from-year`, `--to-year`, `--files`, `--force`, `--max-chars`, `--dry-run`.
- `council extract cambridge --batch` — async batch mode: submits all pending PDFs to the Anthropic Message Batches API (50% off, up to 24h latency). Saves a job file to `data/batch_jobs/{batch_id}.json` and exits. Use `council batch-collect cambridge <batch_id>` to retrieve results when done.
- `council batch-collect cambridge <batch_id>` — retrieves results from a submitted batch. Groups chunk results by document, merges multi-chunk extractions, applies metadata overrides, re-reads PDFs for provenance, saves via `save_extraction()`. Writes grouped error report to `data/extraction_errors.json`.
- `council validate cambridge` — separate step run after each extract batch. Scores all newly extracted docs and writes `data/validation/summary.json`.

**Sync workflow (fast iteration):**
```bash
council extract cambridge --limit 20 --dry-run  # preview cost
council extract cambridge --limit 20
council validate cambridge
# triage REVIEW/FAIL, fix errors, scale up
council extract cambridge --limit 50
council validate cambridge
```

**Batch workflow (production, 50% off):**
```bash
council extract cambridge --max-chars full --batch --dry-run   # preview cost
council extract cambridge --max-chars full --batch             # submit; prints batch_id
# ... up to 24h later ...
council batch-collect cambridge msgbatch_abc123                # save to DB
council validate cambridge                                     # score results
```

**What the batch implementation added (2026-05-31):**
- `MinutesExtractor.build_batch_requests(pdfs, max_chars, council_name, manifest)` — reads all PDFs, splits into chunks, builds request dicts with `custom_id = "{stem}__c{i}of{n}"`.
- `MinutesExtractor.submit_batch(requests)` → `batch_id`.
- `MinutesExtractor.retrieve_batch_results(batch_id)` → `(status, {custom_id: ExtractedMeeting | Exception})`. Handles the full parsing pipeline (markdown stripping, Pydantic validation, error capture).
- `_make_user_content()` extracted as a shared helper used by both sync and batch paths.
- Job metadata persisted at `data/batch_jobs/{batch_id}.json`: includes the full `custom_id → {pdf_path, chunk_idx, n_chunks, meeting_date_hint}` mapping needed by the collect phase.

**Actual results (Cambridge, as of 2026-06-11):**
- **242 docs extracted** total: 178 minutes, 60 agendas, 4 addenda.
- **348 docs pending**: 329 minutes, 19 agendas.
- June 9 batch (`msgbatch_013dcu8czK79suJXKYvTmW9S`): 86 docs, 585 requests (full-doc, all chunks), $19.58.
- June 11 batch (`msgbatch_01TSrRKeTuz74GvByzFdzFA1`): 95 docs re-extracted with Phase 2 agenda prompt; 89 succeeded, 6 failed (see Known Issues below).
- DB totals: 1,896 motions, 4,667 votes, 189 councillors.

**Validation results (2024+ corpus, n=85, 2026-06-11 --max-chars full --force):**
- Quote completeness: 98.7% ✓ (target >80%)
- Paraphrase rate: 16.4% ✓ (target <30%)
- Coverage ratio: 10.39% ✓ (target >5%)
- Keyword gap rate: 12.9% ✓ (target <25%)
- Status: 48 PASS / 37 REVIEW / 0 FAIL

**Known issues (updated 2026-06-17):**

1. **✅ RESOLVED — ValidationError on individual vote objects (6 docs)** — `schemas.py` hardened
   with coercions for all observed model output variations: `"vote"`/`"position"` → `"choice"`;
   `"councillor"` string → split name fields; list-of-strings format (`"Cr Smith - For"`);
   `building_permits.status` synonyms (`"pending"/"granted"` → null/`"approved"`); unparseable
   `votes_for` strings (`"3/0 and 4/0"`) → null. `system_prompt.txt` clarified `"choice"` field.
   All 6 docs collected via `msgbatch_018i8noAF3cf2Q3CSmSYKBVj`: 3 PASS / 3 REVIEW / 0 FAIL.
   REVIEWs are structural artifacts (large-doc L1 mismatch, sparse keyword hits) — not quality issues.

2. **Large agenda ToC-hallucination (100% paraphrase rate)** — 7 large agenda PDFs (11–20
   chunks) were saved successfully but produce 100% paraphrase on validation. Chunk 0 of these
   documents is a table of contents; the model generates plausible-sounding source quotes for
   agenda items visible only in the ToC. Those quotes don't appear verbatim in the source text.
   Affected: `202496e2`, `2420cee0`, `34449c77`, `4e282dd3`, `68da87da`, `7242bbb8`, `936cc360`.
   Fix options: prompt instruction to not quote from ToC; ToC-chunk detection during merge;
   or accept REVIEW as a structural limitation.

**Still not built:**
- Feedback loop: after every ~100 documents, re-run Level 0 keyword scan with updated keyword list. Not automated.
- LLM response caching for the extraction path (Level 1 caches inventory calls; extraction calls are not cached).

---

## Phase 2: Document-Type-Aware Pipeline ✅ CODE COMPLETE (2026-06-11)

All code changes landed in commit `5fa9d5c`. Re-extraction partially done (see Level 5 Known Issues).

**What was built:**

- **P2-0 — Manifest backfill**: `classify_document_type()` rule (filename-based, order-sensitive)
  applied to all 590 manifest entries. Result: 507 minutes / 79 agendas / 4 addenda.
  `BaseCouncilScraper.download()` now writes `document_type` at download time going forward.

- **P2-1 — Census updates** (`scripts/census.py`): reads `document_type` from manifest; adds
  agenda keyword group (`OFFICER RECOMMENDATION`, `RECOMMENDED THAT`, `PROPOSED RESOLUTION`);
  adds `estimated_officer_recommendations` count; suppresses `no_motion_keywords` flag for
  non-minutes documents.

- **P2-2a — DB migration** (`src/models/ontology.py`):
  - `Meeting.document_type: Mapped[Optional[str]]` — values: `minutes`, `agenda`,
    `briefing_notes`, `addendum`, `unknown`, `None` (legacy).
  - `Motion.officer_recommendation: Mapped[Optional[str]]` — populated for agenda extractions.
  - Columns added via `ALTER TABLE` on `council.db` directly (no Alembic).

- **P2-2b — Pydantic schema** (`src/extraction/schemas.py`):
  - `ExtractedMeeting.document_type: Optional[Literal["minutes","agenda","briefing_notes","addendum","unknown"]]`
  - `ExtractedMotion.officer_recommendation: Optional[str]`

- **P2-2c — Agenda system prompt** (`src/extraction/agenda_system_prompt.txt`):
  Same structure as `system_prompt.txt`. Key differences: opening frames extraction as
  "from a council meeting agenda — the meeting has not yet taken place"; populates
  `officer_recommendation` instead of `outcome`; leaves `outcome`, `moved_by`,
  `seconded_by`, `individual_votes` null. PROVENANCE RULE unchanged. All other
  entity types extracted identically.

- **P2-2d — Extractor** (`src/extraction/extractor.py`):
  `agenda_system_prompt.txt` loaded at module level. `extract()`, `extract_from_pdf()`,
  and `build_batch_requests()` accept `document_type: str | None`. Prompt selection:
  `agenda/addendum/briefing_notes → agenda_system_prompt.txt`, else `system_prompt.txt`.
  `save_extraction()` writes `document_type` to `Meeting.document_type` and
  `officer_recommendation` to `Motion.officer_recommendation`.
  `src/cli.py`: `cmd_extract` and `cmd_batch_collect` read `document_type` from manifest
  and pass it through to extractor and `save_extraction()`.

- **P2-3 — Validation** (`src/validation/core.py`):
  `GAP_KEYWORDS_AGENDA` dict added (replaces `MOVED`/`DECLARATION OF INTEREST` with
  `OFFICER RECOMMENDATION`/`RECOMMENDED THAT`). `determine_status()` accepts
  `document_type`; for agendas: skips coverage-based FAIL and coverage REVIEW trigger,
  skips `quote_count == 0 → FAIL` check. `compute_keyword_gaps()` accepts
  `gap_keywords` parameter; `validate_doc()` passes `GAP_KEYWORDS_AGENDA` for agenda docs.
  `scripts/validate_extraction.py`: `compute_schema_completeness()` skips
  `motions_null_outcome` and `ordinary_meeting_no_motions` flags for agendas.
  `determine_status_l4()` skips entity-density check for agendas.

**P2-4 — Re-extraction results** (2026-06-11):
- Batch `msgbatch_01TSrRKeTuz74GvByzFdzFA1`: 95 docs, 89 succeeded, 6 failed.
- Validation of 2024+ corpus (n=85): 48 PASS / 37 REVIEW / 0 FAIL. All 4 aggregate metrics
  within target. REVIEWs decompose into: 7 large agendas with ToC-hallucination (structural
  limitation), 6 failed docs needing re-extraction after schema fix, remainder are minutes with
  `motions_null_outcome` or keyword gap flags.

---

## Level 6: Audit

**Already exists:**
- `council compare <pdf>` gives multi-model comparison for individual PDFs.

**Can be composed now:**
- Manual audit using `council extract --files <list>` on a random sample, then hand-comparing PDFs to DB records.
- `council validate cambridge --files <list>` to score the audited subset.

**Needs new work:**
- Audit report generator: select N random documents from the extracted set, pull their extractions, format for human review.
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
| 9 | Level 4: `scripts/validate_extraction.py` (per-doc confidence scorer) | Level 3c | Medium | **Done** (2026-05-31) |
| 10 | Phase 2: document-type-aware extraction + validation | Level 4 | Medium | **Done** (2026-06-11) — code; re-extraction complete (2026-06-17) |
| 11 | Fix `individual_votes.choice` schema error (6 docs) | Phase 2 | Small | **Done** (2026-06-17) — schema hardened; all 6 collected and validated |
| 12 | Fix large-agenda ToC-hallucination (7 docs) | Phase 2 | Medium | **Pending** — prompt or merge fix |
| 13 | Level 5: extract remaining 347 docs (329 minutes + 18 agendas) | Phase 2 | Small | **Pending** |
| 14 | Level 6: audit report generator | Level 5 | Small | **Pending** |

**Current critical path:** Level 5 batch extraction of remaining 347 pending documents.

---

## Cost Estimation Tooling ✅ COMPLETE (2026-05-31)

**What was built:**
- `src/cost_estimator.py` — shared estimation module used by all three command paths.
  - `estimate_extraction(pdfs, max_chars, model_key, census)` and `estimate_inventory(pdfs, census)` return a `CostEstimate` dataclass.
  - Uses `census.json` char counts — no PDF re-reads. Runtime ~1 second vs ~4 minutes previously.
  - Output tokens estimated by census size bucket (`tiny→2.5k`, `small→6k`, `medium→12k`, `large→18k` tokens) rather than a flat 64k worst-case. The 64k assumption was a **4.9× overestimate** on the Cambridge pending corpus.
  - Multi-chunk full-document extraction (`--max-chars full`) correctly estimates n_chunks via ceiling division and scales both input overhead and output tokens per chunk.
  - `format_preflight(estimate)` returns a compact Rich-formatted string for inline display.

- **Pre-flight banners** added to `cmd_extract` (in `cli.py`) and `inventory.run()` (in `scripts/inventory.py`). Shown automatically before any API call; non-blocking. Respects all filters (`--limit`, `--files`, `--from-year`) so the estimate always matches exactly what's about to run.

- **`--dry-run` flag** added to `council extract`, `council extract-sample`, and `council inventory`. Shows the cost estimate and exits without making any API calls — replaces needing to manually cross-reference `council costs` before a run.

- **`estimate_costs.py` rewritten** to use `src.cost_estimator`:
  - Now covers both inventory and extraction stages in a single run.
  - Highlights the currently-configured model with `*` in the model table.
  - `--force` flag shows cost for the full corpus (all docs), as if running with `--force` — useful for planning a from-scratch re-extraction.
  - Batch pricing annotation: `(50% off, up to 24h)`.

---

## Parallelisable Work

These can be done independently of the main pipeline sequence:

- Populate `minutes_pdf_url` from manifest into meetings table (trivial — URL is in manifest.json, never written to DB)
- Populate `extracted_at` timestamp on meetings (trivial — set datetime.utcnow() in save_extraction)
- Store `minutes_text` in meetings table (small — raw text is now passed to save_extraction via `text=`; just write it to `meeting.minutes_text`)
