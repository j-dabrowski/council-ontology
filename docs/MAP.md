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
> shared reference layer), `docs/review/editor/Editor_prompt.txt` +
> `docs/review/fixer/Fixer_prompt.txt` + its three `*_mode.txt` files
> (post-draft review/fix — two more roles, same shared-layer-plus-modes shape),
> and `docs/research/Researcher_prompt.txt` (precedent research — grows the
> Investigator's Part 3 taxonomy; council-agnostic, not corpus-gated).

---

## Cross-cutting infra

Not owned by one track — gates all of them:
- `TESTING.md` — testing & CI: what's covered, ruff config rationale, why LLM
  calls stay out of the required CI path. Companion to `.github/workflows/ci.yml`.
  Current-state reference — kept accurate as designs change, not a history.
- `CICD_DECISIONS.md` — the CI/CD decision log: dated entries (decision,
  alternatives considered, trade-off) for the choices behind `TESTING.md`'s
  current state, kept even after that state moves on — e.g. the single
  `publish.yml` that committed straight to `main` before the draft/publish
  gate replaced it. Source material for an eventual write-up and for
  interview prep; also tracks open/undecided infra work (Cloud Run API
  deploy).
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
- `pipeline/DATA_ENRICHMENT.md` — pattern/instance re-extraction backlog (restructured
  2026-08-20, `DISCOVERY_LOOP_DESIGN.md` Component B). **Written by the investigator track**
  (unchanged); each entry now also carries a council-agnostic **pattern** layer above its
  corpus-specific instance. **Read by the typology stage** on every new corpus (Component
  C) — `council typology <council>` cross-references its pattern list against the current
  corpus's rare headings/`other_content` before generating the Level 2 schema prompt, so
  known gaps get caught before extraction commits, not only after via re-extraction.
- **Loop:** recursive refinement — cheap broad passes validate expensive deep passes. The
  full Cambridge corpus is extracted, so this track is in maintenance unless a re-extraction
  (from `DATA_ENRICHMENT.md`) or a second council is started.

### 🔍 Investigator — *actively iterating*
Interrogates the database and produces graded, sourced findings. Three prompt modes,
one shared reference layer, two protocol documents.

**Prompt files (runtime artefacts — not docs; iterated, never freely edited mid-run):**
- `investigator/Investigator_prompt.txt` — **shared reference layer** (Parts 0–5):
  schema, data caveats, query tooling, criteria frameworks, failure taxonomy,
  defensibility. Read by all three modes before doing anything. Part 3 (the failure
  taxonomy) now grows two ways: from this project's own corpus investigations (as
  before), and from the 🔭 Research track's human-applied candidates (Part 3.5,
  added 2026-08-20, is the first of the latter, merged directly in design
  conversation before the track's file-review gate existed — see below).
- `investigator/Explorer_prompt.txt` — **exploration mode** (v2.6): generate and test
  novel hypotheses; Stage 9 self-scores the session and proposes the next prompt edit.
- `investigator/Refiner_prompt.txt` — **refinement mode** (v1.0): codify a validated
  finding into a permanent, council-agnostic entry in `tests.py` / `queries.py` —
  or retroactively verify/fix an already-shipped test against the six-dimension
  benchmark (two entry points; the retroactive path is the one with real
  calibration data so far, see `AUDIT_2026-08-14.md`).
- `investigator/Runner_prompt.txt` — **production run mode** (v1.0): execute the frozen
  battery, export JSON snapshots, verify the frontend, spot-check for regressions
  against the latest `AUDIT_<date>.md`. No hypothesis generation, no self-scoring;
  never calls `council publish` itself — a clean run is input to the human
  publish decision, not a substitute for it.

**Protocol documents:**
- `investigator/EXPLORATION_PROTOCOL.md` — benchmark-gated improvement loop for
  `Explorer_prompt.txt`: seven dimensions, Cambridge calibration scores, improvement
  loop. Explorer prompt is improved until benchmark is cleared, then frozen.
- `investigator/REFINEMENT_PROTOCOL.md` — benchmark-gated improvement loop for
  `Refiner_prompt.txt` and the test harness. Six dimensions defined 2026-08-14
  (two hard gates: verification accuracy, caveat/join safety); first calibration
  data recorded.

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

### 🔭 Research — *new, council-agnostic, not corpus-gated*
Grows the investigator's failure/effectiveness taxonomy from real-world AU/UK
local-government precedent (audits, inquiries, news investigations). Added
2026-08-20 (`DISCOVERY_LOOP_DESIGN.md` Components D/E). Unlike the other four
tracks, it has no per-corpus state and no per-council cadence — it runs on
its own trigger (recommended: before onboarding a new council, plus
on-demand — see `RESEARCH_PROTOCOL.md`'s open cadence question).
- `research/Researcher_prompt.txt` — **runtime artefact** (v1.2, gated by
  default): surveys real precedent, drafts candidate genres, self-checks
  against the four-dimension benchmark, and —**file-review mode (default)**
  — writes a ready-to-apply pending-merge file to
  `research/pending_merges/` for a human to open and apply by hand, rather
  than editing `Investigator_prompt.txt` Part 3 / `pipeline/DATA_ENRICHMENT.md`
  directly. **Auto-merge mode** (direct, same-session merge, no file) is
  still available, but only when a human explicitly declares it at session
  start — never Researcher's own choice. Either way ends with a
  machine-readable stage-contract block (`status: DONE`, `gate_mode`,
  pending/merged/rejected counts, `next`). Never DB-scoped like Investigator
  (Principle 0's firewall is what stays absolute: taxonomy-level output
  only, never a claim about a specific council in scope).
- `research/RESEARCH_PROTOCOL.md` — benchmark-gated governance for
  `Researcher_prompt.txt`, same shape as `EXPLORATION_PROTOCOL.md`: four
  dimensions (non-duplication, grounded precedent, data-signature
  translatability, defamation safety), the two-mode merge flow, calibration
  log (empty — no session has run yet).
- `research/pending_merges/` — where a file-review-mode session parks a
  passing candidate's ready-to-apply text (both target-file blocks +
  apply/reject instructions) until a human acts on it. Empty is the normal
  steady state between sessions.
- `research/PRECEDENT_BANK.md` — the audit log of every Researcher
  candidate: `merged` / `candidate — pending human review` / `rejected`,
  each in `Investigator_prompt.txt` Part 3's row-format. Seeded with P1
  (Policy / programme effectiveness), logged retroactively as the worked
  example — it was merged as Part 3.5 directly, before this track existed.
- **Loop:** run Researcher → self-score each candidate against the four
  dimensions → passing candidates get a pending-merge file (default) or are
  merged directly into `Investigator_prompt.txt` Part 3 **and**
  `DATA_ENRICHMENT.md`'s pattern layer in the same session (only if
  auto-merge mode was explicitly declared); failing candidates logged
  `rejected` in `PRECEDENT_BANK.md` (never deleted, so they aren't
  re-proposed). Gated by default, matching every other track — autonomy is
  an explicit, per-session opt-in, not a shipped default.

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
   │  (pattern/    │  write: enrichment│ FINDINGS_SUMM. │                    │
   │  instance)    │  backlog (as before) └────┬────────┘   council publish  │
   │      │        │                           │            (pipeline cmd)   │
   │      │ read: typology stage                │ protocol governs            │
   │      │ cross-references pattern             │ prompt iteration            │
   │      ▼ layer before Level 2 (NEW)            │                            │
   │  (self-loop)  │                             │                            │
   └──────┬────────┘                             │                            │
          │                                      │                            │
          │  council publish exports             │                            │
          └────────── snapshots ─────────────────┴─────────────► snapshots ───┘

                         ┌─────────────────────────────────────────────┐
                         │  🔭 RESEARCH (NEW — council-agnostic)        │
                         │  Researcher_prompt.txt → self-scores vs      │
                         │  RESEARCH_PROTOCOL.md (4 dims)               │
                         │  → pending_merges/ file (default) OR         │
                         │    self-merge (opt-in only)  ───────────────────► Investigator_
                         │  → logs to PRECEDENT_BANK.md                 │      prompt.txt Part 3
                         └─────────────────────────────────────────────┘       + DATA_ENRICHMENT.md
                                                                                (human applies, unless
                                                                                 auto-merge declared)
```

The non-obvious edges, spelled out:

| Edge | Direction | What flows |
|------|-----------|-----------|
| **Pipeline → Investigator** | substrate | The extracted DB + schema is what the investigator queries. Extraction **caveats** (UPPERCASE enums, minutes-only vs agenda contamination, `item_reference` not meeting-unique) are documented in `Investigator_prompt.txt` Part 0 — change the pipeline and that section must follow. |
| **Investigator → Pipeline** (`DATA_ENRICHMENT.md`) | backlog | Every structural kill in an Explorer session is written into `pipeline/DATA_ENRICHMENT.md`, with a council-agnostic pattern layer above the corpus-specific instance — *while `data_enrichment_status` in `config/agent_switches.json` reads OPEN* (`Explorer_prompt.txt` v2.6 step 0). Flip that value to FROZEN once the backlog is judged sufficient and Explorer skips the write (its core investigation is unaffected); reading the file (typology cross-reference, Pattern-exists check) still happens either way. That file lives in the pipeline track but is *populated by the investigator* — it's the bridge that turns "we couldn't test X" into a planned re-extraction. |
| **Pipeline → Pipeline** (`DATA_ENRICHMENT.md` → typology stage) — *new 2026-08-20* | self-loop, read | On every new corpus, the typology convergence loop (`council typology <council>`) cross-references its rare-heading/`other_content` aggregation against `DATA_ENRICHMENT.md`'s pattern layer before generating the Level 2 schema-update prompt. Pure text parse, no new LLM call — reuses the aggregation typology already computes. This is what lets schema-gap knowledge compound across corpora instead of only ever being caught reactively, post-extraction. |
| **Research → Investigator + Pipeline** (→ `pending_merges/` → Part 3 + `DATA_ENRICHMENT.md`) — *new 2026-08-20, gated by default as of v1.2* | taxonomy + pattern growth | A candidate genre from the 🔭 Research track that clears its own four-dimension self-check gets a ready-to-apply file in `research/pending_merges/` (default) for a human to paste into both `Investigator_prompt.txt` Part 3 and `pipeline/DATA_ENRICHMENT.md`'s pattern layer — or, only if a human explicitly declared auto-merge mode at session start, Researcher writes both directly, same session. Council-agnostic — benefits every future corpus, not just whichever one (if any) motivated the research. |
| **RESEARCH_PROTOCOL.md → Researcher_prompt.txt** — *new 2026-08-20* | governance | Same shape as `EXPLORATION_PROTOCOL.md → Explorer_prompt.txt`: benchmark-gated. Default is file-review (Researcher scores its own session, writes pending-merge files, a human applies them); auto-merge is available only as an explicit per-session opt-in, ending in a stage-contract completion block either way. |
| **EXPLORATION_PROTOCOL.md → Explorer_prompt.txt** | governance | The exploration protocol is the benchmark-gated plan for iterating the explorer prompt. Stage 9 of each session self-scores against the benchmark and proposes the next edit; a human approves before the version is bumped. |
| **REFINEMENT_PROTOCOL.md → Refiner_prompt.txt** | governance | The refinement protocol governs how validated findings are codified into permanent battery tests, and (as of 2026-08-14) how already-shipped tests are retroactively verified against the same six-dimension benchmark. |
| **Investigator → Frontend** | findings | Findings in `INVESTIGATIONS.md` become panels via the `INTERACTIVITY.md` recipe; the standard test battery (`src/analysis/tests.py`) feeds the Scorecard; `FINDINGS_SUMMARY.md` feeds the Overview panel. |
| **Pipeline → Frontend** | data | `council publish` (a pipeline CLI command) exports the static JSON snapshots the panels read; drill-down "receipts" come from the `extraction_evidence` table the pipeline populates. |
| **Strategy → all** | priorities | `PRIVATE_ASSESSMENT.md` consumes every track's output to rank what matters next (second council, defamation mitigation on named individuals, About/methodology pages). |
| **Second-council loop** | cross-track | Adding a council touches all three working tracks: pipeline scraper + prompt-generalisation review, de-Cambridge-ing the investigator prompt, and the council-agnostic battery. Tracked in `PIPELINE.md` ("Longer term") and `PRIVATE_ASSESSMENT.md`. |

---

## "Where do I add X?"

| If you're… | Go to |
|------------|-------|
| changing extraction/scraping/validation/schema | `pipeline/PIPELINE.md` |
| noting a field that would unlock a new analysis (this corpus only) | `pipeline/DATA_ENRICHMENT.md` — instance layer (then it becomes a pipeline re-extraction) |
| noting a reusable **cross-corpus** pattern (not just this corpus's gap) | `pipeline/DATA_ENRICHMENT.md` — pattern layer, above the instance; read automatically by the next corpus's typology stage |
| proposing a new failure/effectiveness genre from real-world precedent | `research/Researcher_prompt.txt` (run) — writes a ready-to-apply file to `research/pending_merges/` when a candidate clears its own 4-dimension check (default; you then paste it into `investigator/Investigator_prompt.txt` Part 3 and `pipeline/DATA_ENRICHMENT.md` yourself), or self-merges directly only if you explicitly ran it in auto-merge mode; `research/PRECEDENT_BANK.md` is the resulting audit log |
| improving the researcher prompt | `research/RESEARCH_PROTOCOL.md` (benchmark) → bump `research/Researcher_prompt.txt` |
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
| planning the end-to-end order to run all stages (CLI + agents) for a new corpus | `pipeline/PIPELINE.md` ("Longer term → Corpus onboarding order") — design sketch, not built; first-corpus vs subsequent-corpus sequencing |
| planning for many-council, recurring/scheduled operation (after onboarding) | `pipeline/PIPELINE.md` ("Longer term → Production scale") — design sketch, not built; cross-referenced from `review/CONDUCTOR.md` |
| building a panel or a drill-down | `frontend/INTERACTIVITY.md` — read its hard rule on never hardcoding a councillor name/claim in component source before writing any JSX |
| planning a new product surface | `frontend/PRODUCT_ROADMAP.md` |
| weighing risk, funding, or direction | `strategy/PRIVATE_ASSESSMENT.md` |
| flipping a gate that controls agent behavior (data-enrichment freeze, researcher default gate mode, conductor pass cap) | `config/agent_switches.json` (loaded by `src/agent_config.py`) — not the prose docs that describe each gate |
| onboarding / public/dev reference | root `README.md` |
| adding a test, changing ruff config, editing CI | `TESTING.md` |
| making (or reversing) a CI/CD infra decision — new workflow, auth approach, deploy target | log it in `CICD_DECISIONS.md` (dated entry: decision, alternatives, trade-off), then update `TESTING.md` if the current-state description changed |
| publishing data so it's actually public (`council publish`, Vercel, GCS) | `TESTING.md` ("Draft & publish workflow") — the gate; note it covers the *data* layer only, not component source (see the panel row above) |
| committing changes in this repo | `TESTING.md` ("Commit conventions") |
