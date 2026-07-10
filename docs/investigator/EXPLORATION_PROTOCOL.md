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

**The benchmark (agreed 2026-06-27, derived from Cambridge Phase A–K calibration):**

Seven dimensions, each with a declared threshold. A session passes the benchmark only
when ALL seven clear their threshold. A failing dimension (not the passing ones) drives
the next improvement to `Investigator_prompt.txt`.

| # | Dimension | Threshold | How to measure |
|---|-----------|-----------|----------------|
| 1 | **Domain breadth** | ≥ 4 of the 5 Phase-1 genre domains (A Financial, B Governance, C Integrity, D Transparency) must each have ≥ 1 bespoke hypothesis before testing; domain E Strength expected | Count bespoke hypothesis entries by Phase-1 genre in Stage 2 output |
| 2 | **Stage 1 data survey** | Binary PASS: a structured data profile — table row counts, investigation-critical NULL rates, known corpus gaps, date-span coverage by key table — must exist in scratchpad before the Stage 2 hypothesis list | Check scratchpad for a named profile artifact dated before Stage 2 |
| 3 | **Structural kill rate** | ≤ 10% of bespoke hypotheses tested in Stage 4 die to structurally missing data (columns that the test requires are absent or 100% NULL) | Count hypotheses classified INFEASIBLE or died to schema/NULL gaps; divide by total bespoke tested; Stage 1 should surface these before Stage 4 |
| 4 | **Finding rate** | ≥ 25% of bespoke hypotheses tested produce a Finding (built) or an actionable Banked result | Count `INVESTIGATIONS.md` entries classified `[✓]` Finding or `[◐]` Banked with a clear build path; exclude structural kills (those belong to Dim 3); divide by total bespoke tested |
| 5 | **Evidence completeness** | ≥ 75% of confirmed flagship findings have drill-down data inlined in their snapshot JSON, with ≥ 1 verbatim source quote from `extraction_evidence` per inlined record | Check `frontend/public/data/*.json` for populated drill-down arrays (`declarations`, `awards`, `votes`, `items`, etc.) with a non-empty `quote` field |
| 6 | **Stage completion** | ≥ 6 of 7 Stages 1–7 produce their defined output (Stage 8 is explicitly permitted to defer) | Binary checklist: Stage 1 profile in scratchpad; Stage 2 numbered hypothesis list; Stage 3 `scorecard.json` updated; Stage 4 `INVESTIGATIONS.md` updated; Stage 5 snapshot JSONs carry drill-down; Stage 6 `tsc + vite build` clean and frontend verified; Stage 7 `overview.json` + `FINDINGS_SUMMARY.md` updated |
| 7 | **Framing balance** | 100% of confirmed flagship findings carry both the hostile-reader sentence and the promoter sentence, and are published in the NEUTRAL register | Review each flagship panel's text for the mandatory two-sentence pair (Investigator_prompt.txt Phase 4); verify register is NEUTRAL, not pure-CRITIC |

**Cambridge calibration — Phase A–K sessions scored against the benchmark:**

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

1. Run a full investigation session following Stages 1–8
2. Score against the seven dimensions above; record scores in the session header in `INVESTIGATIONS.md`
3. If all seven ≥ threshold → freeze the protocol version and begin production use on that version
4. If any dimension < threshold → identify the lowest-scoring dimension, update `Investigator_prompt.txt` to address it, increment the version number, and repeat from step 1

### Proposed stages

**Stage 1 — Data survey**
Before forming hypotheses, profile the database: table sizes, date ranges, coverage quality,
known NULL fields, known extraction gaps. Answer "what can this data actually support?"
Output: a structured data profile written to the scratchpad.
Purpose: kills unsupportable hypotheses before they waste test budget (e.g. [latency] was
killed because application_date and decision_date are 100% NULL — a pre-survey would have
caught this immediately).

**Stage 2 — Hypothesis generation**
Generate a broad candidate list anchored to recognised governance criteria (Nolan / CIPFA /
Best-Value). Do not test yet — enumerate first. Each hypothesis should name the table(s) it
requires and the predicted direction.
Output: numbered hypothesis list (format: INVESTIGATIONS.md Phase headers).
Open question: should this happen before or after Stage 1? Surveying first is more efficient
(prunes impossible hypotheses), but cold hypothesis generation before seeing the data may
produce more imaginative candidates. Proposed resolution: a lightweight survey (table sizes
+ known NULL fields) before generation, but deep per-table profiling only on-demand during
Stage 4 testing.

**Stage 3 — Standard battery**
Run `run_test_battery()` from tests.py. Deterministic — no hypothesis needed, same 23 tests
every run. Produces the Scorecard. Should run before bespoke investigations so the baseline
picture is established first.
Output: scorecard.json.

**Stage 4 — Hypothesis testing**
For each non-standard hypothesis from Stage 2, write a query, run it, apply the two-tier
bar (standard test: include regardless; flagship: novel × resident-relevant × surprising),
and classify as Finding / Null / Banked / Infeasible.
Save findings immediately to INVESTIGATIONS.md with the standard entry format. Retain
scratchpad scripts under `scratchpad/`.
Output: classified investigation entries, scratchpad scripts.
Open question: should confirmed findings' evidence be exported here (to a staging file) or
deferred to Stage 5? Exporting immediately during testing means Stage 5 is just assembly,
but it adds overhead to each test loop. To be determined by experience.

**Stage 5 — Evidence export**
For each confirmed Finding, export granular evidence records with verbatim source quotes as
structured JSON. This feeds the Evidence page drill-downs. Run `council publish` to inline
the drill-down data into snapshot files.
Output: updated snapshot JSONs with inlined drill-down data and source quotes.

**Stage 6 — Panel and analysis generation**
For each Finding, produce: chart data, headline, verdict text, valence chip, backTo link.
Register the panel in the battery (BatteryTestPanel) or as a bespoke component. Confirm
every panel corresponds to a battery test (no orphan panels — per methodology v2.2).
Run `council publish cambridge` and verify the frontend renders.
Output: updated Analysis page. Frontend build clean.

**Stage 7 — Summary synthesis**
Once all panels are stable, run a synthesis pass: write the plain-English overview
(7–8 cross-cutting insights), assign the one-liner verdict, regenerate overview.json.
Apply the CRITIC / PROMOTER / NEUTRAL review sequence from Investigator_prompt.txt v2.1
to calibrate framing before publishing.
Output: updated overview.json, updated Overview page content.

**Stage 8 — Visual generation**
Generate the council boundary map graphic (F1) using geocoded data and boundary GeoJSON.
This runs last because it depends on the full tender/planning data being finalised.
Output: SVG/Canvas graphic for Overview page hero.

### Open questions about ordering

The staging above is a first draft. The following tensions need empirical resolution by
running a full investigation cycle under the protocol and noting where it breaks down:

1. **Browse depth vs efficiency.** Unguided browsing is expensive in tokens. The Stage 1
   survey should be driven by a fixed checklist (what tables, what counts, what NULL rates,
   what known gaps), not left to Opus to infer. The checklist itself should be versioned
   alongside `Investigator_prompt.txt`.

2. **Hypothesis generation before vs after data survey.** See Stage 2 note above. First
   full run should try survey-first and note any hypotheses that felt artificially constrained
   by seeing the data profile too early.

3. **When to export evidence.** The current pattern (export during publish, not during testing)
   means a Finding sits unexported for potentially multiple sessions. An alternative: during
   Stage 4, Opus writes a structured `evidence_staging/{hypothesis_id}.json` immediately on
   confirmation, and Stage 5 just assembles these into snapshot files. This keeps evidence
   closer to the investigation moment but adds schema discipline to Stage 4.

4. **How many hypotheses to generate vs how many to test.** Generating 30 and testing 10 is
   fine; generating 100 is waste. The right number is probably "all hypotheses that could
   plausibly clear the two-tier bar given the data profile." Opus should apply the data profile
   as a filter during generation, not after.

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
