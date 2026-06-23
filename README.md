# council-ontology

A research tool for modelling local council politics in Perth, WA. It scrapes public meeting minutes PDFs, uses Claude to extract structured data, and stores the results in a SQLite database for analysis.

**Current target:** City of Cambridge (Town Council), 537 PDFs covering 1995–2026.

---

## How it works

The pipeline follows a recursive refinement strategy: cheap broad passes feed expensive deep passes, and every pass validates the one after it. No blind LLM extraction.

```
council minutes site
        │
        ▼
   council scrape           ← discovers meeting pages, downloads PDFs
        │
        ▼
   council census           ← Level 0: text extraction + keyword scan (free, no LLM)
        │
        ▼
   council inventory        ← Level 1: one cheap Haiku call per doc — what is this document?
        │
        ▼
   council typology         ← Level 1→2: corpus typology for schema review
        │
        ▼
   council sample           ← Level 3a: stratified sample selection
   council extract-sample   ← Level 3b: extract sample with Claude
   council validate-sample  ← Level 3c: validate quotes, coverage, keyword gaps
        │
        ▼
   council extract          ← Level 5: full extraction across all PDFs
   council validate         ← Level 4: per-doc confidence scoring
        │
        ▼
   council analyse          ← query helpers for cross-meeting analysis
```

---

## Three-layer ontology

The database schema (`src/models/ontology.py`) is organised into three layers:

**Semantic** — core entities and relationships
- `Council` — a local government body
- `Councillor` + `CouncillorTerm` — a person and their tenure (ward, role, dates)
- `Site` — a physical address appearing in planning matters

**Kinetic** — actions and events
- `Meeting` — a single council session (ordinary, special, committee, etc.)
- `Motion` — a formal motion with outcome, vote counts, mover, seconder
- `Vote` — an individual councillor's vote (for/against/abstain/absent)
- `PlanningApplication` — a development application considered at a meeting
- `CommunitySubmission` — a written public submission on a planning matter
- `PublicQuestion`, `Deputation`, `Petition`, `Appointment`
- `CommitteeReport`, `BudgetItem`, `InterestDeclaration`, `Tender`
- `DelegatedDecision`, `BuildingPermit`, `OtherItem`
- `ExtractionEvidence` — verbatim source quotes per entity with character offsets

**Dynamic** — relationships and emergent patterns
- `Relationship` — a typed edge between any two entities (ally, opponent, coalition, declared interest, etc.)

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# For headless browser scraping (2022+ Cambridge meetings)
pip install -e ".[browser]"
playwright install chromium
```

Create a `.env` file with your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Dashboard

A React/Vite frontend with a FastAPI backend visualises the extracted data. Six panels: officer recommendation compliance, interest declarations by councillor, contestation rate by year, co-mover network, public engagement by year, and voting alignment heatmap.

```bash
# Start the API (from project root)
uvicorn api.main:app --reload --port 8000

# Start the frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:5173
```

---

## CLI — `council <command>`

All commands accept `-v` / `--verbose` for detailed logging.

---

### Acquisition

#### `council scrape cambridge`
Download PDFs only — no Claude calls. Writes `data/raw/cambridge/manifest.json` with meeting dates and types.

```bash
council scrape cambridge
council scrape cambridge --since-year 2024
```

---

### Pipeline

#### `council census cambridge`
**Level 0:** Free pass across all PDFs — text extraction, keyword scanning, per-document metadata. No LLM calls. Outputs `data/census.json` and `data/census_summary.txt`.

Records: character count, size bucket (tiny/small/medium/large), decade, meeting type, keyword counts across 7 groups (motions, votes, planning, interests, community, budget, procedural), estimated entity counts, outlier flags.

```bash
council census cambridge              # incremental: skips already-scanned PDFs
council census cambridge --force      # rescan everything
council census cambridge --workers 8  # parallel workers (default: min(8, cpu_count))
```

#### `council inventory cambridge`
**Level 1:** One cheap Haiku call per document. Builds a text window (first 20k + last 10k chars) and asks: what kind of document is this, and roughly what does it contain? LLM responses are cached by document hash + prompt version — re-running is free. Cross-references with Level 0 census counts and flags disagreements.

```bash
council inventory cambridge
council inventory cambridge --limit 10
council inventory cambridge --force      # re-run even if inventory exists
```

Per-document output: `data/inventories/{stem}.json`. Corpus summary: `data/inventories/summary.json`.

#### `council typology cambridge`
**Level 1→2:** Analyses the completed inventory to surface the corpus typology. Computes `other_content_rate` — the quality signal for the inventory prompt. When rate > 20%: prints instructions for improving the inventory prompt. When rate ≤ 20%: prints instructions for updating the extraction schema.

```bash
council typology cambridge
council typology cambridge --limit 20    # last 20 files (for iterating on a sample)
council typology cambridge --history     # quality score trend over time
```

Full typology written to `data/cambridge_typology_review.txt`. Quality scores saved to `data/inventory_quality/`.

**Iteration loop:**
1. `council inventory cambridge --force --limit 20`
2. `council typology cambridge --limit 20` — check quality
3. Update `inventory_prompt.txt` based on the printed instructions
4. Repeat until `other_content_rate ≤ 20%`, then do a full re-run before Level 2 schema work

#### `council sample cambridge`
**Level 3a:** Selects a stratified 15–20 doc sample from the census and Level 1 flags. Stratifies by era, size bucket, meeting type, and outliers. Saves canonical selection to `data/{council}_sample.json`.

```bash
council sample cambridge
council sample cambridge --count 20
```

#### `council extract-sample cambridge`
**Level 3b:** Extracts the saved sample. Always runs with `--force` — re-extracts regardless of DB state, to populate `extraction_evidence` for validation.

```bash
council extract-sample cambridge
council extract-sample cambridge --max-chars full   # multi-chunk: extract entire document
```

#### `council validate-sample cambridge`
**Level 3c:** Validates sample extractions against source PDFs. Applies three-tier normalised quote matching (whitespace → stripped alphanumeric → paraphrase) to compute five metrics per document:
- **Quote completeness** — fraction of entities with ≥1 source quote in `extraction_evidence`
- **Paraphrase rate** — quotes not found in normalised source text
- **Coverage ratio** — fraction of extraction window covered by matched quotes
- **Inventory agreement** — extracted counts vs Level 1 inventory counts
- **Keyword gap rate** — MOVED/CARRIED/DA/DECLARATION etc. not covered by any quote

Writes `data/sample_validation/report.txt` and `paraphrase_report.txt`. This is the gate before running at scale.

Pass `--max-chars` matching whatever was used for `extract-sample`.

```bash
council validate-sample cambridge
council validate-sample cambridge --max-chars full
```

**Cambridge baselines (18 docs, 2026-05-31):** completeness 95.0% / paraphrase 4.3% / coverage 22.9% / keyword gap 9.3% — 14 PASS, 4 REVIEW, 0 FAIL.

#### `council extract cambridge`
**Level 5:** Extract all pending PDFs with Claude. Skips already-extracted documents by default. Writes grouped error report to `data/extraction_errors.json`.

```bash
council extract cambridge
council extract cambridge --limit 20
council extract cambridge --from-year 2020 --to-year 2022
council extract cambridge --files abc123.pdf def456.pdf
council extract cambridge --files abc123.pdf --force        # re-extract even if in DB
council extract cambridge --max-chars full                  # multi-chunk: entire document
council extract cambridge --dry-run                         # cost estimate only, no API calls
```

**Batch mode (50% off, async):** Add `--batch` to submit the whole job to the Anthropic Message Batches API instead of running synchronously. Results are available within 24 h and collected with `batch-collect`.

```bash
council extract cambridge --max-chars full --batch --dry-run   # cost preview
council extract cambridge --max-chars full --batch             # submit; prints batch_id
council batch-collect cambridge msgbatch_abc123                # save results to DB
```

#### `council batch-collect cambridge <batch_id>`
Retrieves results from a previously submitted batch job. Checks whether the batch has finished, then parses every response, merges multi-chunk documents, and saves to the database via the standard `save_extraction()` path (provenance fully populated). If the batch is still in progress, prints the status and exits — run again later.

Job metadata (including the `custom_id → PDF mapping`) is persisted at `data/batch_jobs/{batch_id}.json` at submit time.

```bash
council batch-collect cambridge msgbatch_abc123
```

#### `council validate cambridge`
**Level 4:** Per-document confidence scoring for all extracted meetings. Extends Level 3c with two additional checks:
- **Entity density** — motions per 10k chars; flags large Ordinary meetings with suspiciously few motions
- **Schema completeness** — Ordinary meetings must have ≥1 motion; all motions must have a non-null outcome

Writes `data/validation/{stem}.json` per doc and `data/validation/summary.json`.

```bash
council validate cambridge
council validate cambridge --limit 20
council validate cambridge --from-year 2020
council validate cambridge --files abc123.pdf def456.pdf
council validate cambridge --force       # re-validate even if report exists
```

---

### Utilities

#### `council status`
Pipeline and database summary across all councils — downloaded vs ingested counts, year-by-year breakdown, motions, votes, councillors seen.

#### `council docs cambridge`
Per-document table showing which PDFs are in the manifest and which have been extracted.

```bash
council docs cambridge
council docs cambridge --filter pending
council docs cambridge --filter ingested
council docs cambridge --filter no-manifest
```

#### `council compare <pdf>`
**Dev tool.** Runs a single PDF through Haiku 4.5, Sonnet 4.6, and Opus 4.8 in parallel and displays a side-by-side comparison. Does not write to the database. Use when evaluating new Claude model releases.

Update `MODELS` in `scripts/compare_models.py` when new model versions are released.

```bash
council compare bde23c99.pdf
council compare bde23c99.pdf --no-save
```

Saves full structured JSON to `data/model_comparison/`.

#### `council costs`
Estimates API cost for pending documents based on actual PDF text sizes.

```bash
council costs
council costs --from-year 2020
council costs --max-chars full
council costs --show                  # print last saved estimate
```

#### `council analyse cambridge <query>`
Analysis queries against the extracted database.

```bash
council analyse cambridge councillors                    # all councillors by vote count
council analyse cambridge alignment --min-shared 10      # pairwise voting agreement matrix
council analyse cambridge contested --min-against 3      # carried motions with opposition
council analyse cambridge planning --limit 20            # top sites by application count
council analyse cambridge councillor --name Bradley      # one councillor's vote summary
council analyse cambridge motions --tag planning         # motions by tag
council analyse cambridge activity                       # councillor date spans, active status, dissent rate
council analyse cambridge trends                         # contestation rate and topic distribution by year
council analyse cambridge co-movers --min-count 5        # most frequent mover+seconder pairs
council analyse cambridge interests                      # interest declarations per councillor by type
council analyse cambridge engagement                     # public questions, deputations, petitions by year
council analyse cambridge budget                         # budget items and amounts by year
council analyse cambridge divergence                     # officer recommendations vs council outcomes
```

All queries accept `--from-year` and `--to-year` to filter by meeting date.

---

#### `council merge-pdfs <input_dir> <output>`
Concatenates all PDFs in a directory into a single file. Useful for bundling image-based PDFs (e.g. Elections WA reports) into one upload for Google Drive OCR.

```bash
council merge-pdfs data/raw/terms/ data/raw/terms/combined.pdf
council merge-pdfs data/raw/terms/ data/raw/terms/combined.pdf --exclude Survey Stakeholder
```

`--exclude` skips files whose names contain any of the given substrings (case-insensitive).

---

#### `council derive-terms <council>`
Generates a seed CSV (`data/{council}_terms_seed.csv`) of councillor term records derived from vote date spans. Splits councillors with gaps > 2 years in voting activity into separate rows, flagged for review. Edit the CSV to add ward/role and correct dates to actual election dates, then import with `import-terms`.

```bash
council derive-terms cambridge
council derive-terms cambridge --gap-years 3
```

---

#### `council import-terms <council> <csv>`
Imports a councillor terms CSV into the `councillor_terms` table. Dry run by default; pass `--apply` to write. Matches rows by `councillor_id` (preferred) or `given_name` + `family_name`. Replaces existing terms for affected councillors, making re-runs idempotent.

```bash
council import-terms cambridge data/cambridge_terms_seed.csv
council import-terms cambridge data/cambridge_terms.csv --apply
```

CSV columns: `councillor_id, given_name, family_name, ward, role, term_start, term_end, source, notes`

**Populating the CSV from Elections WA PDFs:**
1. Merge PDFs: `council merge-pdfs data/raw/terms/ data/raw/terms/combined.pdf --exclude Survey`
2. Upload `combined.pdf` to Google Drive → right-click → Open with Google Docs (auto-OCRs)
3. Select all, copy, paste into Claude with the prompt at `data/terms_ocr_prompt.txt`
4. Save Claude's CSV output to `data/cambridge_terms_from_elections_wa.csv`
5. Match names to councillor IDs using the seed CSV (`data/cambridge_terms_seed.csv`) and fill `councillor_id`
6. Run `council import-terms cambridge data/cambridge_terms_from_elections_wa.csv --apply`

---

#### `council dedup`
Deduplicates councillor records — merges title/placeholder/swapped-field variants and family-name-only stubs into their canonical records. Dry run by default.

```bash
council dedup                        # dry run
council dedup --apply                # write changes
council dedup --use-terms            # annotate merges with term coverage (TERM ✓ / ✗ / ?)
council dedup --use-terms --apply    # only apply TERM ✓ confirmed merges
```

With `--use-terms`, merges where the stub's vote dates fall outside all known terms for the candidate are held for manual review rather than auto-applied.

---

#### `council build-relationships cambridge`
**Dynamic layer.** Computes ALLY/OPPONENT edges from voting alignment and persists them to the `Relationship` table. Run after `council validate` once the corpus is stable.

```bash
council build-relationships cambridge
council build-relationships cambridge --min-shared 10 --ally 0.85 --opponent 0.60
council build-relationships cambridge --from-year 2024
```

---

#### `council audit cambridge`
**Level 6.** Selects a stratified sample of extracted documents and generates a human-readable markdown report (`data/audit_report.md`) with `<!-- AUDIT: [Y/N/PARTIAL] -->` placeholders per entity. Open side-by-side with PDFs to verify extraction quality.

```bash
council audit cambridge
council audit cambridge --count 20 --from-year 2020
council audit cambridge --all-years --seed 42
```

---

#### `council geocode cambridge`
Geocodes planning `Site` records via Nominatim. Adds lat/lng coordinates to the `Site` table for mapping. Skips already-geocoded sites unless `--force`.

```bash
council geocode cambridge
council geocode cambridge --dry-run
council geocode cambridge --force
```

---

## Source layout

```
src/
  cli.py                  — entry point for the council command
  models/
    ontology.py           — SQLAlchemy ORM (all three layers, 17 tables)
  scraper/
    base.py               — shared scraper interface and MinutesDocument type
    cambridge.py          — City of Cambridge scraper (sitemap + Playwright + Wayback fallback)
  extraction/
    extractor.py          — PDF text → Claude API; sync and batch modes
    schemas.py            — Pydantic models for structured Claude output (13 entity types)
    system_prompt.txt     — extraction prompt for minutes (edit to tune quality)
    agenda_system_prompt.txt — extraction prompt for agendas
    inventory_prompt.txt  — Level 1 inventory-only prompt
  storage/
    database.py           — SQLite init, session factory, schema creation
  analysis/
    queries.py            — reusable query helpers (13 query functions)
  validation/
    core.py               — shared validation logic (five metrics, three-tier quote matching)

api/
  main.py                 — FastAPI backend exposing analysis queries as REST endpoints
                            (run: uvicorn api.main:app --reload --port 8000)

frontend/
  src/
    App.tsx               — six-panel dashboard layout
    api.ts                — typed fetch wrappers for the API
    components/           — AlignmentHeatmap, CoMoverGraph, DivergencePanel,
                            EngagementChart, InterestsChart, TrendsChart
    hooks/useData.ts      — shared data-fetching hook
  (run: cd frontend && npm run dev)

scripts/
  census.py               — Level 0: keyword scan and census across all PDFs
  inventory.py            — Level 1: LLM inventory (one Haiku call per document)
  inventory_typology.py   — Level 1→2: corpus typology report for schema review
  stratified_sample.py    — Level 3a: stratified sample selection
  validate_sample.py      — Level 3c: three-tier quote matching validation on sample
  validate_extraction.py  — Level 4: per-doc confidence scoring for all extracted docs
  build_relationships.py  — Dynamic layer: ALLY/OPPONENT edges from voting alignment
  audit_report.py         — Level 6: human-review audit report generator
  geocode_sites.py        — Nominatim geocoding for planning Site records
  compare_models.py       — dev tool: side-by-side model comparison for a single PDF

estimate_costs.py         — API cost estimator for pending documents

data/
  census.json             — Level 0: per-document metadata and keyword counts
  census_summary.txt      — Level 0: aggregate stats and outlier list
  inventories/            — Level 1: per-document LLM inventories + summary.json
  inventory_quality/      — Level 1: other_content_rate quality scores over time
  {council}_typology_review.txt — Level 1→2: typology report
  {council}_sample.json   — Level 3a: canonical stratified sample (18 docs)
  sample_validation/      — Level 3c: per-doc JSON + report.txt + paraphrase_report.txt
  validation/             — Level 4: per-doc confidence reports + summary.json
  batch_jobs/             — batch job metadata ({batch_id}.json, custom_id → PDF mapping)
  extraction_errors.json  — latest extraction error report (grouped by error class)
  audit_report.md         — Level 6: human audit findings (open alongside PDFs)
  raw/cambridge/          — downloaded PDFs + manifest.json (gitignored except manifest)
  council.db              — SQLite database (gitignored, re-generated from PDFs)

.cache/
  llm_responses/          — cached raw LLM responses ({hash}_{prompt-version}.json)
```

---

## Multi-level extraction pipeline

| Level | What | Cost | Status |
|-------|------|------|--------|
| 0 | Census: text extraction + keyword scan across all PDFs | Free | **Done** |
| 1 | Cheap LLM inventory: one small Haiku call per document | $4.83 actual | **Done** |
| 2 | Schema and prompt revision from inventory typology | Free | **Done** |
| 3a | Stratified sample selection (18 docs) | Free | **Done** |
| 3b | Sample extraction | ~$0.50 | **Done** |
| 3c | Sample validation — all metrics within target | Free | **Done** |
| 4 | Per-document confidence scoring (`council validate`) | Free | **Done** |
| 5 | Full extraction (`council extract`) | $19.58 batch | **Done** (2024+; 244 docs; pre-2024 deferred) |
| 6 | Human audit on random sample | Free | **Tooling done**; human review pending |

See `PIPELINE.md` for the detailed plan and `IMPLEMENTATION_ANALYSIS.md` for build order and dependencies.

---

## Adding a second council

1. Create `src/scraper/<council>.py` subclassing `BaseScraper`
2. Add one entry to the `COUNCILS` dict in `src/cli.py`

All CLI commands work immediately for the new council.
