# Council-Ontology Data Pipeline — Plan, Build Log & Status

> **Consolidated doc.** This merges the former `PIPELINE.md` (plan + principles),
> `IMPLEMENTATION_ANALYSIS.md` (as-built record + dependency graph), and the
> analysis-query design reference from `ANALYSIS_ROADMAP.md`. Three sections,
> top to bottom: **the plan** (below), **the build log**, and **the analysis
> query layer**. The pipeline is complete, so plan and as-built have converged.
> See `../MAP.md` for how this track relates to the investigator and frontend tracks.

## Overview

This document defines the multi-level extraction pipeline for processing council meeting minutes PDFs into structured, auditable data. The core principle is **recursive refinement**: cheap broad passes feed expensive deep passes, and every pass validates the one after it. No blind extraction. By the time a document hits the full LLM call, we already know what it contains, what we expect to get back, and how to verify it.

Current state: 613 PDFs in manifest (Cambridge, 1995–2026, cleaned 2026-06-22). 580 extracted (506 min/66 agenda/4 addendum/4 unknown). Full corpus complete.

**Current strategy (as of 2026-06-23):** Full corpus extracted. Pre-2024 batch complete.
Council Setup (terms seeding + dedup) complete. 14,013 motions / 16,249 votes / 405 councillors.
Phase C cleanup (build-relationships, geocode) and Level 6 human audit are the immediate next steps.
LLM response archive system added (2026-06-23) — all future extraction runs automatically archive
raw API responses to `data/llm_archive/` for deterministic DB rebuilding. All 12 historical batches
retroactively downloaded (3,358 chunk files, 66 MB). Archive covers the full DB.

**Schema fixes applied during pre-2024 batch (2026-06-22):**
- `ExtractedCommunitySubmission.position`: added synonym map ("objection" → "object", "in support" → "support", etc.) + null fallback for unknowns — previously caused ValidationError on 3 docs
- `ExtractedPlanningApplication.status`: added synonym map + null fallback for unknowns — previously caused ValidationError on 2 docs
- `system_prompt.txt` motion outcome rule: added RECEIVED/NOTED/ACCEPTED/ENDORSED → "carried" mapping

## Next Steps (as of 2026-06-23)

### ✅ Phase A — Prepare — DONE
### ✅ Phase B — Pre-2024 batch extraction — DONE (580 meetings total; 506 min/66 agenda/4 addendum/4 unknown)
### ✅ Council Setup — Terms seeding + dedup — DONE (58 terms imported; 405 councillors after 83 merges)

### Phase C — Post-extraction cleanup (immediate)

```bash
council build-relationships cambridge --all-years   # refresh ALLY/OPPONENT edges with full corpus
council geocode cambridge                           # geocode planning sites from pre-2024 docs
```

Then run all analysis queries without `--from-year` to see 30-year trends.

### Phase D — Level 6 human audit

```bash
council audit cambridge --count 20 --all-years --seed 42
# Open data/audit_report.md alongside each PDF and fill in AUDIT: [Y/N/PARTIAL] annotations
```

### Phase E — Gap recovery (parallel, low urgency)

Email admin@cambridge.wa.gov.au requesting missing minutes for 2022 Jan/Feb/Mar/Apr/Jun and
2023 Jan/Feb/Mar/Apr/Jun/Jul (WA Local Government Act 1995 s.5.22). If no response in 4 weeks,
lodge FOI via foi@cambridge.wa.gov.au. If PDFs are obtained: drop into data/raw/cambridge/,
run `council census cambridge`, then extract with `--files`.

**[ ] Agenda coverage — SCOPED 2026-06-24 (INVESTIGATIONS [24]). Conclusion: the live
scrape is largely a dead end; the real unlock is finance-aware RE-EXTRACTION of minutes.**

Findings from scoping the scrape:
- The Playwright scraper (`src/scraper/cambridge.py`) already collects *all* meeting-document
  PDFs per OpenCities accordion item (agenda + minutes both, where the CMS lists them) — it is
  NOT the bottleneck. 66 agendas (2021–2026) are already captured and extracted; 42 dates have
  both an agenda and minutes.
- **The CMS only publishes agendas from 2021 onward** (1 in 2021 → 8/8/14/22/13 through 2026).
  There are NO pre-2021 agendas online. So re-running the live scrape yields ~zero new agendas.
- Therefore agendas CANNOT help [24]'s critical window: the portfolio peak ($73M, Apr 2018) and
  most of the drawdown (2018–2021) predate any available agenda. My earlier note overstated the
  agenda payoff for [24] — corrected here.

What WOULD make [24] buildable (and is the better investment):
1. **Finance-aware re-extraction of EXISTING minutes** (1995–2026). The monthly "Investment
   Schedule" and budget-review reports are already in the minutes — but as free text in
   `budget_items.description`. Re-extract into typed fields (report-as-at date, fund_type =
   municipal/reserve/endowment-lands/trust, balance, and reserve-transfer transactions with
   from/to/amount/purpose). This densifies the series enough to normalise to EOFY and to
   classify drawdowns as planned vs distress — the actual [24] crux. See DATA_ENRICHMENT.md #1.
2. **2021+ agendas** (already in DB) give forward-looking officer rationale for the recent tail
   only. Marginal for [24]; more useful for the officer-capture genre (DATA_ENRICHMENT.md #3).

Pre-2021 agenda avenues (low priority, low yield): Wayback CDX (same path that returned nothing
for the 2022–23 minutes gap; council likely never published pre-2021 agendas) or FOI to the
council. Not worth pursuing for [24].

Hygiene if agendas are ever widened: **dedup agenda vs minutes for the same month's report** so
the same Investment Schedule isn't double-counted; carry existing agenda-contamination filtering.

### Known dedup gaps (not blocking; will self-resolve with more data)

The following councillor ambiguities remain after dedup and are documented for future resolution.
None affect the 2024+ corpus (all current-serving councillors are fully resolved).

**Ambiguous family-only stubs** — multiple candidates share a surname and none have term records.
Will resolve once pre-2024 votes are attributed during Phase C and future extraction runs:
- ` Everett` (234 votes) — Ian / Julian / Graham / Rod Everett — none with terms
- ` McKerracher` (259 votes) — Kate / Margaret / James / Kerry McKerracher — none with terms
- ` Steele` (50 votes + 2 `name unknown` variants) — Ian vs David Steele — neither has terms

**Fuzzy single-candidate, no term confirmation** — single close-match candidate exists but has
no electoral record to confirm. Low stakes (0–2 votes each); leave as stubs until pre-2024
extraction provides vote dates that can confirm the match:
- ` Robert` → J Roberts (92% name match, 0 votes)
- ` Peters` → Eric Peterson (86% match, 0 votes)
- ` McAlister` → Jo McAllister (95% match, 2 votes)

**Same-person under different first-name forms** — requires manual merge; not auto-detectable
without a nickname dictionary:
- Kate Barlow (id=2, terms from 2023) and Catherine Barlow (id=79, terms from 2019) are the
  same councillor. Merge id=79 → id=2 once confirmed. Check via:
  ```bash
  sqlite3 data/council.db "SELECT id, given_name, family_name FROM councillors WHERE family_name='Barlow' ORDER BY id"
  ```

**2017 terms gap** — no Cambridge election results for 2017 (absent from statewide PDF).
Seats up were O'Connor and Grinceri (Coast) and MacRae and King (Wembley) from the 2013 cohort.
To fill: check Elections WA for a Cambridge-specific 2017 notice PDF, or contact the Town directly.

### Phase E — Website data refresh (programmatic)

**Done (2026-06-23).** `council publish cambridge` exports six static JSON snapshots to
`frontend/public/data/` which the React frontend reads directly (no live API needed).

Snapshots: `interests`, `divergence`, `co-movers`, `alignment`, `trends`, `engagement`,
plus a `manifest.json`. Each file has `{"published_at": "<ISO>", "data": ...}`.

Run after any pipeline step that changes analysis results (build-relationships, new batch, etc.):

```
council publish cambridge
```

Pipeline steps (dedup, build-relationships, geocode) must be run separately beforehand.

### Longer term

- **Prompt generalisation review (prerequisite for second council)**: before
  running the pipeline on any new council, conduct a read-through of all LLM-facing
  prompts — `src/extraction/system_prompt.txt`, `src/extraction/agenda_system_prompt.txt`,
  `Investigator_prompt.txt`, and `src/extraction/inventory_prompt.txt` — and remove or
  generalise any Cambridge-specific references (place names, thresholds, heuristics,
  examples). Prompts should refer to "the council", "this jurisdiction", "the documents"
  rather than naming Cambridge. Also verify that `src/analysis/tests.py` battery test_ids
  and valences make sense for a different council type (metro vs regional, WA vs other
  state). Only after this review is complete should the pipeline be pointed at a new council.

- **Second council**: add 2 lines to `COUNCILS` dict in `cli.py` + new `src/scraper/<council>.py` subclass; all pipeline commands work automatically; **also run Council Setup (see below) for terms seeding before Level 0**

---

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
| 5 | Batch extraction (~$7-20) | **Done** — full corpus complete (2026-06-22); 580 total extracted (506 min/66 agenda/4 addendum/4 unknown); 14,013 motions / 16,249 votes / 405 councillors |
| 6 | Human audit | **Tooling done** (2026-06-18) — report generator built; human review pending |

### Phase 2 — Document-type-aware pipeline upgrade

The scraper now downloads **both** agendas and minutes per meeting (as of 2026-06-09). Phase 1
validation applied minutes-only metrics to all documents, producing misleading FAILs and REVIEWs
on agendas, which structurally cannot have vote outcomes. Phase 2 makes every pipeline stage
aware of document type so agendas are extracted and validated correctly in their own right.

| Step | Description | Status |
|------|-------------|--------|
| P2-0 | `classify_document_type()` — backfill manifest + census | **Done** (2026-06-11) |
| P2-1 | Census updates — agenda keyword group, type-aware flags | **Done** (2026-06-11) |
| P2-2a | DB migration — `meetings.document_type`, `motions.officer_recommendation` | **Done** (2026-06-11) |
| P2-2b | Pydantic schema — `document_type` on `ExtractedMeeting`, `officer_recommendation` on `ExtractedMotion` | **Done** (2026-06-11) |
| P2-2c | Agenda extraction prompt — `agenda_system_prompt.txt` | **Done** (2026-06-11) |
| P2-2d | Extractor — prompt selection by type; write `document_type` to DB | **Done** (2026-06-11) |
| P2-3 | Validation — branch `determine_status`, `GAP_KEYWORDS`, schema completeness by type | **Done** (2026-06-11) |
| P2-4 | Re-extract agendas with agenda prompt; re-validate 2024+ corpus | **Done** (2026-06-20) — all 6 failures resolved; 2024+ corpus complete; 57 PASS/30 REVIEW/0 FAIL |
| P2-5 | Inventory prompt variant for agendas (Level 1) | **Pending** (low priority) |
| P2-6 | Sample selection stratified by document type (Level 3a) | **Pending** (low priority) |

P2-5 and P2-6 are independent improvements that can follow the main pipeline.

### Known Corpus Gaps (Cambridge, confirmed 2026-06-22)

`council scraper-audit cambridge` reports these years below the completeness quota.
All gaps were investigated via Playwright re-scrape, Wayback CDX, and direct URL
probing before being declared unrecoverable from online sources.

**2022 — missing Jan, Feb, Mar, Apr, Jun (13 meeting dates total vs expected ~18)**

*Speculated cause:* Cambridge migrated from static HTML meeting pages (reliably
indexed in their sitemap up to 2021) to a JS-rendered OpenCities CMS around
May 2022. Meetings published before the migration were on the old system and were
not carried into the new CMS. Wayback Machine has no crawl of the old pages for
Jan–Jun 2022 (the site was behind Akamai CDN that Wayback's crawler could not
access). The CMS year-filter (used by the Playwright scraper) returns nothing for
those months.

**2023 — missing Jan, Feb, Mar, Apr, Jun, Jul (11 meeting dates total vs expected ~18)**

*Speculated cause:* The CMS transition effects appear to have extended into H1
2023. The Playwright scraper finds no meetings in the new accordion for those
months, and Wayback has no archived records either.

**Minor single-month absences (below quota threshold, not investigated further)**
- 1995: Feb–Mar missing — start of archive; earliest digitised record is April 1995.
- 2006: Nov missing — likely the council did not hold an ordinary meeting that month.
- 2017: Feb missing — same; single-month gaps at this level are within normal schedule variation.
- All years: Jan missing — Cambridge council traditionally does not hold ordinary meetings in January.

**Recovery options (attempt in order before accepting gap)**

1. **Manual browser check** — Open `https://www.cambridge.wa.gov.au/About/Town-Council/Agendas-Minutes`
   in a browser, select the failing year from the dropdown, and count meetings shown. If the site
   shows meetings for the missing months that the scraper missed, re-inspect the form element names
   via DevTools (`ctl11$ctl00$ctl18$ctl00$ctl00` was the selector as of 2026-04).

2. **Council website search** — Search `site:cambridge.wa.gov.au "council meeting" "minutes" "february 2022"`
   or browse any separate "archive" or "past meetings" section outside the main accordion page.

3. **Contact the council directly** — Under WA Local Government Act 1995 s.5.22, councils must make
   minutes available for public inspection. The Records Officer can provide digital copies.
   - Phone: (08) 9347 6000
   - Email: admin@cambridge.wa.gov.au
   - Request: *"Digital copies of Ordinary Council Meeting minutes for [months/year] that do not
     appear to be published on the council website."*

4. **Freedom of Information (FOI)** — If the council does not respond or claims the records are not
   publicly available, lodge a FOI request under WA Freedom of Information Act 1992 via
   foi@cambridge.wa.gov.au.

`council scraper-audit cambridge` will print these instructions automatically when gaps are detected.
`council wayback-fill cambridge 2022 2023 --months 1-7` re-runs the CDX search if needed.

---

### Known Issues / Blockers (as of 2026-06-20)

**Issue 1 — ✅ RESOLVED (2026-06-17): ValidationError on individual vote objects (6 docs)**

`schemas.py` hardened with multiple coercions: `"vote"`/`"position"` → `"choice"` field remapping;
`"councillor"` single string → split name fields; list-of-strings vote format (`"Cr Smith - For"`);
`building_permits.status` synonym map (`"pending"/"granted"` → null/`"approved"`); unparseable
`votes_for` strings (`"3/0 and 4/0"`) → null. `system_prompt.txt` clarified `"choice"` field name.
All 6 docs collected and validated: 3 PASS / 3 REVIEW / 0 FAIL. REVIEWs are structural artifacts
(large-doc L1 inventory mismatch, sparse keyword hits) — not extraction quality problems.

**Issue 2 — ✅ RESOLVED (2026-06-20): interest_type ValidationError (`"author_subject_to_policy"`)**

LLM returned non-standard interest type string from a WA Author Interest declaration. Fixed via
`ExtractedInterestDeclaration.normalise_lower` validator: unknown values coerced to `"other"`.

**Issue 3 — ✅ RESOLVED (2026-06-20): Phantom pending docs (date+type already in DB)**

Cambridge has multiple PDFs per meeting date (agenda + minutes). The pre-2024 extraction had set
`minutes_pdf_path` to one filename; a subsequent extraction of the other PDF for the same meeting
wrote a new path, orphaning the original — or left the row with a mismatched path. This caused
14 meetings to appear pending even though they were already extracted.

Two fixes applied to `cli.py`:
1. `save_extraction()` in `extractor.py` always updates `minutes_pdf_path` (removed the `not
   meeting.minutes_pdf_path` guard).
2. Pre-filter in `cmd_extract` now checks both filename AND (date+meeting_type) in DB before
   flagging a PDF as pending. If the date+type already exists, the PDF is treated as done.

**Issue 4 — ✅ RESOLVED (2026-06-20): Batch submission subprocess deadlock / pypdf timeout**

`council extract --batch` previously used a `ThreadPoolExecutor(max_workers=1)` for PDF text
extraction in the batch-build phase. PyMuPDF (fitz) hangs indefinitely in worker threads for some
malformed PDFs — threads cannot be killed, so the entire batch build hung.

Fixes:
- Switched to per-PDF `multiprocessing.Process` with `terminate()` / `kill()` on timeout.
- Subprocess uses only pypdf (first) then fitz (fallback) — no Anthropic client import.
- Queue deadlock prevented: `q.get(timeout=...)` called BEFORE `p.join()` so the parent drains
  the pipe before waiting on the child.
- Request building (Anthropic client, prompt construction) stays in the main process via the new
  `build_requests_from_text()` method on `MinutesExtractor`.

**Issue 5 — Large agenda ToC-hallucination (7 docs, REVIEW status)**

Large agenda PDFs (800k–1.5M chars, 11–20 extraction chunks) show high paraphrase on validation.
Root cause: chunk 0 is a table of contents; model generates quotes for items not yet seen in body.

Affected docs: `202496e2`, `2420cee0`, `34449c77`, `4e282dd3`, `68da87da`, `7242bbb8`,
`936cc360` (all 2024–2026 agendas, all "large" size bucket).

Fix applied: `agenda_system_prompt.txt` updated with rule ("do not quote from the table of
contents"). These 7 docs remain REVIEW until re-extracted; data is usable for analysis.

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

## Council Setup: Terms Seeding (run once per council, before Level 0)

Populates `councillor_terms` with ward, role, and term dates from electoral commission
records. This is ground truth that all downstream steps depend on:
- Councillor deduplication (`scripts/dedup_councillors.py`) uses term coverage to
  distinguish same-name councillors across eras and to confirm merges
- Relationship building (`council build-relationships`) needs accurate term windows
  to assign voting behaviour to the correct councillor
- Analysis queries can filter to "sitting councillors" for any given meeting date

**Do this before running Level 0 on any new council.**

### WA councils — Elections WA statewide reports

Elections WA publishes statewide PDF reports with full candidate and vote results for
every ordinary election (1999–present). Text is embedded in the PDFs (no OCR needed).

**Step 1 — Extract election results:**

A council-specific extraction script fetches the relevant PDF pages and outputs a CSV:

```bash
# Cambridge (1999–2023, 12 elections):
python scripts/extract_cambridge_elections.py
# → data/cambridge_elections_raw.csv  (132 rows, all candidates + elected flag)
```

For a new WA council, create a matching script by:
1. Finding the council's result pages across the statewide reports (probe with the
   `pdfplumber` approach in `extract_cambridge_elections.py` — search for `COUNCIL NAME`
   in all-caps across page text)
2. Confirming the page indices and running the same parser

Report URLs are listed in `data/elections_wa_urls.txt`. The 2003–2023 statewide reports
all have embedded text; 1999–2001 appendices also work. Reports older than 1999 are not
digitised — contact the council directly for pre-1999 ordinary elections.

**Step 2 — Import into DB:**

```bash
council import-terms cambridge data/cambridge_elections_raw.csv --apply
```

The CSV format is:
```
election_date, ward, role, given_name, family_name, elected, votes
```
Only rows with `elected=TRUE` are imported as terms; `votes` is informational only.

**Step 3 — Verify coverage then dedup:**

```bash
python scripts/dedup_councillors.py          # preview: shows TERM ✓ vs TERM ? merges
python scripts/dedup_councillors.py --apply  # merge confirmed duplicates
```

### Known gaps (Cambridge)

- **2017**: The 2017 statewide report PDF is missing Cambridge's results page (the page
  is absent, though the election occurred — 7,354 voters participated). The seats up in
  2017 were O'Connor and Grinceri (Coast) and MacRae and King (Wembley), all from 2013.
  **To fill:** check if Elections WA published a Cambridge-specific 2017 notice PDF, or
  contact the Town of Cambridge directly.
- **Pre-1999**: Cambridge ran in-person elections before joining the postal system.
  Results for 1993, 1995, 1997 are not in the Elections WA online archive.
  **To fill:** contact the Town of Cambridge (admin@cambridge.wa.gov.au) or check
  council annual reports from those years.

### Other states / councils

Each state's electoral commission publishes results differently:
- **NSW**: NSW Electoral Commission election results portal (downloadable CSVs)
- **VIC**: Victorian Electoral Commission, council election results by LGA
- **QLD**: ECQ publishes by-election and general election results per council

In all cases, the target is the same CSV format above, imported via `council import-terms`.

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
- Five metrics per document:
  - **Quote completeness**: fraction of extracted entities with ≥1 source quote.
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

Seven metrics per document — five inherited from Level 3c, two new.

**Level 3c metrics (quote-level accuracy — right to test on a small sample before batch):**
- **Quote completeness** — fraction of entities with ≥1 source quote
- **Paraphrase rate** — quotes not matchable in normalised source text
- **Coverage ratio** — fraction of extraction window covered by matched quotes
- **Inventory agreement** — extracted counts vs Level 1 inventory counts
- **Keyword gap rate** — MOVED/CARRIED/DA etc. not covered by any quote span

**Level 4 metrics (corpus-level sanity — only meaningful at scale):**
- **Entity density** — motions per 10k chars; flags large Ordinary meetings with suspiciously few motions. On a small sample a low-density doc might just be a Special Meeting; you need volume to know what normal looks like.
- **Schema completeness** — Ordinary meetings must have ≥1 motion; all motions must have a non-null outcome. A DB integrity check that only becomes meaningful once extractions are being saved at scale.

Composite status: PASS / REVIEW / FAIL per document.

Shared validation logic lives in `src/validation/core.py` — imported by both
`validate_sample.py` (Level 3c) and `validate_extraction.py` (Level 4).

`council validate` is a **separate step** from `council extract`, run explicitly after each batch.

### Output
- `data/validation/{stem}.json` per doc
- `data/validation/summary.json` aggregate (pass/review/fail counts, average metrics)

---

## Level 5: Batch Extraction (actual costs: $19.58 batch for 2024+ subset; ~$50 batch for pre-2024 corpus; ~$70 total)

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
council extract cambridge --max-chars full --batch --dry-run   # preview cost (actual pre-2024 batch: ~$50)
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

### Tooling (done 2026-06-18)

`scripts/audit_report.py` + `council audit cambridge [--count N] [--from-year YYYY] [--seed N]`

Selects N documents stratified by era × size bucket, excluding the Level 3 sample. For each
document, pulls all extracted entities from DB (motions, votes, planning applications, etc.)
with source quotes and validation status, and formats them as a human-readable markdown
report with `<!-- AUDIT: [Y/N/PARTIAL] -->` comment placeholders per entity.

Output files:
- `data/audit_report.md` — full report (open side-by-side with PDFs)
- `data/audit_selection.json` — which documents were sampled

Current report: 12 docs, 2024+, seed=42, generated 2026-06-18.

### Human review task (pending)
- Open each PDF alongside the report section.
- For each extracted entity, mark `[Y]` (correct), `[N]` (wrong), or `[PARTIAL]` and add notes.
- Record precision/recall/error-rate summary.

### Output
- Completed `data/audit_report.md` with filled-in AUDIT annotations.
- Quality statement: "Across N audited documents, extraction captured X% of motions, Y% of votes, Z% of planning applications. Most common gap: ... Most common error: ..."

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
  llm_archive/                 # LLM response archive (all extraction runs, sync + batch)
    index.json                 #   catalog of all runs: run_id, council, model, dates, imported flag
    {run_id}/                  #   one directory per run (sync_YYYYMMDD_HHMMSS or msgbatch_...)
      manifest.json            #     run metadata + import status
      {stem}__c{i}of{n}.json  #     raw API response per chunk, keyed by custom_id

.cache/
  llm_responses/               # Cached raw LLM responses for Level 1 inventory
    {hash}.json                # Keyed by doc_hash + prompt_version (re-running inventory reads from here)

scripts/
  extract_cambridge_elections.py  # Council Setup: download + parse Elections WA PDFs → CSV
  import_terms.py              # Council Setup: CSV → councillor_terms DB rows
  dedup_councillors.py         # Post-setup: merge councillor name variants
  archive_import.py            # Re-import LLM responses from archive into DB (no API calls)
  census.py                    # Level 0
  inventory.py                 # Level 1
  inventory_typology.py        # Level 1→2 (council typology)
  stratified_sample.py         # Level 3a
  validate_sample.py           # Level 3c
  validate_extraction.py       # Level 4
  build_relationships.py       # Dynamic layer: ALLY/OPPONENT edges from voting alignment
  audit_report.py              # Level 6: human-review audit report generator

data/
  elections_wa_urls.txt        # Council Setup: Elections WA report PDF URLs (WA councils)
  cambridge_elections_raw.csv  # Council Setup: extracted election results (Cambridge, 1999–2023)

src/validation/
  core.py                      # Shared validation logic (Levels 3c and 4)
```

### LLM Response Archive

Every extraction run (sync or batch) automatically archives raw LLM responses before parsing.
This enables deterministic DB rebuilding without re-calling the API.

**Archive commands:**
```bash
council archive-status cambridge                     # list all archived runs + unarchived batch jobs
council archive-download cambridge --all             # download all historical batches from Anthropic API
council archive-download cambridge <batch_id>        # download a specific batch
council archive-import cambridge <run_id>            # re-import into DB (skips already-extracted)
council archive-import cambridge <run_id> --force    # re-import + overwrite existing extractions
python scripts/archive_import.py cambridge <run_id>  # standalone (same as CLI)
```

**Archive format** (`data/llm_archive/`):
- `index.json` — catalog with run_id, source (sync/batch), model, dates, imported flag
- `{run_id}/manifest.json` — run-level metadata
- `{run_id}/{stem}__c{i}of{n}.json` — one file per LLM chunk with raw response + chunk metadata

**Note on inventory:** Level 1 inventory responses are already cached at `.cache/llm_responses/{sha}_{prompt_version}.json`. Re-running `council inventory` reads from cache for free — no separate archive needed.

---

## Current Model Configuration

- Development / iteration: claude-haiku-4-5-20251001 (standard API)
- Production: claude-sonnet-4-6 (batch API)
- Prompt version tracked in extraction cache key
- max_tokens: 64,000
- thinking: {"type": "adaptive"}


═══════════════════════════════════════════════════════════════════════════════
                    BUILD LOG — as-built record (was IMPLEMENTATION_ANALYSIS.md)
═══════════════════════════════════════════════════════════════════════════════

Per-level "what was actually built", the build-order dependency graph, and the
completed analysis/query/cost/dedup work. Plan-side detail is above; this is the
as-built half of the same pipeline.
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

**Actual results (Cambridge, as of 2026-06-22 — full corpus COMPLETE):**
- **580 docs extracted** total: 506 minutes, 66 agendas, 4 addenda, 4 unknown.
- **0 docs pending** (full corpus done).
- June 9 batch (`msgbatch_013dcu8czK79suJXKYvTmW9S`): 86 docs, 585 requests (full-doc, all chunks), $19.58.
- June 11 batch (`msgbatch_01TSrRKeTuz74GvByzFdzFA1`): 95 docs re-extracted with Phase 2 agenda prompt; 89 succeeded, 6 failed.
- June 17 batch + fixes: all 6 failures resolved (schema hardening + interest_type coercion).
- Pre-2024 batch (2026-06-22): all remaining ~329 pre-2024 minutes extracted. Actual cost: ~$50 batch.
- DB totals: 14,013 motions, 16,249 votes, 405 councillors.

**Validation results (2024+ corpus, n=87, 2026-06-20):**
- Quote completeness: 98.1% ✓ (target >80%)
- Paraphrase rate: 6.2% ✓ (target <30%)
- Coverage ratio: 12.6% ✓ (target >5%)
- Keyword gap rate: 12.6% ✓ (target <25%)
- Status: 57 PASS / 30 REVIEW / 0 FAIL

**Known issues (updated 2026-06-20):**

1. **✅ RESOLVED — ValidationError on individual vote objects (6 docs)** — `schemas.py` hardened
   with coercions for all observed model output variations: `"vote"`/`"position"` → `"choice"`;
   `"councillor"` string → split name fields; list-of-strings format (`"Cr Smith - For"`);
   `building_permits.status` synonyms (`"pending"/"granted"` → null/`"approved"`); unparseable
   `votes_for` strings (`"3/0 and 4/0"`) → null. `system_prompt.txt` clarified `"choice"` field.
   All 6 docs collected via `msgbatch_018i8noAF3cf2Q3CSmSYKBVj`: 3 PASS / 3 REVIEW / 0 FAIL.
   REVIEWs are structural artifacts (large-doc L1 mismatch, sparse keyword hits) — not quality issues.

2. **✅ RESOLVED — interest_type ValidationError (`"author_subject_to_policy"`)** — LLM returned
   a non-standard WA Author Interest declaration string. Added `normalise_lower` validator to
   `ExtractedInterestDeclaration`: strips `" interest"` suffix, lower-cases, then maps any
   unrecognised value to `"other"`.

3. **✅ RESOLVED — Phantom pending docs (secondary date+type pre-filter)** — Cambridge has multiple
   PDFs per meeting date (agenda + minutes). A meeting already in DB appeared pending because its
   `minutes_pdf_path` pointed to a different filename. Two fixes: (a) `save_extraction()` always
   updates `minutes_pdf_path` (removed `not meeting.minutes_pdf_path` guard); (b) pre-filter in
   `cmd_extract` checks both filename AND date+meeting_type before treating a PDF as pending. If
   the date+type exists in DB, the PDF is skipped. Reduced phantom pending from 14 to 0.

4. **✅ RESOLVED — Batch build subprocess deadlock** — `council extract --batch` previously used
   `ThreadPoolExecutor(max_workers=1)` for PDF text extraction. PyMuPDF hangs in worker threads
   for malformed PDFs; threads can't be killed. Switched to per-PDF `multiprocessing.Process`
   with terminate/kill on timeout. Queue deadlock prevented by calling `q.get(timeout=...)` before
   `p.join()`. Subprocess is lightweight (pypdf/fitz only). New `build_requests_from_text()`
   method keeps Anthropic client and prompt construction in the main process.

5. **Large agenda ToC-hallucination (REVIEW status, 7 docs)** — 7 large agenda PDFs (11–20
   chunks) show high paraphrase on validation. Chunk 0 is a table of contents; model generates
   quotes for items not yet seen in body text. Affected: `202496e2`, `2420cee0`, `34449c77`,
   `4e282dd3`, `68da87da`, `7242bbb8`, `936cc360`. Prompt rule added to `agenda_system_prompt.txt`
   ("do not quote from the table of contents"). These docs remain REVIEW; data is usable.

**LLM response archive (built 2026-06-23):**

Every extraction run (sync and batch) now auto-archives raw LLM responses to `data/llm_archive/`
before parsing. Archive is keyed by run ID (`sync_YYYYMMDD_HHMMSS` for sync, `msgbatch_...` for batch).

What was built:
- `_write_archive_chunk()` in `extractor.py` — module-level function; writes one JSON file per chunk;
  non-fatal (archive failure logs a warning, never aborts extraction).
- `archive_dir` param threaded through `extract_from_pdf()` → `extract()` → `_extract_chunk()`.
  Each chunk file is `{stem}__c{i}of{n}.json` (matching the batch custom_id pattern).
- `archive_dir` + `id_map` params added to `retrieve_batch_results()`; raw responses written
  before markdown stripping so the authentic API response is preserved.
- `cmd_extract()` (sync): creates `sync_YYYYMMDD_HHMMSS` run dir, passes to extractor, writes
  manifest and updates `data/llm_archive/index.json` after the loop.
- `cmd_batch_collect()`: creates `{batch_id}` run dir, passes to `retrieve_batch_results()`,
  writes manifest + updates index after collection.
- `scripts/archive_import.py` — standalone re-import script. Reads chunk files, merges, applies
  metadata overrides, re-reads PDFs for provenance, calls `save_extraction()`. Marks run imported.
- `council archive-status cambridge` — table view of all archived runs with import status.
- `council archive-import cambridge <run_id> [--force]` — re-import without any API calls.

Archive format: `data/llm_archive/{run_id}/{stem}__c{i}of{n}.json` with fields:
`custom_id`, `pdf_path`, `chunk_idx`, `n_chunks`, `document_type`, `meeting_date_hint`,
`model`, `archived_at`, `source` (sync/batch), `status` (ok/error), `raw_response`.

**Note:** Inventory responses already cached at `.cache/llm_responses/{sha}_{prompt_version}.json`.
Re-running `council inventory` reads from cache for free — no separate archive needed.

**Still not built:**
- Feedback loop: after every ~100 documents, re-run Level 0 keyword scan with updated keyword list. Not automated.

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

**P2-4 — Re-extraction results** (completed 2026-06-20):
- Batch `msgbatch_01TSrRKeTuz74GvByzFdzFA1`: 95 docs, 89 succeeded, 6 failed.
- All 6 failures subsequently resolved: schema hardening (vote field coercions) + interest_type
  coercion + secondary date+type pre-filter + subprocess deadlock fix.
- Validation of 2024+ corpus (n=87): 57 PASS / 30 REVIEW / 0 FAIL. All 4 aggregate metrics
  within target. REVIEWs: 7 large agendas with ToC-hallucination (REVIEW, prompt rule applied),
  remainder are minutes with `motions_null_outcome` or keyword gap flags.

---

## Level 6: Audit ✅ TOOLING COMPLETE (2026-06-18)

**What was built:**
- `scripts/audit_report.py` + `council audit cambridge [--count N] [--from-year YYYY] [--seed N] [--list-only]`
- Stratified sampling (era × size_bucket from `census.json`) with Level 3 sample excluded.
- For each selected meeting: pulls motions + votes + all entity tables + `extraction_evidence` from DB,
  loads validation JSON, formats as a markdown report with `<!-- AUDIT: [Y/N/PARTIAL] -->` per entity.
- Writes `data/audit_report.md` and `data/audit_selection.json` (selection record).
- `--list-only` flag shows candidates without generating the full report.

**Human review task still pending.** Reviewer opens PDFs side-by-side with the report and fills in
AUDIT annotations. No automated precision/recall computation yet — manual tally from annotations.

---

## Councillor Deduplication ✅ COMPLETE (2026-06-20)

**Problem:** `_get_or_create_councillor` created a separate DB record for every distinct
name format returned by the LLM. The same person accumulated records under "Cr Barlow",
"Kate Barlow", "Barlow", "null Barlow", "Barlow Cr" (swapped), etc. — 193 councillors
for a council with ~13 active members. This fragmented vote counts and polluted the
alignment matrix (165 ally pairs, many self-pairings at 100%).

**What was built:**

- `_normalise_councillor_name(given, family)` added to `extractor.py`. Handles:
  - Swapped fields (`Barlow Cr` → `Cr Barlow` → `Barlow`)
  - Honorific prefixes (`Cr`, `Mayor`, `Councillor`, `Deputy Mayor`) stripped from given_name
  - Multi-token prefixes (`Cr Gavin Foley` → `Gavin Foley`)
  - Placeholder given names (`null`, `Name`, `Unknown`) cleared
  - Self-repetitions (`Barlow Barlow`) cleared
  - Compound surname particles (`Le` + `Page` → `Le Page`)
  - Family-name-only fallback: when given_name is empty after normalisation, prefers an
    existing full-name councillor with the same family_name over creating a new stub.

- Duplicate-vote dedup key in `save_extraction()` updated to use normalised names, so
  "Cr Barlow" and "Kate Barlow" in the same motion are correctly treated as the same person.

- `scripts/dedup_councillors.py` — one-time migration script. Two passes:
  - Pass 1: bad records (title/placeholder/swapped/self-repeat given_name) → merged into
    canonical using normalised-slug match, single-canonical, or 2024+-votes-winner heuristic.
  - Pass 2: family-only stubs → merged using same heuristic.
  - Updates FK columns: `votes.councillor_id`, `motions.moved_by_id/.seconded_by_id`,
    `appointments.councillor_id`, `interest_declarations.councillor_id`.
  - Deletes duplicate votes before remapping to avoid UNIQUE(motion_id, councillor_id) violations.
  - `--apply` flag required to write changes; dry-run by default.

**Result:**
- Councillors: 193 → 106 (84 merged, 3 in-place slug fixes)
- `council build-relationships cambridge` re-run: 62 ALLY edges, 0 OPPONENT (from 165/0 before)
- Shared vote counts now correct: Gary Mack / Georgie Randklev shows 375 shared votes
  (was split across ~12 phantom records)
- Cambridge votes near-unanimously — 0 opponent pairs at the ≤40% threshold

**To re-run dedup after future extractions:**
```bash
python scripts/dedup_councillors.py          # preview
python scripts/dedup_councillors.py --apply  # write
council build-relationships cambridge        # refresh edges
```

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
| 10 | Phase 2: document-type-aware extraction + validation | Level 4 | Medium | **Done** (2026-06-11) — code; re-extraction complete (2026-06-20) |
| 11 | Fix `individual_votes.choice` schema error (6 docs) | Phase 2 | Small | **Done** (2026-06-17) — schema hardened; all 6 collected and validated |
| 12 | Fix `interest_type` validation error | Phase 2 | Small | **Done** (2026-06-20) — `normalise_lower` validator; unknown values → `"other"` |
| 13 | Fix phantom pending docs (secondary date+type pre-filter) | Phase 2 | Small | **Done** (2026-06-20) — `save_extraction()` always updates path; pre-filter checks date+type |
| 14 | Fix batch build subprocess deadlock | Phase 2 | Medium | **Done** (2026-06-20) — multiprocessing.Process per PDF; queue drain before join; pypdf-first worker |
| 15 | Fix large-agenda ToC-hallucination (7 docs) | Phase 2 | Medium | **Partial** — prompt rule added; 7 docs remain REVIEW until re-extracted |
| 16 | Dynamic layer: `scripts/build_relationships.py` | Level 5 | Small | **Done** (2026-06-18) — ALLY/OPPONENT edges from voting alignment; `--from-year 2024` default |
| 17 | Level 5: 2024+ corpus complete | Phase 2 | — | **Done** (2026-06-20) — 244 extracted; n=87: 57 PASS/30 REVIEW/0 FAIL |
| 18 | Level 5: extract remaining pre-2024 docs | — | Medium | **Done** (2026-06-22) — full corpus complete; 580 extracted |
| 19 | Level 6: audit report generator | Level 5 | Small | **Done** (2026-06-18) — human review still pending |
| 20 | Councillor deduplication + extractor name normalisation | Dynamic layer | Medium | **Done** (2026-06-20) — 193 → 106 councillors; 62 ALLY edges written |
| 21 | Analysis query layer expansion + geocoding + officer divergence | Level 5 complete | Medium | **Done** (2026-06-20) — see Analysis section below |

**Current critical path:** Phase C cleanup — `council build-relationships cambridge --all-years` + `council geocode cambridge` — then Level 6 human audit.

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

## Analysis Query Layer ✅ COMPLETE (2026-06-20)

**What was built:**

- `src/analysis/queries.py` — 8 new query functions added; 5 existing functions updated with
  `from_year`/`to_year` parameters (`contested_motions`, `motions_by_tag`, `top_planning_sites`,
  `councillor_vote_summary`, `list_councillors`). New functions:
  - `councillor_activity_ranges(session, council_id, from_year, to_year, min_votes=10)` —
    per-councillor date span, is_active flag (last vote within 18 months), and dissent rate
    (fraction of votes cast against a motion that carried). `min_votes=10` suppresses AGM proxy
    voters (family members with 1–7 votes at a single special meeting).
  - `contestation_by_year(session, council_id, from_year, to_year)` — % of carried motions with
    ≥1 dissenting vote per year, plus top 3 most-contested motion titles per year.
  - `topic_distribution_by_year(session, council_id, from_year, to_year, top_tags=8)` — per-year
    motion counts per tag. Tags split from comma-separated `motions.tags` in Python; top 8 tags
    tracked, remainder binned as "other".
  - `co_mover_pairs(session, council_id, from_year, to_year, min_count=5, active_only=False)` —
    (mover, seconder) pairs ranked by frequency. Uses SQLAlchemy aliased joins for two
    simultaneous councillor lookups. `active_only` filters via `councillor_activity_ranges`.
  - `interest_declarations_summary(session, council_id, from_year, to_year)` — per-councillor
    declaration counts by type (financial/impartiality/proximity/other) plus top 3 motion topics
    where declarations occurred (approximated via meeting-level join to motions).
  - `public_engagement_by_year(session, council_id, from_year, to_year)` — public questions,
    deputations, and petitions per year. Three separate subqueries merged by year key.
  - `budget_by_year(session, council_id, from_year, to_year, top_n=5)` — budget item counts,
    items with extracted amounts, indicative total, and top N items by amount per year.
  - `planning_outcomes(session, council_id, from_year, to_year, limit=10)` — outcome breakdown
    (approved/refused/deferred/pending), approval rate, top sites, and top applicants.
    Replaces the previous `top_planning_sites`-only planning query in the CLI.

- `src/analysis/divergence.py` — new module for officer recommendation vs. council decision
  matching. For each meeting date with both an agenda and a minutes document: matches agenda
  motions (with `officer_recommendation`) to minutes motions (with `outcome`) by exact item
  number first, then title fuzzy match (`difflib.SequenceMatcher`, threshold 0.5). Classifies
  each matched pair: CARRIED → FOLLOWED, LOST/DEFERRED → DIVERGED, others skipped.
  **2024+ result:** 133 matched pairs, 4 diverged (3%) — 3 DEFERREDs, 1 LOST.
  Exposed via `council analyse cambridge divergence [--from-year YYYY] [--limit N]`.

- `scripts/geocode_sites.py` — Nominatim geocoding script. Reads sites where `latitude IS NULL`,
  queries `nominatim.openstreetmap.org` with address + "City of Cambridge WA Australia" context,
  writes `latitude`/`longitude` back. Rate-limited to 1.1 req/sec (Nominatim policy). Incremental
  by default; `--force` re-geocodes existing. `--dry-run` shows what would be geocoded without
  API calls. Note: `Site.latitude` and `Site.longitude` columns already existed in the schema —
  no migration required.
  Exposed via `council geocode cambridge [--force] [--dry-run]`.

- `src/cli.py` — 7 new `council analyse cambridge <query>` subcommands: `activity`, `trends`,
  `co-movers`, `interests`, `engagement`, `budget`, `divergence`. `--from-year`/`--to-year` args
  added to the `analyse` subparser and threaded through all branches (new and existing).
  New args: `--min-votes` (activity), `--min-count` (co-movers), `--active-only` (co-movers).
  `council geocode` subcommand added.

**2024+ corpus results from new queries:**
- Activity: 13 councillors (≥10 votes), 9 active. Xavier Carr highest dissent rate (4.2%).
- Trends: contestation 15% (2024) → 9% (2025) → 5% (2026).
- Co-movers (active only): Cutler→Le Page leads (30); Mack→Le Page (26); Kennerly→Le Page (25).
- Interests: Le Page 72 declarations, Barlow 69, Carr 60. Gary Mack has 10 FINANCIAL declarations.
- Engagement: public questions 48 (2024) → 136 (2025) → 88 (2026).
- Budget: indicative totals $184M (2024), $816M (2025), $3.1B (2026) — includes large building permit aggregates.
- Planning: 50% approval rate (8/16 decided); Floreat Activity Centre the most-contested site (4 applications).
- Divergence: 133 agenda↔minutes pairs matched, 4 diverged (3%).

**Full corpus gain:** Run all queries without `--from-year` after pre-2024 extraction completes.
Re-run `council geocode cambridge` to pick up new planning sites from pre-2024 docs.

---

## Parallelisable Work

These can be done independently of the main pipeline sequence:

- ~~Populate `minutes_pdf_url` from manifest into meetings table~~ **Done 2026-06-17** — backfilled for all 243 meetings.
- Populate `extracted_at` timestamp on meetings (trivial — set datetime.utcnow() in save_extraction)
- Store `minutes_text` in meetings table (small — raw text is now passed to save_extraction via `text=`; just write it to `meeting.minutes_text`)


═══════════════════════════════════════════════════════════════════════════════
             ANALYSIS QUERY LAYER — design reference (was ANALYSIS_ROADMAP.md)
═══════════════════════════════════════════════════════════════════════════════

The data/query design behind the completed analysis features: per-query return
shapes, SQL sketches, frontend data contracts, the corpus-expansion checklist,
and original build order. All shipped; kept as the design record.

## Part 1: Query functions

All new functions go in `src/analysis/queries.py`. All accept `from_year: int | None = None`
and `to_year: int | None = None`. Default callers pass `from_year=2024` for now; when the
full corpus lands, callers pass nothing (no filter).

Every function documented below includes the data shape returned and the visualisation it feeds.

---

### Q1 — Councillor activity ranges

**Function:** `councillor_activity_ranges(session, council_id, from_year, to_year)`

**Returns:**
```python
list[CouncillorActivity]

@dataclass
class CouncillorActivity:
    councillor_id: int
    given_name: str
    family_name: str
    first_vote_date: date
    last_vote_date: date
    total_votes: int
    is_active: bool        # last_vote_date within 18 months of today
    dissent_rate: float    # fraction of votes cast against the carried majority
```

**SQL sketch:**
```sql
SELECT c.id, c.given_name, c.family_name,
       MIN(m.meeting_date), MAX(m.meeting_date), COUNT(v.id)
FROM councillors c
JOIN votes v ON v.councillor_id = c.id
JOIN motions mt ON v.motion_id = mt.id
JOIN meetings m ON mt.meeting_id = m.id
WHERE m.council_id = :council_id
  AND (:from_year IS NULL OR strftime('%Y', m.meeting_date) >= :from_year)
GROUP BY c.id
```

`is_active`: `last_vote_date >= today - 18 months`. This is a heuristic — council elections
are ~4 years apart; an 18-month gap almost always means the person left.

`dissent_rate`: a second query counts votes where `v.choice = 'AGAINST'` and the motion's
`outcome = 'CARRIED'` — i.e. the councillor voted against something that passed.

**Known dedup artifact:** Some councillors with 1–7 votes and a single meeting date are family
members recorded as proxy voters at AGMs of Electors (e.g. "Catherine Barlow", "Georgina
Randklev", entries from 2025-10-28 and 2026-02-24). Filter these from the activity list with
`total_votes >= 10` by default, or expose a `--min-votes N` flag. Do not delete these records
— they are real attendees at specific meeting types.

**Visualisation powered:**
- Councillor cards (name, active badge, vote count, dissent rate, date span)
- Gantt timeline (Y-axis: councillors sorted by first vote; X-axis: years; bar = active period)
- "Current vs. former" label on all other councillor charts

**Full corpus gain:** Extends bars back to 1995. Gary Mack's record (1995–2026, 452 votes)
becomes the visual anchor of 30 years of continuous service.

---

### Q2 — Contestation rate by year

**Function:** `contestation_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[YearContestationStats]

@dataclass
class YearContestationStats:
    year: int
    total_carried: int
    contested: int           # carried with votes_against >= 1
    contestation_rate: float # contested / total_carried
    most_contested: list[tuple[str, int]]  # [(motion_title, votes_against), ...] top 3
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
       COUNT(mt.id) as total,
       SUM(CASE WHEN mt.votes_against >= 1 THEN 1 ELSE 0 END) as contested
FROM motions mt
JOIN meetings m ON mt.meeting_id = m.id
WHERE mt.outcome = 'CARRIED'
  AND m.document_type = 'minutes'
  AND m.council_id = :council_id
GROUP BY yr ORDER BY yr
```

**2024+ corpus baseline:** 2024: 103 carried / 15 contested (14.6%),
2025: 186 / 16 (8.6%), 2026: 189 / 10 (5.3%). Three data points — interpretable but thin.

**Visualisation powered:**
- Line chart: contestation rate (%) over time
- Bar chart: total carried vs. contested per year (stacked)
- Annotation layer: hover on a year to see the 3 most-contested motions

**Full corpus gain:** 30-year trend. The early extracted years (1995–2023, sparse) show near-zero
contestation, which may be genuine or may reflect incomplete extraction. Treat pre-2024 values
as illustrative until the full batch runs. Add a visual note: "2024–2026: full coverage;
earlier years: partial."

---

### Q3 — Topic distribution by year

**Function:** `topic_distribution_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
dict[int, dict[str, int]]
# {year: {tag: motion_count}}
# e.g. {2024: {"governance": 120, "planning": 45, "budget": 30, ...}}
```

**Implementation note:** `motions.tags` is a comma-separated string (e.g. `"planning,development"`).
Split on `,`, strip whitespace, count each tag independently. The top 8 tags in the current
corpus are: governance (881), planning (425), procedural (418), infrastructure (323),
community (241), budget (240), policy (124), development (107). Use these as the canonical
display tags; bin everything else as "other".

**Visualisation powered:**
- Stacked area chart: years on X, stacked bands per tag coloured by category
- Pie/donut for a selected year (filter by clicking a year on the area chart)
- "What Cambridge spends its time on" — governance and procedural always dominate;
  spikes in planning or infrastructure signal development periods

**Full corpus gain:** The area chart fills in. 2024+ shows what recent Cambridge looks like;
pre-2024 shows the historical baseline. The shape across 30 years is the interesting story.

---

### Q4 — Co-mover pairs

**Function:** `co_mover_pairs(session, council_id, from_year, to_year, min_count=5)`

**Returns:**
```python
list[CoMoverPair]

@dataclass
class CoMoverPair:
    mover_id: int
    mover_name: str
    seconder_id: int
    seconder_name: str
    count: int          # motions where this pair moved+seconded
```

**SQL sketch:**
```sql
SELECT mt.moved_by_id, mt.seconded_by_id, COUNT(*) as n
FROM motions mt
JOIN meetings m ON mt.meeting_id = m.id
WHERE m.council_id = :council_id
  AND mt.moved_by_id IS NOT NULL
  AND mt.seconded_by_id IS NOT NULL
GROUP BY mt.moved_by_id, mt.seconded_by_id
HAVING COUNT(*) >= :min_count
ORDER BY n DESC
```

**Known data quality issue:** The councillor named "Shannon Unknown" in co-mover results is a
dedup artifact — the family name was extracted without a given name, and the normaliser filled
`given_name = "Unknown"`. These pairs (e.g. `Shannon Unknown → Melanie Foley: 16`) are
pre-2024 data from a partially extracted doc. Filter by `is_active=True` for the 2024+ view
to avoid these stubs surfacing.

**Visualisation powered:**
- Chord diagram: councillors on a circle, arc thickness = co-mover count (most compact for this)
- Alternative: directed graph with labelled edges (mover → seconder)
- Supplements the voting alignment heatmap: two councillors who always vote together AND always
  propose together is the strongest signal of a working partnership

**Full corpus gain:** Pre-2024 co-mover pairs from earlier terms flesh out historical alliances
(e.g. Shannon/Foley pairing from pre-2015 data).

---

### Q5 — Interest declarations by councillor and type

**Function:** `interest_declarations_summary(session, council_id, from_year, to_year)`

**Returns:**
```python
list[InterestSummary]

@dataclass
class InterestSummary:
    councillor_id: int
    councillor_name: str
    total: int
    by_type: dict[str, int]   # {"IMPARTIALITY": 40, "FINANCIAL": 5, "PROXIMITY": 2, ...}
    top_topics: list[str]     # top 3 motion tags where this councillor declared
```

**SQL sketch (two queries):**
```sql
-- 1. Counts by councillor and type
SELECT id.councillor_id, id.interest_type, COUNT(*) as n
FROM interest_declarations id
JOIN meetings m ON id.meeting_id = m.id
WHERE m.council_id = :council_id
GROUP BY id.councillor_id, id.interest_type

-- 2. Motion topics where declarations occur (join via meeting_id)
SELECT id.councillor_id, mt.tags, COUNT(*) as n
FROM interest_declarations id
JOIN meetings m ON id.meeting_id = m.id
JOIN motions mt ON mt.meeting_id = m.id
WHERE m.council_id = :council_id AND mt.tags IS NOT NULL
GROUP BY id.councillor_id, mt.tags
```

**2024+ corpus data:** 521 total declarations. Le Page (73), Barlow (69), Carr (61), Mayes (56),
Mack (52). Predominantly IMPARTIALITY (456), then PROXIMITY (31), FINANCIAL (21). FINANCIAL
declarations (21) are worth surfacing distinctly — they indicate a pecuniary interest.

**Visualisation powered:**
- Horizontal bar chart per councillor, segmented by type (IMPARTIALITY/FINANCIAL/PROXIMITY),
  sorted by total. Le Page stands out at the top.
- Click a councillor's bar → expand to a list of specific declarations with meeting dates
  and the motion subject they related to.
- "Most declared topics" for a councillor — which tags appear most in motions near their
  declarations. (Note: approximate — this is per-meeting, not per-motion-item.)

**Full corpus gain:** Extends to all historical declarations. The pattern of who declares most
across 30 years may shift — some councillors with low 2024 counts may have had high earlier
periods.

---

### Q6 — Public engagement by year

**Function:** `public_engagement_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[EngagementStats]

@dataclass
class EngagementStats:
    year: int
    public_questions: int
    deputations: int
    petitions: int
    total: int
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
  COUNT(DISTINCT pq.id) as questions,
  COUNT(DISTINCT d.id)  as deputations,
  COUNT(DISTINCT p.id)  as petitions
FROM meetings m
LEFT JOIN public_questions pq ON pq.meeting_id = m.id
LEFT JOIN deputations d ON d.meeting_id = m.id
LEFT JOIN petitions p ON p.meeting_id = m.id
WHERE m.council_id = :council_id AND m.document_type = 'minutes'
GROUP BY yr ORDER BY yr
```

**2024+ corpus data:** 610 public questions, 134 deputations, 20 petitions — distributed
across 2024–2026. These numbers are only from minutes (not agendas, which also list questions
and deputations as proposals). Decide whether to include agenda counts too — they'll be higher
but represent planned slots, not actual attendees.

**Visualisation powered:**
- Stacked bar or grouped bar per year: questions / deputations / petitions in distinct colours
- Spike in deputations in a specific year signals a controversial decision period
- "How much does the public engage with Cambridge council?" — the baseline story

**Full corpus gain:** The most meaningful trend over 30 years. A rising line here is the real
civic signal. Not useful until pre-2024 extraction runs — 2024–2026 is only 3 data points.
Mark this chart as "preview — 30-year data pending" until then.

---

### Q7 — Budget aggregate by year

**Function:** `budget_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[BudgetYearStats]

@dataclass
class BudgetYearStats:
    year: int
    total_items: int
    items_with_amount: int
    total_amount: float | None    # sum of amounts in dollars
    largest_items: list[tuple[str, float]]  # [(description, amount)] top 5
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
  COUNT(bi.id) as total,
  SUM(CASE WHEN bi.amount IS NOT NULL THEN 1 ELSE 0 END) as with_amount,
  SUM(bi.amount) as total_amount
FROM budget_items bi
JOIN meetings m ON bi.meeting_id = m.id
WHERE m.council_id = :council_id AND m.document_type = 'minutes'
GROUP BY yr ORDER BY yr
```

**Known data quality issue:** `budget_items.amount` was extracted as a raw number from motion
text. The LLM may have extracted sub-totals, line-item amounts, and annual totals for the same
budget cycle — double-counting is likely. Do not present the summed total as "total council
spend." Instead present it as "total dollar value of budget items discussed in council." Add
a caveat to the frontend.

**Visualisation powered:**
- Bar chart: total dollar value discussed in council per year (with caveat tooltip)
- Table: top 5 largest single items per year (clickable to see the motion)
- "Cambridge's biggest financial decisions" as a discovery feature

**Full corpus gain:** Extends to pre-2024 budget cycles.

---

### Q8 — Planning approval rate

**Function:** `planning_outcomes(session, council_id, from_year, to_year)`

**Returns:**
```python
@dataclass
class PlanningOutcomes:
    total: int
    approved: int
    refused: int
    deferred: int
    pending: int
    approval_rate: float        # approved / (approved + refused)
    top_sites: list[tuple[str, int]]  # [(address, n_applications)]
    top_applicants: list[tuple[str, int]]  # [(applicant, n_applications)]
```

**2024+ corpus note:** Only 107 planning applications extracted. The 2024+ corpus includes
agendas (which carry fuller planning detail) and minutes (which carry the voted outcome).
The 63 APPROVED / 19 REFUSED split gives a 77% approval rate — but this is from partial data.
Treat as directional until the full corpus lands.

**Visualisation powered:**
- Donut chart: APPROVED / REFUSED / DEFERRED / PENDING breakdown
- Table: top sites by application count (which addresses keep coming back to council)
- Table: top applicants (developers / agents with most applications)
- Map (requires E1 geocoding): dots coloured by outcome

**Full corpus gain:** ~5,700 estimated planning items across the full corpus. The historical
approval rate and top sites become meaningful with full data.

---

## Part 2: CLI additions

Extend `council analyse` with new subcommands. All follow the existing pattern in `src/cli.py`.

### C1 — `council analyse cambridge activity`

```
council analyse cambridge activity [--min-votes N] [--from-year YYYY] [--to-year YYYY]
```

Calls Q1. Prints a table: name / first vote / last vote / total votes / is_active / dissent_rate.
Default `--min-votes 10` to suppress AGM proxy voters.

### C2 — `council analyse cambridge trends`

```
council analyse cambridge trends [--from-year YYYY] [--to-year YYYY]
```

Calls Q2 (contestation) + Q3 (topic distribution). Prints two tables: year × contestation_rate,
and year × tag counts. The frontend reads the JSON export from this.

### C3 — `council analyse cambridge co-movers`

```
council analyse cambridge co-movers [--min-count N] [--from-year YYYY] [--to-year YYYY] [--active-only]
```

Calls Q4. Default `--min-count 5`, `--active-only` filters to councillors with `is_active=True`.

### C4 — `council analyse cambridge interests`

```
council analyse cambridge interests [--from-year YYYY] [--to-year YYYY]
```

Calls Q5. Prints per-councillor declaration counts by type. Flags any FINANCIAL declarations
explicitly (these are pecuniary interest — worth surfacing).

### C5 — `council analyse cambridge engagement`

```
council analyse cambridge engagement [--from-year YYYY] [--to-year YYYY]
```

Calls Q6. Prints per-year: questions / deputations / petitions / total.

### C6 — `council analyse cambridge budget`

```
council analyse cambridge budget [--from-year YYYY] [--to-year YYYY] [--top N]
```

Calls Q7. Prints year total + top N items by amount.

### C7 — `council analyse cambridge divergence`

```
council analyse cambridge divergence [--from-year YYYY] [--to-year YYYY] [--min-similarity F]
```

Calls E2 (officer divergence). Prints matched pairs: meeting date / item title / officer
recommendation summary / council outcome / diverged (Y/N).

### Fix — add `--from-year` / `--to-year` to existing `alignment` subcommand

`voting_alignment_matrix()` in `queries.py` already accepts `from_year`/`to_year`.
The CLI handler in `src/cli.py` doesn't expose them. Add these two args to the `alignment`
branch in `cmd_analyse`. One-line fix.

---

## Part 3: Data enrichment — site geocoding (E1)

**Script:** `scripts/geocode_sites.py`

**New columns on `sites` table:**
```sql
ALTER TABLE sites ADD COLUMN lat REAL;
ALTER TABLE sites ADD COLUMN lng REAL;
ALTER TABLE sites ADD COLUMN geocode_status VARCHAR(10);
-- values: 'ok', 'failed', 'skipped'
```

**Logic:**
1. Query all `sites` where `lat IS NULL` and `address IS NOT NULL`.
2. For each address: prepend ", City of Cambridge WA" to the raw string for context.
3. Call Nominatim geocoding API (free, no key required, rate-limit: 1 req/sec).
4. Write `lat`, `lng`, `geocode_status` back to the DB.
5. Incremental: skip sites with `geocode_status IS NOT NULL` unless `--force`.

**CLI:** `council geocode cambridge [--force] [--dry-run]`

**Expected results:** 107 planning applications → at most 107 unique sites. Many will share
addresses. Perth suburb geocoding via Nominatim is reliable for street-level addresses.

**Visualisation powered:**
- Map layer on the planning chart: dots at geocoded positions, coloured by outcome
- "Where are the most-discussed development sites in Cambridge?" — the geographic story

**Full corpus gain:** ~5,700 planning items → many more unique sites. The map becomes
meaningful at scale.

---

## Part 4: Officer divergence matching (E2)

This is the highest-novelty analysis the project can produce — comparing what officers
recommended (from agendas) to what councillors actually decided (from minutes).

**Prerequisite:** Both an agenda and its matching minutes must be extracted for the same
meeting. This is only guaranteed for 2024+ (where the scraper was fixed to download both).

**New module:** `src/analysis/divergence.py`

### Matching strategy

For each meeting date where both an agenda and a minutes document exist in the DB:

1. **Meeting-level match:** `agenda.meeting_date = minutes.meeting_date AND
   agenda.meeting_type ≈ minutes.meeting_type` (fuzzy, because type labels vary slightly —
   "Ordinary Council Meeting" vs "Council Meeting"). Match on date first; use type as
   a tiebreaker if multiple meetings on the same day.

2. **Motion-level match:** For each motion in the agenda (with `officer_recommendation`),
   find the best-matching motion in the minutes by:
   - Item number (exact, if present on both)
   - Title similarity (fuzzy string match — `difflib.SequenceMatcher`, threshold 0.6)
   - Recommendation text overlap (if item number and title both absent)

3. **Divergence classification** for each matched pair:
   - `FOLLOWED` — council voted CARRIED and officer recommended approval (or LOST and
     officer recommended refusal).
   - `DIVERGED` — council voted CARRIED where officer recommended refusal, or vice versa,
     or council voted DEFERRED/LOST on a recommended approval.
   - `UNMATCHED` — agenda item has no matching minutes motion (possible for items
     withdrawn or carried forward).
   - `NO_RECOMMENDATION` — the agenda motion has `officer_recommendation IS NULL`.

### Output schema

```python
@dataclass
class DivergencePair:
    meeting_date: date
    item_number: str | None
    title: str
    officer_recommendation: str    # text from agenda
    council_outcome: str           # from minutes: CARRIED/LOST/DEFERRED/etc.
    diverged: bool
    match_confidence: float        # 0.0–1.0 from fuzzy match score
```

**CLI:** `council analyse cambridge divergence [--from-year YYYY] [--min-confidence F]`

**Expected output (2024+ corpus):**
Currently: 61 agendas extracted, 103 minutes (Council Meeting/Ordinary) extracted in the
same period. Not all agenda+minutes pairs will match cleanly due to meeting type label
variation. Estimate: ~40–50 meeting pairs matchable; ~400–600 motion pairs.

**Visualisation powered:**
- "Council vs officers" panel: "Cambridge council followed officer recommendations in X% of
  cases." Below: a table of divergences sorted by meeting date, with motion text.
- Per-topic divergence rate: did council diverge more on planning than governance?
- Per-councillor: who moved the dissenting motions when council diverged from officers?

**Deferred until:** This analysis requires human spot-checking of the match quality before
publishing numbers. After the matching script is built, run it and review a sample of
`match_confidence < 0.8` pairs manually.

---

## Part 5: Frontend data contracts

What each visualisation needs from the backend. This section defines the JSON shape
each frontend component should expect. The CLI commands above can emit `--json` output
in these shapes; a Flask/FastAPI layer serves them to the frontend.

### Alignment heatmap

```json
{
  "councillors": ["Gary Mack", "Georgie Randklev", ...],
  "matrix": [[1.0, 0.92, ...], [0.92, 1.0, ...], ...],
  "total_shared": [[0, 452, ...], [452, 0, ...], ...]
}
```
Source: existing `voting_alignment_matrix()`. Emit as JSON with `--json` flag on the CLI.

### Voting network graph

```json
{
  "nodes": [{"id": 1, "name": "Gary Mack", "votes": 452, "is_active": true}, ...],
  "edges": [{"source": 1, "target": 3, "weight": 0.92, "shared": 380, "kind": "ALLY"}, ...]
}
```
Source: `relationships` table (ALLY edges) + Q1 for node metadata.

### Councillor activity timeline (Gantt)

```json
[
  {"name": "Gary Mack", "first": "1995-07-25", "last": "2026-05-26",
   "votes": 452, "is_active": true, "dissent_rate": 0.02},
  ...
]
```
Source: Q1.

### Contestation trend

```json
[
  {"year": 2024, "total_carried": 103, "contested": 15, "rate": 0.146},
  {"year": 2025, "total_carried": 186, "contested": 16, "rate": 0.086},
  ...
]
```
Source: Q2.

### Topic distribution stacked area

```json
[
  {"year": 2024, "governance": 120, "planning": 45, "budget": 30, "infrastructure": 28, ...},
  ...
]
```
Source: Q3.

### Interest declaration bar chart

```json
[
  {"name": "Michael Le Page", "total": 73,
   "by_type": {"IMPARTIALITY": 68, "FINANCIAL": 3, "PROXIMITY": 2}},
  ...
]
```
Source: Q5.

### Planning map

```json
[
  {"address": "123 Wembley Rd", "lat": -31.93, "lng": 115.83,
   "status": "APPROVED", "applications": 3, "site_id": 12},
  ...
]
```
Source: Q8 + E1.

### Officer divergence panel

```json
{
  "total_matched": 487,
  "diverged": 28,
  "divergence_rate": 0.057,
  "by_tag": {"planning": 0.09, "budget": 0.03, "governance": 0.02},
  "examples": [
    {"date": "2024-06-25", "title": "Development Application ...", "outcome": "REFUSED",
     "officer_recommendation": "RECOMMENDED APPROVAL", "diverged": true}
  ]
}
```
Source: E2.

---

## Corpus expansion checklist

When pre-2024 extraction is complete (329 minutes), run these in order:

```bash
# Re-run deduplication (new pre-2024 names may create new stubs)
python scripts/dedup_councillors.py          # preview
python scripts/dedup_councillors.py --apply  # write

# Refresh dynamic layer
council build-relationships cambridge --all-years  # needs --all-years flag added

# Widen all analysis queries (remove from_year default)
council analyse cambridge activity             # no --from-year → all years
council analyse cambridge trends               # 30-year contestation + topic charts
council analyse cambridge alignment --all-years
council analyse cambridge co-movers --all-years
council analyse cambridge interests --all-years
council analyse cambridge engagement --all-years
council analyse cambridge budget --all-years
council analyse cambridge divergence --all-years  # only adds minutes-side; agendas only 2024+

# Re-geocode (new planning sites from pre-2024 docs)
council geocode cambridge

# Re-validate for quality assurance
council validate cambridge --all-years
```

**What changes with the full corpus:**

| Chart | 2024+ (now) | Full corpus |
|-------|-------------|-------------|
| Contestation trend | 3 data points | 30-year line |
| Topic distribution | 3 years | 30-year stacked area |
| Councillor timeline | 2024–2026 activity only | Full career spans (e.g. Mack 1995–2026) |
| Co-mover pairs | Current-term pairs | Historical partnership record |
| Interest declarations | 521 records | ~5,700 estimated records |
| Planning map | 107 applications | ~5,700 estimated applications |
| Public engagement | 3-year preview | 30-year trend (the compelling civic story) |
| Officer divergence | 2024+ agendas only | Still 2024+ only (no historical agendas) |

---

## Build order

Implement in this sequence. Each step is independently shippable.

1. **Fix alignment CLI** — add `--from-year`/`--to-year` to `council analyse cambridge alignment`.
   One-line change in `src/cli.py`. Unblocks using the alignment data with a year filter.

2. **Q1 — councillor activity ranges** + **C1** CLI. This is the foundation for all
   "who is active" filtering in every other query. Build first.

3. **Q2 + Q3 — contestation and topic trends** + **C2** CLI. These two go together (same
   `--from-year` / `--to-year` args, same output table). Powers the two timeline charts.

4. **Q5 — interest declarations** + **C4** CLI. Self-contained. The political data journalists
   want. Build early.

5. **Q4 — co-mover pairs** + **C3** CLI. Depends on Q1 (`--active-only` filter). Can work
   without it if you accept the name-stub noise.

6. **Q6 + Q7 + Q8 — engagement, budget, planning** + **C5/C6** CLI. Three small queries,
   low effort, add them together.

7. **E1 — geocoding**. One-off enrichment script. Run once, done.

8. **E2 — officer divergence**. The most complex piece. Build last, after the simpler
   queries have been validated. Requires manual spot-checking of match quality.

---
