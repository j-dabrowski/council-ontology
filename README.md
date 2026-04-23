# council-ontology

A research tool for modelling local council politics in Perth, WA. It scrapes public meeting minutes PDFs, uses Claude to extract structured data, and stores the results in a SQLite database for analysis.

**Current target:** City of Cambridge (Town Council), covering meetings from 2020 onwards (~538 PDFs).

---

## How it works

```
council minutes site
        │
        ▼
   src/scraper/          ← discovers meeting pages, downloads PDFs
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

### `council run cambridge`
Full pipeline: scrape the council's minutes page, download PDFs, extract with Claude, save to the database.

```bash
council run cambridge
council run cambridge --limit 3        # test with 3 PDFs before burning API credits
council run cambridge --since-year 2022
```

### `council scrape cambridge`
Download PDFs only — no Claude calls. Writes `data/raw/cambridge/manifest.json` with meeting dates and types.

```bash
council scrape cambridge
council scrape cambridge --since-year 2024
```

### `council extract cambridge`
Process already-downloaded PDFs with Claude (no HTTP requests to the council site).

```bash
council extract cambridge
council extract cambridge --limit 5
council extract cambridge --from-year 2020 --to-year 2022
council extract cambridge --files abc123.pdf def456.pdf   # targeted
council extract cambridge --files abc123.pdf --force      # re-extract even if already in DB
```

`--limit` applies after date filtering: `--limit 5 --from-year 2020` means the first 5 PDFs from 2020+.

### `council status`
Show pipeline and database summary across all councils — downloaded vs ingested counts, year-by-year breakdown, motions, votes, councillors seen.

### `council docs cambridge`
Per-document table showing which PDFs are in the manifest and which have been extracted to the database.

```bash
council docs cambridge
council docs cambridge --filter pending    # only unextracted PDFs
council docs cambridge --filter ingested
```

---

## Scripts

### `scripts/batch_extract.py`
Iterative extraction runner for working through a large backlog. Writes a structured error report to `data/extraction_errors.json` grouping failures by error class (missing field, JSON parse error, schema mismatch, etc.) to make systematic prompt fixes efficient.

```bash
python scripts/batch_extract.py --limit 5
python scripts/batch_extract.py --model claude-sonnet-4-6 --limit 20
python scripts/batch_extract.py --from-year 2020
python scripts/batch_extract.py --files abc123.pdf def456.pdf --force
```

Already-extracted documents are skipped; the script is safe to re-run at any point.

### `scripts/eval_prompt.py`
Evaluates the extraction prompt against `data/eval/benchmark.json` — a set of PDFs with known expected criteria. Scores across five dimensions: `meta`, `roster`, `motions`, `votes`, `planning`. Saves each run with a SHA so you can track regressions.

```bash
python scripts/eval_prompt.py --quick --compare   # fast iteration loop: one PDF, delta vs last run
python scripts/eval_prompt.py --compare           # full check: all benchmark PDFs × all models
python scripts/eval_prompt.py --history           # score timeline
python scripts/eval_prompt.py --show              # print latest results without API calls
```

Typical workflow: edit `src/extraction/system_prompt.txt`, then run `--quick --compare` to see the delta.

### `scripts/compare_models.py`
Runs a single PDF through all three Claude models in parallel and displays a side-by-side comparison — meeting metadata, motion counts, vote detail, councillor lists — with cells highlighted where models disagree. Saves full structured JSON to `data/model_comparison/` for deeper inspection.

```bash
python scripts/compare_models.py bde23c99.pdf
python scripts/compare_models.py bde23c99.pdf --no-save
```

### `estimate_costs.py`
Estimates API cost for pending documents across models and batch/non-batch modes, based on actual PDF text sizes. Saves timestamped reports to `data/cost_estimates/`.

```bash
python estimate_costs.py --from-year 2020
python estimate_costs.py --from-year 2020 --max-chars full   # no truncation
python estimate_costs.py --show                               # print last saved estimate
python estimate_costs.py --quiet                             # summary only, no per-doc lines
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
  storage/
    database.py           — SQLite init, session factory, schema creation
  analysis/
    queries.py            — reusable query helpers

scripts/
  batch_extract.py        — iterative extraction with error reporting
  eval_prompt.py          — prompt quality evaluation against benchmark
  compare_models.py       — side-by-side model comparison for a single PDF

estimate_costs.py         — API cost estimator for pending documents
data/
  raw/cambridge/          — downloaded PDFs + manifest.json (gitignored except manifest)
  eval/benchmark.json     — benchmark PDFs and expected extraction criteria
  council.db              — SQLite database (gitignored, re-generated from PDFs)
```

---

## Adding a second council

1. Create `src/scraper/<council>.py` subclassing `BaseScraper`
2. Add one entry to the `COUNCILS` dict at `src/cli.py:30`

That's it — all CLI commands and scripts work immediately for the new council.

---

## Recommended extraction workflow

```
Phase 1 — Test (cheap)
  python scripts/batch_extract.py --model claude-haiku-4-5-20251001 --limit 5
  → review data/extraction_errors.json, fix prompt or schema, repeat

Phase 2 — Pre-production sample
  python scripts/batch_extract.py --model claude-sonnet-4-6 --limit 20

Phase 3 — Production
  council extract cambridge   (Sonnet batch for ~$43, or Sonnet+Haiku merge for ~$71)

Phase 4 — Targeted enhancement
  python scripts/compare_models.py <complex-meeting>.pdf
```
