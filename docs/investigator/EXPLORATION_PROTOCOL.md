# Investigation Protocol

The staged, benchmark-gated plan for running and **iteratively improving** an
investigation. This document governs how `Investigator_prompt.txt` (the runtime
prompt used each investigation) is versioned: improve until a declared benchmark
is met, then freeze and run. Relocated from the former ANALYSIS_ROADMAP.md.

Related: `Investigator_prompt.txt` (the prompt this protocol improves),
`INVESTIGATIONS.md` (the record each run appends to), `FINDINGS_SUMMARY.md`
(the synthesis output).

---

### Current approach

Investigations have been conducted by prompting Claude Code Opus with extended thinking
enabled. Opus autonomously spawns subagents, queries the database, forms hypotheses,
tests them, and writes findings to INVESTIGATIONS.md. The `Investigator_prompt.txt`
(currently v2.2) governs investigation stance, test bars, severity grading, and framing.

This produced the 30+ investigations in INVESTIGATIONS.md, but it is not reproducible in
a controlled way: two Opus runs on the same corpus may explore different hypotheses, apply
different rigor thresholds, or skip the same check. The goal is to formalise this into a
staged, ordered protocol that is auditable and improvable.

### Goal

A protocol that:
- Produces the same standard tests every run (tests.py battery already achieves this for
  the fixed 23 tests; the protocol extends discipline to bespoke investigations)
- Can be run by any sufficiently capable model given only the protocol document and the DB
- Maps explicitly onto the three output pages: Evidence / Analysis / Overview
- Is improved iteratively only until a declared benchmark is met, then frozen and reused

### Improvement model: benchmark-gated, not open-ended

The protocol should follow the same discipline as the Level 1 inventory loop in PIPELINE.md:
iterate to improve, stop when a benchmark is met, then use the frozen version repeatedly.

**Analogy:** The inventory prompt was iterated until `other_content_rate ≤ 20%`. Once that
threshold was reached the prompt was frozen and the same version ran across the full corpus.
The investigation protocol should work identically — improve until it clears a declared score,
then stop improving and start running.

This matters because open-ended iterative improvement has no stopping condition. Each run
always reveals something that could be done better. The result is a protocol that is
perpetually being refined rather than being used productively.

**The benchmark must be declared before iterative improvement begins.** Defining the target
after seeing results introduces post-hoc goalpost-moving. The benchmark should specify:
- What a "good" investigation run looks like (coverage, depth, efficiency)
- How to score a completed run against those criteria
- What score constitutes "good enough to freeze"

**The benchmark, current version (rewritten 2026-08-23, `Explorer_prompt.txt`
v3.0 — see the note directly below the table for what changed and why):**

Four dimensions, each with a declared threshold. A session passes the benchmark only
when ALL four clear their threshold. A failing dimension (not the passing ones) drives
the next improvement to `Explorer_prompt.txt`.

| # | Dimension | Threshold | How to measure |
|---|-----------|-----------|----------------|
| 1 | **Register-gap reduction** | ≥ 1 bespoke hypothesis this session explicitly targets a register gap, of either kind below, on a dimension that is neither `data_blocked` nor `out_of_scope` | Read the register; check the Stage 1 hypothesis list for ≥ 1 entry naming a matching dimension. **Two kinds of gap both satisfy this (added 2026-08-27, Explorer v3.1):** (a) a `docs/investigator/coverage_register.json` dimension with corpus-scope `verdict` EMPTY or THIN; (b) a dimension with corpus-scope `verdict` MODERATE/DENSE but `meeting_verdict` EMPTY/THIN — computed by `src/analysis/coverage_register.py`'s `granularity_report()` (cross-references the register against `_MEETING_BATTERY`, never a hand-maintained field, so it can't drift the way a second stored verdict could). One hypothesis satisfies the dimension regardless of which kind it targets — this doesn't raise the bar, it recognises a second real kind of gap the four-dimension benchmark didn't previously have visibility into. |
| 2 | **Structural kill rate** | ≤ 10% of bespoke hypotheses tested in Stage 2 die to structurally missing data (columns that the test requires are absent or 100% NULL) | Count hypotheses classified INFEASIBLE or died to schema/NULL gaps; divide by total bespoke tested; `council profile`'s output (S2) should surface most of these before Stage 2 |
| 3 | **Finding rate** | ≥ 25% of bespoke hypotheses tested produce a Finding (built) or an actionable Banked result | Count `INVESTIGATIONS.md` entries classified `[✓]` Finding or `[◐]` Banked with a clear build path; exclude structural kills (those belong to Dim 2); divide by total bespoke tested |
| 4 | **Framing balance** | 100% of confirmed flagship findings carry both the hostile-reader sentence and the promoter sentence, and are published in the NEUTRAL register | Review each flagship write-up for the mandatory two-sentence pair (`Investigator_prompt.txt` Stage-2 write-up discipline); verify register is NEUTRAL, not pure-CRITIC |

**What changed 2026-08-23, and why (`docs/AGENT_DESIGN.md` §3 Q2, §6 Step 5):**
Explorer's scope narrowed to discovery only — it no longer surveys the
corpus (S2, `council profile`, is a script now) or builds anything
(evidence export, panels, synthesis, visuals all left for future S10
Renderer owners). The old seven-dimension benchmark measured duties that no
longer belong to this prompt, so three dimensions dropped rather than being
carried forward as dead weight: **Stage 1 data survey** (the stage itself
is gone — S2 replaced it), **Evidence completeness** and **Stage
completion** (both measured build-stage output that Explorer no longer
produces). **Domain breadth** didn't drop — it *became* **Register-gap
reduction**: the coverage audit (`COVERAGE_AUDIT_2026-08-23.md`, finding
F1) found that per-session breadth counting tracked whichever genre a
session happened to notice (corpus gravity), not the instrument's actual
gaps; scoring against the register's worst open row instead makes session
planning cumulative-coverage-aware rather than breadth-for-its-own-sake.
Structural kill rate, finding rate, and framing balance are unchanged in
definition, only renumbered and re-pointed at the new stage numbers.

**Historical note (2026-08-20, pre-dates the above):** domain F
(Effectiveness, `Investigator_prompt.txt` Part 3.5) was added to the old
six-domain-breadth check after the Cambridge calibration below was scored —
those sessions predate it and cannot be read as having covered it. This
note is kept for the calibration table's own context; domain-breadth
counting itself no longer exists as a dimension as of the rewrite above.

**Cambridge calibration — Phase A–K sessions scored against the *original*
seven-dimension benchmark (kept verbatim as history; the current benchmark
is the four-dimension table above):**

These sessions were exploratory, run without the staged protocol, and spread across
multiple sessions rather than a single end-to-end run. They are the calibration
reference — the corpus from which the benchmark was derived — not a passing target.

Counts used: 27 bespoke hypotheses tested (hypotheses [1]–[28] excluding [7] which was
already built before Phase A, and excluding synthesis/battery/interactivity build entries
which are not hypotheses). Flagship panels built: 9 ([1], [2], [8], [9], [11], [12],
[18], [19], [27/28]).

| # | Dimension | Cambridge score | Pass? | Root cause of any gap |
|---|-----------|-----------------|-------|-----------------------|
| 1 | Domain breadth (≥ 4/5) | 5/5 genres covered across corpus | ✓ | — |
| 2 | Stage 1 data survey (binary) | No structured profile produced; organic exploration only | ✗ | Stage 1 not yet in prompt; target for v2.3 |
| 3 | Structural kill rate (≤ 10%) | 3 structural failures / 27 tested = 11% | ✗ | [latency] (100% NULL dates), [6] (placeholder `submitter_name`), [25] (confidential = missingness) — all catchable by a NULL-rate check in Stage 1 |
| 4 | Finding rate (≥ 25%) | 11 publishable / 27 tested = 41% | ✓ | — |
| 5 | Evidence completeness (≥ 75%) | 7/9 flagships have drill-down + quotes = 78% | ✓ | [8] Tenure and [27/28] Sponsorship are Tier-2 backlog in INTERACTIVITY.md |
| 6 | Stage completion (≥ 6/7) | 6/7 Stages 1–7 produced output | ✓ | Stage 1 data profile absent (same root as Dim 2) |
| 7 | Framing balance (100%) | 9/9 flagships calibrated post-session 8 | ✓ | — |

**Cambridge benchmark score: 5/7 dimensions pass.** Both failures (Dim 2, Dim 3) share
one root cause: Stage 1 was never formally executed, so three structurally unsupportable
hypotheses burned test budget rather than being caught before testing. Adding a
structured Stage 1 checklist to `Investigator_prompt.txt` (v2.3 target) is expected to
fix both dimensions in a single improvement.

**The improvement loop (now unblocked):**

1. Run a full investigation session following Stages 1–3
2. Score against the four dimensions above; record scores in the session header in `INVESTIGATIONS.md`
3. If all four ≥ threshold → freeze the protocol version and begin production use on that version
4. If any dimension < threshold → identify the lowest-scoring dimension, update `Explorer_prompt.txt` to address it, increment the version number, and repeat from step 1

### Stages (rewritten 2026-08-23 — discovery-only, `docs/AGENT_DESIGN.md` §6 Step 5)

Three stages remain, renumbered from the original eight. The five dropped
stages didn't go away — they moved to other owners (see each entry below)
— so this is the S3-Discovery slice of a bigger flow, not a shrunken
version of the same job. `Explorer_prompt.txt` v3.0's own preamble and
Stage 3 carry the operating-layer detail; this section is the stage
contract shape (inputs / output / stopping condition) matching the pattern
every other stage in this doc set uses.

**Stage 1 — Hypothesis generation (register-gap seeded)**
Read `docs/investigator/coverage_register.json` and `council profile`'s
output (or `data/<council>_profile.json`) first — not a Stage of their own
anymore, since both are now scripted (S2 profile; the register is a static
file with its own verifier, `src/analysis/coverage_register.py`). Also run
`granularity_report()` (same module, added 2026-08-27) — a dimension's
corpus-scope density and its meeting-scope density are different
questions, and the register's own `verdict` only ever answered the former.
Generate a broad candidate list anchored to recognised governance criteria
(Nolan / CIPFA / Best-Value), with at least one hypothesis explicitly
targeting the register's worst open gap — either a corpus-scope EMPTY/THIN
row, or a row DENSE/MODERATE at corpus scope but EMPTY/THIN at meeting
scope (dimension 1's two-kind definition, above); not `data_blocked`/
`out_of_scope` either way. Do not test yet — enumerate first. Each
hypothesis should name the table(s) it requires and the predicted
direction.
Output: numbered hypothesis list (format: `INVESTIGATIONS.md` Phase headers).

**Stage 2 — Hypothesis testing**
For each hypothesis from Stage 1, write a query, run it, apply the
two-tier bar (standard test: include regardless; flagship: novel ×
resident-relevant × surprising), and classify as Finding / Null / Banked /
Infeasible. For a meeting-scope-gap hypothesis (added 2026-08-27): its
natural `n` is small by nature ("1 of 4," "2 of 9") — that's the honest
count at that scale, not a thin-data signal the way the same `n` would
read on a corpus-wide test, so don't default it to DIRECTIONAL-ONLY purely
on `n`'s size (`Explorer_prompt.txt`'s Stage 2 states this in full). Save findings immediately to `INVESTIGATIONS.md` with the
standard entry format (n, base rate, era, severity grade, strength +
superlative check where relevant, hostile-reader and promoter sentences —
`Investigator_prompt.txt` §4.6, `Explorer_prompt.txt`'s Stage-2 write-up
discipline). A structural kill also writes to
`pipeline/DATA_ENRICHMENT.md` per the existing procedure. Retain scratchpad
scripts under `scratchpad/`. **No build step** — this stage ends at the
`INVESTIGATIONS.md` entry; turning a Finding into a battery test is S4
(Refiner), not this stage.
Output: classified investigation entries, scratchpad scripts.

**Stage 3 — Self-score and propose**
Score the session against the four benchmark dimensions above; record in
the `INVESTIGATIONS.md` session header. If all four pass, note the
benchmark as cleared. If any fails, draft (don't apply) a targeted,
minimal `Explorer_prompt.txt` edit addressing the lowest-scoring
dimension, for a human to review.
Output: session header scores; a proposed prompt edit, if any dimension failed.

**Where the other five stages went**, for anyone holding the old numbering
in their head: old Stage 1 (data survey) → **S2, `council profile`**
(script, `src/analysis/profile.py`); old Stage 3 (standard battery) →
**S6, `council draft`** (already scripted — `run_test_battery()` always
ran there, never inside an Explorer session); old Stages 5–6 (evidence
export, panel/analysis generation) and old Stage 7 (summary synthesis) →
future **S10 Renderer** (`docs/AGENT_DESIGN.md` §6 Step 6, not built yet);
old Stage 8 (visual generation) → the frontend track generally (it was
never really an Explorer investigation stage — a one-time asset build, not
counted in the old benchmark's own Stage-completion dimension either).

### Open questions about ordering — resolved by the 2026-08-23 rewrite

The four tensions logged below applied to the old eight-stage design and
are moot now that Stages 1 (survey), 3 (battery), 5–6 (evidence/panel
build), and 7 (synthesis) no longer exist in this prompt. Kept as history,
not live questions:

1. **Browse depth vs efficiency** (old Stage 1 survey checklist design) —
   moot; the survey is `council profile`, a deterministic script with no
   token cost per run.
2. **Hypothesis generation before vs after data survey** — moot in the old
   framing (there's no in-session survey to order against); resolved in
   practice by `Explorer_prompt.txt` v3.0's preamble, which reads the
   profile before Stage 1 unconditionally.
3. **When to export evidence** — moot; evidence export is a future S10
   Renderer concern, not this prompt's.
4. **How many hypotheses to generate vs test** — still live, but now a
   Stage 1 judgment call rather than an ordering question between two
   stages that no longer both exist.

### Protocol document home

`Investigator_prompt.txt` is the canonical protocol document (now at v2.2). The staged
protocol above should be added to it as a numbered preamble that Opus follows in order.
Each stage should define:
- What inputs it reads
- What output it produces and where it saves it
- What the stopping condition is

The next step is to run a single new council (or a Cambridge refresh) end-to-end following
this staged order, note every deviation and inefficiency, and increment the protocol to v2.3.
The protocol version should be noted at the top of each INVESTIGATIONS.md session header.
