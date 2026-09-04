# Canonical Test Registry — findings + build plan

Status: **Phase 1 and 2 built** (Steps 1–11, 2026-09-04). Written 2026-09-04.
Audience: the person handing Part E's steps, one at a time, to a fresh model
instance. Parts A–D are the context every step assumes — kept as the record
of the pre-registry state, not updated to describe the current one.
Phase 2 turned out to be one panel, not four — see A.5's 2026-09-04
correction. Phase 3 (Step 12, now five panels) is still outstanding.

---

## Part A — What exists today

### A.1 There is already one battery. There is not already one registry.

"Three separately authored surfaces" is half true. The **test set** is authored
once, in Python:

- `src/analysis/tests.py` — `_BATTERY`, 29 generator functions, each returning a
  `TestResult` dataclass. `_MEETING_BATTERY`, 14 of those same functions, which
  additionally take `meeting_id=` and return a one-meeting recount.
- `src/cli.py` `_generate_snapshots()` writes `scorecard.json`
  (`{summary, tests: [TestResult…]}`); `cmd_draft` writes `local/digest.json`
  (same shape plus `meeting_id`/`meeting_date`).
- All three frontend surfaces read one of those two files. None authors a test
  list of its own.

So the three surfaces are **three renderings of one array**. What has drifted is
the *copy* and the *grouping*.

### A.2 The three surfaces

| Surface | File | Reads | Grouping | Per-test rendering |
|---|---|---|---|---|
| Scorecard | `components/ScorecardPanel.tsx` (147 ln) | `api.scorecard()` | `groupTestsByGenre` | inline `TestRow` |
| Analysis | `pages/AnalysisPage.tsx` (61 ln) | `api.scorecard()` | `groupTestsByGenre` | `BESPOKE_PANELS[test_id]` else `BatteryTestPanel` |
| Digest | `pages/DigestPage.tsx` (72 ln) | `api.digest()` | `groupTestsByGenre` | `BatteryTestCard` |

`BatteryTestPanel.tsx` exports `BatteryTestCard` (pure, takes a resolved test)
and `BatteryTestPanel` (fetches, finds by id, delegates). `bespokePanels.tsx` is
a 12-entry `Record<test_id, ComponentType>`.

### A.3 Where copy and structure actually drift

1. **All 12 bespoke panels hardcode heading, subtitle and valence.**

   | test_id | scorecard `title` (data) | bespoke panel `title` (JSX literal) |
   |---|---|---|
   | `conflict.recusal_management` | Do councillors step out when they declare a conflict? | Declaring a Conflict — Do Councillors Step Out, or Vote Anyway? |
   | `procurement.concentration` | Where did the tender money go? | Where Cambridge's Tender Money Went |
   | `governance.power_spread` | Does consensus hide a power hierarchy? | Who Wins — Power on a Split Council |
   | `engagement.question_responsiveness` | Are residents' questions answered, or quietly 'taken on notice'? | Answered in the Room — or Quietly Taken on Notice? |
   | `engagement.participation` | How much does the public take part? | Public Engagement by Year |

   Worse than wording: `valence="critical"` is a **literal** in those panels
   while the battery *computes* valence per run. A run that flips a test to
   neutral leaves the panel red. Several subtitles also restate `era` as a
   constant.

2. **Meeting-scoped titles are a third copy**, authored inside `tests.py`'s
   meeting branch ("Did anyone declare a conflict this meeting?").

3. **Categories are inferred by regex over free-text `genre`** (12 distinct
   strings across 29 tests). The "Planning & fairness" bucket matches **zero**
   tests — first-match-wins routes `planning.repeat_applicant` (genre
   "Integrity / fairness") to Integrity and `planning.big_dollar_leniency`
   ("Governance / fairness") to Governance. A dead branch.

4. **Three id namespaces**: `test_id`, `detail_panel` slug, snapshot filename.
   Anchors are built from the slug (`#panel-declared`, `id="sc-declared"`).

### A.4 Spec fields — where each stands today

| Spec field | Today |
|---|---|
| `id` | exists as `test_id`, **load-bearing** — see B.1 |
| `category` | does not exist; inferred by regex from `genre` |
| `question_technical` | exists as `question` |
| `question_public` | **does not exist** |
| `title_technical` | exists as `title` — several state the conclusion, not the measure |
| `title_public` | **does not exist** |
| `finding` | exists as `headline` — **computed per run** |
| `valence` | exists — **computed per run** |
| `severity` | exists as `grade` — **computed per run** |
| `principles` | exists as `principle`, one prose string — not an array |
| `n`, `scope`, `era` | exist — **computed per run** |
| `method` | **does not exist** |
| `caveats` | **does not exist** (fragments leak into `era`: "· DIRECTIONAL (n<30)") |
| `objection` / `response` | **do not exist** |
| `evidence_query` | **does not exist**; derivable — see Part D |
| `has_deep_dive` | implicit in `BESPOKE_PANELS` keys |
| `public_interest` | **does not exist** |
| `meeting_scope` | exists twice: `_MEETING_BATTERY`, and `scope` on each result |

### A.5 Panels with no battery test

Not scorecard rows and not analysis panels, so nothing blocks Phase 1. **Kept,
not deleted** — re-wired in Phases 2 and 3 (Part E).

Rendered on no route today, because they lost their home when `HomePage.tsx`
was replaced by the Overview/Analysis split. All 8 already have published
snapshots and `queries.py` functions behind them — the export work is done,
they are missing a route and a registry row:

| Component | Snapshot | Query | Phase |
|---|---|---|---|
| `TrendsChart` (`ContestationChart`) | `trends.json` | `contestation_by_year` | 2 — **done** (Step 11) |
| `PlanningTrendChart` | `planning.json` | `planning_trend_by_year` | retired, not Phase 2 — see below |
| `PlanningObjectionsPanel` | `planning.json` | `planning_objection_stats` | retired, not Phase 2 — see below |
| `InterestsChart` (the chart export only) | `interests.json` | `interest_declarations_summary` | **3**, corrected 2026-09-04 — see below |
| `DissentProfilesChart` | `dissent.json` | `dissent_profiles` | 3 |
| `DissentCoalitionsPanel` | `dissent.json` | `dissent_coalition_pairs` | 3 |
| `AlignmentHeatmap` | `alignment.json` | `voting_alignment_matrix` | 3 |
| `CoMoverGraph` | `co-movers.json` | `co_mover_pairs` | 3 |

**2026-09-04, executing Step 11 — three corrections to the table above,**
found by actually reading `INVESTIGATIONS.md`'s 2026-06-26 panel-consolidation
entry and the component source, not by re-reading this plan harder:

- `TrendsChart` — as planned. Wired to `governance.unanimity_trend`; numbers
  checked against the scorecard row across all 31 overlapping years in real
  data, exact agreement. Done.
- `PlanningObjectionsPanel` and `PlanningTrendChart` are **not** "no existing
  test covers these" — `INVESTIGATIONS.md` already retired both, with reasons:
  `PlanningObjectionsPanel` is a coarser binary (with/without objection)
  duplicate of `planning.objection_responsiveness`'s dose-response bucketing
  (confirmed by reading both components); `PlanningTrendChart` was looked at
  and rejected on the merits ("approval-rate trend isn't a quality
  criterion"). Neither is Phase 2 work. Codifying a new test for either now
  would mean overriding a documented prior investigative judgment, not
  filling a gap — out of scope unless a human deliberately reopens that
  question.
- `InterestsChart` **moves to Phase 3.** It renders a per-councillor bar
  chart with the councillor's name on the axis (folded only below a small-N
  floor within each interest-type category, same pattern as
  `ConflictRecusalPanel` — the name itself is never hidden). That's
  `individual_implicating`, the exact thing the "four Phase 3 panels...
  chart and name individual councillors" line below was already describing;
  the original table just put it in the wrong column. Phase 3 is five
  panels, not four. `config/test_registry.json` can't record "known
  individual-implicating candidate, not yet built" as a row with the
  frontend routing suppressed — Step 4's parity test enforces a strict 1:1
  between registry rows and real `_GENERATORS` entries, so a row only exists
  once a real, computed test does. This table is where that classification
  lives instead.

Two things make the split above non-negotiable:

- `TrendsChart`'s contestation-by-year measure **is** `governance.unanimity_trend`
  ("what share of carried motions drew at least one dissenting vote, over
  time") — a test that has no bespoke panel today. That one needs no new test at
  all, only a `BESPOKE_PANELS` entry.
- The five Phase 3 panels **chart and name individual councillors**. Every test
  in the battery today is `UNIT_INSTITUTIONAL` — `tests.py` says so explicitly
  and `src/invariant_gate.py` enforces it at S7. Giving them registry rows means
  the system's first `individual_implicating` claims, which pulls in tier
  derivation, `entity_resolution`, and possibly S9 reply packets. That is its
  own phase, not a routing change.

Out of scope entirely: `OverviewPanel` (a corpus synthesis, not a test),
`CouncillorModal`, `MapPage`, About/Contact/Evidence.

**`pages/HomePage.tsx` is deleted** in Phase 1 — dead (never imported by
`App.tsx`), and its hand-maintained panel order is precisely what the registry
replaces.

---

## Part B — Decisions (settled 2026-09-04)

### B.1 `test_id` stays the primary key. No renumbering to `INT-CONF-01`.

It is the join key in `docs/investigator/coverage_register.json` (CI-verified by
`verify_register()` / `tests/test_coverage_register.py`), the key of
`BESPOKE_PANELS`, the cross-council comparability contract in `tests.py`'s
module docstring, and is referenced by the invariant gate, editor scoring and
`INVESTIGATIONS.md`. `id` in the registry **is** the dotted `test_id`. An
optional non-key `code: "INT-CONF-01"` may be added for display/citation.

### B.2 The registry is the static layer. Results stay computed.

`finding`, `valence`, `severity`, `n`, `era` change every run and every council;
baking them into source would freeze one council's answers into the frontend and
break the comparability the battery exists for.

- **`config/test_registry.json`** — authored once, council-agnostic: `id`,
  `code?`, `order`, `category`, `question_technical`, `question_public`,
  `title_technical`, `title_public`, `principles[]`, `method`, `caveats[]`,
  `objection`, `response`, `evidence_query`, `evidence_snapshot`,
  `has_deep_dive`, `public_interest`, `meeting_scope`, `detail_panel`.
- **`scorecard.json` / `digest.json`** — unchanged: `finding` (`headline`),
  `verdict`, `valence`, `severity` (`grade`), `n`, `base_rate`, `era`, `scope`,
  `data_ok`, `chart`, `series`.
- **`resolveTests(registry, snapshot)` → `ResolvedTest[]`**, joined on `id`.
  Every surface consumes `ResolvedTest[]` and nothing else. The spec's single
  row is `ResolvedTest` — it is just not a single *file*.

Read the acceptance criterion as: **the scorecard's structure, order, grouping
and copy come entirely from the registry; the numbers are joined in from the
snapshot and are not touched.**

### B.3 DECISION 1 — the registry owns the list of tests. `_BATTERY` is deleted.

`_BATTERY` (which 29 tests run, in what order) and `_MEETING_BATTERY` (which 14
are meeting-scoped) are deleted. `tests.py` keeps a lookup with no opinion about
membership or order:

```python
_GENERATORS = {"procurement.threshold_gaming": _t_threshold_gaming, ...}
```

`run_test_battery` walks the registry's rows in `order` and looks each `id` up;
`run_meeting_digest` walks the rows where `meeting_scope` is true. One list,
stated once, in the file a human reads.

Consequences, and they are the whole cost:
- **The file lives at `config/test_registry.json`** (beside
  `agent_switches.json`, which `src/agent_config.py` already loads the same
  way), not inside `frontend/`, because Python reads it too. The frontend
  imports it through a Vite alias.
- **The battery must refuse to run** if a registry row names an id with no
  generator, or a generator has no row — never quietly produce 28 tests.

### B.4 DECISION 2 — the registry defines `has_deep_dive`.

`registry.json` carries `has_deep_dive`; `bespokePanels.tsx` is demoted to a
lookup ("the registry says this test has a deep dive — find its component").
Reading the registry tells you which tests have deep dives. Step 4's test
asserts agreement **in both directions**: `true` with no component is an error,
and a component whose row says `false` is an error.

### B.5 The registry authors the rendered copy — including for the S7 gate.

**This one is a safety property, not a preference.** `src/invariant_gate.py`
scans six rendered strings of every claim for councillor names — `c.title`,
`c.headline`, `c.verdict`, `c.question`, `c.base_rate`, `c.era`. If the frontend
starts rendering `registry.title_technical` while the gate keeps scanning a
`TestResult.title` set inside `tests.py`, **the gate is checking text that is no
longer displayed.** That is a hole, not a tidiness issue.

The fix keeps the gate working unchanged and makes the registry provably
authoritative: **generator bodies are not touched at all.** `run_test_battery`
overwrites `title` and `question` on each result from the registry row *after*
calling the generator:

```python
r = _GENERATORS[row["id"]](session, council_id, pc)
r.title = row["title_technical"]
r.question = row["question_technical"]
```

Because Part D seeds those two fields verbatim from the current run, the
regenerated `scorecard.json` is byte-identical — which is the verification for
the whole Python change. Change the registry and the rendered title changes on
every surface *and* in what the gate scans. `genre` and `principle` stay as the
generators set them, unread by the new frontend; stripping the now-redundant
kwargs from the 57 `TestResult` constructions is deferred cleanup, not this work.

`run_meeting_digest` does **not** overwrite: the meeting-scoped titles have no
registry field yet (Step 10), so those keep the generator's phrasing.

### B.6 Two enums must be wider than the brief.

- **`severity`** — `tests.py` defines seven grades; five appear in the current
  run. Type all seven, including the unused `Commendable` and `Integrity flag`,
  or a future run becomes a type error at the worst moment.
- **`valence`** — the brief lists `not_computable` as a fourth valence. In the
  data it is not: `data_ok: false` rows carry `valence: "neutral"` and
  `grade: "Not computable on this corpus"`, and the summary counts them
  separately. Keep valence at three and derive "not computable" from `data_ok`,
  or the summary counts change and the page stops looking the same.
- **`category`** — the brief's four map exactly onto the four non-empty
  rendered groups. Dropping the empty "Planning & fairness" bucket changes
  nothing on screen.

### B.7 `evidence_query` — two fields, because two things are being asked for

"The query that produces the underlying rows" is a `queries.py` function for 14
tests and inline ORM code inside `tests.py` for the other 15. What the frontend
can actually fetch is a snapshot.

- `evidence_query` — the `queries.py` function name, or `"tests.<generator>"`
  where the test computes inline. Auditor-facing; never invented.
- `evidence_snapshot` — the `api.ts` snapshot key backing the deep dive, or
  `null`.

### B.8 `objection` / `response` ship empty.

Typed `string | null`, seeded `null`, rendered nowhere yet — a separate pass
fills them. Step 4's test must **not** require them non-empty, or that pass
can't land incrementally.

---

## Part C — How it fits together

```
                    config/test_registry.json
                     (29 rows — the one file you read
                      to see every test the system runs)
                              │
              ┌───────────────┴───────────────────┐
              │                                   │
         BUILD TIME                          RENDER TIME
      (`council draft`)                        (browser)
              │                                   │
              ▼                                   │
   run_test_battery walks the rows in `order`,    │
   looks each id up in _GENERATORS, runs it,      │
   then overwrites title/question from the row    │
              │                                   │
              ▼                                   ▼
      scorecard.json  ───────────────►  resolveTests(registry, snapshot)
      digest.json        (numbers)       joined on `id`
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                                Scorecard     Analysis       Digest
                                                  │
                                                  └─► BESPOKE_PANELS[id]
                                                      or BatteryTestPanel
```

One registry row plus one snapshot row makes one `ResolvedTest`. Run the battery
on a second council and the registry half is byte-identical; only the snapshot
half changes.

---

## Part D — The 29-row seed table

Verbatim from `data/draft/cambridge/draft_20260904_082327/`. `category` is what
`groupTestsByGenre` produces **today**, so seeding from this column preserves the
rendered page exactly. `deep` = has a `BESPOKE_PANELS` entry. `mtg` = in
`_MEETING_BATTERY`.

| # | id | category | detail_panel | deep | mtg | evidence_query | evidence_snapshot |
|---|---|---|---|---|---|---|---|
| 1 | `procurement.threshold_gaming` | integrity_procurement | threshold-gaming | – | – | `tests._t_threshold_gaming` | null |
| 2 | `procurement.incumbency` | integrity_procurement | incumbency | – | – | `tests._t_procurement_incumbency` | null |
| 3 | `procurement.single_source` | integrity_procurement | single-source | – | – | `tests._t_single_source` | null |
| 4 | `procurement.concentration` | integrity_procurement | tenders | ✓ | ✓ | `tender_concentration` | tenders |
| 5 | `procurement.decider_supplier_conflict` | integrity_procurement | decider-supplier | – | ✓ | `decider_supplier_conflict` | null |
| 6 | `conflict.recusal_management` | integrity_procurement | declared | ✓ | ✓ | `conflict_recusal_stats` | declared |
| 7 | `conflict.recusal_trend` | integrity_procurement | recusal | ✓ | – | `recusal_compliance_trend` | recusal |
| 8 | `conflict.delegate_body_conflict` | integrity_procurement | delegate-body-conflict | – | – | `delegate_body_conflict` | null |
| 9 | `planning.repeat_applicant` | integrity_procurement | repeat-applicant | – | – | `tests._t_repeat_applicant` | null |
| 10 | `planning.big_dollar_leniency` | governance_culture | big-dollar | – | ✓ | `tests._t_big_dollar_leniency` | null |
| 11 | `governance.officer_ratification` | governance_culture | divergence | ✓ | ✓ | `officer_divergence` | divergence |
| 12 | `governance.power_spread` | governance_culture | power | ✓ | – | `voting_power` | power |
| 13 | `governance.oversight_body_capture` | governance_culture | oversight-body-capture | – | – | `oversight_body_capture` | null |
| 14 | `governance.unanimity_trend` | governance_culture | unanimity | – | ✓ | `tests._t_unanimity_trend` | trends *(Phase 2)* |
| 15 | `governance.chair_capture` | governance_culture | mayoral | ✓ | – | `mayoral_agenda_setting` | mayoral |
| 16 | `governance.durable_faction` | governance_culture | sponsorship | ✓ | – | `sponsorship_network` | sponsorship |
| 17 | `governance.incumbency` | governance_culture | tenure | ✓ | – | `councillor_tenure` | tenure |
| 18 | `governance.freshman_effect` | governance_culture | freshman | – | – | `tests._t_freshman` | null |
| 19 | `governance.election_cycle` | governance_culture | election-cycle | – | – | `tests._t_election_cycle` | null |
| 20 | `governance.attendance` | governance_culture | attendance | – | ✓ | `tests._t_attendance` | null |
| 21 | `planning.objection_responsiveness` | transparency_engagement | dose | ✓ | ✓ | `objection_dose_response` | dose |
| 22 | `transparency.confidential_share` | transparency_engagement | transparency | ✓ | ✓ | `transparency_by_year` | transparency |
| 23 | `transparency.confidential_tender_size` | transparency_engagement | confidential-tender-size | – | ✓ | `tests._t_confidential_tender_size` | null |
| 24 | `transparency.confidential_topics` | transparency_engagement | confidential-topics | – | ✓ | `tests._t_confidential_topics` | null |
| 25 | `engagement.participation` | transparency_engagement | engagement | ✓ | ✓ | `public_engagement_by_year` | engagement |
| 26 | `engagement.deputation_dissent` | transparency_engagement | deputations | – | ✓ | `tests._t_deputation_dissent` | null |
| 27 | `engagement.question_responsiveness` | transparency_engagement | question-responsiveness | ✓ | ✓ | `public_question_responsiveness` | question-responsiveness |
| 28 | `finance.eoy_spending` | financial | eoy | – | – | `tests._t_eoy_spending` | null |
| 29 | `finance.reserve_trajectory` | financial | reserve | – | – | `tests._t_reserve_trajectory` | null |

Counts to assert: **29 rows · 12 deep · 14 mtg · 9/11/7/2 by category.**

Category order and labels (unchanged from today):
`integrity_procurement` → "Integrity & procurement" ·
`governance_culture` → "Governance & culture" ·
`transparency_engagement` → "Transparency & engagement" ·
`financial` → "Financial".
Within a category: critical → neutral → supportive (today's `VALENCE_ORDER`),
then by `order`.

---

## Part E — The steps

**Phase 1** (Steps 1–10) — the registry and the 29 existing tests.
**Phase 2** (Step 11) — re-wire the four institutional orphans.
**Phase 3** (Step 12) — the four individual-implicating orphans, through the
invariant gate.

Hand them over one at a time. Every step ends with `npm run lint && npm run
build` from `frontend/`; steps touching Python also need `pytest -q` from the
repo root.

**Standing context for every step.** Read `docs/MAP.md`, then
`docs/frontend/INTERACTIVITY.md`'s **hard rule** — no `.tsx` file may contain a
literal councillor name, a specific stat, or a narrative claim about a named
individual as a string constant. The registry is data, not a component, and it
is council-agnostic: **no council name, no number, no finding text belongs in
`config/test_registry.json` either.** `method`, `caveats` and `objection`
describe the *measure*, never this corpus's answer.

**One commit per step.** A step whose acceptance checks pass is committed before
the next step starts — nothing bundled across steps, nothing left uncommitted
between them, so any step can be reviewed or reverted on its own. If a step's
acceptance check fails, do not commit: report instead.

Keep the message to a subject line plus at most a couple of sentences. Name the
plan and the step number in the subject:

```
Test registry step 3: read the battery list from config/test_registry.json

Deletes _BATTERY/_MEETING_BATTERY in favour of _GENERATORS plus the registry's
own order, and repoints coverage_register.py's two extractors at the registry.
scorecard.json regenerates byte-identical to draft_20260904_082327.
```

That is deliberately terser than this repo's usual commit style, because this
file carries the reasoning each message would otherwise have to spell out — a
reader who wants the why has one place to go. The rule from `docs/TESTING.md`
"Commit conventions" that applies in full to every one of these commits:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — Types and scaffolding (no behaviour change)

Create `frontend/src/registry/types.ts`:

- `TestCategory = "integrity_procurement" | "governance_culture" | "transparency_engagement" | "financial"`
- `Valence` — re-export from `api.ts`; do **not** add a fourth member (B.6)
- `Severity` — all seven `G_*` strings from `src/analysis/tests.py`, verbatim:
  `"Sound practice" | "Good-governance strength" | "Commendable" | "Observation" | "Governance concern" | "Integrity flag" | "Not computable on this corpus"`
- `interface TestRegistryEntry` — exactly B.2's static fields
- `interface ResolvedTest extends TestRegistryEntry` — plus `finding`, `verdict`,
  `valence`, `severity`, `data_ok`, `n`, `base_rate`, `era`, `scope`, `chart`,
  `series` (types copied from `ScorecardTest` in `api.ts`)
- `CATEGORY_ORDER: TestCategory[]` and `CATEGORY_LABEL: Record<TestCategory, string>`
  with Part D's four labels in that order

Wire the shared file so both sides can reach `config/test_registry.json`:
- `frontend/tsconfig.app.json`: add `"resolveJsonModule": true`
- `frontend/vite.config.ts`: alias (e.g. `@registry` →
  `resolve(__dirname, '../config/test_registry.json')`) and, if the dev server
  refuses to serve outside its root, `server.fs.allow: ['..']`. If that proves
  troublesome, fall back to a prebuild copy into `frontend/src/registry/` — but
  try the alias first; a copy step adds a way for the two to diverge.

Do not touch any component. Acceptance: `npm run build` passes; nothing imports
the new file yet.

---

### Step 2 — Seed `config/test_registry.json`

Write a **one-off** seeder, `scripts/seed_test_registry.py`, whose docstring says
plainly that it is a one-time scaffold, is not part of any pipeline, and must
never be re-run over a hand-edited registry.

It reads the newest `data/draft/cambridge/draft_*/scorecard.json`,
`src/analysis/tests.py` (`_BATTERY`, `_MEETING_BATTERY` — still present at this
step) and `frontend/src/bespokePanels.tsx`, and writes
`config/test_registry.json`: a JSON array, one object per test, in `_BATTERY`
order, matching Part D exactly.

- `id` ← `test_id` · `order` ← 1-based `_BATTERY` index
- `category` ← Part D's column (deriving it via today's genre regex is fine; the
  committed output must equal Part D)
- `question_technical` ← `question`, **verbatim** · `title_technical` ← `title`,
  **verbatim** (Step 3's byte-identical check depends on this)
- `principles` ← `principle` split on `·`, each trimmed, parentheticals kept on
  their fragment
- `detail_panel` ← `detail_panel` · `has_deep_dive` ← id ∈ `BESPOKE_PANELS` ·
  `meeting_scope` ← id ∈ `_MEETING_BATTERY`
- `evidence_query` / `evidence_snapshot` ← Part D
- `question_public`, `title_public`, `method` ← `""` · `caveats` ← `[]` ·
  `objection`, `response` ← `null` · `public_interest` ← `false` · `code` omitted

Then add `frontend/src/registry/index.ts`: import the JSON through the alias,
assert `TestRegistryEntry[]`, export `REGISTRY`, `REGISTRY_BY_ID`, and
`resolveTests(snapshotTests: ScorecardTest[]): ResolvedTest[]` — joining on `id`,
ordered by `CATEGORY_ORDER` then valence then `order`. A snapshot test with no
row, or a row with no snapshot test, gets a named `console.error` and is skipped;
never throw, never render a placeholder. (Step 4 is the real gate; this path is
for a dev pointing at an old draft.)

Still no component change. Acceptance: 29 rows matching Part D's counts;
`npm run build` passes.

---

### Step 3 — Python reads the registry; `_BATTERY` is deleted

This is the B.3 + B.5 change. Read both sections before starting.

1. Add a loader — `src/test_registry.py`, modelled on `src/agent_config.py`
   (plain `json.load` of `config/test_registry.json`, a small frozen dataclass or
   typed dict per row, `DEFAULT_PATH` beside the module).
2. In `src/analysis/tests.py`: replace `_BATTERY` with
   `_GENERATORS = {test_id: function}` covering all 29, and **delete**
   `_MEETING_BATTERY`.
3. `run_test_battery` walks registry rows in `order`, looks each `id` up, calls
   the generator exactly as before, then overwrites `r.title` /
   `r.question` from the row (B.5). Its existing per-test `except` guard stays;
   use the row's `id` for the error result's `test_id` instead of
   `fn.__name__`.
4. `run_meeting_digest` walks rows where `meeting_scope` is true. It does **not**
   overwrite title/question — meeting-scoped copy stays in the generators until
   Step 10.
5. **Fail loudly at startup**: a row whose `id` has no generator, or a generator
   with no row, raises with both sets named. Never run a partial battery.
6. **Do not touch a single generator body.** The 57 `TestResult` constructions
   keep their `title=` / `question=` / `genre=` / `principle=` kwargs; the first
   two are now overwritten, the last two are simply unread by the new frontend.

`src/analysis/coverage_register.py`'s `extract_shipped_test_ids()` and
`extract_meeting_scope_test_ids()` AST-parse `_BATTERY` / `_MEETING_BATTERY` and
**will break**. Repoint both at the registry — they get simpler (a `json.load`
and a comprehension, no AST). `tests/test_coverage_register.py` must still pass
unchanged.

**Acceptance — the whole verification of this step:** run
`council draft cambridge`, then diff the new `scorecard.json` against
`data/draft/cambridge/draft_20260904_082327/scorecard.json` ignoring
`published_at`. It must be **byte-identical**. Anything else means the registry
disagrees with what the battery was saying, and the seed in Step 2 is wrong —
fix the seed, never the assertion. Also confirm `pytest -q` passes whole.

---

### Step 4 — Parity test in CI

Add `tests/test_test_registry.py` (pytest, no DB, no network). Assert:

1. every registry `id` has a `_GENERATORS` entry and vice versa, with the
   symmetric difference named in the failure message;
2. `{id where has_deep_dive}` == the keys of `BESPOKE_PANELS` — **both
   directions** (B.4). Regex the `"…": Component` keys out of
   `frontend/src/bespokePanels.tsx`; it is one flat literal, a small documented
   regex is fine;
3. `order` is exactly `1..29`, unique;
4. every `category` is one of the four; every `detail_panel` is unique and
   non-empty;
5. every `evidence_query` either names a `def` in `src/analysis/queries.py` /
   `divergence.py`, or starts with `tests.` and names a `def` in
   `src/analysis/tests.py`.

Do **not** assert `question_public` / `title_public` / `method` / `objection` are
non-empty — they are filled later, and blocking on them stalls every
intermediate commit.

Acceptance: passes; whole suite passes. Sanity-check it bites — flip one
`has_deep_dive`, confirm red, revert.

---

### Step 5 — Categories from the registry

Add `frontend/src/registry/grouping.ts`: `groupByCategory(tests: ResolvedTest[])`
driven by `CATEGORY_ORDER` / `CATEGORY_LABEL` and each entry's `category` — no
regex, no `genre`, no "Other" bucket (Step 4 guarantees every id has a category),
and no dead "Planning & fairness" branch.

Leave `groupTestsByGenre.ts` untouched; the three surfaces still import it. It is
deleted at the end of Step 9.

Acceptance: build passes; no surface has changed.

---

### Step 6 — Scorecard renders from the registry ← the acceptance gate

`ScorecardPanel.tsx`: fetch as now, pass through `resolveTests`, group with
`groupByCategory`, render `TestRow` from `ResolvedTest`.

Field swaps, and only these: `t.title` → `t.title_technical`; the `genre` meta
chip → `CATEGORY_LABEL[t.category]`; `t.principle` → `t.principles.join(" · ")`.
Everything else — headline, verdict, grade, n, era, the valence chip, the `sc-`
anchors, the `#panel-` links, the named-individual redaction guardrail, the
summary counts, both `chart-note` paragraphs — stays byte-identical. **Keep the
guardrail exactly as it is**; it is a defamation control, not formatting.

Because Steps 2 and 3 kept the copy verbatim, the rendered output should be
**identical**, not merely similar.

Acceptance: build + lint. Then by hand: `npm run dev`, corner switch to DRAFT,
compare `/` before and after — same 29 rows, same four sections, same order
within each, same 10/10/7/2 summary. Any visible change is a bug in this step,
not an improvement; report it rather than absorbing it.

---

### Step 7 — Analysis page and the generic panel

`AnalysisPage.tsx`: resolve + `groupByCategory`; keep the `BESPOKE_PANELS[t.id]`
/ `BatteryTestPanel` fork and the `id={`panel-${t.detail_panel}`}` anchors
exactly as they are.

`BatteryTestPanel.tsx`: `BatteryTestCard` takes a `ResolvedTest`; `title` ←
`title_technical`, `subtitle` ← `question_technical`, meta chip ←
`CATEGORY_LABEL[category]`, principle ← `principles.join(" · ")`.

While here, extract the duplicated guardrail (`findNamedCouncillorsInText`,
`escapeRegExp`, `redactNamedCouncillors`) — currently character-identical in
`ScorecardPanel.tsx` and `BatteryTestPanel.tsx` — into
`frontend/src/guardrail.ts` and import it in both. **Move it verbatim; do not
re-derive it.**

Acceptance: `/analysis` renders the same panels in the same order with the same
headings; every `#panel-…` anchor from the scorecard still lands. Spot-check
three back-links and three forward-links.

---

### Step 8 — Bespoke panels stop authoring their own copy ← where the drift dies

Change `BESPOKE_PANELS` to `Record<string, ComponentType<{ test: ResolvedTest }>>`
and have `AnalysisPage` pass the resolved entry. In each of the 12 panels:

- `title="…"` → `test.title_technical`
- `subtitle="…"` → `test.question_technical` (drop the duplicated era suffix —
  era renders in the meta line; if a subtitle carried something the question does
  not, put it in `method` in the registry, not back into JSX)
- `valence="critical"` → `test.valence`
- `backTo="sc-declared"` → `` `sc-${test.detail_panel}` ``

Everything inside the card body — charts, drill-downs, `SourceQuote` receipts,
`CouncillorModal` links — is untouched.

This step **does change five visible headings** (A.3's table), deliberately: the
panel and its scorecard row now say the same thing. It is the one intended
visible change in Phase 1. Do the other seven panels first and confirm no diff,
then the five, and **list the before/after pairs in the handoff summary** so they
are reviewed as copy, not skimmed as refactor noise. Note in the summary that
`valence` was a hardcoded literal in all 12 and is now computed.

Acceptance: build + lint; `/analysis` shows 12 bespoke panels whose headings
match their scorecard rows; no panel shows a valence colour that disagrees with
its scorecard chip.

---

### Step 9 — Digest, and cleanup

`DigestPage.tsx`: resolve + `groupByCategory` like the others. The digest
snapshot carries only the 14 `meeting_scope` tests, so the resolver yields 14
rows and a category may be absent — correct, do not pad.

The digest's per-test `title` is the **meeting-scoped** phrasing ("Did anyone
declare a conflict this meeting?"), which the registry has no field for (B.5).
Do not invent one and do not substitute the corpus-wide title. Keep rendering the
snapshot's own `title` **on this surface only**, with a one-line comment saying a
`title_meeting` / `question_meeting` pair belongs in the registry and is
deliberately deferred to Step 10. Take `category`, `principles` and
`detail_panel` from the registry as elsewhere.

Then: delete `frontend/src/groupTestsByGenre.ts` (now unimported), delete
`frontend/src/pages/HomePage.tsx` (A.5), and drop `genre` / `title` / `question`
from the frontend's `ScorecardTest` interface if nothing else reads them —
leaving the Python `TestResult` untouched.

Acceptance: build + lint; with a draft present, `/digest` in DRAFT mode shows the
same 14 cards with the same meeting-scoped headings as before.

---

### Step 10 — Documentation

- `docs/frontend/INTERACTIVITY.md` — a short section under the hard rule: a
  panel's heading, subtitle and valence come from the registry entry, never from
  JSX; adding a battery test means adding a registry row, and the battery refuses
  to run without one.
- `docs/MAP.md` — one row in "Where do I add X?": *adding a governance test, or
  re-wording its public-facing copy* → `config/test_registry.json` (with
  `src/analysis/tests.py` owning the computation). Follow the table's voice; no
  line references.
- `docs/TESTING.md` — `config/test_registry.json` is now load-bearing for
  `council draft`; note `tests/test_test_registry.py` in the CI section.
- `docs/frontend/PRODUCT_ROADMAP.md` — record what is deliberately open:
  `question_public` / `title_public` / `method` / `caveats` unfilled;
  `objection` / `response` awaiting their own pass; `public_interest` all `false`
  so no lay-facing surface can be built from it yet; meeting-scoped copy still in
  `tests.py`; Phases 2 and 3 outstanding.
- Mark this file's status **Phase 1 built**; leave Parts A–D as the record of the
  pre-registry state.

---

### Step 11 — PHASE 2: re-wire the institutional orphan — DONE 2026-09-04

Turned out to be one panel, not four — see A.5's 2026-09-04 correction above.

- **`TrendsChart` (`ContestationChart`)** — its measure *is*
  `governance.unanimity_trend`. Added to `BESPOKE_PANELS` under that id, that
  row's `has_deep_dive` flipped to `true`, `evidence_snapshot: "trends"` set.
  No new test. Panel's own copy confirmed coming from the registry row
  (Step 8's rule); its numbers agreed with the scorecard row's exactly across
  all 31 overlapping years in real data.
- **`PlanningTrendChart`, `PlanningObjectionsPanel`** — not attempted.
  `INVESTIGATIONS.md` already retired both with documented reasons (a
  duplicate, and a rejected-on-the-merits measure respectively — A.5 above)
  before this plan was written; codifying a test for either would override
  that judgment, not fill a gap. Left alone.
- **`InterestsChart`** — reclassified to Phase 3 (A.5 above); not attempted
  here.

Acceptance (revised): `/analysis` renders one more panel (`TrendsChart`);
`pytest -q` green including `test_coverage_register.py` and
`test_test_registry.py`; `council draft` clean — met.

---

### Step 12 — PHASE 3: the individual-implicating orphans (now five)

`InterestsChart`, `DissentProfilesChart`, `DissentCoalitionsPanel`, `AlignmentHeatmap`,
`CoMoverGraph` chart and name individual councillors. Every battery test today
is `UNIT_INSTITUTIONAL`; these would be the system's first
`individual_implicating` claims.

**Do not start this step as a frontend task.** Read
`docs/INFORMATION_ARCHITECTURE.md` §4 (the claim object, unit of analysis, tier
derivation), `src/invariant_gate.py`, and `docs/AGENT_DESIGN.md` first, and
expect to touch `unit_of_analysis`, `named_entities`, `entity_resolution`,
tier derivation, and possibly S9 reply packets (`src/reply_packets.py`) before
any of these can ship. Scope this step properly when Phase 2 is done; it is
listed here so it is not forgotten, not because it is ready.

---

### Deliberately not in this plan

Renumbering `test_id` (B.1) · stripping the now-redundant `title=` / `question=`
/ `genre=` / `principle=` kwargs from the 57 `TestResult` constructions (B.5) ·
filling `objection` / `response` (B.8) · building a lay-facing page off
`public_interest` · moving meeting-scoped copy into the registry (Step 9) · any
change to a computed number, anywhere.
