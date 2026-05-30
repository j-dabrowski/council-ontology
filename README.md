# council-ontology

A research tool for modelling local council politics in Perth, WA. It scrapes public meeting minutes PDFs, uses Claude to extract structured data, and stores the results in a SQLite database for analysis.

**Current target:** City of Cambridge (Town Council), 537 PDFs covering 1995–2026.

---

## How it works

```
council minutes site
        │
        ▼
   src/scraper/          ← discovers meeting pages, downloads PDFs
        │
        ▼
   scripts/census.py     ← Level 0: text extraction + keyword scan (free, no LLM)
        │
        ▼
   scripts/inventory.py  ← Level 1: one cheap Haiku call per doc — what is this document?
        │
        ▼
   src/extraction/       ← sends PDF text to Claude, parses structured output
        │
        ▼
   src/storage/          ← saves meetings, motions, votes to SQLite
        │
        ▼
   src/analysis/         ← query helpers for cross-meeting analysis
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
- `Motion` — a formal motion moved at a meeting, with outcome and vote counts
- `Vote` — an individual councillor's vote on a motion (for/against/abstain/absent), including declared interests
- `PlanningApplication` — a development application considered at a meeting
- `CommunitySubmission` — a written public submission on a planning matter

**Dynamic** — relationships and emergent patterns
- `Relationship` — a typed edge between any two entities (ally, opponent, coalition, declared interest, etc.); used for surfacing voting blocs and patterns over time

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

## CLI — `council <command>`

All commands accept `-v` / `--verbose` for detailed logging.

### Pipeline

#### `council run cambridge`
Full pipeline: scrape, download PDFs, extract with Claude, save to the database.

```bash
council run cambridge
council run cambridge --limit 3        # test with 3 PDFs before burning API credits
council run cambridge --since-year 2022
```

#### `council scrape cambridge`
Download PDFs only — no Claude calls. Writes `data/raw/cambridge/manifest.json` with meeting dates and types.

```bash
council scrape cambridge
council scrape cambridge --since-year 2024
```

#### `council extract cambridge`
Process already-downloaded PDFs with Claude (no HTTP requests to the council site).

```bash
council extract cambridge
council extract cambridge --limit 5
council extract cambridge --from-year 2020 --to-year 2022
council extract cambridge --files abc123.pdf def456.pdf   # targeted
council extract cambridge --files abc123.pdf --force      # re-extract even if already in DB
council extract cambridge --max-chars full                # multi-chunk: extract entire document
```

#### `council status`
Show pipeline and database summary across all councils — downloaded vs ingested counts, year-by-year breakdown, motions, votes, councillors seen.

#### `council docs cambridge`
Per-document table showing which PDFs are in the manifest and which have been extracted to the database.

```bash
council docs cambridge
council docs cambridge --filter pending     # only unextracted PDFs
council docs cambridge --filter ingested
council docs cambridge --filter no-manifest # PDFs with no manifest entry
```

---

### Scripts (via CLI or standalone)

#### `council census cambridge`
**Level 0:** Free pass across all PDFs — text extraction, keyword scanning, and per-document metadata. No LLM calls. Outputs `data/census.json` and `data/census_summary.txt`.

```bash
council census cambridge              # incremental: skips already-scanned PDFs
council census cambridge --force      # rescan everything
council census cambridge --workers 8  # parallel workers (default: min(8, cpu_count))
council census cambridge --quiet      # suppress per-document output
```

The census records: character count, size bucket (tiny/small/medium/large), decade, meeting type, keyword counts across 7 groups (motions, votes, planning, interests, community, budget, procedural), section header count, estimated entity counts, and flags for outliers.

#### `council inventory cambridge`
**Level 1:** One cheap Haiku call per document. Builds a text window from the first 20,000 characters + the last 10,000 characters of each PDF, then asks: what kind of document is this, and roughly what does it contain? LLM responses are cached in `.cache/llm_responses/` by document hash + prompt version, so re-running is free. Cross-references with Level 0 census counts and flags disagreements.

```bash
council inventory cambridge              # incremental: skips already-inventoried PDFs
council inventory cambridge --limit 10   # first 10 only
council inventory cambridge --force      # re-run even if inventory exists
```

Per-document output in `data/inventories/{stem}.json`; corpus summary in `data/inventories/summary.json`.

#### `council typology cambridge`
**Level 1→2:** Analyses the completed inventory to surface the corpus typology. This is the bridge between iterating on the inventory prompt and moving to Level 2 schema work.

Each run computes the **`other_content_rate`** — the percentage of documents where the inventory's free-text `other_content` field is substantive (> 30 chars). This is the quality signal for the inventory prompt:

- **Rate > 20%** (needs improvement): prints a Claude Code prompt that reads the typology report and updates `src/extraction/inventory_prompt.txt` + the `DocumentInventory` Pydantic model. Paste it into Claude Code, then re-run inventory on a sample and check again.
- **Rate ≤ 20%** (acceptable): prints a Claude Code prompt to update the extraction schema (`schemas.py`, `system_prompt.txt`) based on what the now-reliable inventory has validated.

The full typology report (meeting type distribution, entity averages, section heading patterns, all `other_content` values) is written to `data/cambridge_typology_review.txt`.

Quality scores are saved to `data/inventory_quality/` for trend tracking.

```bash
council typology cambridge                # full corpus
council typology cambridge --limit 20     # last 20 updated files only (for iterating on a sample)
council typology cambridge --history      # show quality score trend over time
council typology cambridge --quiet        # file only (prompt box still printed)
```

**Iteration loop:**
1. `council inventory cambridge --force --limit 20` — re-run inventory on a sample
2. `council typology cambridge --limit 20` — check quality
3. Paste the prompt into Claude Code to improve `inventory_prompt.txt`
4. Repeat until `other_content_rate ≤ 20%`, then do a full re-run before moving to Level 2

#### `council sample cambridge`
**Level 3a:** Selects a stratified 15–20 doc sample from the census and Level 1 inventory flags. Stratifies by era, size bucket, meeting type, and outliers. Saves canonical selection to `data/{council}_sample.json`.

```bash
council sample cambridge
council sample cambridge --count 20
```

#### `council extract-sample cambridge`
**Level 3b:** Extracts the saved sample (reads `data/{council}_sample.json`). Always runs with `--force` — re-extracts regardless of DB state, to populate `extraction_evidence` for validation.

```bash
council extract-sample cambridge
council extract-sample cambridge --max-chars full   # extract entire document (multi-chunk)
```

#### `council validate-sample cambridge`
**Level 3c:** Validates sample extractions against the source PDFs. Applies three-tier normalised quote matching (whitespace normalisation → stripped alphanumeric → paraphrase) to compute paraphrase rate, coverage ratio, inventory agreement, and keyword gap rate. Writes `data/sample_validation/report.txt` and `paraphrase_report.txt`. Gate before Level 4.

The `--max-chars` value controls the coverage denominator — it should match whatever was used for `extract-sample`. Default is 80k (single-chunk mode). Pass `full` when extraction was run with `--max-chars full`.

```bash
council validate-sample cambridge
council validate-sample cambridge --max-chars full
```

#### `council batch cambridge`
Iterative extraction runner for working through a large backlog. Writes a structured error report to `data/extraction_errors.json` grouping failures by error class.

```bash
council batch cambridge --limit 5
council batch cambridge --limit 20 --model claude-sonnet-4-6
council batch cambridge --from-year 2020
council batch cambridge --files abc123.pdf def456.pdf --force
```

Already-extracted documents are skipped; safe to re-run at any point.

#### `council eval`
Evaluates the extraction prompt against benchmark PDFs. Scores across five dimensions: `meta`, `roster`, `motions`, `votes`, `planning`.

```bash
council eval --quick --compare    # fast iteration: one PDF, delta vs last run
council eval --compare            # full check: all benchmark PDFs × all models
council eval --history            # score timeline
council eval --show               # print latest results without API calls
```

#### `council compare <pdf>`
Runs a single PDF through all three Claude models in parallel and displays a side-by-side comparison. Saves full structured JSON to `data/model_comparison/`.

```bash
council compare bde23c99.pdf
council compare bde23c99.pdf --no-save
```

#### `council costs`
Estimates API cost for pending documents across models and batch/non-batch modes, based on actual PDF text sizes.

```bash
council costs
council costs --from-year 2020
council costs --max-chars full    # no truncation
council costs --show              # print last saved estimate
council costs --quiet             # summary only
```

#### `council analyse cambridge <query>`
Run analysis queries against the extracted database.

```bash
council analyse cambridge councillors                    # all councillors by vote count
council analyse cambridge alignment --min-shared 10      # pairwise voting agreement matrix
council analyse cambridge contested --min-against 3      # carried motions with opposition
council analyse cambridge planning --limit 20            # top sites by application count
council analyse cambridge councillor --name Bradley      # one councillor's vote summary
council analyse cambridge motions --tag planning         # motions by tag
```

---

## Source layout

```
src/
  cli.py                  — entry point for the council command
  models/
    ontology.py           — SQLAlchemy ORM (all three layers)
  scraper/
    base.py               — shared scraper interface and MinutesDocument type
    cambridge.py          — City of Cambridge scraper (sitemap + Playwright + Wayback fallback)
  extraction/
    extractor.py          — PDF text extraction and Claude API call
    schemas.py            — Pydantic models for structured Claude output
    system_prompt.txt     — extraction prompt (edit this to tune quality)
    inventory_prompt.txt  — Level 1 inventory-only prompt
  storage/
    database.py           — SQLite init, session factory, schema creation
  analysis/
    queries.py            — reusable query helpers

scripts/
  census.py               — Level 0: keyword scan and census across all PDFs
  inventory.py            — Level 1: LLM inventory (one Haiku call per document)
  inventory_typology.py   — Level 1→2: corpus typology report for schema review
  stratified_sample.py    — Level 3a: stratified sample selection
  validate_sample.py      — Level 3c: three-tier quote matching validation
  batch_extract.py        — iterative extraction with error reporting
  eval_prompt.py          — prompt quality evaluation against benchmark
  compare_models.py       — side-by-side model comparison for a single PDF

estimate_costs.py         — API cost estimator for pending documents

data/
  census.json             — Level 0: per-document metadata and keyword counts
  census_summary.txt      — Level 0: aggregate stats and outlier list
  inventories/            — Level 1: per-document LLM inventories + summary.json
  inventory_quality/      — Level 1: other_content_rate quality scores over time
  {council}_typology_review.txt — Level 1→2: typology report (generated by council typology)
  {council}_sample.json   — Level 3a: canonical stratified sample (18 docs)
  sample_validation/      — Level 3c: per-doc JSON + report.txt + paraphrase_report.txt
  raw/cambridge/          — downloaded PDFs + manifest.json (gitignored except manifest)
  council.db              — SQLite database (gitignored, re-generated from PDFs)
  eval/benchmark.json     — benchmark PDFs and expected extraction criteria
  validation/             — Level 4: per-document confidence reports (pending)
  extraction_errors.json  — latest batch error report

.cache/
  llm_responses/          — cached raw LLM responses ({hash}_{prompt-version}.json)
```

---

## Multi-level extraction pipeline

The project follows a layered approach to avoid blind LLM extraction at scale.

**Key design principle: each level is a quality gate for the next.** You don't touch the extraction schema until Level 1 inventory is trustworthy, because the schema should reflect what you've actually validated exists in the corpus — not what you guessed upfront. The inventory prompt is iterated until the `other_content_rate` (unclassified content) falls to ≤ 20%, then and only then does Level 2 schema work begin.

| Level | What | Cost | Status |
|-------|------|------|--------|
| 0 | Census: text extraction + keyword scan across all PDFs | Free | **Done** |
| 1 | Cheap LLM inventory: one small Haiku call per document | $4.83 actual | **Done** |
| 2 | Schema and prompt revision using Level 0/1 data | Free | **Done** |
| 3a | Stratified sample selection (18 docs) | Free | **Done** |
| 3b | Sample extraction | ~$0.50 | **Done** |
| 3c | Sample validation (paraphrase 10%, coverage 9.9%, keyword gap 10.9%) | Free | **Done** |
| 4 | Confidence metrics and per-document validation script | Free | Pending |
| 5 | Batch extraction with progressive validation | ~$7-20 | Pending |
| 6 | Human audit on random sample | Free | Pending |

See `PIPELINE.md` for the detailed plan and `IMPLEMENTATION_ANALYSIS.md` for build order and dependencies.

---

## Adding a second council

1. Create `src/scraper/<council>.py` subclassing `BaseScraper`
2. Add one entry to the `COUNCILS` dict at `src/cli.py:30`

All CLI commands and scripts work immediately for the new council.
