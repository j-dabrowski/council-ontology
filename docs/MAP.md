# Documentation Map

**Start here.** This project is run as four loosely-coupled sub-projects ("tracks").
Each track has its own docs, its own iteration loop, and its own state of completion.
This file maps every doc to its track and — more importantly — shows **how the tracks
feed each other**. Read this first in a fresh session, then open the track you're working in.

> The public/dev entry point is the root `README.md` (schema, CLI, dashboard, layout).
> `docs/MAP.md` (this file) is the internal index. The two prompts that run on the LLM
> are **runtime artifacts**, not docs: `src/extraction/*.txt` (extraction) and
> `docs/investigator/Investigator_prompt.txt` (investigation).

---

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
Interrogates the database and produces graded, sourced findings.
- `investigator/Investigator_prompt.txt` — **the runtime prompt** used each investigation
  (role, criteria, standard of proof, valences, two-tier bar). This is operational, not
  documentation; it is iterated, never freely edited mid-run.
- `investigator/INVESTIGATION_PROTOCOL.md` — the **benchmark-gated plan for improving** that
  prompt: the staged protocol, the stopping condition, the version discipline.
- `investigator/INVESTIGATIONS.md` — the detective's notebook; every hypothesis, finding, and
  honest null, by session/phase.
- `investigator/FINDINGS_SUMMARY.md` — the prose synthesis across all findings.
- **Loop:** run protocol → append to INVESTIGATIONS → score against the benchmark → if below
  threshold, improve `Investigator_prompt.txt` and bump its version; if at threshold, freeze
  and run. INVESTIGATION_PROTOCOL.md owns this loop.

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
| **INVESTIGATION_PROTOCOL.md → Investigator_prompt.txt** | governance | The protocol is the benchmark-gated **plan for iterating** the runtime prompt. The prompt is the artifact; the protocol decides when to improve it, how to score it, and when to freeze it. Each INVESTIGATIONS session header notes the prompt version used. |
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
| running or recording an investigation | `investigator/Investigator_prompt.txt` (run) → `investigator/INVESTIGATIONS.md` (record) |
| improving how investigations are run | `investigator/INVESTIGATION_PROTOCOL.md` → then bump `Investigator_prompt.txt` |
| writing up cross-cutting conclusions | `investigator/FINDINGS_SUMMARY.md` |
| building a panel or a drill-down | `frontend/INTERACTIVITY.md` |
| planning a new product surface | `frontend/PRODUCT_ROADMAP.md` |
| weighing risk, funding, or direction | `strategy/PRIVATE_ASSESSMENT.md` |
| onboarding / public/dev reference | root `README.md` |
