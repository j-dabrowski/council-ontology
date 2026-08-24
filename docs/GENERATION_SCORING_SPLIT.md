# Generation/Scoring Split — implementation plan

**What this is.** The design for separating each LLM role's *generation*
session from the session (or script) that *scores* its output — the fourth
design artefact of the 2026-08 redesign line
(`investigator/COVERAGE_AUDIT_2026-08-23.md` → `INFORMATION_ARCHITECTURE.md`
→ `AGENT_DESIGN.md` → this). Design only, accepted for implementation;
nothing here is built. Written 2026-08-24 for a separate implementation
session to execute step by step — §7 is the build order.

**The problem.** Three of the four scored roles (Explorer, Editor — and
Renderer by reference, though it doesn't score itself) read their own
scoring rubric in the same session that produces their primary output, and
Explorer and Editor then self-score against that rubric in that same
session:

- `Explorer_prompt.txt` v3.0 states the four benchmark dimensions *and
  their numeric thresholds* inline (Stage 3), read before Stage 1 begins;
  the session scores itself at close.
- `Editor_prompt.txt` v0.4's "Read first" list names `EDITOR_PROTOCOL.md`
  as "the benchmark this session is scored against," and the output
  template's Score block has the session grade all eight dimensions on its
  own review.
- `Renderer_prompt.txt` v1.0 doesn't self-score, but its shared layer
  cites `RENDERER_PROTOCOL.md` as "the fidelity/framing benchmark each
  mode is scored against."
- `Refiner_prompt.txt` v1.2's seven dimensions are the work procedure
  itself — a different shape, handled differently below (§4).

**The precedent this follows.** The pipeline already solved this class of
problem once, deliberately: the Level 0 census keyword counts are never
shown to the extraction model, "so they stay an independent check"
(README.md, `scripts/census.py`). A model that can see the check it will
be graded against can shape its output toward the check instead of toward
the underlying goal. The census kept measurement independent by
construction, not by asking the model to be objective. This design applies
the same construction to the agent roles.

**Scope — one risk, not two.** Two distinct risks exist here, and this
design fixes only the second:

- **Risk A** — same-model-family scoring is an imperfect measurement even
  in a fresh context (a Claude session judging another Claude session's
  output may share its blind spots). **Out of scope.** Multi-model or
  human-anchored judging is future work. For this round, a fresh-context
  Claude scoring session with no shared conversation state is an
  acceptable and sufficient judge, and nothing below should be gold-plated
  toward Risk A.
- **Risk B** — the *same session* that generates the output knows the
  rubric and grades itself in that same context, contaminating the primary
  output, not just its measurement. **This is what the design fixes:**
  generation and scoring become genuinely separate invocations with no
  shared context. Separate *invocations*, not separate models.

**Status of implementing sessions:** do not widen scope toward Risk A, do
not add autonomy anywhere, and keep every human gate exactly where it is.

---

## 1. The uniform mechanism

One pattern, four role-specific instantiations:

1. **The generation prompt loses every reference to its benchmark.** No
   protocol filename, no dimension list, no threshold, no "you will be
   scored," no self-score output section, no proposed-prompt-edit step.
   What stays is *procedure* — how to do the job well — even where a
   benchmark dimension happens to measure compliance with that procedure.
   The session may know the method; it may not know the measurement.
2. **The generation session produces its output in a defined,
   machine-readable shape** — extending the stage-contract JSON sidecar
   pattern Editor v0.3, Fixer, and Researcher already share, never a new
   invention. The shape exists so scoring can be done *to* the output, not
   *by* its author.
3. **Scoring runs afterward, split by dimension:**
   - **Script**, for every dimension decidable from the structured output
     (counts, cross-references against other machine-readable artefacts,
     vocabulary/contract validity). Free, deterministic, runs every time —
     the same assignment rule as `AGENT_DESIGN.md`'s owner table.
   - **Fresh agent session** (`claude -p`, the existing
     `load_prompt`/`run_claude` invocation path from
     `scripts/conductor_loop.py` — a new process, so no shared context by
     construction), for judgment-only dimensions. The scorer reads the
     output, its inputs, and the protocol; it never reads the generation
     role's operating prompt and never shares a conversation with the
     session it scores.
4. **The protocol doc becomes the scorer's rubric home**, not the
   generator's reading. Where a dimension is currently defined inside the
   generation prompt (Editor's Score block), the definition moves into the
   protocol — the single-source-of-truth pointer flips direction.
5. **Scoring output lands next to what it scored**, as a new sidecar in
   the same (gitignored) location, named `*_score*` / `*_verification*` —
   never overwriting or editing the generation output it judges.
6. **Prompt-edit proposals move to the scoring stage.** Today a failing
   self-score has the generating session draft its own prompt fix. Under
   the split, the scorer (which legitimately sees both output and rubric)
   drafts the proposal; the human-approval gate before any version bump is
   unchanged.

**Acceptance check for every role's step (add to that step's verification):**
after the prompt edits, `grep -iE "PROTOCOL\.md|benchmark|self-score|scored
against" ` over the generation prompt and its mode files must return only
changelog/history lines, and ideally nothing. Same spirit as the
component-source name grep in `frontend/INTERACTIVITY.md` — a mechanical
sweep, because "we removed it" is exactly the kind of claim that drifts.

**Scorer prompts** live in `docs/agent_prompts/<role>_scorer.txt`, same
placeholder/`sed` conventions as `editor.txt`/`fixer.txt`, indexed in
`AGENT_PROMPTS.md`. Scorers get the same `--allowedTools` set (they write
their score file and run read-only queries); they gain no authority any
current role lacks — in particular, no scorer edits a generation prompt,
snapshots, or anything under `frontend/`.

---

## 2. Editor (S8) — build first

### 2.1 Verified current state

- `Editor_prompt.txt` v0.4 "Read first" includes `EDITOR_PROTOCOL.md — the
  benchmark this session is scored against…`.
- The output template contains a Score section: the session grades all
  eight dimensions of its own review, and the verdict line couples two
  conditions ("all thresholds met, 0 blocking flags").
- The eight dimensions are *defined in the prompt's Score block*;
  `EDITOR_PROTOCOL.md` explicitly defers to it ("not duplicated here").
- The machine contract that downstream code actually consumes
  (`defamation_review_<n>.json`: `run_id`/`council`/`pass`/`status`/
  `tracks`/`reviewed_at`) does **not** include the Score — verified in
  `scripts/conductor_loop.py` (`latest_review_record` validates only
  `run_id`/`status`/`tracks`/`pass`) and `src/publish_gate.py`. The split
  can therefore keep that contract byte-compatible.
- Editor v0.4 has **zero real runs**. Every real chain (August 2026) ran
  v0.3, whose calibration data the v0.4 narrowing already partially
  invalidated. This is why Editor goes first — see §7.
- One latent contract bug supports the redesign: `conductor_loop.py`
  raises on `status: FAIL` with empty `tracks`. Under the current prompt,
  the verdict line couples two conditions ("all thresholds met, 0 blocking
  flags"), so a self-scored threshold miss with no flag pinned to any
  claim — plausible for a holistic dimension like framing balance —
  produces exactly that: FAIL with nothing to dispatch, and a crash. The
  §2.2 verdict redesign closes this path by construction, without losing
  the strict behavior (see the decision note there).

### 2.2 What moves out of `Editor_prompt.txt` (→ v0.5)

**Removed:**
- The `EDITOR_PROTOCOL.md` bullet from "Read first."
- The entire Score section from the output template (both the markdown
  block and any instruction to compute it).
- The dual-condition verdict line. New rule, stated plainly: **status is
  FAIL if and only if the review contains ≥ 1 BLOCKING flag.** There is no
  second, aggregate path to FAIL — but nothing that could FAIL today is
  left without a path, because of the holistic-flag outlet added below.
  This is a **deliberate behavior change**, not a clarification: today's
  verdict line couples "all thresholds met" with "0 blocking flags," so a
  self-scored threshold miss can FAIL the run on its own, even with zero
  flags raised. That path has to go regardless (the Score block leaves
  the prompt — post-split, the review session produces no threshold
  scores at all), and it was also the crash path noted in §2.1 (FAIL with
  empty `tracks`). What must not be lost with it is the *strictness*: a
  review-wide concern the Editor can't pin to one claim must still be
  able to stop the run.

**Added — the holistic-flag outlet.** New prompt instruction: a
review-wide concern that cannot be pinned to a single claim (e.g. a
systematic framing imbalance across the draft, or the Editor's own
judgment that some part of its review is uninvestigable as written) is
**still expressed as a flag** — BLOCKING or ADVISORY per its severity,
`location` given at the snapshot or draft level, and `tracks` set to the
owning track if a Fixer mode could genuinely act on it, or to the new
track value **`human`** when none could. A `human`-track flag must state
its reasoning concretely enough for a person to review — what was
observed, why it can't be localised, what the reviewer would need to
decide — not just "below target." Every FAIL therefore carries ≥ 1 flag,
and every flag carries a routable track: the empty-`tracks` crash state
becomes unrepresentable.

**The `human` track (contract extension):** `conductor_loop.py`'s
`VALID_TRACKS` gains `"human"`. A FAIL whose flags include a
`human`-track flag is escalated immediately — same handling and same
exit path as a Fixer BLOCKED report (`escalate_blocked()`), because it
is the same thing declared one step earlier: a decision that isn't the
loop's to make. No Fixer is dispatched for that pass, including for any
co-flagged ordinary tracks — the human's decision may change what those
fixes should be, and the pass cap shouldn't burn passes while a human
item is open. `src/publish_gate.py` is unaffected (it reads `status`
only, and an escalated run never reaches it).

**Decision note (2026-08-24), for the record.** Three options were
weighed for the unpinned-threshold-miss case:
1. flags-only verdict with no outlet — never crashes, but a concern the
   Editor itself judged below-target would silently ship as PASS;
2. keep the aggregate-FAIL path and have the Layer-1 validator
   synthesize a placeholder flag so `tracks` is never empty, dispatched
   to Fixer — strict, but a locationless flag dispatched to Fixer
   predictably yields BLOCKED, arriving at the same human escalation one
   wasted agent call later, and polluting Fixer's calibration data on
   the way;
3. **(chosen)** flags-only verdict plus the holistic-flag outlet and the
   `human` track — the same strictness as option 2, expressed at the
   source (the Editor states its own reasoning while it still has the
   context, rather than a validator back-filling a placeholder), and
   escalating directly on the existing BLOCKED path with no new
   machinery. This is also the shape the project owner independently
   specified for the "90% score, nothing flagged, nothing to
   investigate" case: create an ad-hoc flag carrying the scoring
   reasoning and escalate to the human, with the run resuming after
   approval.

**Kept, unchanged:** the role framing (false PASS worse than false
BLOCKING), the full procedure (steps 1–5), the S7 boundary section
verbatim — it is *procedure* (don't re-derive what the gate proved), even
though a scoring dimension also measures compliance with it — the
track-tagging rules, the Conductor-loop section, the disclaimer
obligation, and the "What this prompt is not" section.

**Added:** two structured arrays in the JSON sidecar (additive fields
only; the six existing fields and their meanings are frozen):

```json
{
  "...existing six fields...": "unchanged",
  "claims": [
    {"location": "<snapshot.json field | file:line>",
     "snapshot": "<file>",
     "named_individual": true,
     "scorecard_test_id": "<test_id or null>"}
  ],
  "flags": [
    {"severity": "BLOCKING|ADVISORY",
     "tracks": ["frontend | pipeline | doc | human"],
     "criterion": "<one of the enumerated criterion slugs>",
     "location": "<same vocabulary as claims[].location; snapshot- or
                   draft-level for a holistic flag>",
     "summary": "<one line>",
     "reasoning": "<required for human-track flags: what was observed,
                    why it can't be localised, what the reviewer must
                    decide>"}
  ]
}
```

The markdown flag entries stay as-is for humans; the sidecar arrays are
the same content in the machine-trustworthy form, mirroring how the
existing sidecar already duplicates the stage-contract block.

### 2.3 The scoring stage: `council editor-score <council> <run_id>`

**Layer 1 — deterministic validator (script, every run).** A new module
(suggested: `src/editor_score.py`) reading only the run directory plus
`gate_report.json` and `scorecard.json`:

| Check | Source dimension (old numbering) | How |
|-------|----------------------------------|-----|
| Sidecar/markdown stage-contract agreement; all required fields present; `run_id` matches directory | (contract hygiene) | parse both, compare |
| Every flag: `tracks` ⊆ {frontend, pipeline, doc, human} and non-empty; `criterion` ∈ the enumerated slug vocabulary; `location` non-empty; `human`-track flags carry a non-empty `reasoning` | (routability) | vocabulary check |
| Verdict consistency: FAIL ⟺ ≥ 1 BLOCKING flag | (verdict integrity) | count |
| Disclaimer present in the markdown | 7 | string check |
| **False positives vs S7**: no flag whose `location` traces to a `scorecard_test_id` that `gate_report.json` shows passed carries a criterion in {small-n, name-free-schema, entity-resolution} | 8 | cross-reference |
| Per-dimension percentages (placement, small-n exposure on non-scorecard claims, etc.) computed from `claims[]` × `flags[]` | 1–6 (as descriptive stats) | arithmetic |

The percentages stop being verdict inputs; they become measurements the
calibration process reads.

**Layer 2 — fresh-context judgment scorer (agent,
`docs/agent_prompts/editor_scorer.txt`).** Reads: the draft, the review
files, `EDITOR_PROTOCOL.md` (which now owns the dimension definitions),
`Investigator_prompt.txt` Part 4, `PRIVATE_ASSESSMENT.md`. Never reads
`Editor_prompt.txt`, and is never told what the review session was
instructed beyond what the protocol defines. Its job, per the protocol's
existing calibration questions:
- **False-negative probe:** independently re-review a sample of claims
  (including every named-individual claim) cold, then compare against the
  review's flags. A risk it finds that the review missed is the finding
  that matters most.
- **Flag validity:** for each flag, is the cited criterion actually
  violated at that location? Is the track tag right?
- **Judgment-quality dimensions** the script can't touch: proportionality
  /overclaim correctness, innocent-explanation adequacy, singling-out
  fairness, blended-statistics calls, caveat-integration quality, framing
  balance.

**Output:** `editor_score_<n>.json` + `editor_score_<n>.md` in the same
run directory (Layer 1 fields + Layer 2 findings + any proposed
`Editor_prompt.txt` edit for human review).

**Human comparison is not replaced.** `EDITOR_PROTOCOL.md`'s "compare the
editor's flags against a human's independent read" remains the calibration
bar; Layer 2 assists it and structures it, and `maintenance.yml`'s
activation checklist items (real false-positive data, independently
human-reviewed cycles) are now fed by these score files instead of by the
session's own claims about itself.

### 2.4 Loop interaction

- `conductor_loop.py`: **one small extension** (the loop shape,
  pass cap, and publish invariant are untouched): `VALID_TRACKS` gains
  `"human"`, and a FAIL carrying any `human`-track flag escalates
  immediately on the existing `escalate_blocked()` path instead of
  dispatching Fixers (§2.2). `CONDUCTOR.md` gets the matching sentence.
  Optionally (recommended, and cheap): run Layer 1 inside the loop
  immediately after `latest_review_record()` and treat a structural
  failure as exit 2 (malformed review), same class as the existing
  sidecar validation. Layer 2 is **not** in the pass loop — it runs once
  per chain (after the chain ends, PASS or escalation), because its
  purpose is calibration, not gating, and an in-loop LLM scorer would
  double the chain's agent cost for no routing benefit. In automated
  operation (`maintenance.yml`), the scoring stage is ordered **before**
  any opt-in publish step, and a hard Layer-2 finding (a missed real
  risk) fails that workflow step so an auto-profile publish cannot
  proceed past it in the same run.
- **Escalation transport (forward-compatible note).** Everything above
  describes escalation as it works today: the run stops, prints/logs the
  reason, and waits for a human to act and re-dispatch — fully
  asynchronous, no live blocking gate anywhere. A branch-based
  escalation model is separately designed (working-branch segments;
  success PRs to `main`; an escalation opens a PR to a `staging` branch
  whose merge is the approval that resumes the run —
  `AUTOMATION_ARCHITECTURE.md` Part 4, revised 2026-08-24; summary in
  this plan's appendix). This plan's contracts are
  deliberately transport-agnostic: the `human`-track flag's `reasoning`
  field, the review sidecar, and the score files are exactly the payload
  such an escalation PR would carry, and nothing in this design assumes
  which transport delivers them.
- `EDITOR_PROTOCOL.md` (→ v0.4): takes ownership of the eight dimension
  definitions (moved from the prompt's Score block, adjusted: the
  percentage dimensions described as Layer-1 measurements, the judgment
  dimensions as Layer-2 questions); documents the two-layer scoring
  stage; states explicitly that v0.3-era chain scores were produced by
  rubric-aware self-grading and are not comparable with post-split
  scores; keeps its calibration history verbatim.

---

## 3. Explorer (S3) — build second

### 3.1 Verified current state

- Stage 3 is the final stage of the same session that ran Stages 1–2, and
  the four dimensions *with thresholds* are stated inline in the prompt
  read at session start. `EXPLORATION_PROTOCOL.md` is in the preamble's
  reading list.
- The genuinely gameable surface is narrower than "the whole benchmark":
  dimensions 1 (register-gap seeding) and 4 (both framing sentences,
  NEUTRAL register) measure compliance with procedure the session must
  keep reading to do the job at all. Dimensions 2 (structural-kill rate
  ≤ 10%) and 3 (finding rate ≥ 25%) are outcome thresholds over the
  session's *own classifications* — a session that knows "kills must stay
  under 10%" has a standing incentive to log a borderline structural kill
  as an ordinary null, and one that knows "findings must clear 25%" has
  one to inflate a Banked entry's "clear build path." Classification
  honesty is exactly what the current design cannot measure.
- The prompt also carries its own CALIBRATION LOG (benchmark scores and
  threshold talk, appended session by session) and a changelog whose v3.0
  entry restates the benchmark — both are rubric disclosure to the
  generating session.
- Explorer v3.0 has zero sessions run against the four-dimension
  benchmark (Sessions 8–11 all pre-date it), so — as with Editor — no
  post-redesign calibration data is invalidated by changing the prompt
  now.

### 3.2 What moves out of `Explorer_prompt.txt` (→ v3.1)

**Removed:**
- Stage 3 in its entirety (self-score + propose).
- Every reference to `EXPLORATION_PROTOCOL.md`, the benchmark, its
  dimensions, and its thresholds — including Stage 1's aside explaining
  what the register seeding "replaces" in the old benchmark (the
  instruction *seed from the worst open gap* stays; the benchmark
  genealogy goes), and Stage 2's threshold-free framing stays as written.
- The CALIBRATION LOG section **moves to `EXPLORATION_PROTOCOL.md`**
  (appended there by the scoring stage / human, not by Explorer). The
  **STANDING CONFOUND CHECKLIST stays in the prompt** — it is operating
  knowledge, not scoring history. The changelog is trimmed to version +
  one-line summary per entry, with the benchmark detail living in the
  protocol's own history.

**Kept:** ROLE, Principles 0/1/2, Stage 1 (register seeding as procedure,
genre catalog), the identification strategy, Stage 2 including the full
write-up discipline (n/base-rate/era/grade/strength, hostile-reader and
promoter sentences — these are how findings are made defensible, not a
score), the `DATA_ENRICHMENT.md` write procedure, and INVESTIGATIONS.md
discipline.

**Added — the defined output shape.** A new closing step ("Close the
session," replacing Stage 3, framed as the machine-readable session
summary the pipeline consumes — with no mention of scoring): write
`data/exploration/session_<id>.json` (gitignored; `<id>` = the
INVESTIGATIONS.md session number):

```json
{
  "session_id": 12,
  "date": "YYYY-MM-DD",
  "prompt_version": "v3.1",
  "hypotheses": [
    {"id": 50,
     "register_dimension": 13,
     "register_verdict_at_session": "THIN",
     "tables": ["..."],
     "classification": "finding | null | banked | infeasible",
     "banked_build_path": false,
     "flagship": false,
     "entry": "<INVESTIGATIONS.md phase/anchor>"}
  ],
  "status": "DONE"
}
```

This sidecar also closes a logged gap elsewhere: `discovery.yml`'s PR body
currently points at a GCS path because "no role has a structured
session-summary contract to extract that from yet"
(`AUTOMATION_ARCHITECTURE.md`'s logged simplification) — this is that
contract.

### 3.3 The scoring stage: `council explore-score <session_id>`

**Script part** (suggested: `src/exploration_score.py`), from the sidecar
plus `coverage_register.json`:
- **Dimension 1:** ≥ 1 hypothesis whose `register_dimension` row was
  EMPTY/THIN and neither `data_blocked` nor `out_of_scope`
  (`register_verdict_at_session` guards against the register changing
  between session and scoring; the scorer cross-checks it against the
  live register and reports drift rather than failing on it).
- **Dimension 2:** `infeasible / total ≤ 10%`.
- **Dimension 3:** `(finding + banked_build_path) / total ≥ 25%`.
- Sidecar↔INVESTIGATIONS.md reconciliation: every listed hypothesis has a
  matching entry; every session entry is listed.

**Fresh-agent part** (`docs/agent_prompts/explorer_scorer.txt`), reading
the session's INVESTIGATIONS.md entries, the sidecar, and
`EXPLORATION_PROTOCOL.md` — never `Explorer_prompt.txt`:
- **Dimension 4:** hostile-reader + promoter sentences present on every
  confirmed flagship, register genuinely NEUTRAL.
- **Classification honesty spot-check** — the check the split newly makes
  meaningful: were any `infeasible` outcomes logged as `null` (or vice
  versa)? Does each `banked_build_path: true` entry's own text actually
  state a build path (the same eligibility language Refiner Step 0
  applies)? This directly protects Refiner's queue as well.
- On any failing dimension: draft the minimal `Explorer_prompt.txt` edit
  (the duty that leaves the generation session), for human review.

**Output:** `data/exploration/session_<id>_score.json` + `.md`; the
scorer (not Explorer) records the four scores in the INVESTIGATIONS.md
session header and appends the calibration-log entry to
`EXPLORATION_PROTOCOL.md`.

### 3.4 Loop interaction

`EXPLORATION_PROTOCOL.md`'s improvement loop keeps its shape and
thresholds; step 2 changes from "Score against the four dimensions;
record in the session header" (performed by the session) to "run
`council explore-score`" (performed after it). Freeze semantics are
unchanged. The protocol notes that Session ≤ 11 scores were produced by
rubric-aware self-grading and post-split scores start a new comparable
series — kept as history, per the project's existing practice of marking
old calibration data historical rather than deleting it.

---

## 4. Refiner (S4) — no split; independent verification instead

**Do not design a generation/scoring split here.** The seven dimensions
*are* the procedure — hiding "hand-derive the number independently" from
the session would hide how to do the job. The fix is different: stop
*trusting the self-report* for any dimension that can be independently
verified against Refiner's actual artifacts (the generator code, its
declaration block, the register, the draft output). Dimension 7 already
has exactly this shape — `tests/test_coverage_register.py` checks the
register against the real battery on every test run instead of believing
Refiner's claim — and is the template.

Audit of the seven dimensions, verified against `Refiner_prompt.txt` v1.2
and `REFINEMENT_PROTOCOL.md`:

| # | Dimension | Independently checkable? | The check to build |
|---|-----------|--------------------------|--------------------|
| 1 | Verification accuracy | **Partially — via a persisted artifact.** The hand-derivation itself can't be scripted, but its *re-execution* can: Refiner already writes fresh verification SQL/Python; require it to ship that as a runnable harness file, `tests/battery_verification/<test_id>.py`, that recomputes the number from raw tables and compares it to the generator's live output. Run under a `db` pytest marker (excluded from required CI per `TESTING.md`'s no-DB rule; run locally / in DB-bearing workflows). Converts "I checked and it matched" into a check that keeps running — and keeps guarding against future regressions of the same number, which the current one-time self-report never did. |
| 2 | Caveat/join safety | **Partially — lint for the known incident classes.** New static checks (AST/regex over `queries.py`): any use of `item_reference` in a join expression outside `_linked_declared_votes` is a failure; enum string literals compared against vote/outcome/interest columns must be UPPERCASE (with the documented `community_submissions.position` lowercase exception); year-trend/dollar-aggregation functions must contain a `document_type == 'minutes'` filter unless on a small allowlist (`officer_divergence`). Honest limit to state in the code and protocol: this catches *recurrence of the two real incident classes* (`recusal_compliance_trend`, `tender_concentration`) and the documented enum trap — it does not catch a novel fan-out. The general "same fact, multiple rows" question stays procedure + dimension-1's harness (a fan-out that inflates the number fails the harness comparison). |
| 3 | Encapsulation | **Fully.** AST check: no `session.execute`/`text(` in `tests.py`; every raw-SQL call site in `queries.py` has an adjacent comment. Required CI (no DB needed). |
| 4 | Council-agnosticism (static half) | **Fully, for the greppable part.** AST signature check (only `council_id` + generic year params); literal scan for council names, hardcoded council ids, and year literals inside function bodies — against an explicit allowlist file recording the known backlog (the 2018–2021 Inquiry-window hardcodings in `_recusal_era`/`_RECUSAL_ERAS` and `public_question_responsiveness`), so the check lands without failing on documented debt, and any *new* literal fails loudly. Required CI. The run-against-a-second-DB half stays blocked, as the protocol already records. |
| 5 | Chart & drill-down completeness | **Fully, from draft output.** Script over the draft snapshots: every battery claim's `chart` payload non-empty; every flagship's drill-down array carries ≥ 1 verbatim quote. Belongs with the DB-bearing checks (needs a real draft), e.g. inside `council draft`'s own post-battery validation or the `db`-marked suite. |
| 6 | Independent reproducibility | **Yes — and only via the split's machinery.** Today the *same session* is told to read the docstring "with no memory of this session," which is not a thing a session can do; this dimension has never actually been measured. Replace with a cheap fresh-context check (`docs/agent_prompts/refiner_cold_reader.txt`): a session given *only* the function's source (docstring + comments + body — no INVESTIGATIONS.md, no protocol context beyond the two questions) states what the test measures and why its join is safe; a human (or the invoking script) compares that against the finding. Runs per newly-refined generator; batchable retroactively. This is the one place Refiner gets a fresh-agent stage, and it verifies an artifact, not a session. |
| 7 | Declaration completeness | **Extend the existing check.** `test_coverage_register.py` verifies register membership only; nothing today parses the `# claim declaration:` comments (verified — no consumer exists in `src/` or `tests/`). Build the parser: extract each declaration block, compare declared `unit`/`strength`/`principle` (and `superlative_check` presence when `strength=superlative`) against the actual `TestResult(...)` keyword arguments, and `MIN_N` coherence against `config/invariants.json`. Enforced for generators that carry a block (the 29 pre-v1.2 generators remain backlog, per the protocol's existing asymmetry); a block whose stated fields mismatch the call is a hard failure. Required CI (pure AST, no DB). |

**Prompt delta (`Refiner_prompt.txt` → v1.3):** additive only. Step 1
gains "persist your verification query as
`tests/battery_verification/<test_id>.py` in the harness shape" (with a
template to copy); step 9 is reworded from the self-performed cold read to
"write the docstring so a cold reader passes the external check" and notes
the check is run independently; the Output self-report block stays — it
remains the session's claim, but the protocol now states that for
dimensions 2 (lint scope), 3, 4 (static), 5, and 7, **the harness is the
verdict of record**, and for 1 and 6 the persisted artifact / cold reader
is. `REFINEMENT_PROTOCOL.md`'s "How to measure" column is updated per the
table above.

No Risk-B contamination concern requires removing the benchmark from
Refiner's prompt, and doing so would degrade the work — leave it in.

---

## 5. Renderer (S10) — verification stage, built before first run

### 5.1 Verified current state

- Confirmed: no inline self-score exists, and this design keeps it that
  way. The mode files' "Fidelity self-check" is procedure (a pre-flight
  checklist), not a scored benchmark — it stays.
- One small Risk-B-shaped disclosure to remove: the shared layer's
  Related-docs entry citing `RENDERER_PROTOCOL.md` as "the … benchmark
  each mode is scored against." Since the protocol's five shared
  dimensions are near-identical to the self-check the modes keep, this
  removal costs nothing and buys consistency: drop the bullet
  (`Renderer_prompt.txt` → v1.1, no other generation-side change).
- Renderer has never run. Its only verification path today is a human
  manually checking fidelity — which can't run inside `maintenance.yml`'s
  eventual "Renderer refresh" step. Building verification now, before the
  first real run, is retrofit-free.

### 5.2 The verification stage: `council render-verify <mode> <council> <run_id>`

**Script part** (suggested: `src/render_verify.py`), a comparison between
the rendered markdown and the structured claims it was derived from —
mostly diffing, not judgment:

- **Roster name scan** — the hard-fail check. Reuse
  `src/invariant_gate.py`'s `usable_roster_names` + `find_names_in_text`
  (small refactor: the matcher currently takes a `TestResult`; extract a
  text-taking core both callers share). Plain-language output must contain
  zero roster names (its input is person-free by construction — a name in
  the output is fabrication, the C2a failure class caught at a new
  surface). Synthesis output may contain only names carried by
  reply-complete `individual`-unit claims in its input.
- **Number diff.** Extract numeric tokens (digits, percents, years,
  currency) from the rendered prose; each must appear in the source
  claims' fields (`headline`/`verdict`/`n`/`base_rate`/`era`/chart
  payload), after normalising the common forms (percent vs fraction,
  thousands separators). A number with no source match is a hard fail; a
  *source* number absent from the output is fine (rendering may
  summarise). Spelled-out or approximated quantities ("about a quarter")
  are beyond the script — they're listed as unmatched-prose items and
  handed to the agent pass, not silently passed.
- **Citation validity** (synthesis): every cited `test_id` exists in the
  input battery; every cross-cutting insight cites ≥ 1.
- **Reply gate re-derivation** (synthesis, hard gate — protocol
  dimension 6): recompute from the battery which `individual`-unit claims
  have incomplete `reply`; confirm none of their content (name, statistic,
  or headline text) appears in the output, and that `claims_skipped` in
  the stage-contract block equals the recomputed count.
- **Stage-contract block** parses and is internally consistent.

- **Fresh-agent semantic pass** (`docs/agent_prompts/renderer_verifier.txt`)
  — for what diffing can't see: prose that drifted while every number
  survived. Reads *only* the rendered output, the source claims (plus the
  relevant INVESTIGATIONS.md entries for synthesis), and
  `RENDERER_PROTOCOL.md`; never the Renderer prompt or mode files, never
  the generation session. Produces a per-sentence (plain-language) or
  per-insight (synthesis) trace table — which claim(s) back it, verdict
  per protocol dimension — covering: dropped/softened caveats (dim 2),
  denominator/uncertainty preservation (dim 3), strength-ladder fidelity
  (dim 4), NEUTRAL register (dim 5), framing balance (dim 7), plus
  adjudication of the script's unmatched-prose list against dimension 1.

**Output:** `render_verification_<mode>_<n>.json` + `.md` in the run
directory, with a stage-contract block (`status: PASS|FAIL`,
`hard_failures: [...]`, `next:`).

### 5.3 Graduated activation (human doesn't leave yet)

Same pattern as `maintenance.yml`'s commented-out cron: the automated
stage runs on **every** render from the very first one, and human review
remains mandatory alongside it until a verifiable checklist in
`RENDERER_PROTOCOL.md` is met — proposed conditions, to be recorded there
as conditions rather than vibes:
1. ≥ 3 real runs per mode where `render-verify` and an independent human
   read agree on the verdict;
2. zero drifts found by the human that the stage missed (a miss resets
   the count);
3. explicit project-owner sign-off, logged in the protocol's changelog.

Until then, `render-verify` PASS means "cleared for human review," never
"cleared." `RENDERER_PROTOCOL.md` (→ v1.1) documents the stage, the
checklist, and re-labels its dimension table with each dimension's owner
(script / agent pass / both).

---

## 6. What lands where — summary of new artifacts

| Artifact | Kind | Home |
|----------|------|------|
| `src/editor_score.py` + `council editor-score` | script + CLI | Layer-1 validator, invokes Layer 2 |
| `docs/agent_prompts/editor_scorer.txt` | scorer prompt | fresh-context judgment scorer |
| `editor_score_<n>.json/.md` | scoring output | draft run directory (gitignored) |
| `data/exploration/session_<id>.json` | generation sidecar | Explorer's session summary |
| `src/exploration_score.py` + `council explore-score` | script + CLI | dims 1–3 + reconciliation |
| `docs/agent_prompts/explorer_scorer.txt` | scorer prompt | dim 4 + classification honesty |
| `data/exploration/session_<id>_score.json/.md` | scoring output | alongside the sidecar |
| `tests/battery_verification/<test_id>.py` (+ template) | verification harness | `db`-marked pytest, per generator |
| battery lint checks (dims 2/3/4-static) | required-CI pytest | new `tests/test_battery_lint.py` |
| declaration-block parser (dim 7 extension) | required-CI pytest | extends `src/analysis/coverage_register.py` or sibling module |
| `docs/agent_prompts/refiner_cold_reader.txt` | scorer prompt | dim 6, per new generator |
| `src/render_verify.py` + `council render-verify` | script + CLI | diff checks + invokes agent pass |
| `docs/agent_prompts/renderer_verifier.txt` | scorer prompt | semantic fidelity pass |
| `render_verification_<mode>_<n>.json/.md` | scoring output | draft run directory |

Everything scoring-related is gitignored alongside what it scores, matching
the existing draft-directory convention; the harness/lint/parser code and
prompts are git-tracked like their peers.

---

## 7. Build order

Every post-redesign prompt version (Editor v0.4, Explorer v3.0, Renderer
v1.0) has zero real runs, so **no post-redesign calibration data is
invalidated by any of these changes today** — the "Editor has the most
calibration data at risk" concern resolves cleanly: the real chains ran
v0.3, whose scores the v0.4 narrowing already made non-comparable, and the
flag-level lessons from those chains (what a real draft's risks look like)
survive any prompt-shape change because they're about the *drafts*, not
the Score block. What creates risk is *waiting*: the first real v0.4 chain
would burn the only "first calibration cycle" on a prompt shape this
design is about to change.

1. **Editor split (§2).** Highest-stakes role, and its window is closing —
   `maintenance.yml` is one dispatch away from producing the first v0.4
   chain. Ship v0.5 + `editor-score` before that first chain, so the first
   real calibration cycle lands on the final shape. Includes the sidecar
   arrays, both scoring layers, `EDITOR_PROTOCOL.md` inversion, and the
   §1 acceptance grep. **Done 2026-08-24** — see "Build log" below; the
   window this item worried about closed a few hours before this step
   shipped (a real v0.4 chain already ran, `docs/review/REVIEW.md`'s
   2026-08-24 entry), so the "before that first chain" framing didn't hold
   in practice, though nothing about the split itself needed to change as
   a result.
2. **Explorer split (§3).** Same zero-runs reasoning; do it before the
   next discovery dispatch. Includes the session sidecar (which also
   closes `discovery.yml`'s session-summary gap), `explore-score`, the
   calibration-log relocation, and the protocol-loop rewording.
3. **Renderer verification (§5).** Before Renderer's first real run —
   the one role that can be built correctly from the start instead of
   retrofitted. The roster-scan refactor here is small and self-contained.
4. **Refiner independent checks (§4).** Additive hardening with no closing
   window (Refiner's prompt shape barely changes); last, but not optional
   — the lint + declaration parser also permanently guard the 29 shipped
   generators, and the Explorer scorer's classification-honesty check
   (step 2) protects Refiner's queue in the meantime.

Each step ships value alone and none depends on a later one. Within each
step: code + tests first, then the prompt/protocol edits, then the
acceptance grep, then the doc sweep (§8).

---

## 8. Tests, fixtures, and doc deltas

**New tests (required CI unless noted):**
- `tests/test_editor_score.py` — Layer-1 validator against fixture run
  directories: a clean PASS review; a FAIL with valid flags; a sidecar/
  markdown mismatch; an invalid track; a missing criterion; a FAIL with
  zero blocking flags (verdict-integrity failure); a `human`-track flag
  with and without `reasoning` (valid / invalid); and the dimension-8
  fixture — a synthetic `gate_report.json` + `scorecard.json` pair with a
  flag re-litigating a passed claim.
- `tests/test_conductor_loop.py` (new — `conductor_loop.py` currently has
  no test coverage): with subprocess calls stubbed, a FAIL carrying a
  `human`-track flag escalates immediately (exit 1) with no Fixer
  dispatch, including when ordinary tracks are co-flagged; a FAIL with
  only ordinary tracks still dispatches as today; unknown tracks still
  raise.
- `tests/test_exploration_score.py` — dims 1–3 arithmetic on synthetic
  sidecars (each threshold's pass/fail edge), the blocked/out-of-scope
  register-row exclusion, and sidecar↔entries reconciliation failures.
- `tests/test_battery_lint.py` — each lint rule on synthetic sources
  (violating and clean), plus the always-on run against the real
  `queries.py`/`tests.py` with the allowlist honoured — same
  synthetic-plus-real pattern `tests/test_coverage_register.py`
  established.
- Declaration-parser tests — block↔`TestResult` kwarg match, mismatch,
  missing superlative check, backlog (no block) tolerated.
- `tests/test_render_verify.py` — number extraction/normalisation, roster
  scan on synthetic prose (including the no-bare-surname rule), citation
  validity, reply-gate recomputation, `claims_skipped` reconciliation.
- `db`-marked (not required CI): the `battery_verification/` harness
  runner; chart/drill-down completeness.

**Existing tests:** minimal changes. The Editor sidecar change is
additive and `publish_gate` is untouched; `conductor_loop.py` changes
only as described in §2.4 (`VALID_TRACKS` + human-track escalation) and
gains its first tests above; `test_coverage_register.py` is untouched
(the parser extends, not replaces). If any existing test asserts the
exact Editor markdown template, update the fixture to the v0.5 shape.

**Doc deltas:**

| File | Change |
|------|--------|
| `Editor_prompt.txt` → v0.5, `EDITOR_PROTOCOL.md` → v0.4 | per §2 |
| `Explorer_prompt.txt` → v3.1, `EXPLORATION_PROTOCOL.md` | per §3 |
| `Refiner_prompt.txt` → v1.3, `REFINEMENT_PROTOCOL.md` | per §4 |
| `Renderer_prompt.txt` → v1.1, `RENDERER_PROTOCOL.md` → v1.1 | per §5 |
| `docs/AGENT_PROMPTS.md` | scorer/verifier invocation entries (same command-layer pattern; note scorers are per-run follow-ons, not self-directing roles) |
| `docs/MAP.md` | the Exploration-loop description (currently "Stage 3 self-score") and the Editor/Renderer rows updated; new "Where do I add X?" rows for scoring a session/review/render |
| `docs/TESTING.md` | the new required-CI checks, the `db` marker convention, `render-verify`/`editor-score`/`explore-score` in the workflow descriptions |
| `docs/AUTOMATION_ARCHITECTURE.md` | Explorer session sidecar closes the logged session-summary simplification; `maintenance.yml`'s activation-checklist items point at `editor_score_<n>.json` as their data source |
| `docs/AGENT_DESIGN.md` | short cross-reference from §2's role roster to this doc (the roles' scoring column changed owner) |

**Deliberately unchanged:** `CONDUCTOR.md`'s loop and pass cap, the
publish invariant and both gate profiles, `Fixer_prompt.txt` and its
modes, `Researcher_prompt.txt` (its self-check gates a *merge proposal* a
human already reviews file-by-file — same class as Refiner: the check is
the procedure, and the human gate is the independent verifier; revisit
only if auto-merge mode ever becomes the default), all S0–S7 scripts, and
every autonomy-ladder position.

---

## Appendix — the branch-based escalation model (proposed 2026-08-24)

Not part of this plan's build order — **designed in full 2026-08-24 in
`AUTOMATION_ARCHITECTURE.md` Part 4 (the authoritative version; this
appendix is the summary)**, with the decision record in
`CICD_DECISIONS.md`'s matching entry; from there the root `README.md`
once built. Recorded here because it is the intended *transport* for
every escalation this plan defines (§2.4's note), and the plan's
contracts were shaped to fit it.

**The model.** A logical run executes as a chain of working-branch
segments. Success PRs to `main`; an escalation PRs to `staging`, whose
merge is the approval that resumes the run — each resume branching off
staging, so approved partial work (including any amendments the human
pushed before approving) is the substrate the next segment builds on:

```
main ──────────────────────────────────────────────► (final PR merge)
  │ reset staging = main                                    ▲
  ▼                                                         │
staging ──► working_session_1 ──fail──► PR → staging        │
  │           (branch off staging)        │ approve/merge   │
  ▼◄──────────────────────────────────────┘                 │
staging ──► working_session_2 ──fail──► PR → staging        │
  │           (branch off staging,        │ approve/merge   │
  ▼◄──────── resumes from run_state) ─────┘                 │
staging ──► working_session_3 ──success──► PR → main ───────┘
```

**Rules settled so far:**
- staging = main + approved partial work, always; it never deploys and
  never merges to main itself — the final segment's PR to main carries
  the whole approved lineage in one reviewed merge.
- A dispatch chooses one of two modes; staging never resets between
  segments, and one logical run at a time either way (single-lane
  staging, enforced by a workflow concurrency group):
  - **fresh** — reset staging = main, start from the beginning. Chosen
    when there is no prior approved work, or when the human's upstream
    fix invalidates it (e.g. an extraction-prompt change staling
    already-approved extractions).
  - **resume** — keep staging (which still holds the approved segments
    of a previously declined run), merge main into it as the first
    step, and continue from `run_state.json` at staging HEAD —
    re-running only the failed stage onward, never recomputing approved
    work. Only the human can judge which mode a given fix calls for,
    which is why it's a dispatch input, not inferred.
- **Where a manual fix goes before a resume — by fix type, and resume's
  unconditional main→staging merge makes it a non-decision at dispatch:**
  a fix to the *run's own work* (a bad intermediate output, wrong
  partial state) is committed directly to staging — it's run-scoped and
  reaches main via the final PR like the rest of the run's work; a fix
  to the *instrument* (prompt, script, config, schema) goes to main via
  normal dev flow — it should benefit every future run, and an
  instrument fix living only on staging is hostage to this run
  succeeding (declined-and-abandoned means the next fresh dispatch's
  reset silently wipes it). Resume's first-step merge is a no-op when
  main hasn't moved, carries the fix when it has, and handles both at
  once — the human never tells the dispatch where they made changes.
- `run_state.json` (run id, sequence position, segment number, pass
  counts) is committed on the working branch, so after an approval merge
  it sits at staging's HEAD — the resume workflow triggers on
  merge-to-staging and needs no state outside git.
- The escalation PR's review payload is exactly this plan's contract
  artefacts: the `human`-track flag's `reasoning`, the review sidecars,
  the score files.

**The two human responses to an escalation PR.** GitHub is deliberately
only the trigger and approval surface — development stays in the human's
own environment (local editor, a Claude Code session, a hosted coding
agent), never in a GitHub-resident feedback/revision loop (a
request-changes → revision-agent cycle was considered and rejected
2026-08-24 for exactly that reason: it shifts the development
environment onto GitHub).
1. **Approve + merge** → the run resumes from staging, as above. This
   includes the "amend, then approve" case with no extra machinery: the
   working branch is an ordinary branch, so a human who finds the
   partial work fixable checks it out wherever they work, pushes the
   fix, and merges — the resume builds on the corrected version
   automatically, because segments always branch off staging.
2. **Close (decline)** → the logical run ends. Branch kept for
   forensics; the closed PR is itself the record; the lane is released.
   **A decline discards only the failed segment's work** (which lives on
   the closed PR's branch and never reached staging) — the approved
   segments stay in staging indefinitely, because a decline rejects the
   failure, not the human's own earlier approvals. **No automatic
   retry** — a decline carries no information to retry *with*, so a
   blind re-run would reproduce the same failure at full cost. Decline
   means the run can't be saved by iterating as-is: the human makes the
   fix by hand (placed per the fix-type rule above — instrument fixes on
   main, run-scoped fixes on staging), then
   dispatches the retry in whichever mode the fix calls for — **resume**
   (the common case: continue from the last approved stage with the fix
   merged in, no recomputation of approved work) or **fresh** (the fix
   staled the approved work itself; reset and redo). Anything salvageable
   from the declined segment can be cherry-picked from its branch by
   hand. Same principle as the Conductor's existing cap rule: persistent
   failure signals the instrument, not the iteration count.

---

## Build log

Same convention as `docs/AGENT_DESIGN.md`'s dated build-order entries:
what actually shipped, and any deviation from this spec with its reason.

### 2026-08-24 — Step 1, Editor split (§2)

Shipped as specified, with one forced deviation and one factual note.

**What shipped:** `Editor_prompt.txt` → v0.5 (removed the
`EDITOR_PROTOCOL.md` "Read first" bullet and the entire Score
section/verdict-computation instruction; new single-path verdict rule,
FAIL iff ≥ 1 BLOCKING flag; the holistic-flag outlet with the `human`
track and its required `reasoning`; `claims[]`/`flags[]` added to the JSON
sidecar, additive, the six existing fields unchanged). `EDITOR_PROTOCOL.md`
→ v0.4 (now owns all eight dimension definitions and the enumerated
criterion slug vocabulary; documents the two-layer scoring stage; notes
v0.3-era scores aren't comparable post-split). `scripts/conductor_loop.py`:
`VALID_TRACKS` gains `"human"`; a FAIL carrying a `human`-track flag
escalates immediately via the existing `escalate_blocked()` path, before
any pass-cap check, dispatching no Fixer for that pass even when ordinary
tracks are co-flagged. `docs/review/CONDUCTOR.md` gets the matching
sentence, per §2.4. New `src/editor_score.py` (Layer 1, deterministic —
contract hygiene, flag routability, verdict integrity, the disclaimer
string, and dimension 8's false-positive cross-check against
`gate_report.json`) and `docs/agent_prompts/editor_scorer.txt` (Layer 2, a
fresh-context agent that never reads `Editor_prompt.txt`). New `council
editor-score <council> <run_id>` CLI command (`src/cli.py`): runs Layer 1,
embeds its result into Layer 2's prompt as `<layer1_json>`, invokes Layer
2 via `run_claude`, then reads back the combined `editor_score_<n>.json`
Layer 2 itself writes and exits non-zero on anything but `status: PASS`.
`maintenance.yml` runs `council editor-score` once per chain (regardless
of PASS or escalation, per §2.4 — its purpose is calibration, not gating)
and adds a fourth condition to the publish step: a non-clean score blocks
an auto-profile publish in the same run even on a clean Editor PASS.
`docs/AGENT_PROMPTS.md`, `docs/MAP.md`, `docs/TESTING.md`,
`docs/AUTOMATION_ARCHITECTURE.md` updated per §8's table (Editor-scoped
deltas only — the Explorer/Renderer rows §8 also names are out of scope
for this step and untouched). New tests: `tests/test_editor_score.py`
(Layer 1 — the full §8 fixture list: clean PASS, FAIL with valid flags,
sidecar/markdown mismatch, invalid track, missing criterion,
verdict-integrity failure in both directions, human-track flag with and
without `reasoning`, dimension 8 plus its two negative-control fixtures)
and `tests/test_conductor_loop.py` (human-track FAIL escalates with no
Fixer dispatched even with a co-flagged ordinary track; an ordinary-track
FAIL still dispatches as before; unknown tracks still raise). Full suite
green (159 passed), ruff clean. The §1 acceptance grep
(`grep -iE "PROTOCOL\.md|benchmark|self-score|scored against"` over
`Editor_prompt.txt`) returns nothing outside its Changelog section — one
live-section hit (the S7-boundary paragraph explaining why re-litigating
an S7-cleared claim is a defect) was reworded to drop the
`EDITOR_PROTOCOL.md` reference rather than kept as an exception.

**Deviation (forced, not a spec conflict): `VALID_TRACKS` split into
`FIXER_TRACKS` (`{frontend, pipeline, doc}`) and `VALID_TRACKS`
(`FIXER_TRACKS | {"human"}`).** §2.4 says plainly "`VALID_TRACKS` gains
`"human"`," but `src/cli.py`'s `council fixer` subcommand already imports
that exact name for its `choices=` list — growing it in place would have
made `council fixer human <council> <run_id>` a valid-looking CLI
invocation with no `human_mode.txt` behind it, silently broken rather than
refused at the parser. `FIXER_TRACKS` is now the three Fixer-dispatchable
tracks (what `council fixer`'s choices and `run_conductor_loop`'s dispatch
loop use); `VALID_TRACKS` is the full flag-track vocabulary Editor may
emit and `run_conductor_loop`'s unknown-track check validates against —
exactly `VALID_TRACKS` as the spec describes it, just decomposed so the
CLI can't accidentally inherit the new value. `src/editor_score.py`
imports `VALID_TRACKS` from `scripts/conductor_loop` for the same flag
validation, one source of truth, matching the existing precedent of
`src/cli.py` already importing `conductor_loop`'s constants rather than
duplicating them.

**Live demonstration (real run, not a fixture):** `council editor cambridge
draft_20260823_173842` (a real `claude -p` call) produced a genuinely
v0.5-shaped `defamation_review_1.json`/`.md` — 28 `claims[]`, 4 `flags[]`,
and, unprompted by any example in this session's own conversation, a
`["human"]`-tracked BLOCKING flag (the still-unresolved four-way
councillor-identity split) with a concrete `reasoning` field, tagged
`human` specifically because `Fixer[pipeline]` had already reported
BLOCKED on the identical flag in a prior real pass — exactly the outlet
§2.2 designed, working as designed on its first live use. `council
editor-score cambridge draft_20260823_173842` then ran Layer 1 for real
against that output: `structural_ok: true`, zero findings, zero false
positives, measurements matching the review exactly
(`claims_reviewed: 28`, `flags_blocking: 1`, `flags_advisory: 3`). Layer
2's real `claude -p` invocation then failed with "Credit balance is too
low" from this environment's account before it could write
`editor_score_1.json`/`.md` — an account/billing constraint on the
session that ran this build, not a defect in `src/editor_score.py`,
`docs/agent_prompts/editor_scorer.txt`, or `src/cli.py`'s `editor-score`
command (which correctly detected the missing output file and exited
non-zero rather than reporting false success). Layer 2's real output
shape therefore remains unverified against a live run; re-run `council
editor-score cambridge draft_20260823_173842` once account credit is
available to complete this — the draft directory and its pass-1 review
are left in place for that purpose.

**Factual note, not a deviation:** §7's own reasoning for building Editor
first was to land the split "before that first [v0.4] chain." A real v0.4
chain (`python scripts/conductor_loop.py cambridge --max-passes 3` →
`draft_20260823_171209`, PASS on pass 2) already completed and is recorded
in `docs/review/REVIEW.md` and `docs/strategy/PRIVATE_ASSESSMENT.md`,
committed before this implementation session started. Nothing about the
split's design needed to change as a result — the real chain's flags and
fixes are about the *drafts* (per §7's own argument for why prompt-shape
changes don't invalidate flag-level lessons), not about the Score block
this step removed — but the "first real calibration cycle lands on the
final shape" framing in §7 item 1 didn't hold in practice; that chain's
`defamation_review_1.json` predates `claims[]`/`flags[]` and can't be fed
to `council editor-score` as-is. The live end-to-end demonstration this
step's "Definition of done" calls for therefore needs a *fresh* `council
editor` run (v0.5) against a draft directory with no existing review, not
a re-score of that chain's output.
