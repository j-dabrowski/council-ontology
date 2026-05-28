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
   scripts/census.py     ← free pass: text extraction + keyword scan across all PDFs
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
```

#### `council status`
Show pipeline and database summary across all councils — downloaded vs ingested counts, year-by-year breakdown, motions, votes, councillors seen.

#### `council docs cambridge`
Per-document table showing which PDFs are in the manifest and which have been extracted to the database.

```bash
council docs cambridge
council docs cambridge --filter pending    # only unextracted PDFs
council docs cambridge --filter ingested
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
  batch_extract.py        — iterative extraction with error reporting
  eval_prompt.py          — prompt quality evaluation against benchmark
  compare_models.py       — side-by-side model comparison for a single PDF

estimate_costs.py         — API cost estimator for pending documents

data/
  census.json             — Level 0: per-document metadata and keyword counts
  census_summary.txt      — Level 0: aggregate stats and outlier list
  raw/cambridge/          — downloaded PDFs + manifest.json (gitignored except manifest)
  council.db              — SQLite database (gitignored, re-generated from PDFs)
  eval/benchmark.json     — benchmark PDFs and expected extraction criteria
  inventories/            — Level 1: per-document LLM inventories + summary.json
  validation/             — Level 4: per-document confidence reports (pending)

.cache/
  llm_responses/          — cached raw LLM responses ({hash}_{prompt-version}.json)
  extraction_errors.json  — latest batch error report
```

---

## Multi-level extraction pipeline

The project follows a layered approach to avoid blind LLM extraction at scale:

| Level | What | Cost | Status |
|-------|------|------|--------|
| 0 | Census: text extraction + keyword scan across all PDFs | Free | **Done** |
| 1 | Cheap LLM inventory: one small Haiku call per document | ~$1-2 | **Done** |
| 2 | Schema and prompt revision using Level 0/1 data | Free | Pending |
| 3 | Prompt validation against stratified 15-20 doc sample | ~$1-2 | Pending |
| 4 | Confidence metrics and per-document validation script | Free | Pending |
| 5 | Batch extraction with progressive validation | ~$7-20 | Pending |
| 6 | Human audit on random sample | Free | Pending |

See `PIPELINE.md` for the detailed plan and `IMPLEMENTATION_ANALYSIS.md` for build order and dependencies.

---

## Adding a second council

1. Create `src/scraper/<council>.py` subclassing `BaseScraper`
2. Add one entry to the `COUNCILS` dict at `src/cli.py:30`

All CLI commands and scripts work immediately for the new council.
