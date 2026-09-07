# From a 14-card digest to an exception report and a /watch feed

Status: **built** (Steps 1–8, 2026-09-07). Written 2026-09-06.
Fourth in the sequence, after `TEST_REGISTRY_PLAN.md`, `PANEL_FRAMING_PLAN.md`
and `SURFACE_PROJECTION_PLAN.md` (all built).
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes — kept as the record
of the pre-`/watch` state, not updated to describe the current one; see the
measurements below and each step's own commit for what actually shipped.

This plan spans the pipeline, the publish gate and three frontend surfaces —
more than the previous three. `/watch` publishes (B.3, settled 2026-09-06), so
Step 5 moves a boundary that until now has kept every single-meeting claim off
the live site. Read B.3 before Step 4.

**The public/full split Step 5 measured** (the number that decides how much
of the feed a reader actually sees): over the real corpus — 506 minutes
meetings, 1169 exception-claims total — only **5 claims across 5 meetings**
were withheld as full-tier, all `transparency.confidential_topics`, all
genuine leaks (an item description naming a councillor directly). The
published `watch.json` carries **1164 of 1169** exceptions; every row that
drops one records the count in `exceptions_withheld` rather than silently
looking quieter than the meeting actually was (B.3). Not a large share — the
feed ships as designed, not as a reduced one.

---

## Part A — What is already there

### A.1 The exception engine is largely built. Do not rebuild it.

`src/analysis/digest.py` already computes "did this meeting deviate from
baseline", by exactly the method the brief describes:

- **`score_salience(claim, baselines, body_class, policy)`** returns
  `max(novelty, digest_floor)`.
- **novelty** is a two-sided percentile of the claim's `stat` against the
  distribution of that same statistic across every other meeting **of the same
  body class** — `src/analysis/meeting_baselines.py`, cached corpus-wide in
  `data/cambridge_meeting_baselines.json` (460 meetings considered), so no run
  recomputes it. A 4-member committee is never scored against full council.
- **`digest_floor`** is the per-generator "any occurrence" floor. Eight
  generators already declare `digest_floor=1.0`: a tender awarded, a conflict
  declared, an item closed, a deputation heard, an unexplained absence, a
  confidential topic, a confidential tender, a decider↔supplier collision.
- **`compose_period_digest()`** already separates `candidates` (all claims) from
  `highlights` (salience ≥ `min_salience`, capped at `max_highlights`).
- Novelty is disabled where a `(test_id, body_class)` has fewer than
  `min_baseline_meetings` priors — a thin baseline cannot support a percentile.

What the brief adds is that the threshold should be **per test, in the
registry**. Today it is split between a global `min_salience: 0.7` in
`config/digest_policy.json` and `digest_floor=` arguments inside `tests.py`.
See B.2 — that is the real change, and it is a move, not a build.

### A.2 The 14 null cards are a rendering choice, not a computation problem

`DigestPage.tsx` renders every claim `run_meeting_digest()` returns, through
`BatteryTestCard`, grouped by category. The salience layer that would tell it
which of the 14 to show already runs — in `compose_period_digest()`, whose
output (`local/period_digest.json`) the frontend never reads. `DigestPage`
reads `local/digest.json`, which is the raw 14.

So the brief's constraint — *do not delete the underlying per-meeting test
computation, only the presentation changes* — is satisfied almost by default:
`run_meeting_digest()` keeps running, and the meeting battery keeps producing 14
claims per meeting. What changes is which of them reach a reader, and the shape
of the surface they reach them on.

### A.3 This supersedes the LLM-ranked digest, deliberately

`docs/frontend/PRODUCT_ROADMAP.md` F2 and the 2026-08-27 review of the
all-14-cards UI concluded the fix was an LLM interestingness-ranked digest. This
brief specifies a **deterministic per-test threshold** instead. That is a change
of direction, and on the evidence a good one: it is auditable, needs no LLM call
per meeting, is comparable across councils, and rides machinery that already
exists (A.1). Step 8 records the change in the roadmap so it reads as a decision
rather than as drift.

### A.4 The digest is deliberately unpublishable today

`local/digest.json` and `local/period_digest.json` land in a `local/`
subdirectory that is excluded from `manifest.json`'s `snapshots` list and from
Editor's `*.json` scope, and `tests/test_publish_gate.py` asserts that exclusion
(`test_digest_is_excluded_from_manifest_and_glob`). In Publish mode — including
the live site — `/digest` shows "snapshot not found" by design.

A public `/watch` feed cannot be built on data the publish gate forbids to
ship, so this boundary moves — see B.3, settled.

S7 already runs over digest claims — `cmd_draft` writes
`local/digest_gate_report.json` — but diagnostically, never blocking. The
machinery to gate a meeting claim exists; what B.3 adds is permission for a
gated one to ship, and a filter for the ones that cannot.

### A.5 Provenance: two fields of five are in the database

Verified against `data/council.db` and the pipeline's artifact directories, over
**506 minutes meetings**:

| Brief's field | Where it actually lives | Coverage |
|---|---|---|
| source PDF filename | `meetings.minutes_pdf_path` (DB) — also `minutes_pdf_url` | **580/580** meetings |
| extraction timestamp | `meetings.extracted_at` (DB) | **376/506** minutes meetings |
| extraction run id | `data/batch_jobs/<batch_id>.json` → `batch_id`. **Not in the DB.** | **376/506**, and **ambiguous for 320** — see below |
| model used | same files → `model`. **Not in the DB.** | same 376; one value corpus-wide (`claude-haiku-4-5-20251001`) |
| per-document validation score | `data/validation/<pdf-hash>.json` → `status` (PASS/REVIEW/FAIL) plus `coverage_ratio`, `quotes.paraphrase_rate`. **Not in the DB.** | **580/580** |

Three facts that decide how Step 3 is written:

1. **The join works.** `meetings.minutes_pdf_path` is
   `data/raw/<council>/<hash>.pdf`; `data/validation/<hash>.json` carries the
   matching `meeting_id`; `data/batch_jobs/*.json`'s `id_map` is keyed
   `<hash>__cNofM`. Spot-checked end to end on meeting 238.
2. **130 minutes meetings have no run id, model or extraction timestamp** —
   `extracted_at` is null for exactly the set absent from every batch job. They
   were extracted by some earlier, non-batch path.
3. **320 meetings appear in more than one batch job**, so "the extraction run
   id" is not a single value. A rule is needed (B.5).

**No snapshot and no API endpoint carries any of the five today.** The frontend
reads static snapshots; `api/main.py` has no provenance route. Requirement 5 is
therefore a real pipeline step, not a wiring-up.

---

## Part B — Decisions

### B.1 Reuse `score_salience()`. The exception rule is a threshold on it.

A test is an **exception** for a meeting when its claim clears that test's own
threshold. Everything else collapses into the one-line summary. Do not write a
second scoring path beside the existing one, and do not change how novelty is
computed — the two-sided percentile against a body-class baseline is the part
that is already right.

### B.2 Thresholds move into the registry, one per test, three kinds.

Add `digest_threshold` to each registry row where `meeting_scope` is true (14
rows; `null` on the other 15). One object, one of three shapes:

```json
{"kind": "any_occurrence"}                        // n >= 1 is the exception
{"kind": "percentile", "min_salience": 0.7}       // two-sided novelty vs baseline
{"kind": "ratio", "vs": "median", "min": 2.0}     // >= 2x the body-class median
{"kind": "absolute", "min": 3}                    // raw stat threshold
```

`any_occurrence` reproduces today's `digest_floor: 1.0`; `percentile` reproduces
today's global `min_salience: 0.7`. Seed from those two so the first run's
exception set is explainable, then tune per test as real meetings are reviewed —
tuning is a registry edit, not a code change, which is the point of moving it.

`digest_floor` and the global `min_salience` are then dead. Follow
`TEST_REGISTRY_PLAN.md` B.5's pattern: **do not touch generator bodies** — leave
`digest_floor=` in place, unread, and delete it in a later cleanup. `stat` stays
on the generator; it is a computed value, not a policy.

### B.3 SETTLED: `/watch` is public, and carries data when published.

Decided 2026-09-06. `/watch` is "the surface that shows the system is live", and
a page that only renders on a developer's machine is not that. `watch.json`
becomes a real snapshot: it enters `manifest.json`, `council publish` copies it
to `frontend/public/data/`, and the live site renders the feed.

That widens what ships, so it goes through the gate the project already has for
exactly this, rather than around it:

- **Per-claim tier derivation, not whole-batch.** `derive_claim_tiers()`
  (`src/invariant_gate.py`) already returns `public` | `full` per claim, reusing
  `run_invariant_gate`'s own checks via a one-claim call so the two cannot
  drift. `project_to_institutional()` gives the name-free candidate. The
  **published** `watch.json` carries public-tier claims only.
- **A dropped claim is recorded, not silently absent.** Each row carries
  `exceptions_withheld: N`. A feed that quietly omits the one exception that
  named someone would misreport the meeting as quieter than it was, and this
  project's own convention is that nulls are load-bearing.
- **Dropping, not failing.** One un-publishable claim among hundreds of meetings
  must not sink a draft. The filter removes it; the run then re-runs
  `run_invariant_gate` over what survived and **fails** if anything is left —
  a check that can only fire on a bug in the filter.

Two facts make this cheaper than it sounds. The current draft's
`local/digest_gate_report.json` is `passed: true` with **zero violations** for
its meeting, and every generator in the battery is `UNIT_INSTITUTIONAL` by
declaration, so the common case is that a meeting's claims are already
publishable. The exception to watch for is `governance.attendance`, whose
meeting claim is built from the names of genuinely-absent members — a meeting
with an absence is where the name-free text check will actually bite.

**Nobody knows yet how often that happens across 506 meetings.** Step 5 must
measure it and report the number before the feed ships; see its acceptance.

### B.4 The feed backfills the whole corpus, paginated.

`/watch` shows one row per **minutes** meeting, newest first — 506 rows for
Cambridge. Computing them is not new work: `meeting_baselines.py` already runs
`run_meeting_digest()` over every meeting to build the baseline distributions,
so the corpus-wide pass is a cost already paid once by
`council meeting-baselines`. Extend that pass rather than adding a second one.

Render the newest 50 and page from there; `config/digest_policy.json`'s existing
`display_window_months` is a display default, not a computation limit.

### B.5 Provenance is reported exactly as it is, gaps included.

The brief: *if a field is not currently persisted through to the API, say so
rather than faking it.* Per A.5:

- **Do not invent a run id** for the 130 meetings that have none. The footer
  renders `not recorded` for `run_id`, `model` and `extracted_at` on those rows,
  and the plan's Step 3 reports the exact count it found rather than the count
  in A.5 — the corpus may have moved.
- **Multiple batches per PDF (320 meetings):** record **all** batch ids for the
  document, and show the most recent by `submitted_at` as the run id with a
  count when there is more than one ("msgbatch_013dcu… +2 earlier"). A single
  arbitrary pick would misattribute which run produced the rows on screen.
- **Validation score** is the file's `status` (PASS/REVIEW/FAIL) plus
  `coverage_ratio`. Show both — `status` alone hides how thin a PASS can be
  (meeting 238 is a PASS at `coverage_ratio` 0.054).
- These are **files outside the database**, so the join belongs in the export
  step, not in a query module. Persisting them into the schema is a pipeline
  change and is **not in this plan** — Step 3 writes it down as a recommendation
  instead.

### B.6 The collapsed line states the count, because the count is the point.

Per the brief:

> 12 May 2026 — 33 items, 20 motions, nothing outside baseline. 14 tests run,
> all within norms.

The "14 tests run" clause is load-bearing: it is what distinguishes a quiet
meeting from a broken pipeline. When there **are** exceptions, the same line
still reports how many of the 14 ran and how many stayed within norms, so the
denominator never disappears.

---

## Part C — Tables

### C.1 The 14 meeting-scope tests and their seed thresholds

Seeded from today's behaviour (B.2): `any_occurrence` where the generator
declares `digest_floor=1.0`, `percentile` at `min_salience` 0.7 otherwise.

| id | seed threshold | from |
|---|---|---|
| `procurement.concentration` | `any_occurrence` | `digest_floor=1.0` |
| `procurement.decider_supplier_conflict` | `any_occurrence` | `digest_floor=1.0` |
| `conflict.recusal_management` | `any_occurrence` | `digest_floor=1.0` |
| `transparency.confidential_share` | `any_occurrence` | `digest_floor=1.0` |
| `transparency.confidential_tender_size` | `any_occurrence` | `digest_floor=1.0` |
| `transparency.confidential_topics` | `any_occurrence` | `digest_floor=1.0` |
| `engagement.deputation_dissent` | `any_occurrence` | `digest_floor` conditional on a deputation |
| `governance.attendance` | `any_occurrence` | `digest_floor` conditional on a genuine absence |
| `planning.big_dollar_leniency` | `percentile` 0.7 | global default |
| `planning.objection_responsiveness` | `percentile` 0.7 | global default |
| `governance.officer_ratification` | `percentile` 0.7 | global default |
| `governance.unanimity_trend` | `percentile` 0.7 | global default |
| `engagement.participation` | `percentile` 0.7 | global default |
| `engagement.question_responsiveness` | `percentile` 0.7 | global default |

Two of these deserve review once real meetings have been read: the brief singles
out "a declared conflict where the member stayed and voted" as an
any-occurrence case, but `conflict.recusal_management`'s meeting claim counts
**declarations**, not stay-and-vote events. If the intended exception is the
narrower one, that is a change to what the generator reports, not to the
threshold — flag it in Step 2 and leave the generator alone.

### C.2 The `watch.json` record shape

One object per minutes meeting:

```
meeting_id, meeting_date, meeting_type, body_class
counts:      { items, motions, other_items }        // from meeting_inventory()
tests:       { run, exceptions, within_baseline }   // run is always 14 today
exceptions:  [ { test_id, finding, verdict, valence, severity,
                 stat, baseline_median, threshold_kind, why } ]
provenance:  { pdf_filename, pdf_url, extracted_at, run_id, run_id_count,
               model, validation_status, coverage_ratio }
```

`why` is a short scripted phrase naming which threshold fired and by how much
("2 tenders awarded; body-class median 0", "novelty 0.94 vs 0.70 threshold") —
scripted, never authored, and never a claim about anyone.

Any provenance field with no value is `null` and renders as `not recorded`
(B.5). No field is omitted from the object — an absent key and a recorded
absence read the same in JSON and must not.

---

## Part D — The steps

Eight steps. 1–4 are pipeline; 5 is publishing; 6–7 are frontend; 8 is docs.

Every step ends with `pytest -q` from the repo root where it touches Python, and
`npm run lint && npm run build` from `frontend/` where it touches the frontend.

**Standing context for every step.** Read `docs/MAP.md`,
`docs/frontend/TEST_REGISTRY_PLAN.md` Parts B–C,
`docs/frontend/PRODUCT_ROADMAP.md` F2, and `docs/frontend/INTERACTIVITY.md`'s
hard rule.

**Two constraints govern every step:**
- *Do not delete the underlying per-meeting test computation.*
  `run_meeting_digest()` and all 14 generators keep running and keep producing
  what they produce. Only the presentation and the selection change.
- *Do not fake provenance.* A field with no recorded value is `null` and says
  `not recorded`. If a step finds that a field is less available than Part A
  says, report the real numbers rather than working around them.

**One commit per step**, committed once its acceptance checks pass; if they
fail, do not commit — report. Subject names the plan and step number, body at
most a couple of sentences. `docs/TESTING.md` "Commit conventions" applies:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — `digest_threshold` in the registry

1. Extend `TestRegistryEntry` (`frontend/src/registry/types.ts`) and the loader
   (`src/test_registry.py`) with `digest_threshold`, the tagged union in B.2 —
   `null` for the 15 rows where `meeting_scope` is false.
2. Seed `config/test_registry.json` from Part C.1.
3. Extend `tests/test_test_registry.py`: `digest_threshold` is non-null exactly
   when `meeting_scope` is true; every object matches one of the four kinds;
   `percentile.min_salience` is in [0, 1]; `ratio.min` and `absolute.min` are
   positive.

Nothing reads it yet. Acceptance: 14 non-null / 15 null; suite green.

---

### Step 2 — The exception rule reads the registry

In `src/analysis/digest.py`, add `deviates(claim, baselines, body_class, entry)`
returning a small result — `{is_exception, why, threshold_kind, baseline_median}`
— implementing the four kinds against the existing baseline distributions.
`percentile` delegates to the existing `_two_sided_percentile`; keep
`score_salience()` for `compose_period_digest()`'s ranking, which is a separate
consumer and is not part of this brief.

Thin-baseline behaviour is unchanged: below `min_baseline_meetings`, a
`percentile` test cannot fire, and only `any_occurrence` / `absolute` can.

Leave every generator body alone (B.2), including the now-unread `digest_floor=`
arguments.

Report, from the current corpus: how many of the 506 minutes meetings produce
zero exceptions, and the distribution of exception counts. If nearly every
meeting has one, or nearly none does, the seed thresholds are wrong — say so
with the numbers rather than adjusting them silently.

Acceptance: unit tests for each of the four kinds, including the thin-baseline
case; the distribution reported.

---

### Step 3 — The provenance join

New `src/provenance.py`: `meeting_provenance(session, meeting_ids)` returning
Part C.2's `provenance` object per meeting, joining `meetings.minutes_pdf_path`
→ `data/validation/<hash>.json` → `data/batch_jobs/*.json` per A.5, with B.5's
multi-batch rule.

**Verify the coverage yourself and report the real numbers** — A.5 says 376 of
506 minutes meetings have a run id and 320 documents appear in more than one
batch, measured 2026-09-06. Report what you find. If a field is less available
than that, say so; do not widen the join to make it look complete.

End the step's summary with one short recommendation on whether run id, model
and validation status belong in the schema rather than in loose files — with
reasons, not a proposal to build it. That is a pipeline change and is not in
this plan.

Acceptance: unit tests over a fixture directory covering a meeting with full
provenance, one with no batch record, and one appearing in two batches;
coverage numbers reported.

---

### Step 4 — `watch.json`

Per B.3, `watch.json` is a published snapshot — it is written to the draft
root alongside `scorecard.json`, **not** to `local/`.

Extend the corpus-wide pass in `src/analysis/meeting_baselines.py` — which
already runs `run_meeting_digest()` over every meeting — to emit Part C.2's
record per minutes meeting, and add `council watch <council>` to write
`watch.json`. `cmd_draft` calls it, alongside the existing digest artifacts.

Write **two** views, as `compose_period_digest()` already does per candidate:
the full record, and the public projection B.3 requires. Step 5 decides which
one the snapshot file carries; this step produces both and keeps them
distinguishable.

Keep writing `local/digest.json` unchanged. The old artifact stays until Step 6
stops reading it, so the two surfaces can be compared against the same run.

Acceptance: `watch.json` for the current corpus; row count equals the minutes
meeting count; spot-check three meetings against `council meeting-digest` output
for the same meeting and confirm the exception set matches what Step 2 scores.

---

### Step 5 — Publishing `watch.json` through the gate

The step B.3 commits to. Do the measurement first — it may change what the rest
of the step has to handle.

**Measure before building.** Run the per-claim tier derivation over every
minutes meeting and report: how many claims are `public`, how many `full`, how
many meetings lose at least one exception to the filter, and which `test_id`s
account for the drops. If a large share of the feed is being withheld, that is a
finding to report before wiring anything up — a feed that withholds most of its
content is not the surface the brief asked for, and the fix would be upstream in
the generators, not here.

Then:

1. `watch.json` joins `manifest.snapshots` and `file_hashes` so `council
   publish` copies it. Add it to `CLAIM_DERIVED_SNAPSHOTS` in `src/cli.py`
   alongside `scorecard`, or give it its own per-claim path — it is claim-derived
   but, unlike the scorecard, is filtered per claim rather than tiered as a
   batch. Say which you chose and why.
2. Apply B.3's filter: published rows carry public-tier claims only, each row
   carries `exceptions_withheld`, and `run_invariant_gate` re-runs over the
   surviving claims and fails the run if anything is left.
3. Rewrite `tests/test_publish_gate.py`'s
   `test_digest_is_excluded_from_manifest_and_glob` to assert the **new**
   boundary: `digest.json` and `period_digest.json` stay in `local/` and out of
   the manifest; `watch.json` is expected in it. Do not weaken the test to
   accommodate the change — it should still fail if `digest` leaks.
4. Add a placeholder `frontend/public/data/watch.json` in the same shape as the
   other placeholder snapshots, so a build before the first real publish renders
   an empty feed rather than an error.

**Editor's scope.** `docs/review/editor/Editor_prompt.txt` reviews the draft
directory's non-recursive `*.json`, so a root-level `watch.json` enters its scope
automatically. Measure the file size first: 506 meetings of exceptions plus
provenance may be far past what a review pass can hold. If it is, give Editor a
bounded slice — the newest N meetings — and write the rationale and the bound
into the prompt, with the rest covered by the scripted per-claim gate. **Do not
leave a silently-truncated review**: whatever Editor sees, the prompt must say
what it is and what covers the remainder.

Acceptance: the measurement above, reported with real numbers; the gate test
passes and asserts both directions of the new boundary; a `council draft` run
produces a `watch.json` whose surviving claims clear `run_invariant_gate`; the
Editor scope decision stated with the file size that drove it.

### Step 6 — `/watch`

New `frontend/src/pages/WatchPage.tsx`: chronological feed, newest first, one
row per meeting.

- **Collapsed row** — B.6's line: date, item and motion counts, then either
  "nothing outside baseline · 14 tests run, all within norms" or "N outside
  baseline · 14 tests run".
- **Expanded** — the exception cards, rendered through the existing
  `BatteryTestCard` (the wrapped variant `SURFACE_PROJECTION_PLAN.md` Step 3
  kept for exactly this), each with its `why` line; then the run-metadata
  footer from `provenance`, with `not recorded` wherever a field is null.
- Newest 50, paged (B.4).

Route `/watch` in `App.tsx`, add it to `SiteNav`, and replace `/digest` with
`<Navigate to="/watch" replace />`. Delete `DigestPage.tsx` and the `digest`
entry in `api.ts` only once nothing imports them.

The named-individual guardrail applies here as everywhere: every rendered
`finding` goes through `RedactedText`.

`watch` is a published snapshot (B.3), so `api.ts` reads it through the normal
`getSnapshot("watch")` path — it renders in both Draft and Publish mode, unlike
the old digest.

Acceptance: build + lint; `/watch` lists the corpus newest-first in both modes,
rows expand, `/digest` redirects. Report how many of the visible rows have
exceptions and how many are quiet — a feed that is all-exceptions or
all-quiet means Step 2's thresholds need review, and that is a finding to
report, not to fix here.

---

### Step 7 — The latest-meeting strip

On `OverviewPage`, above the overview panel: date, item and motion counts,
exception count, and a link through to that meeting's row in the feed —
`#/watch?meeting=<id>`, resolved through the anchors module
(`SURFACE_PROJECTION_PLAN.md` B.2) rather than a hand-written href, with
`WatchPage` scrolling to and expanding the named row.

Reads the first record of `watch.json`, which is published (B.3), so the strip
carries real data on the live site. Should the snapshot be missing — a build
before the first publish — the strip renders nothing at all rather than an error
card: it is a strip, not a panel, and a fault there would deface the home page.

Acceptance: build + lint; the strip's numbers match the feed's top row exactly.

---

### Step 8 — Documentation

- `docs/frontend/PRODUCT_ROADMAP.md` — F2 is superseded: the digest is an
  exception report driven by per-test registry thresholds, not an LLM
  interestingness ranking (A.3). Record why, so the change reads as a decision.
- `docs/frontend/TEST_REGISTRY_PLAN.md` — `digest_threshold` joins the registry's
  field list; `digest_floor` in `tests.py` is now unread and awaiting cleanup.
- `docs/TESTING.md` — the moved draft/publish boundary: `watch.json` publishes,
  `digest.json` and `period_digest.json` stay local; the rewritten gate test; the
  per-claim filter and what `exceptions_withheld` means to a reader.
- `docs/review/editor/Editor_prompt.txt` and `docs/review/REVIEW.md` — whatever
  Step 5 settled about Editor's view of `watch.json`.
- `docs/INFORMATION_ARCHITECTURE.md` — meeting claims now reach a published
  surface through per-claim tier derivation; note it against §4, which describes
  the whole-batch rule.
- `docs/MAP.md` — a "Where do I add X?" row: *tuning what counts as an exception
  for a meeting* → `config/test_registry.json`'s `digest_threshold`, not code.
- `docs/pipeline/PIPELINE.md` — Step 3's provenance finding: which fields are in
  the schema, which are in loose files, and the recommendation.
- Mark this file's status **built**, and record the public/full split Step 5
  measured — it is the number that says how much of the feed a reader sees.

---

### Deliberately not in this plan

Persisting run id / model / validation status into the schema (B.5 — Step 3
recommends, does not build) · building an institutional reduction for any claim
that currently has none. **Correction, 2026-09-07:** the parenthetical this
line originally carried here — "`INSTITUTIONAL_PROJECTIONS` is empty; a
`full`-tier claim is withheld, not reduced" — was wrong when this plan was
written: `INSTITUTIONAL_PROJECTIONS` (`src/invariant_gate.py`) already had
three registered reducers (`conflict.recusal_management`,
`governance.attendance`, `procurement.decider_supplier_conflict`), built
earlier in the S7/tier-derivation redesign and confirmed live on the real
corpus by Step 8 — a claim on one of those three degrades to its name-free
form instead of being withheld. What's still genuinely not in this plan is
building a *new* reduction for a test that has none today · S9 reply packets
for a meeting claim that names someone · deleting `digest_floor` from the 8
generators (B.2) · the LLM-ranked digest F2 described (A.3) · changing how
novelty is computed (B.1) · any change to what the 14 generators measure —
including `conflict.recusal_management`'s declaration-vs-stay-and-vote question
(C.1), which is flagged for a decision, not fixed here.
