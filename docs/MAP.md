# Documentation Map

**Start here.** This project is run as five loosely-coupled sub-projects ("tracks").
Each track has its own docs, its own iteration loop, and its own state of completion.
This file maps every doc to its track and — more importantly — shows **how the tracks
feed each other**. Read this first in a fresh session, then open the track you're working in.

> The public/dev entry point is the root `README.md` (schema, CLI, dashboard, layout).
> `docs/MAP.md` (this file) is the internal index. The prompts that run on the LLM
> are **runtime artifacts**, not docs: `src/extraction/*.txt` (extraction),
> `docs/investigator/Investigator_prompt.txt` + `Explorer_prompt.txt` /
> `Refiner_prompt.txt` (investigation — two active modes, one shared
> reference layer; `Runner_prompt.txt` is archived), `docs/review/editor/Editor_prompt.txt` +
> `docs/review/fixer/Fixer_prompt.txt` + its three `*_mode.txt` files
> (post-draft review/fix — two more roles, same shared-layer-plus-modes shape),
> `docs/render/Renderer_prompt.txt` + its two `*_mode.txt` files
> (S10 audience rendering — same shape again, never run yet), and
> `docs/research/Researcher_prompt.txt` (precedent research — grows the
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
  (`review/CONDUCTOR.md`). As of 2026-08-24 Editor's own review session no
  longer scores itself — a separate follow-on, `council editor-score`
  (two layers: a deterministic script, then a fresh-context agent that
  never reads `Editor_prompt.txt`), does (`docs/GENERATION_SCORING_SPLIT.md`
  §2). Start at `review/REVIEW.md`. Untested as of 2026-08-10 — see that
  file's status note before treating any of it as calibrated.
- `render/` — the S10 audience-rendering stage, after a claim has cleared
  S7/S8 (and S9, for any named-individual claim): **Renderer**, two modes
  (plain-language: institutional product → resident-facing summary;
  synthesis: deep product → cross-claim prose, the `FINDINGS_SUMMARY.md` /
  Overview successor) on one shared layer, same shape as Investigator and
  Fixer. Start at `render/Renderer_prompt.txt`; benchmark in
  `render/RENDERER_PROTOCOL.md`. New 2026-08-23, never run — no calibration
  data yet.
- `src/reply_packets.py` — S9 right of reply, packet assembly (scripted, no
  LLM): groups every `individual`-unit claim with no reply on file by the
  person it names, renders a fixed template, writes it for a human to send
  (`council reply-packets <council>`). Never sends anything itself. Today
  the battery is 100% `institutional`-unit, so a healthy run always
  produces zero packets.
- `AGENT_PROMPTS.md` — the fixed, ready-to-run invocation command for every
  agent role across all tracks (Explorer/Refiner, Researcher,
  Conductor/Editor/Fixer, Renderer) — no per-call customization for the self-directing
  roles, so the same command works for a human starting a session or a
  future scheduled/programmatic caller. The prompt *text* itself lives one
  level down, in `agent_prompts/<role>.txt` (same pattern as every mode
  prompt file — never inlined here, so there's exactly one copy); this doc
  is the command layer plus GitHub Actions setup (install, auth) on top of
  those files.
- `AUTOMATION_ARCHITECTURE.md` — partially built; running the
  full agent pipeline via GitHub Actions: the GCS-vs-git rule that decides
  where every file lands, a stage-by-stage input/output map, and a uniform
  rule (any pipeline run that writes a git-tracked file change opens its
  own PR — never a direct commit) applied across the DB-update pipeline
  and every agent role. Part 4 (revised and built 2026-08-24) specifies
  and implements the branch-based escalation model: logical runs as
  chains of working-branch segments, success PRs to `main`, escalations
  PR to a `staging` branch whose merge is the approval that resumes the
  run (fresh/resume dispatch modes, `run_state.json`, `resume.yml`).
  Extends
  `pipeline/PIPELINE.md`'s "Production scale" section into the
  investigator/review tracks that section doesn't cover.
- `INFORMATION_ARCHITECTURE.md` + `AGENT_DESIGN.md` — the 2026-08-23
  top-down redesign (accepted, not built): the general-engine/domain-pack
  split, the S1–S10 information flow, the claim object with its
  unit-of-analysis field, tier derivation (institutional vs deep product),
  the scripted invariant gate ahead of a narrowed Editor, right of reply,
  and the corpus-role discovery/confirmation split — then the stage-by-stage
  owner assignment derived from that flow (Runner retired, Renderer added,
  autonomy ladder for scheduled operation, build order). Grounded in
  `investigator/COVERAGE_AUDIT_2026-08-23.md` (see the investigator track).
  Until the build lands, the *current-state* docs below remain accurate;
  these two describe the target.

## The five tracks

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
  defensibility. Read by both modes before doing anything (Runner, the third
  mode, is archived — see below). Part 3 (the failure
  taxonomy) now grows two ways: from this project's own corpus investigations (as
  before), and from the 🔭 Research track's human-applied candidates (Part 3.5,
  added 2026-08-20, is the first of the latter, merged directly in design
  conversation before the track's file-review gate existed — see below).
- `investigator/Explorer_prompt.txt` — **exploration mode** (v3.0, discovery-only
  as of 2026-08-23): generate and test novel hypotheses, seeded from the
  coverage register's worst open gap rather than raw domain-breadth counting;
  no longer surveys the corpus (consumes `council profile`'s output instead)
  or builds anything (panels/evidence/synthesis moved to the future Renderer
  role). Stage 3 self-scores the session against a four-dimension benchmark
  and proposes the next prompt edit.
- `investigator/Refiner_prompt.txt` — **refinement mode** (v1.2): codify a validated
  finding into a permanent, council-agnostic entry in `tests.py` / `queries.py` —
  or retroactively verify/fix an already-shipped test against the
  seven-dimension benchmark (two entry points; the retroactive path is the
  one with real calibration data so far, see `AUDIT_2026-08-14.md`). As of
  2026-08-23 also emits a declaration block (unit/MIN_N/strength/principle)
  for the S7 invariant gate and updates the coverage register.
- `investigator/Runner_prompt.txt` — **ARCHIVED 2026-08-23** (`AGENT_DESIGN.md`
  §2/§6 Step 6). Its duties were all scripted the moment S7 existed: battery
  execution/export is `council draft`; regression spot-checks are the S7
  invariant gate plus CI; "clean run as input to the human publish decision"
  is the draft manifest + `gate_report.json`. Kept for the historical record;
  no invocation command exists for it any more (`AGENT_PROMPTS.md`).

**Protocol documents:**
- `investigator/EXPLORATION_PROTOCOL.md` — benchmark-gated improvement loop for
  `Explorer_prompt.txt`: four dimensions (rewritten 2026-08-23 — register-gap
  reduction, structural kill rate, finding rate, framing balance; the original
  seven-dimension Cambridge calibration is kept as history), improvement
  loop. Explorer prompt is improved until benchmark is cleared, then frozen.
- `investigator/REFINEMENT_PROTOCOL.md` — benchmark-gated improvement loop for
  `Refiner_prompt.txt` and the test harness. Seven dimensions (declaration
  completeness added 2026-08-23; the original six defined 2026-08-14
  (two hard gates: verification accuracy, caveat/join safety); first calibration
  data recorded.

**Investigation records:**
- `investigator/INVESTIGATIONS.md` — the detective's notebook; every hypothesis,
  finding, and honest null, by session/phase. Session headers record benchmark scores.
- `investigator/FINDINGS_SUMMARY.md` — the prose synthesis across all findings.
- `investigator/COVERAGE_AUDIT_2026-08-23.md` — one-off audit of cumulative
  battery/hypothesis coverage against external oversight frameworks (WA OAG
  program, ISSAI 300, patrol/fire-alarm); found the survivorship gap lives
  between taxonomy and battery, and seeds the redesign's coverage register.
  Git-tracked (names no individuals — allow-listed in `.gitignore`, unlike
  the other investigation records).
- `investigator/coverage_register.json` — the audit's grid as data
  (`docs/AGENT_DESIGN.md` §6 Step 4): one row per dimension, the `test_id`s
  that cover it, a DENSE/MODERATE/THIN/EMPTY verdict plus `data_blocked`/
  `out_of_scope` flags. `src/analysis/coverage_register.py`'s
  `verify_register()` cross-checks it against the real battery's test_ids
  (statically parsed from `tests.py`, no DB) — `tests/test_coverage_register.py`
  runs this on every test run, so the register can't silently drift from
  what's actually shipped. Not yet read by Explorer or updated by
  Refiner/Researcher — that wiring is Step 5.

**Loop (Exploration):** run Explorer prompt → append to INVESTIGATIONS → Stage 3
self-score → if below threshold, propose edit to `Explorer_prompt.txt` and bump
version; if at threshold, freeze Explorer and hand off to Refiner.
**Loop (Refinement):** run Refiner prompt → verify test against hand-computed number
→ score against refinement benchmark → if below threshold, improve `Refiner_prompt.txt`;
if at threshold, freeze and use `council draft` for production (scripted — Runner,
which used to stand in this spot, is archived).

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
| **Investigator → Pipeline** (`DATA_ENRICHMENT.md`) | backlog | Every structural kill in an Explorer session is written into `pipeline/DATA_ENRICHMENT.md`, with a council-agnostic pattern layer above the corpus-specific instance — *while `data_enrichment_status` in `config/agent_switches.json` reads OPEN* (`Explorer_prompt.txt` v3.0 Stage 2 step 0). Flip that value to FROZEN once the backlog is judged sufficient and Explorer skips the write (its core investigation is unaffected); reading the file (typology cross-reference, Pattern-exists check) still happens either way. That file lives in the pipeline track but is *populated by the investigator* — it's the bridge that turns "we couldn't test X" into a planned re-extraction. |
| **Pipeline → Pipeline** (`DATA_ENRICHMENT.md` → typology stage) — *new 2026-08-20* | self-loop, read | On every new corpus, the typology convergence loop (`council typology <council>`) cross-references its rare-heading/`other_content` aggregation against `DATA_ENRICHMENT.md`'s pattern layer before generating the Level 2 schema-update prompt. Pure text parse, no new LLM call — reuses the aggregation typology already computes. This is what lets schema-gap knowledge compound across corpora instead of only ever being caught reactively, post-extraction. |
| **Research → Investigator + Pipeline** (→ `pending_merges/` → Part 3 + `DATA_ENRICHMENT.md`) — *new 2026-08-20, gated by default as of v1.2* | taxonomy + pattern growth | A candidate genre from the 🔭 Research track that clears its own four-dimension self-check gets a ready-to-apply file in `research/pending_merges/` (default) for a human to paste into both `Investigator_prompt.txt` Part 3 and `pipeline/DATA_ENRICHMENT.md`'s pattern layer — or, only if a human explicitly declared auto-merge mode at session start, Researcher writes both directly, same session. Council-agnostic — benefits every future corpus, not just whichever one (if any) motivated the research. |
| **RESEARCH_PROTOCOL.md → Researcher_prompt.txt** — *new 2026-08-20* | governance | Same shape as `EXPLORATION_PROTOCOL.md → Explorer_prompt.txt`: benchmark-gated. Default is file-review (Researcher scores its own session, writes pending-merge files, a human applies them); auto-merge is available only as an explicit per-session opt-in, ending in a stage-contract completion block either way. |
| **EXPLORATION_PROTOCOL.md → Explorer_prompt.txt** | governance | The exploration protocol is the benchmark-gated plan for iterating the explorer prompt. Stage 3 of each session self-scores against the benchmark and proposes the next edit; a human approves before the version is bumped. |
| **REFINEMENT_PROTOCOL.md → Refiner_prompt.txt** | governance | The refinement protocol governs how validated findings are codified into permanent battery tests, and (as of 2026-08-14) how already-shipped tests are retroactively verified against the same seven-dimension benchmark. |
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
| running an exploration session (new hypotheses) | `council explore` (`investigator/Explorer_prompt.txt` underneath) → `investigator/INVESTIGATIONS.md` (record) |
| codifying a finding into the test battery | `council refine` (`investigator/Refiner_prompt.txt` underneath) → `src/analysis/tests.py` + `queries.py` |
| adding a governance test, or re-wording its public-facing copy | `config/test_registry.json` — the registry row (id/category/title/question/principles/etc.); `src/analysis/tests.py` still owns the computation |
| running the frozen battery in production | `council draft <council>` — scripted; Runner is archived, this was always its whole job under the hood |
| improving the exploration prompt | `investigator/EXPLORATION_PROTOCOL.md` (benchmark) → bump `Explorer_prompt.txt` |
| improving the refinement prompt / harness | `investigator/REFINEMENT_PROTOCOL.md` (benchmark) → bump `Refiner_prompt.txt` |
| writing up cross-cutting conclusions | `investigator/FINDINGS_SUMMARY.md` (current, hand-maintained) — or `render/synthesis_mode.txt` (run) once Renderer has real calibration data |
| reviewing a draft for defamation exposure | `review/editor/Editor_prompt.txt` (run) → writes `data/draft/<council>/<run_id>/defamation_review_<n>.md` |
| scoring a completed Editor review | `council editor-score <council> <run_id>` (`src/editor_score.py` Layer 1, deterministic; `docs/agent_prompts/editor_scorer.txt` Layer 2, fresh-context agent — `docs/GENERATION_SCORING_SPLIT.md` §2.3) → writes `editor_score_<n>.json/.md` next to the review it scored |
| improving the editor prompt | `review/editor/EDITOR_PROTOCOL.md` (now the scorer's rubric — Editor itself no longer reads it) → bump `Editor_prompt.txt`; a failing score's proposed edit comes from `editor-score`'s Layer 2, not from Editor's own session |
| fixing a flagged claim (frontend/pipeline/doc) | `review/fixer/<track>_mode.txt` (run) — only the track(s) the editor tagged |
| adding a fourth fixer track | `review/fixer/FIXER_PROTOCOL.md` — additive by design, see "Adding a fourth mode" |
| chaining editor + fixer, or asking what happens after a FAIL | `review/CONDUCTOR.md` — the loop, the pass cap, the one rule (never calls `council publish`); `council editor-loop <council>` runs the scripted version (`scripts/conductor_loop.py`) |
| assembling right-of-reply packets for a named-individual claim | `council reply-packets <council>` (script, `src/reply_packets.py`) — never sends anything; a human sends the output |
| rendering a claim for residents or writing cross-claim synthesis | `council render plain_language <council> <run_id>` or `council render synthesis <council> <run_id>` (`render/Renderer_prompt.txt` + the mode file underneath) |
| improving the renderer prompt | `render/RENDERER_PROTOCOL.md` (benchmark) → bump `Renderer_prompt.txt` or the relevant mode file |
| planning the end-to-end order to run all stages (CLI + agents) for a new corpus | `pipeline/PIPELINE.md` ("Longer term → Corpus onboarding order") — design sketch, not built; first-corpus vs subsequent-corpus sequencing |
| planning for many-council, recurring/scheduled operation (after onboarding) | `pipeline/PIPELINE.md` ("Longer term → Production scale") — design sketch, not built; cross-referenced from `review/CONDUCTOR.md` |
| implementing (or revising) the 2026-08-23 top-down redesign — claim object, invariant gate, tier products, role changes | `INFORMATION_ARCHITECTURE.md` (the flow) + `AGENT_DESIGN.md` (owners, file deltas, §6 build order) — read the coverage audit row above them first |
| building a panel or a drill-down | `frontend/INTERACTIVITY.md` — read its hard rule on never hardcoding a councillor name/claim in component source before writing any JSX |
| planning a new product surface | `frontend/PRODUCT_ROADMAP.md` |
| weighing risk, funding, or direction | `strategy/PRIVATE_ASSESSMENT.md` |
| flipping a gate that controls agent behavior (data-enrichment freeze, researcher default gate mode, conductor pass cap) | `config/agent_switches.json` (loaded by `src/agent_config.py`) — not the prose docs that describe each gate |
| onboarding / public/dev reference | root `README.md` |
| adding a test, changing ruff config, editing CI | `TESTING.md` |
| making (or reversing) a CI/CD infra decision — new workflow, auth approach, deploy target | log it in `CICD_DECISIONS.md` (dated entry: decision, alternatives, trade-off), then update `TESTING.md` if the current-state description changed |
| publishing data so it's actually public (`council publish`, Vercel, GCS) | `TESTING.md` ("Draft & publish workflow") — the gate; note it covers the *data* layer only, not component source (see the panel row above) |
| committing changes in this repo | `TESTING.md` ("Commit conventions") |
