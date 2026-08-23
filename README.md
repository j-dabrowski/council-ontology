# council-ontology

A research tool for modelling local council politics in Perth, WA. It scrapes public meeting minutes PDFs, uses Claude to extract structured data into a SQLite database, and runs a **standard battery of governance tests** over it — each result flagged supportive, neutral, or critical and anchored to a recognised criterion — surfaced through an interactive dashboard.

**Current target:** City of Cambridge (Town Council), 580 documents covering 1995–2026.

---

## How it works

The pipeline follows a recursive refinement strategy: cheap broad passes feed expensive deep passes, and every pass validates the one after it. No blind LLM extraction.

```
council minutes site
        │
        ▼
   council scrape           ← Discovery: discovers meeting pages, downloads PDFs
   council scraper-audit    ← cadence audit: flags any year short of the council's
                              expected meeting rhythm (Cambridge: 2022–2023)
   council wayback-fill     ← recovers flagged gaps from Wayback Machine CDX before
                              declaring them unrecoverable
        │
        ▼
   council census           ← Census (Level 0): text extraction + keyword scan
                              (free, no LLM — these counts are never shown to the
                              model, so they stay an independent check)
        │
        ▼
   council inventory        ← Inventory (Level 1): one cheap Haiku call per doc —
                              what is this document, and what does it contain?
        │
        ▼
   council typology         ← Schema prep (Level 1→2): corpus typology review;
                              other_content_rate is the "what did the schema miss"
                              signal that drives the Inventory convergence loop
        │
        ▼
   council sample           ← Level 3a: stratified sample selection
   council extract-sample   ← Level 3b: extract sample with Claude
   council validate-sample  ← Validation, sampled: quote completeness, paraphrase
                              rate, coverage, inventory agreement, keyword gaps —
                              the gate the Extraction convergence loop runs against
                              before the full corpus is trusted at scale
        │
        ▼
   council extract          ← Extraction (Level 5): full extraction across all
                              PDFs; every fact forced to carry a source quote
   council validate         ← Validation, full corpus (Level 4): per-doc confidence
                              scoring, plus entity density and schema completeness
        │
        ▼
   council audit            ← Audit (Level 6): human marks a random sample against
                              the source PDFs — ground-truths the metrics above
        │
        ▼
   council profile          ← Corpus profile: NULL rates, document/date spans,
                              identity-resolution state, record-quality metrics
                              as one machine-readable document
        │
        ▼
   council analyse          ← query helpers for cross-meeting analysis
        │
        ▼
   council explore          ← Explorer: generate/test novel hypotheses
   council refine           ← Refiner: codify a validated finding into
                              the permanent, council-agnostic test battery
        │
        ▼
   council draft            ← generate candidate JSON snapshots to data/draft/,
                              gated by the S7 invariant gate (scripted — small-n,
                              unnamed claims, unresolved identities all block here)
        │
        ▼
   council editor-loop      ← Editor reviews the draft for everything the S7
                              gate can't catch mechanically; Fixer acts on
                              whatever it flags; loops until PASS or escalation
        │
        ▼
   council publish          ← the gate: copy a *reviewed* draft into
                              frontend/public/data/ for the frontend
                              (--from-draft always required; --confirm or a
                              re-validated Editor PASS record, depending on
                              --gate-profile)
```

(`council reply-packets` and `council render` are two further stages — right
of reply for any named-individual claim, and audience-facing rendering —
documented in the CLI reference below; omitted above to keep this diagram to
the critical path every draft actually goes through.)

---

## Results

Full corpus: **580 documents** (506 minutes / 66 agendas / 4 addenda / 4 unknown), City
of Cambridge, 1995-04-18 to 2026-06-09 — **14,013 motions**, **16,249 votes**,
**400 councillors**.

**Provenance.** Of the 44,929 entities extracted across the corpus, **98.15%** carry
at least one verbatim source quote pinned to a character offset in the original PDF
(`extraction_evidence`, 71,486 quote rows). The weakest entity type is motions, at
94.8% — every other entity type clears 98.8%.

**Validation** (`council validate`, per-doc reports at `data/validation/*.json`,
corpus summary at `data/validation/summary.json`):

| | Full corpus (n=580) | 2024+ subset (n=87, tuned) |
|---|---|---|
| Quote completeness | 83.7% | 98.1% |
| Paraphrase rate | ~4–5% | 6.2% |
| PASS / REVIEW / FAIL | 256 / 183 / 141 | 57 / 30 / 0 |

The extraction prompt was iteratively tuned against the 87 documents dated 2024
onward (its convergence loop, see `council validate-sample` below), then frozen and
run unmodified across the remaining 493 documents spanning 1995–2023 — quote
completeness on that untuned set is **81.1%**. The 83.7% full-corpus figure blends
both sets, weighting every document equally.

**Officer divergence** (`council analyse cambridge divergence`,
`src/analysis/divergence.py`): matching agenda recommendations to minutes outcomes
across 203 paired motions, council followed the officer's recommendation **97.0%**
of the time.

Reproduce these: `council status` (corpus scale), `data/validation/summary.json`
(validation metrics, or re-run `council validate cambridge`), `council analyse
cambridge divergence` (officer agreement).

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

## Testing & CI

```bash
pip install -e ".[dev]"
ruff check src/ scripts/ api/ tests/
pytest tests/ -q
```

`tests/` covers the extraction/storage layer and the eval framework's
`PASS`/`REVIEW`/`FAIL` gate (`src/validation/core.py`) — all pure-function
or in-memory-DB tests, no API key or network needed. `.github/workflows/ci.yml`
runs this plus a frontend job (`npm ci && npm run lint && npm run build`) on
every push to `main` and every PR.

Publishing is two manually-triggered (`workflow_dispatch`) workflows, not
one: `.github/workflows/draft.yml` pulls `data/council.db` from a private
GCS bucket — authenticated via workload identity federation (OIDC), no
service account key stored anywhere — runs `council draft`, and stages the
output in GCS for review. `.github/workflows/publish.yml` then runs
`council publish --from-draft ... --gate-profile ...` against a *reviewed*
draft and commits the refreshed snapshots — `--from-draft` is always
required, and clearance always comes from a verifiable authorization
record: either a human-typed `--confirm` (`--gate-profile interactive`,
the default), or an independent re-validation of Editor's own on-disk PASS
record (`--gate-profile auto`) — never a single agent's self-assessment.
See `docs/review/CONDUCTOR.md`'s "Gate profiles" section and
`src/publish_gate.py`.
`frontend/public/data/*.json` currently holds obviously-fake placeholder
data (`scripts/generate_placeholder_data.py`), not real output — see
`docs/TESTING.md` for the full draft/publish shape, the one-time GCP setup,
and why the raw DB stays out of a public GitHub Release regardless.

See `docs/TESTING.md` for what's covered, the ruff rule-selection
rationale, and why LLM calls are deliberately kept out of the required CI
path.

---

## Dashboard

A React/Vite frontend visualises the analysis. It reads **static JSON snapshots**
(no live API needed) that `council publish` copies into `frontend/public/data/`
from a reviewed `council draft` run.

The page is organised as a **standard test battery**:

- **Overview** — a cross-cutting synthesis of the whole corpus.
- **Scorecard** — every standard governance test, each flagged **supportive /
  neutral / critical** (and "not computable" where the corpus can't support it).
  The same battery runs on any council, so results are comparable.
- **23 test panels**, one per battery test, in the same order as the scorecard.
  Rich findings get a bespoke panel; the rest are rendered by a generic
  `BatteryTestPanel` from the test's chart payload.

Every panel exists *because it is a test* — there are no orphan charts. Panels are
interactive where the data supports it (e.g. click a councillor in the conflict
panel to reveal their actual declared interests, each with the verbatim minute
quote), and the scorecard rows ↕ panels are linked both ways.

```bash
# 1. Generate candidate snapshots from the database (re-run after any data change)
council draft cambridge            # → data/draft/cambridge/<run_id>/*.json

# 2. Review the draft (investigator + Editor), then publish it
council publish cambridge --from-draft data/draft/cambridge/<run_id> \
  --confirm "reviewed by <you>, <date>"   # → frontend/public/data/*.json

# 3. Run the frontend
cd frontend && npm run dev         # → http://localhost:5173
# or: npm run build && npm run preview
```

**Previewing a draft before it's published.** Between steps 1 and 2 you can
render an unreviewed draft in the real dashboard, locally, without touching
`frontend/public/data/`:

```bash
cd frontend
VITE_DRAFT_DIR=../data/draft/cambridge/<run_id> npm run dev
# → http://localhost:5173, serving that draft's JSON instead of the
#   committed placeholder data — for local review only, nothing is published
```

This is a dev-only Vite plugin — see `docs/TESTING.md` ("Draft & publish
workflow") for how it works and why it's safe to leave in the codebase
unused.

> The methodology behind the battery — the criteria findings are judged against,
> the standard of proof, the supportive/neutral/critical valences — lives in
> `docs/investigator/Investigator_prompt.txt`. The hypothesis-by-hypothesis record
> (findings and nulls) is in `docs/investigator/INVESTIGATIONS.md`; the prose
> synthesis in `docs/investigator/FINDINGS_SUMMARY.md`; the interactivity backlog
> in `docs/frontend/INTERACTIVITY.md`. See `docs/MAP.md` for the full doc map.
>
> (`api/main.py` is a legacy FastAPI backend that served the same queries as REST;
> the live site uses the static snapshots above and does not need it.)

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

#### `council scraper-audit cambridge`
Cadence audit for the scraped corpus. A missing PDF is invisible from inside the corpus, so the expectation has to come from outside it: Cambridge is required to hold at least one ordinary meeting a month (January excepted), and this checks each scraped year against that floor — printing a per-year completeness table and flagging any year with too few meeting dates or too long a gap between them. It currently flags 2022 and 2023 (four to five consecutive months missing), traced to a council website migration in mid-2022 that neither the new site nor the Wayback Machine cover. `clean` mode re-classifies or drops non-meeting noise from the manifest.

```bash
council scraper-audit cambridge              # report: per-year completeness + gap guidance
council scraper-audit cambridge clean         # dry run: what would be reclassified/removed
council scraper-audit cambridge clean --apply
```

#### `council wayback-fill cambridge <years...>`
Queries the Wayback Machine's CDX API for archived copies of minutes in years/months the live site no longer serves — the second thing to try once `scraper-audit` flags a gap, before declaring it unrecoverable.

```bash
council wayback-fill cambridge 2022 2023
council wayback-fill cambridge 2022 --months 1-4
council wayback-fill cambridge 2022 --months 1-4 --download   # fetch + update manifest
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

**Scripted alternative:** `council inventory-loop cambridge` runs this exact recipe end to end — steps 1/2/4 scripted, step 3 dispatched as a real `claude -p` call using the same generated instructions. `--dry-run` costs nothing.

```bash
council inventory-loop cambridge --dry-run
council inventory-loop cambridge --limit 20 --max-passes 5
```

Standalone step 3 alone (used internally by the loop, or on its own):

```bash
council inventory-refine cambridge
```

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

Writes `data/sample_validation/report.txt`, `paraphrase_report.txt`, and `summary.json` (the same four target checks as one structured verdict). This is the gate before running at scale.

Pass `--max-chars` matching whatever was used for `extract-sample`.

```bash
council validate-sample cambridge
council validate-sample cambridge --max-chars full
```

**Iteration loop:** extract the sample, validate, read `report.txt`'s INTERPRETATION section, hand-edit `system_prompt.txt` (or `agenda_system_prompt.txt` for agendas), re-extract, repeat until quote completeness >80%, paraphrase <30%, coverage >5%, keyword gap <25%.

**Scripted alternative:** `council extraction-loop cambridge` runs this recipe end to end — extract/validate/threshold-check scripted, the prompt edit dispatched as a real `claude -p` call reading the exact same INTERPRETATION text. `--dry-run` costs nothing; a real run bills at extraction-tier pricing (not the cheap Haiku inventory calls).

```bash
council extraction-loop cambridge --dry-run
council extraction-loop cambridge --max-passes 5
```

Standalone (used internally by the loop, or on its own):

```bash
council extraction-refine cambridge
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

#### `council profile cambridge`
**S2 corpus profile:** a scripted, no-LLM pass over the already-extracted corpus — document/date spans (including a zero-meeting-month gap detector), entity row counts, NULL/coverage rates on the fields already known to be structurally sparse (planning application dates, `councillor_terms`), vote-choice distribution, and identity-resolution signals (councillors with no vote/term activity on this council, family names shared by more than one councillor id — a "worth checking" heuristic, not a confirmed split). One machine-readable document, replacing hand-maintained corpus caveats with something computed fresh each run.

```bash
council profile cambridge
```

Writes `data/{council}_profile.json` (gitignored, refreshed every run) and prints a summary.

#### `council explore`
**S3 discovery:** Explorer generates and tests novel hypotheses against the extracted corpus — a real Claude session (real time, real usage), not a script. Self-directing: no council argument, reads `docs/investigator/Investigator_prompt.txt` Part 0 for scope, seeds itself from the coverage register's worst open gap. Ends with a self-score against `docs/investigator/EXPLORATION_PROTOCOL.md`.

```bash
council explore
```

Findings are appended to `docs/investigator/INVESTIGATIONS.md` (gitignored — names real people).

#### `council refine`
**S4 codification:** Refiner turns a validated Explorer finding into a permanent, council-agnostic entry in `src/analysis/tests.py` / `queries.py`, plus a declaration block (unit of analysis, minimum sample size, principle) the S7 invariant gate enforces. Self-directing — picks the oldest not-yet-refined eligible candidate from `INVESTIGATIONS.md` itself. A real Claude session, not a script.

```bash
council refine
```

---

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

#### `council draft cambridge`
Exports the analysis and the **standard test battery** as static JSON snapshots to
`data/draft/cambridge/<run_id>/` — a private staging area, never committed, never
served. Re-run after any data change (extraction, dedup, relationship build) to get
a fresh candidate for review.

```bash
council draft cambridge
# → data/draft/cambridge/draft_20260805_120000/{overview,scorecard,...}.json + manifest.json
```

The `scorecard` snapshot is produced by the council-agnostic battery in
`src/analysis/tests.py` (`run_test_battery`): each test carries a stable `test_id`,
a recognised-criterion mapping, a supportive/neutral/critical valence, and a chart
payload. Adding a test there makes it run on every council and appear as a panel
automatically.

Before `manifest.json` is written, the **S7 invariant gate** runs over the battery, scripted, no LLM (`src/invariant_gate.py`) — a claim naming someone without declaring it, resting on too small a sample, or naming someone whose identity isn't cleanly resolved blocks the draft immediately, before Editor ever sees it. This is where the Editor role reviews everything else — overclaim language, missing context, unfair singling-out — and Fixer's track-scoped modes act on whatever it flags (`docs/review/`) — nothing here is public until `council publish` says so. To view a draft in the real dashboard while reviewing it, see "Previewing a draft before it's published" in the Dashboard section above.

---

#### `council editor cambridge <run_id>`
**S8, standalone:** defamation-reviews one draft, no Fixer/re-draft loop attached. `council editor-loop` below calls this exact command internally, once per pass — this exists on its own for re-reviewing a draft without re-drafting it, or debugging Editor in isolation.

```bash
council editor cambridge draft_20260805_120000
```

#### `council fixer <track> cambridge <run_id>`
**Standalone:** acts on one track's (`frontend` / `pipeline` / `doc`) flagged issues from the highest-numbered `defamation_review_<n>` in a draft directory, no loop attached. `council editor-loop` calls this exact command internally, once per flagged track — this exists on its own for re-running one track's fix, or debugging a mode in isolation.

```bash
council fixer frontend cambridge draft_20260805_120000
```

#### `council editor-loop cambridge [--max-passes N] [--dry-run]`
**S8:** the scripted draft → Editor → Fixer review loop — draft, review, apply any flagged fixes, repeat up to the pass cap. Composed entirely from the standalone commands above (`council draft`, `council editor`, `council fixer`) rather than a private, duplicated dispatch — every stage this loop drives is independently runnable through the same command a human would use. The pass-counting and dispatch-by-track mechanics are scripted; Editor's and Fixer's own judgment calls, one hop inside those commands, are real `claude -p` sessions. Never calls `council publish` itself; stops at a clean PASS or an escalation and prints what to run next. `--dry-run` prints the plan and makes no `claude` calls — free to run.

```bash
council editor-loop cambridge --dry-run
council editor-loop cambridge --max-passes 3
```

#### `council reply-packets cambridge [--regenerate]`
**S9 right of reply:** assembles one packet per named person, covering every claim about them that hasn't already been sent (tracked in a persisted `sent_ledger.json` — a rerun never re-approaches the same person about the same claim unless `--regenerate` is passed). Scripted, no LLM — never sends anything itself.

```bash
council reply-packets cambridge
```

#### `council render <mode> <council> <run_id>`
**S10:** Renderer turns an already-reviewed draft into an audience-facing product — `plain_language` mode (institutional data → resident-facing summary) or `synthesis` mode (deep product → cross-claim prose). A real Claude session. Not yet wired into any automated workflow, and not yet run for real — this is the only way to run it today.

```bash
council render plain_language cambridge draft_20260805_120000
council render synthesis cambridge draft_20260805_120000
```

---

#### `council publish cambridge --from-draft <path> [--gate-profile interactive|auto] [--confirm "<note>"]`
The gate. Copies a *reviewed* draft's snapshots verbatim into
`frontend/public/data/` for the dashboard — it never recomputes from the
database, so what was reviewed is exactly what ships. `--from-draft` is
always required. `--gate-profile` (default `interactive`) picks how
clearance is proven: `interactive` requires `--confirm`, a human vouching
directly; `auto` requires no `--confirm` and instead independently
re-validates a real Editor PASS record already in the draft directory. See
`docs/review/CONDUCTOR.md`'s "Gate profiles" section — there's no way to
publish without clearing one of these.

```bash
council publish cambridge \
  --from-draft data/draft/cambridge/draft_20260805_120000 \
  --confirm "reviewed by Josef, 2026-08-05, no issues found"
# → frontend/public/data/{overview,scorecard,...}.json + manifest.json
```

Before copying, it re-hashes every draft file and refuses if anything has
changed since the draft was generated (`src/publish_gate.py`) — a review is
only valid for the exact bytes it looked at. See `docs/TESTING.md` for the
full draft → review → publish rationale, including the tier concept that
keeps a future paywalled "full" report out of the public tree by default.

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
    queries.py            — reusable query helpers (per-panel analysis functions)
    tests.py              — the Standard Test Battery: run_test_battery() returns a
                            valenced TestResult per standard governance test
    divergence.py         — officer-recommendation vs outcome matching
  validation/
    core.py               — shared validation logic (five metrics, three-tier quote matching)

  publish_gate.py          — the draft → publish gate seam: DraftManifest,
                            verify_draft_integrity, check_clearance
                            (two gate profiles — interactive: human --confirm;
                            auto: re-validates Editor's on-disk PASS record)

api/
  main.py                 — legacy FastAPI backend (REST view of the queries); not
                            used by the live site, which reads the static snapshots
                            written by `council publish`

frontend/
  src/
    App.tsx               — page layout: Overview + Scorecard + the 23 test panels,
                            in scorecard order (every panel is a battery test)
    api.ts                — typed loaders for the static JSON snapshots (/data/*.json)
    components/
      OverviewPanel        — cross-cutting synthesis (landing panel)
      ScorecardPanel       — the test battery, each row flagged supportive/neutral/critical
      BatteryTestPanel     — generic panel for any test without a bespoke one
      DrillDown            — reusable drill-down drawer + SourceQuote ("the receipt")
      ValenceChip          — the supportive/neutral/critical flag
      <flagship panels>    — ConflictRecusal, RecusalTrend, Power, Sponsorship,
                             TenderConcentration, Transparency, Tenure, Mayoral,
                             ObjectionDose, Divergence, Engagement
      <retired, kept for reuse> — AlignmentHeatmap, CoMoverGraph, TrendsChart,
                             InterestsChart, PlanningTrendChart, PlanningObjections,
                             DissentProfiles, DissentCoalitions (not rendered; each
                             would need promoting to a battery test to return)
    hooks/useData.ts      — shared data-fetching hook
  public/data/*.json      — published snapshots (copied in by `council publish`
                            from a reviewed `council draft`; currently
                            placeholder data — see scripts/generate_placeholder_data.py)
  (run: council draft cambridge, review it, council publish cambridge --from-draft ...
   --confirm ..., then cd frontend && npm run dev)

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
  draft/{council}/{run_id}/ — council draft output: candidate snapshots + manifest
                            (hashes, tiers) for review; gitignored, never served
  published_full/{council}/{run_id}/ — council publish's full-tier (paywall-pending)
                            output; gitignored — private, not part of the public site

.cache/
  llm_responses/          — cached raw LLM responses ({hash}_{prompt-version}.json)
```

---

## Multi-level extraction pipeline

| Level | Stage | What | Cost | Status |
|-------|-------|------|------|--------|
| 0 | Census | Text extraction + keyword scan across all PDFs | Free | **Done** |
| 1 | Inventory | Cheap LLM inventory: one small Haiku call per document | $4.83 actual | **Done** |
| 2 | Schema | Schema and prompt revision from inventory typology | Free | **Done** |
| 3a | Extraction (sample) | Stratified sample selection (18 docs) | Free | **Done** |
| 3b | Extraction (sample) | Sample extraction | ~$0.50 | **Done** |
| 3c | Validation (sample) | Sample validation — all metrics within target; gates the extraction convergence loop | Free | **Done** |
| 4 | Validation (full corpus) | Per-document confidence scoring (`council validate`) | Free | **Done** |
| 5 | Extraction (full corpus) | Full extraction (`council extract`) | ~$70 actual | **Done** (580 docs; full corpus complete 2026-06-22) |
| 6 | Audit | Human audit on random sample, ground-truthing the validation metrics | Free | **Tooling done**; human review pending |

See `docs/pipeline/PIPELINE.md` for the detailed plan, build log, and dependency graph.

---

## Investigator, review, and render pipeline

| Stage | Role | What | Cost | Status |
|-------|------|------|------|--------|
| S2 | Profile | Corpus profile — NULL rates, spans, identity-resolution state | Free | **Built** |
| S3 | Explorer | Hypothesis discovery, tested on training corpora | Claude Code session | **Built**, discovery-only as of v3.0 |
| S4 | Refiner | Codify a validated finding into the permanent battery | Claude Code session | **Built**, v1.2 |
| S6/S7 | Draft + gate | Frozen battery run; scripted invariant gate (name-free, MIN_N, identity) | Free | **Built** |
| S8 | Editor + Fixer | Semantic review (4 classes) + track-scoped fix loop | Claude Code session | **Built**; first real run 2026-08-24 (FAIL, escalated on a human merge decision) |
| S9 | Right of reply | Packet assembly for individual-unit claims | Free | **Built**; never sent for real |
| S10 | Renderer | Plain-language / synthesis rendering of a reviewed draft | Claude Code session | **Built**; never run for real (no calibration data) |
| — | Publish | Human-gated copy into the public site | Free | **Built** |

See `docs/INFORMATION_ARCHITECTURE.md` and `docs/AGENT_DESIGN.md` for the detailed flow and design rationale.

---

## Adding a second council

1. Create `src/scraper/<council>.py` subclassing `BaseScraper`
2. Add one entry to the `COUNCILS` dict in `src/cli.py`

All CLI commands work immediately for the new council — including `council draft`,
which runs the identical test battery and produces a comparable scorecard. Because
every test uses a stable `test_id`, two councils' results line up test-for-test
(and "not computable" rows show which tests a given corpus supports).

---

## Documentation

**`docs/MAP.md` is the index** — it maps every doc to its sub-project track and
shows how the tracks connect. Point a fresh session at it first. The docs are
organised into four tracks under `docs/`:

| Track | Docs | What it covers |
|-------|------|----------------|
| **root** | `README.md`, `docs/MAP.md` | This file (pipeline, schema, CLI, dashboard, layout) + the doc map |
| | `docs/TESTING.md` | Testing & CI: what's covered, ruff config rationale, why LLM calls stay out of required CI |
| **pipeline** | `docs/pipeline/PIPELINE.md` | Extraction pipeline: plan, build log, dependency graph, analysis-query design (merged) |
| | `docs/pipeline/DATA_ENRICHMENT.md` | Forward-looking re-extraction / external-join backlog (populated by the investigator) |
| **investigator** | `docs/investigator/Investigator_prompt.txt` | The runtime investigation prompt: criteria (Nolan / CIPFA / Best Value), standard of proof, valences, two-tier bar |
| | `docs/investigator/INVESTIGATION_PROTOCOL.md` | The benchmark-gated plan for iterating the prompt above |
| | `docs/investigator/INVESTIGATIONS.md` | The detective's notebook — every hypothesis, findings and honest nulls |
| | `docs/investigator/FINDINGS_SUMMARY.md` | Prose synthesis of what the corpus says, in the round |
| **frontend** | `docs/frontend/INTERACTIVITY.md` | The panel-interactivity recipe and per-panel drill-down backlog |
| | `docs/frontend/PRODUCT_ROADMAP.md` | Forward-looking product surfaces (council map, digest feed) |
| **strategy** | `docs/strategy/PRIVATE_ASSESSMENT.md` | Private: defamation / grant-readiness / ambition assessment (gitignored) |
