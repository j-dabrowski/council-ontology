# Council-Ontology Extraction Pipeline: Master Plan

## Overview

This document defines the multi-level extraction pipeline for processing council meeting minutes PDFs into structured, auditable data. The core principle is **recursive refinement**: cheap broad passes feed expensive deep passes, and every pass validates the one after it. No blind extraction. By the time a document hits the full LLM call, we already know what it contains, what we expect to get back, and how to verify it.

Current state: 537 downloaded PDFs for Town of Cambridge (1995-2026). 196 ingested. 341 pending.

---

## Pipeline Status

### Phase 1 — Minutes-only extraction (original)

| Level | Description | Status |
|-------|-------------|--------|
| 0 | Census: text extraction + keyword scan | **Done** (2026-05-28) |
| 1 | Cheap LLM inventory (Haiku, $4.83 actual) | **Done** (2026-05-28) |
| 2 | Schema and prompt revision | **Done** (2026-05-29) |
| 3a | Sample selection (`council sample`) | **Done** (2026-05-30) |
| 3b | Sample extraction (`council extract-sample`) | **Done** (2026-05-30) |
| 3c | Sample validation (`council validate-sample`) | **Done** (2026-05-30) — all metrics within target |
| 4 | Confidence metrics and validation script | **Done** (2026-05-31) |
| 5 | Batch extraction (~$7-20) | **Done** (2026-06-09) — 86 docs, $19.58 batch |
| 6 | Human audit | Pending |

### Phase 2 — Document-type-aware pipeline upgrade

The scraper now downloads **both** agendas and minutes per meeting (as of 2026-06-09). Phase 1
validation applied minutes-only metrics to all documents, producing misleading FAILs and REVIEWs
on agendas, which structurally cannot have vote outcomes. Phase 2 makes every pipeline stage
aware of document type so agendas are extracted and validated correctly in their own right.

| Step | Description | Status |
|------|-------------|--------|
| P2-0 | `classify_document_type()` — backfill manifest + census | **Pending** |
| P2-1 | Census updates — agenda keyword group, type-aware flags | **Pending** |
| P2-2a | DB migration — `meetings.document_type`, `motions.officer_recommendation` | **Pending** |
| P2-2b | Pydantic schema — `document_type` on `ExtractedMeeting`, `officer_recommendation` on `ExtractedMotion` | **Pending** |
| P2-2c | Agenda extraction prompt — `agenda_system_prompt.txt` | **Pending** |
| P2-2d | Extractor — prompt selection by type; write `document_type` to DB | **Pending** |
| P2-3 | Validation — branch `determine_status`, `GAP_KEYWORDS`, schema completeness by type | **Pending** |
| P2-4 | Re-extract agendas with agenda prompt; re-validate full 2024+ corpus | **Pending** |
| P2-5 | Inventory prompt variant for agendas (Level 1) | **Pending** |
| P2-6 | Sample selection stratified by document type (Level 3a) | **Pending** |

Steps P2-0 through P2-4 are interdependent and should land together.
P2-5 and P2-6 are independent improvements that can follow.

---

## Phase 2 Detail: Document-Type-Aware Pipeline Upgrade

### Background and motivation

The Cambridge website accordion returns both an agenda PDF and a minutes PDF per meeting.
The scraper fix (2026-06-09) now collects all PDFs. This means the DB contains:
- **Minutes** — voted outcomes, MOVED/CARRIED language, complete political record
- **Agendas** — officer recommendations, proposed resolutions, planning assessments, budget detail (no vote outcomes — the meeting hasn't happened yet from the agenda's perspective)
- **Briefing forum notes** — discussion summaries, no formal motions
- **Addenda** — late-added agenda items, same structure as agendas

Agendas are valuable: they let you compare what officers *recommended* vs what councillors *decided*, and carry richer planning and budget context than the brief minute entries.

Validation results as of 2026-06-09 (n=54, 2024+):
- 14 PASS / 31 REVIEW / 9 FAIL — degraded from pre-scrape-fix 7 PASS / 35 REVIEW / 1 FAIL
- 5 of the 9 FAILs are agenda PDFs being judged by minutes metrics
- Most REVIEWs are also agendas or committee docs with non-standard language

### P2-0: Document type classification

**Files:** `src/scraper/base.py` (download), `scripts/census.py`, manifest entries

Classification rule (apply in order, case-insensitive, against the PDF filename only — not the full URL path):

| Filename contains | `document_type` |
|---|---|
| `minutes` | `minutes` |
| `agenda` | `agenda` |
| `addendum` | `addendum` |
| `briefing-forum`, `briefing-notes`, `briefing_forum`, `briefing_notes` | `briefing_notes` |
| anything else | `unknown` |

**Backfill:** One-off script to classify all existing manifest entries and rewrite `census.json`.
**Going forward:** `BaseCouncilScraper.download()` infers and writes `document_type` into the manifest entry at download time.

### P2-1: Census updates

**File:** `scripts/census.py`

- Read `document_type` from manifest; include it in each census record.
- Add agenda-specific keyword group:
  ```python
  "agenda": {
      "OFFICER RECOMMENDATION": r"OFFICER RECOMMENDATION",
      "RECOMMENDED THAT":       r"RECOMMENDED THAT",
      "PROPOSED RESOLUTION":    r"PROPOSED RESOLUTION",
  }
  ```
- Suppress `no_motion_keywords` flag when `document_type in ('agenda', 'briefing_notes', 'addendum', 'unknown')`.
- Add `estimated_officer_recommendations` derived count (from `OFFICER RECOMMENDATION` + `RECOMMENDED THAT` hits) alongside `estimated_motions`.

### P2-2a: DB migration

**File:** `src/models/ontology.py`

Add to `Meeting`:
```python
document_type: Mapped[Optional[str]] = mapped_column(String(20))
# values: 'minutes', 'agenda', 'briefing_notes', 'addendum', 'unknown', None (legacy)
```

Add to `Motion`:
```python
officer_recommendation: Mapped[Optional[str]] = mapped_column(Text)
# Populated for agenda extractions: what the officer recommended before the vote.
# Null for minutes (outcome is the authoritative field instead).
```

Run migration with `ALTER TABLE` on `council.db` directly (SQLite; no Alembic in this project).

### P2-2b: Pydantic schema updates

**File:** `src/extraction/schemas.py`

Add to `ExtractedMeeting`:
```python
document_type: Optional[Literal["minutes", "agenda", "briefing_notes", "addendum", "unknown"]] = None
```

Add to `ExtractedMotion`:
```python
officer_recommendation: Optional[str] = None
# For agenda extractions: the officer's recommended resolution text.
```

### P2-2c: Agenda extraction prompt

**New file:** `src/extraction/agenda_system_prompt.txt`

Same overall structure as `system_prompt.txt` with these differences:
- Opening: "You are extracting from a **council meeting agenda** (not minutes). The meeting has not yet taken place. Extract what officers *propose*, not what councillors *decided*."
- `document_type`: always output `"agenda"` (or `"addendum"` if the document is an addendum).
- Motions: populate `officer_recommendation` (the recommended resolution text) instead of `outcome`. Leave `outcome`, `moved_by`, `seconded_by`, `individual_votes` null/empty.
- All other entity types (planning applications, public questions, deputations, petitions, budget items, interest declarations, tenders, delegated decisions, building permits) extracted identically.
- PROVENANCE RULE applies unchanged.

A separate `briefing_notes_system_prompt.txt` is optional — the agenda prompt works for briefing forums too since both lack vote outcomes. Add only if quality testing shows a gap.

### P2-2d: Extractor updates

**File:** `src/extraction/extractor.py`

- Load `agenda_system_prompt.txt` alongside `system_prompt.txt` at module level.
- `MinutesExtractor.extract()`, `extract_from_pdf()`, and `build_batch_requests()` accept `document_type: str | None = None`.
- Select system prompt: `agenda/addendum/briefing_notes → agenda_system_prompt.txt`, everything else → `system_prompt.txt`.
- `save_extraction()`: write `document_type` to `Meeting.document_type`; write `officer_recommendation` to `Motion.officer_recommendation`.

**File:** `src/cli.py` (and `scripts/batch_extract.py` if separate)
- When building the extraction job list, read `document_type` from manifest and pass it to the extractor.

### P2-3: Validation updates

**File:** `src/validation/core.py`

`GAP_KEYWORDS` — split into per-type sets:
```python
GAP_KEYWORDS_MINUTES = {
    "MOVED": r"\bMOVED\b",
    "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
    "DECLARATION OF INTEREST": r"DECLARATION OF INTEREST",
    "DEPUTATION": r"\bDEPUTATION\b",
    "PETITION": r"\bPETITION\b",
}
GAP_KEYWORDS_AGENDA = {
    "OFFICER RECOMMENDATION": r"OFFICER RECOMMENDATION",
    "RECOMMENDED THAT": r"RECOMMENDED THAT",
    "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
    "DEPUTATION": r"\bDEPUTATION\b",
    "PETITION": r"\bPETITION\b",
}
GAP_KEYWORDS_BRIEFING = {
    "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
}
```

`determine_status()` — accept `document_type` and branch:
- **minutes / unknown**: existing rules unchanged.
- **agenda / addendum**: remove `quote_count == 0 → FAIL` (empty agenda items are possible); remove `completeness_rate < 0.50 → FAIL` (outcomes are structurally absent, completeness denominator is misleading); keep paraphrase rate and coverage checks.
- **briefing_notes**: only flag FAIL on paraphrase rate ≥ 0.80 and coverage < 0.01 (very light — these are discussion docs).

`validate_doc()` — read `document_type` from the DB meeting record; pass it through to `determine_status()` and `compute_keyword_gaps()`.

**File:** `scripts/validate_extraction.py`

`compute_schema_completeness()`:
- For `document_type in ('agenda', 'addendum', 'briefing_notes')`: skip `ordinary_meeting_no_motions` and `motions_null_outcome` flags entirely.
- For agendas: optionally add a light check — if the meeting has > 5 agenda items but all have `officer_recommendation IS NULL`, flag `agenda_missing_recommendations`.

`determine_status_l4()`:
- Pass `document_type` through; skip the entity-density check for agendas (density is meaningless without formal motions).

### P2-4: Re-extract and re-validate

After P2-0 through P2-3 are implemented:

1. Re-extract all 2024+ **agenda** documents with the new prompt:
   ```
   council extract cambridge --from-year 2024 --max-chars full --force --batch
   ```
   (Only agenda PDFs will use the new prompt; minutes re-extraction is optional unless `--force` is passed.)

2. Re-validate:
   ```
   council validate cambridge --from-year 2024 --max-chars full --force
   ```

3. Target outcomes:
   - Minutes: > 20 PASS, < 10 REVIEW (most legitimate REVIEWs are committee meetings with non-standard language)
   - Agendas: > 80% PASS (they are structurally simpler — officer recommendations are consistent)
   - Overall FAILs: < 5 (extraction or PDF errors only)

### P2-5: Inventory prompt variant (Level 1)

**File:** `src/extraction/inventory_prompt.txt` (or a new `agenda_inventory_prompt.txt`)

For agendas, the inventory should ask for `officer_recommendation_count` instead of `motion_count`. This matters for new councils where the inventory convergence loop (other_content_rate ≤ 20%) runs before extraction. Low priority for Cambridge where Level 1 is already complete.

### P2-6: Sample selection by document type (Level 3a)

**File:** `scripts/stratified_sample.py`

Add `document_type` as a stratification axis. Guarantee the sample contains at least:
- 3 minutes (Ordinary Council Meeting)
- 2 agendas (Ordinary Council Meeting)
- 1 briefing forum notes
- 1 special meeting (minutes or agenda)

Or maintain separate sample files: `data/cambridge_minutes_sample.json` and `data/cambridge_agenda_sample.json`.

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

## Level 5: Batch Extraction (main cost, ~$7–20 standard / ~$3–10 batch)

Full extraction across entire corpus. Two modes:

**Sync mode** — fast iteration in batches of 20:
```bash
council extract cambridge --limit 20 --dry-run   # preview cost
council extract cambridge --limit 20             # extract
council validate cambridge                       # score
# triage REVIEW/FAIL, fix errors, scale up
council extract cambridge --limit 50
council validate cambridge
```

**Batch mode** — 50% off, async (up to 24h), good for the full corpus:
```bash
council extract cambridge --max-chars full --batch --dry-run   # preview: ~$133 vs ~$267
council extract cambridge --max-chars full --batch             # submit; prints batch_id
# ... wait up to 24h ...
council batch-collect cambridge msgbatch_abc123                # parse + save to DB
council validate cambridge                                     # score all results
```

### Batch implementation (done 2026-05-31)
- `council extract --batch` submits all pending PDFs to the Anthropic Message Batches API.
  Multi-chunk documents (`--max-chars full`) produce one request per chunk with `custom_id = "{stem}__c{i}of{n}"`.
  Job metadata (including the custom_id → PDF mapping) persisted to `data/batch_jobs/{batch_id}.json`.
- `council batch-collect <council> <batch_id>` polls status, retrieves results, merges chunks, and
  calls `save_extraction()` with full provenance (re-reads PDF text for char-offset resolution).
- `MinutesExtractor` new methods: `build_batch_requests()`, `submit_batch()`, `retrieve_batch_results()`.
  `_make_user_content()` extracted as shared helper for both sync and batch paths.

### Tasks
- After each sync batch or after `batch-collect`, run `council validate cambridge` and triage:
  - PASS → continue
  - REVIEW → spot-check 2-3 per batch; adjust thresholds if false positives
  - FAIL → identify error class in `data/extraction_errors.json`, fix prompt/schema/parsing, re-extract
- After every 100 documents: re-run Level 0 keyword detection with any new keywords discovered.
- Note: pre-Level-2b extractions already in DB (196 docs) will fail Level 4 (no extraction_evidence). Re-extract with `--force` to populate provenance.

### Output
- All documents extracted with per-document confidence scores.
- `data/extraction_errors.json`: structured error log grouped by error class.
- `data/batch_jobs/{batch_id}.json`: batch job metadata and chunk mapping.

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

## Level 7: Production Run (optional, ~$10–40 on Sonnet batch)

If Haiku extraction quality was insufficient, re-extract on a stronger model.

### Tasks
- Run 10 documents on Sonnet (standard API) to check for new edge cases from richer output.
  Change `_MODEL` in `src/extraction/extractor.py` to `claude-sonnet-4-6`.
- If clean, submit full corpus via batch: `council extract cambridge --max-chars full --force --batch`.
  Note: batch mode disables adaptive thinking (requires streaming); Sonnet batch uses no thinking parameter.
- Re-run `council validate cambridge --force` on all results.
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
