# Documentation Map

**Start here.** This project is run as four loosely-coupled sub-projects ("tracks").
Each track has its own docs, its own iteration loop, and its own state of completion.
This file maps every doc to its track and — more importantly — shows **how the tracks
feed each other**. Read this first in a fresh session, then open the track you're working in.

> The public/dev entry point is the root `README.md` (schema, CLI, dashboard, layout).
> `docs/MAP.md` (this file) is the internal index. The prompts that run on the LLM
> are **runtime artifacts**, not docs: `src/extraction/*.txt` (extraction),
> `docs/investigator/Investigator_prompt.txt` + `Explorer_prompt.txt` /
> `Refiner_prompt.txt` / `Runner_prompt.txt` (investigation — three modes, one
> shared reference layer), and `docs/review/editor/Editor_prompt.txt` +
> `docs/review/fixer/Fixer_prompt.txt` + its three `*_mode.txt` files
> (post-draft review/fix — two more roles, same shared-layer-plus-modes shape).

---

## Cross-cutting infra

Not owned by one track — gates all of them:
- `TESTING.md` — testing & CI: what's covered, ruff config rationale, why LLM
  calls stay out of the required CI path. Companion to `.github/workflows/ci.yml`.
- `review/` — the AI-assisted review/fix stage between `council draft` and
  `council publish`: **Editor** (reviews a draft for defamation exposure
  across every track) and **Fixer** (three modes — frontend / pipeline /
  doc — that act on Editor's flags), chained by the **Conductor**
  (`review/CONDUCTOR.md`). Start at `review/REVIEW.md`. Untested as of
  2026-08-10 — see that file's status note before treating any of it as
  calibrated.

## The four tracks

### 🛠 Pipeline — *mostly frozen*
Turns council-minutes PDFs into a structured, auditable SQLite database.
- `pipeline/PIPELINE.md` — the consolidated pipeline doc: **plan + build log + analysis-query
  design** (merged from the former PIPELINE / IMPLEMENTATION_ANALYSIS / ANALYSIS_ROADMAP).
- `pipeline/DATA_ENRICHMENT.md` — forward-looking re-extraction / external-join backlog.
  **Authored by the investigator track**, consumed here (see cross-connections).
- **Loop:** recursive refinement — cheap broad passes validate expensive deep passes. The
  full Cambridge corpus is extracted, so this track is in maintenance unless a re-extraction
  (from `DATA_ENRICHMENT.md`) or a second council is started.

### 🔍 Investigator — *actively iterating*
Interrogates the database and produces graded, sourced findings. Three prompt modes,
one shared reference layer, two protocol documents.

**Prompt files (runtime artefacts — not docs; iterated, never freely edited mid-run):**
- `investigator/Investigator_prompt.txt` — **shared reference layer** (Parts 0–5):
  schema, data caveats, query tooling, criteria frameworks, failure taxonomy,
  defensibility. Read by all three modes before doing anything.
- `investigator/Explorer_prompt.txt` — **exploration mode** (v2.3): generate and test
  novel hypotheses; Stage 9 self-scores the session and proposes the next prompt edit.
- `investigator/Refiner_prompt.txt` — **refinement mode** (stub): codify a validated
  finding into a permanent, council-agnostic entry in `tests.py` / `queries.py`.
- `investigator/Runner_prompt.txt` — **production run mode** (stub): execute the frozen
  battery, export JSON snapshots, verify the frontend. No hypothesis generation.

**Protocol documents:**
- `investigator/EXPLORATION_PROTOCOL.md` — benchmark-gated improvement loop for
  `Explorer_prompt.txt`: seven dimensions, Cambridge calibration scores, improvement
  loop. Explorer prompt is improved until benchmark is cleared, then frozen.
- `investigator/REFINEMENT_PROTOCOL.md` — benchmark-gated improvement loop for
  `Refiner_prompt.txt` and the test harness. Benchmark TBD after first refinement run.

**Investigation records:**
- `investigator/INVESTIGATIONS.md` — the detective's notebook; every hypothesis,
  finding, and honest null, by session/phase. Session headers record benchmark scores.
- `investigator/FINDINGS_SUMMARY.md` — the prose synthesis across all findings.

**Loop (Exploration):** run Explorer prompt → append to INVESTIGATIONS → Stage 9
self-score → if below threshold, propose edit to `Explorer_prompt.txt` and bump
version; if at threshold, freeze Explorer and hand off to Refiner.
**Loop (Refinement):** run Refiner prompt → verify test against hand-computed number
→ score against refinement benchmark → if below threshold, improve `Refiner_prompt.txt`;
if at threshold, freeze and use Runner for production.

### 🖥 Frontend — *active*
The React/Vite dashboard that renders findings with drill-down to source quotes.
- `frontend/INTERACTIVITY.md` — the panel-interactivity recipe and per-panel drill-down backlog.
- `frontend/PRODUCT_ROADMAP.md` — forward-looking surfaces (council boundary map, digest feed).
- **Loop:** a finding becomes a panel via the INTERACTIVITY recipe; `council publish` exports
  the snapshots the panels read.

### 📈 Strategy — *private*
- `strategy/PRIVATE_ASSESSMENT.md` — honest assessment of defamation exposure, grant-readiness,
  and the long-range ambition. Gitignored. Reads the output of every other track to set priorities.

---

## How the tracks connect

```
                         ┌─────────────────────────────────────────────┐
                         │  STRATEGY (PRIVATE_ASSESSMENT.md)            │
                         │  reads everything → sets priorities          │
                         └───────▲─────────────▲──────────────▲────────┘
                                 │             │              │
   ┌───────────────┐   DB + schema    ┌────────────────┐  findings   ┌──────────────┐
   │   PIPELINE    │ ───────────────► │  INVESTIGATOR  │ ──────────► │   FRONTEND   │
   │  PIPELINE.md  │  (substrate +    │ Investigator_  │  become     │INTERACTIVITY │
   │               │   caveats feed   │ prompt.txt +   │  panels     │PRODUCT_ROAD- │
   │  DATA_ENRICH- │   prompt Part 0) │ INVESTIGATIONS │             │MAP.md        │
   │  MENT.md  ◄───┼──────────────────┤ + PROTOCOL +   │             └──────┬───────┘
   │   (re-extract │  enrichment       │ FINDINGS_SUMM. │                    │
   │    backlog)   │  backlog authored └───────┬────────┘   council publish  │
   └──────┬────────┘  by investigator          │            (pipeline cmd)   │
          │                                     │ protocol governs            │
          │  council publish exports            │ prompt iteration            │
          └────────── snapshots ────────────────┴─────────────► snapshots ────┘
```

The non-obvious edges, spelled out:

| Edge | Direction | What flows |
|------|-----------|-----------|
| **Pipeline → Investigator** | substrate | The extracted DB + schema is what the investigator queries. Extraction **caveats** (UPPERCASE enums, minutes-only vs agenda contamination, `item_reference` not meeting-unique) are documented in `Investigator_prompt.txt` Part 0 — change the pipeline and that section must follow. |
| **Investigator → Pipeline** (`DATA_ENRICHMENT.md`) | backlog | When an investigation is **scored against the protocol benchmark**, the gaps it hits (fields that would unlock deeper analysis) are written into `pipeline/DATA_ENRICHMENT.md`. That file lives in the pipeline track but is *populated by the investigator* — it's the bridge that turns "we couldn't test X" into a planned re-extraction. |
| **EXPLORATION_PROTOCOL.md → Explorer_prompt.txt** | governance | The exploration protocol is the benchmark-gated plan for iterating the explorer prompt. Stage 9 of each session self-scores against the benchmark and proposes the next edit; a human approves before the version is bumped. |
| **REFINEMENT_PROTOCOL.md → Refiner_prompt.txt** | governance | The refinement protocol governs how validated findings are codified into permanent battery tests. Benchmark TBD after first refinement run. |
| **Investigator → Frontend** | findings | Findings in `INVESTIGATIONS.md` become panels via the `INTERACTIVITY.md` recipe; the standard test battery (`src/analysis/tests.py`) feeds the Scorecard; `FINDINGS_SUMMARY.md` feeds the Overview panel. |
| **Pipeline → Frontend** | data | `council publish` (a pipeline CLI command) exports the static JSON snapshots the panels read; drill-down "receipts" come from the `extraction_evidence` table the pipeline populates. |
| **Strategy → all** | priorities | `PRIVATE_ASSESSMENT.md` consumes every track's output to rank what matters next (second council, defamation mitigation on named individuals, About/methodology pages). |
| **Second-council loop** | cross-track | Adding a council touches all three working tracks: pipeline scraper + prompt-generalisation review, de-Cambridge-ing the investigator prompt, and the council-agnostic battery. Tracked in `PIPELINE.md` ("Longer term"), `DATA_ENRICHMENT.md` #12, and `PRIVATE_ASSESSMENT.md`. |

---

## "Where do I add X?"

| If you're… | Go to |
|------------|-------|
| changing extraction/scraping/validation/schema | `pipeline/PIPELINE.md` |
| noting a field that would unlock a new analysis | `pipeline/DATA_ENRICHMENT.md` (then it becomes a pipeline re-extraction) |
| running an exploration session (new hypotheses) | `investigator/Explorer_prompt.txt` (run) → `investigator/INVESTIGATIONS.md` (record) |
| codifying a finding into the test battery | `investigator/Refiner_prompt.txt` (run) → `src/analysis/tests.py` + `queries.py` |
| running the frozen battery in production | `investigator/Runner_prompt.txt` |
| improving the exploration prompt | `investigator/EXPLORATION_PROTOCOL.md` (benchmark) → bump `Explorer_prompt.txt` |
| improving the refinement prompt / harness | `investigator/REFINEMENT_PROTOCOL.md` (benchmark) → bump `Refiner_prompt.txt` |
| writing up cross-cutting conclusions | `investigator/FINDINGS_SUMMARY.md` |
| reviewing a draft for defamation exposure | `review/editor/Editor_prompt.txt` (run) → writes `data/draft/<council>/<run_id>/defamation_review_<n>.md` |
| improving the editor prompt | `review/editor/EDITOR_PROTOCOL.md` (benchmark) → bump `Editor_prompt.txt` |
| fixing a flagged claim (frontend/pipeline/doc) | `review/fixer/<track>_mode.txt` (run) — only the track(s) the editor tagged |
| adding a fourth fixer track | `review/fixer/FIXER_PROTOCOL.md` — additive by design, see "Adding a fourth mode" |
| chaining editor + fixer, or asking what happens after a FAIL | `review/CONDUCTOR.md` — the loop, the pass cap, the one rule (never calls `council publish`) |
| planning for many-council, recurring/scheduled operation | `pipeline/PIPELINE.md` ("Longer term → Production scale") — design sketch, not built; cross-referenced from `review/CONDUCTOR.md` |
| building a panel or a drill-down | `frontend/INTERACTIVITY.md` — read its hard rule on never hardcoding a councillor name/claim in component source before writing any JSX |
| planning a new product surface | `frontend/PRODUCT_ROADMAP.md` |
| weighing risk, funding, or direction | `strategy/PRIVATE_ASSESSMENT.md` |
| onboarding / public/dev reference | root `README.md` |
| adding a test, changing ruff config, editing CI | `TESTING.md` |
| publishing data so it's actually public (`council publish`, Vercel, GCS) | `TESTING.md` ("Draft & publish workflow") — the gate; note it covers the *data* layer only, not component source (see the panel row above) |
| committing changes in this repo | `TESTING.md` ("Commit conventions") |
