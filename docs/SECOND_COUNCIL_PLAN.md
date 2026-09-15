# Second-Council Readiness — implementation plan

**Status:** plan only, nothing built. Written 2026-09-15 from a read-through of
the pipeline, analysis, publish and frontend layers. Two decisions are settled
and not open for re-litigation by an implementing session: the site serves
**one deploy with council-segmented paths** (Phase 2), and the synthetic
council **Testville** is selectable in Draft mode only (Phase 2.5).

**Scope:** everything that has to change *before* a second council's corpus is
extracted and published, plus the onboarding run itself. Cross-track — it
touches pipeline, investigator (battery), review and frontend. `docs/MAP.md`
routes each individual change to the doc that governs it; this file is the
order and the gates.

**Read before starting:** `docs/MAP.md`, then
`docs/pipeline/PIPELINE.md` ("Longer term → Corpus onboarding order →
Subsequent corpora onboarded") and `docs/frontend/INTERACTIVITY.md` (its hard
rule on hardcoded content in component source — Phase 3 widens that rule).

---

## How to execute this plan

- **One step at a time, in order.** Each step names its files, its change, and
  an acceptance check. Don't batch steps across a phase gate.
- **Stop on any plan-vs-codebase contradiction.** If a file, symbol or
  behaviour this plan describes isn't what you find, stop and ask — every
  time, not just the first time. This plan was written against the tree at
  commit `70b80ee`; symbols move.
- **No commits without an explicit go-ahead**, and no `Co-Authored-By` trailer
  in this repo.
- Once Phase 0 lands, Phases 1, 2 and 3 can be worked in any order, with one
  dependency: steps 3.2 and 3.6 need Phase 2's `councils.json` and its
  mode-dependent council list. Phase 4 gates Phase 5.

---

## Part A — What's already ready

Worth stating, because it's most of the hard part and it means no
re-architecting:

- **The data model is already multi-council.** A `councils` registry table,
  and every function in `src/analysis/queries.py` and `src/analysis/tests.py`
  takes `council_id` and filters on it. One `data/council.db` holds N councils.
- **Most filesystem paths are already namespaced per council:**
  `data/raw/<key>/`, `data/draft/<key>/<run_id>/`,
  `data/published_full/<key>/<run_id>/`, `data/<key>_profile.json`,
  `data/<key>_sample.json`, `data/<key>_meeting_baselines.json`,
  `data/reply_packets/<key>/`, and the digest/watch preview dirs.
- **The test registry split is the right shape already.**
  `config/test_registry.json` holds the static, council-agnostic half of each
  test (id, category, question, principles, objection/response);
  the snapshot holds the computed half; `frontend/src/registry/index.ts`'s
  `resolveTests()` joins them and errors loudly on either side being orphaned.
- **The extraction prompts are jurisdiction-generic, not council-specific.**
  `src/extraction/system_prompt.txt`, `agenda_system_prompt.txt` and
  `inventory_prompt.txt` contain no reference to Cambridge — they address
  "Western Australian local government" documents.
- **`build_method_record()` already takes `council_key` and an overridable
  `data_dir`** — so the `/method` fix in Phase 1 is a wiring change, not a
  rewrite.
- **The agent stages are all council-parameterised**: `council draft`,
  `editor`, `editor-score`, `fixer`, `editor-loop`, `reply-packets`, `render`
  all take a council argument and write under a per-council draft directory.
- **The onboarding sequence is already designed** (PIPELINE.md, "Subsequent
  corpora onboarded" — battery-before-Explorer, Researcher optional), and
  terms-seeding is documented for WA plus other states.

`docs/strategy/PRIVATE_ASSESSMENT.md` currently says "the scraper is the only
new code; the battery runs out of the box." The scraper part is right. The
battery part is not — see B2/B3 below. That line should be corrected as part
of Phase 6.

---

## Part B — Blockers

Each of these produces **wrong output, silently**, for council #2. None of
them is caught by the existing gates: the publish gate verifies the bytes
match what was reviewed, not whether the prose is true; CI has no
second-council case to run.

### B1 — `council publish` overwrites the live site

`cmd_publish` in `src/cli.py` copies public-tier snapshots to a flat
`frontend/public/data/<name>.json` and writes one
`frontend/public/data/manifest.json`. Publishing council #2 deletes council
#1's live data. There is no council segment anywhere in the public path.

### B2 — Battery verdicts are Cambridge conclusions, not derived results

In `src/analysis/tests.py`, 52 of 57 `TestResult` constructions set `valence`
and `grade` unconditionally, and roughly 30 carry static verdict prose that
asserts a specific Cambridge finding. Two concrete examples:

- `_t_confidential_tender_size` hardcodes `valence=CRITICAL`,
  `grade=G_CONCERN`, and a verdict reading "The contracts residents can least
  scrutinise are systematically the largest (rank-sum p≈0.002)… Only ~1 in 5
  confidential tenders carries an amount". Every clause is a Cambridge
  measurement. Run it against a council where confidential tenders are
  *smaller* and it reports council #2's median alongside Cambridge's
  conclusion.
- `_t_transparency`'s verdict asserts "A strong two-decade openness baseline
  with a single Inquiry-era spike" — a Cambridge history, emitted for any
  corpus.

`_t_procurement_threshold_gaming` shows the pattern done correctly: it
computes `clean`, then branches `valence`, `grade`, `headline` and `verdict`
off it. That is the target shape for all of them.

This is the largest correctness risk in the whole plan, and the one most
likely to reach a published page, because a reviewer reading a draft snapshot
sees a plausible sentence attached to a real number.

### B3 — A Cambridge-specific era boundary is hardcoded in two tests

`_RECUSAL_ERAS` / `_recusal_era` in `src/analysis/queries.py` and
`public_question_responsiveness` in the same file hardcode 2018–2021 (the Town
of Cambridge Authorised Inquiry) as the `pre` / `inquiry` / `post` split.
`Refiner_prompt.txt` Step 4 already logs this as a known, unfixed
council-agnosticism failure. For council #2 those era labels are meaningless
but the tests still compute and label them.

### B4 — Per-corpus extraction-quality artifacts share one global path

These are written to fixed, council-less paths:

| Artifact | Written by |
|---|---|
| `data/census.json`, `data/census_summary.txt` | `scripts/census.py` |
| `data/inventories/` (+ `summary.json`) | `scripts/inventory.py` |
| `data/inventory_quality/`, `data/<key>_typology_review.txt` | `scripts/inventory_typology.py` |
| `data/validation/summary.json` | `scripts/validate_extraction.py` |
| `data/sample_validation/{summary.json,report.txt}` | `scripts/validate_sample.py` |
| `data/extraction_errors.json` | `src/cli.py` (extract paths) |

Running the pipeline for council #2 overwrites council #1's. These are exactly
the files `/method` traces every figure to (`build_method_record()`), so after
a council-#2 census the `/method` page for council #1 would report council
#2's extraction quality under council #1's name — with a `generated_at` that
looks perfectly fresh. That breaks `docs/frontend/METHOD_PAGE_PLAN.md`'s own
provenance guarantee.

### B5 — `config/meeting_bodies.json` is a single global map with Cambridge's committees

`load_meeting_bodies()` reads one flat `meeting_type → body_class` dict whose
keys are Cambridge's committee names ("Development Committee", "Policy and
Legislation Committee", …). Council #2's meeting types fall through to
`UNKNOWN_BODY_CLASS`, which silently degrades every body-matched baseline
(`src/analysis/meeting_baselines.py`, `src/analysis/digest.py`, and the
body-scoped branches in `tests.py`) and therefore the whole `/watch` feed.
Nothing errors; the comparisons just get quietly worse.

### B6 — Frontend panel prose is hardcoded Cambridge narrative

This is the 2026-08-06 hardcoded-names incident one level up: not names, but
*claims and era labels*.

- `OverviewPanel.tsx` asserts, as literal JSX, "Cambridge is a **broadly sound
  council with specific, nameable weaknesses**", "The tender record passes
  **every** integrity test thrown at it", "the most contentious category…is
  the *least* closed", plus the title "What 30 Years of Minutes Say". Numbers
  come from the snapshot; every conclusion is typed in.
- `RecusalTrendPanel.tsx` and `QuestionResponsivenessPanel.tsx` hardcode
  "Before Inquiry (pre-2018)" / "Inquiry (2018–21)" axis labels and a
  `<ReferenceArea x1={2018} x2={2021}>` band labelled "Authorised Inquiry".
- `TransparencyTrendPanel.tsx`, `ScorecardPanel.tsx`, `TenurePanel.tsx`,
  `PlanningTrendChart.tsx`, `SponsorshipNetworkPanel.tsx` each name Cambridge
  or assert a Cambridge-specific trend in prose.
- 10 files hardcode a corpus span ("1995–2026", "30-year", "30 Years"):
  the five chart components, `InterestsChart`, `PlanningObjectionsPanel`,
  `OverviewPanel`, `CouncilHeader`, `AboutPage`.

`INTERACTIVITY.md`'s hard rule covers councillor names and specific stats. It
does not cover council-specific narrative claims, era labels or corpus spans,
so the pre-deploy grep the rule prescribes won't catch any of the above.
Phase 3 widens the rule.

### B7 — Single-council chrome

- `CouncilHeader.tsx` has a `<select>` bound to local state that nothing
  reads, wrapped in the literal words "Town of … Council" — wrong for any
  council that is a City or a Shire, and a dead control today.
- `MapPage.tsx` hardcodes `LGA_TO_KEY = { "Cambridge": "cambridge" }` and
  builds a single synthetic `cambridge` score object from `/data/scorecard.json`.
- `api/main.py` hardcodes `COUNCIL_SHORT_NAME = "Cambridge"`.
- `OverviewPage`, `AnalysisPage`, `WatchPage`, `MethodPage` footers each
  hardcode the Cambridge name and source URL.
- `AboutPage` says "Currently live: **Town of Cambridge, Western Australia**".
- `RecordPage`'s street-search placeholder is "e.g. Cambridge Street".

### Non-blocking gaps

- **No executable council-agnosticism gate.** `Refiner_prompt.txt` Step 4
  concedes that the real second-council check "isn't possible yet — no second
  council DB is loaded", leaving half of refinement dimension 4 permanently
  `data_ok=False`. Phase 0 closes this with a synthetic council, before any
  real data or LLM spend.
- **Cambridge filename conventions live in the shared scraper base.**
  `src/scraper/base.py`'s `_MINUTES_SHORTHAND`, `_AGENDA_SHORTHAND`,
  `_NOISE_PATTERNS` and `_MEETING_KEYWORD_RE` encode Cambridge's
  pre-CMS naming (`YYYY_MM_DD…m.pdf`, `dv\d\d_`, `-dva.pdf`) in the abstract
  base class, where they apply to every future council.
  `classify_document_type()` / `is_meeting_document()` should take their
  patterns from the subclass.
- **`scripts/extract_cambridge_elections.py` is per-council by design.**
  PIPELINE.md already explains how to write the next one; a parameterised
  `extract_wa_elections.py <COUNCIL NAME>` would remove the copy-paste.
- **No cross-council comparison surface.** The scorecard's whole premise is
  cross-council comparability and `MapPage` is built for a choropleth of many
  councils, but nothing compares two. That's the payoff, not a blocker —
  Phase 6.

---

## Phase 0 — Make second-council-ness testable

Nothing here needs real data, a scraper, or an LLM call. It exists so that
every fix in Phases 1–3 starts from a failing test, and so B2's ~30 static
verdicts can be found mechanically rather than by reading.

**0.1 — Testville: one synthetic council, two consumers.**
Write **one** fixture-corpus builder (suggested:
`src/fixtures/testville.py`, importable from both `tests/` and the CLI) that
seeds a set of councils via the existing models:
- `Cambridge`-shaped council A: enough meetings/motions/votes/tenders/
  declarations to make every battery test computable.
- **Testville**, built to invert A's direction wherever a test has a
  direction: confidential tenders *cheaper* than open, recusal compliance
  *improving* over time, officer divergence *high*, tender amounts *bunched*
  just under $250k, a corpus span that is not 1995–2026.

Testville is the point: a test whose verdict is hardcoded will assert A's
conclusion over Testville's numbers, and that mismatch is what 0.2 detects.

It has two consumers, and they must share one definition — two hand-kept
copies of "the synthetic council" will drift:
- **pytest** (0.2) seeds it into a tmp DB per test run.
- **the dev server** (0.4) seeds it into the local `data/council.db` so it can
  be drafted and browsed like any other council.

**0.2 — `tests/test_council_agnostic.py`.** Run
`run_test_battery(session, council_id)` for both councils and assert:
- **No leakage:** no `TestResult` field (`headline`, `verdict`, `base_rate`,
  `era`, `title`) for Testville contains "Cambridge", "Authorised Inquiry", a
  year outside Testville's own span, or the wrong council's name.
- **Direction tracking:** for each test given an inverted signal in the
  fixture, `valence` and `grade` differ between A and Testville. A test that
  returns the same `valence` for opposite data fails here — that is the B2
  detector. Expect this to fail for ~30 tests on first run; the failing list
  *is* the Phase 1.1 worklist. Land the test with an explicit, shrinking
  xfail/allow list rather than a weakened assertion, so progress is visible
  in the diff.
- **Registry join:** every `config/test_registry.json` row resolves against
  Testville's battery with no orphan on either side.
- **`data_ok` honesty:** a test that can't run on Testville's corpus returns
  `data_ok=False` with the `_nodata` shape, not a zero.

**0.3 — Static content gate in CI.** Extend the INTERACTIVITY hard-rule idea
into a script (suggested `scripts/check_no_hardcoded_content.py`, wired into
`ci.yml`'s Python job) that fails on, in `frontend/src/**` and
`src/analysis/tests.py`:
- any council name from `COUNCILS` (plus "Town of", "City of", "Shire of"
  followed by a capitalised word) in a string literal,
- an era label ("Authorised Inquiry", "pre-2018", "2018–21"),
- a hardcoded corpus span (`19\d\d[–-]20\d\d`, "30-year", "N Years of").
Seed it with an explicit, annotated allow-list of today's known offenders so
it can land green, and have Phases 1 and 3 empty the list. Document the rule
change in `docs/TESTING.md`.

**0.4 — Testville as a draftable dev council.**
So it can be selected and browsed in Draft mode (Phase 2.5), Testville needs
to exist as an ordinary council to the CLI:
- Add a `COUNCILS` entry in `src/cli.py` for `testville` with **no scraper**
  and an explicit `synthetic: True` flag. That flag — not a name check — is
  what every gate keys on.
- Add `council seed-fixture testville` (no LLM, idempotent, refuses to
  overwrite a non-synthetic council at that key) that builds the corpus into
  the local `data/council.db` via the 0.1 builder.
- `council draft testville` then works unchanged, writing
  `data/draft/testville/<run_id>/` for the dev server to serve.
- **`council publish` refuses any council whose registry entry is
  `synthetic`** — a hard gate in `src/publish_gate.py`, tested, not a
  convention. Synthetic data reaching `frontend/public/data/` is the same
  class of failure as the hardcoded-names incident: invisible until deploy.
  This is the first of three independent barriers between Testville and
  production; the other two are in 2.5.
- `data/council.db` is gitignored, so seeding is a local action that never
  travels. Say so in `docs/TESTING.md` — a seeded Testville in a developer's
  local DB is expected, not contamination.

**Acceptance:** `council seed-fixture testville` then `council draft
testville` produces a gate-passing run; `council publish testville` is
refused with a clear reason; pytest and the dev server agree on Testville's
numbers because both call the same builder.

**Gate:** CI green with the new test and the new script, both carrying an
explicit allow-list whose entries are the B2/B6 worklists.

---

## Phase 1 — Data layer: make the battery actually council-agnostic

**1.1 — Derive every verdict from the data.** (`src/analysis/tests.py`)
Work the Phase 0.2 failing list one test at a time. For each:
compute the direction/threshold, then branch `valence`, `grade`, `headline`
and `verdict` off it, following `_t_procurement_threshold_gaming`'s shape.
Where a Cambridge-specific statistic appears in prose (a p-value, "~1 in 5
carries an amount"), either compute it or drop the clause — don't keep it as
an unsourced assertion. Where a test genuinely has no direction (descriptive
`NEUTRAL` tests, `_nodata` returns), record that in a comment so the next
reader doesn't mistake it for an unfixed case.
This is the biggest single piece of work in the plan. It is also the piece
whose acceptance is fully mechanical: Phase 0.2's allow-list empties.

*Governance note:* each edited test is a Refiner-track change. Follow
`docs/investigator/REFINEMENT_PROTOCOL.md` — in particular re-emit the
declaration block (unit / MIN_N / strength / principle) and keep
`config/test_registry.json`'s row and `coverage_register.json` in step. Once a
second real council exists, dimension 4's second half stops being
`data_ok=False`; update `Refiner_prompt.txt` Step 4 to point at the synthetic
fixture as the check that runs *now*.

**1.2 — Parameterise the era boundary.** (`src/analysis/queries.py`)
Replace the hardcoded `_RECUSAL_ERAS` / `_recusal_era` window and
`public_question_responsiveness`'s equivalent with a per-council
"external-scrutiny window" read from config — suggested:
`config/council_eras.json`, `{ "<key>": { "label": "...", "from": YYYY,
"to": YYYY } }`, absent meaning no window. When a council has no window, the
test must degrade to an era-neutral computation or `data_ok=False`, never
invent a split. Update the two tests that consume it, and remove the
known-failure note from `Refiner_prompt.txt` Step 4 once done.

**1.3 — Namespace the per-corpus quality artifacts.** (B4)
Move every path in the B4 table under `data/<council_key>/`, updating
`scripts/census.py`, `inventory.py`, `inventory_typology.py`,
`validate_extraction.py`, `validate_sample.py` and the extract paths in
`src/cli.py`. Then:
- pass `data_dir=Path("data")/key` from `cmd_draft`'s
  `build_method_record()` call, and
- make `method.py`'s `CENSUS_REL` &c. **derive their `source` strings from
  `data_dir`** rather than being module constants — otherwise `/method` cites
  a path it didn't read, which is the exact failure METHOD_PAGE_PLAN's
  provenance rule exists to prevent.
Provide a one-off migration for the existing Cambridge files (a documented
`git mv`-equivalent is fine; don't leave both copies). `tests/fixtures/method/`
and `tests/test_method.py` need the same reshaping.

**1.4 — Per-council meeting-body map.** (B5)
Re-key `config/meeting_bodies.json` by council
(`{ "cambridge": { "<meeting_type>": "<body_class>" } }`) and give
`load_meeting_bodies()` a council argument; thread it through
`meeting_baselines.py`, `digest.py` and `tests.py`. Add a loud diagnostic —
`council profile` is the natural home — reporting any `meeting_type` present
in the DB but absent from that council's map, so an onboarding run surfaces
the gap instead of silently classing everything `unknown`.

**1.5 — Move Cambridge filename patterns out of the scraper base.**
(`src/scraper/base.py`) Turn `_MINUTES_SHORTHAND`, `_AGENDA_SHORTHAND`,
`_NOISE_PATTERNS` and `_MEETING_KEYWORD_RE` into class attributes or
constructor arguments with the generic defaults on the base and Cambridge's
shorthand on `CambridgeScraper`. `classify_document_type()` and
`is_meeting_document()` become methods or take a pattern set. Keep existing
Cambridge behaviour byte-identical — verify against
`data/raw/cambridge/manifest.json`'s `document_type` values.

**Gate:** Phase 0.2's allow-list is empty; `pytest` and `ruff` green; a
Cambridge `council draft --fast-evidence` run produces a snapshot set whose
battery verdicts are unchanged where the data is unchanged (diff the
`scorecard.json` against a pre-change run — any change must be explainable as
a fixed hardcode, not a computation drift).

---

## Phase 2 — Publish and serving: multi-council

**Serving shape — decided 2026-09-15: one site, council-segmented paths.**
`frontend/public/data/<key>/*.json`, routes carry the council, one deploy
serves every council. This is the shape the existing `CouncilHeader`
`<select>` and `MapPage`'s `LGA_TO_KEY` were written toward, and the only one
that supports the cross-council comparison in Phase 6. The per-deploy
alternative is not being built.

**2.1 — Council-segment the publish path.** (`src/cli.py` `cmd_publish`,
`src/publish_gate.py`) Public snapshots go to
`frontend/public/data/<key>/<name>.json`, with the per-council manifest
alongside. Keep every existing integrity check intact — the hash check, the
`manifest.council != key` check, the interactive/auto clearance split, and
the "copy bytes, never recompute" rule all still apply, now per council. Add
the `synthetic` refusal from 0.4 here.
`tests/test_publish_gate.py` gains a two-council case asserting that
publishing B leaves A's files untouched, plus a case asserting a synthetic
council is refused.

**2.2 — `councils.json`, the published council list.** A top-level
`frontend/public/data/councils.json`, rewritten by each publish, listing every
council with published snapshots: key, display name (full — "Town of
Cambridge", so no page has to guess the prefix), source URL, corpus span,
`published_at`, `draft_run_id`. This is the single source the council
selector, the page footers and `MapPage` all read, replacing the literals in
B6/B7. It must contain no full-tier snapshot names and — by construction,
since 2.1 refuses synthetic councils — no Testville.

**2.3 — Draft-mode plumbing.** `frontend/src/api.ts`'s `/data` vs
`/data/draft` prefix and `DevModeSwitch`'s `/data/draft/manifest.json` probe
both need the council segment. `frontend/vite.config.ts`'s `draftOverlay()`
currently hardcodes `findLatestDraftDir('cambridge')` with a comment pointing
at `CouncilHeader`'s hardcoded `<select>`; its URL pattern becomes
`/data/draft/<council>/<name>.json` and it resolves the run directory per
requested council.

**2.4 — Full-tier path.** `data/published_full/<key>/<run_id>/` is already
namespaced — confirm no change is needed.

**2.5 — The council selector, and where Testville may appear.**
The selector's options come from a **mode-dependent** list, because Draft and
Publish answer different questions:

| Mode | Where it runs | Option source | Testville |
|---|---|---|---|
| Publish | dev server *and* every production build | `/data/councils.json` | never |
| Draft | dev server only | draft-overlay council listing | yes, alongside every real council |

- **Publish mode** reads `councils.json` (2.2) — only real councils that have
  actually been published. This is the only path a production build can take:
  `devMode.ts`'s `getMode()` already returns `"publish"` unconditionally when
  `import.meta.env.DEV` is false, and `DevModeSwitch` is already dead code in
  a build. Don't add a second mechanism; key off the existing one.
- **Draft mode** reads a new listing the `draftOverlay()` plugin serves from
  `data/draft/*/` — every council in the system with a gate-passing draft run,
  Testville included, so a developer can flip to Draft and select it like any
  other council.

Three independent barriers keep Testville out of production, none of which
relies on the other: the publish gate refuses synthetic councils (0.4), so it
can never enter `councils.json`; the draft listing is served by a dev-only
Vite middleware that `vite build` never runs; and `getMode()` cannot return
`"draft"` in a build. State that in a comment where the selector reads its
list — the reason there are three is that this repo has already shipped one
class of wrong content that was invisible until deploy.

**Acceptance:** with Cambridge published and Testville seeded and drafted —
in Publish mode the dropdown shows Cambridge only; flipping to Draft shows
Cambridge and Testville, and selecting Testville renders its snapshots;
`npm run build` output contains the string "testville" nowhere; a grep of
`frontend/public/data/` finds no Testville file.

**Gate:** publish Cambridge, then a second real council, and assert both are
readable and neither overwrote the other; `tests/test_publish_gate.py` covers
both that and the synthetic refusal.

---

## Phase 3 — Frontend: de-Cambridge the components

Can run in parallel with Phase 1. Steps 3.2 and 3.6 need Phase 2's
`councils.json` and mode-dependent council list first.

**3.1 — Widen the INTERACTIVITY hard rule.** (`docs/frontend/INTERACTIVITY.md`)
Extend "never hardcode a councillor name or a specific finding" to cover
**council names, council-specific narrative conclusions, era labels, and
corpus spans** — with the same reasoning already written there (neither `tsc`
nor the data-layer publish gate can see a string in `.tsx`), plus the new
reason: a hardcoded conclusion is *wrong for a different council* even when
it's true for this one. Point at the Phase 0.3 script as the mechanical check.

**3.2 — Council identity from data, not literals.**
Make every page read council identity (display name, source URL, corpus span)
from the council list (2.2/2.5), and delete the literals from
`CouncilHeader` — including the surrounding words "Town of … Council", which
belong to the display name, not the template — plus the four page footers,
`AboutPage`, and `RecordPage`'s placeholder (derive it from the street data,
or use a generic example).

Wire the `CouncilHeader` `<select>` to real navigation against the
mode-dependent list from 2.5: selecting a council changes the active council
for every page. Keep the selected council in the route so a link is
shareable and a reload keeps it, rather than in component state. If the list
has exactly one entry, render it as plain text rather than a one-option
dropdown.

**3.3 — Corpus spans from data.** Replace "1995–2026" / "30-year" / "30 Years"
in the 10 files listed in B6 with a value derived from the snapshot.

**3.4 — Era labels from config.** `RecusalTrendPanel` and
`QuestionResponsivenessPanel` take their era labels and `<ReferenceArea>`
bounds from the snapshot (fed by Phase 1.2's `council_eras.json`), and render
the era breakdown only when the council has a window. `TransparencyTrendPanel`
and `OverviewPanel` lose their "Authorised Inquiry" prose the same way.

**3.5 — `OverviewPanel` is a rewrite, not a patch.** Its thesis paragraph,
one-liner and four insight bodies are a hand-written Cambridge synthesis.
Options, in preference order:
1. Render from a synthesis field in the snapshot — which is what
   `docs/render/synthesis_mode.txt` (Renderer) exists to produce. Renderer
   has never been run and has no calibration data, so this is a real
   dependency, not a free win.
2. Reduce the panel to what is computable per council (the stat tiles, the
   valence mix from `scorecard.json`, the span) and drop the narrative until
   Renderer is calibrated.
Do **not** keep the prose behind a `council === "cambridge"` conditional —
that reproduces the hardcoded-claim problem with extra indirection.

**3.6 — `MapPage` reads the council list.** Build `LGA_TO_KEY` and the score
objects from the council list plus each council's `scorecard.json`, instead
of the hardcoded `cambridge` entry. Unpublished LGAs keep the existing grey
"no data" style. Testville has no WA LGA boundary, so it simply won't match a
feature — no special case needed, and that's worth a one-line comment so the
next reader doesn't add one.

**3.7 — `api/main.py`.** Replace `COUNCIL_SHORT_NAME` with a per-request
council parameter (path or query), defaulting from an env var. Low priority —
confirm whether this API is still in use before spending time on it; nothing
in `frontend/src` currently calls it (`api.ts`'s `BASE` is described as
reserved for future endpoints).

**Gate:** Phase 0.3's allow-list is empty; `npm run lint` and `npm run build`
green; the site renders correctly for Cambridge with no visual regression,
and — switched to Testville in Draft mode — renders that council's numbers
with no Cambridge claim, era band or span left on the page. Per the
hardcoded-names incident: **grep component source before any deploy** — the
data-layer gate does not cover it.

---

## Phase 4 — Prompt generalisation review (prerequisite, documented)

`PIPELINE.md` makes this a hard prerequisite to pointing the pipeline at a new
council, and it's the standing instruction on this project. Do it as a
read-through with a written record, not a grep.

**4.1 — Extraction prompts** (`src/extraction/system_prompt.txt`,
`agenda_system_prompt.txt`, `inventory_prompt.txt`). No "Cambridge" appears
in any of the three, so the question is subtler: do the heading conventions,
item-numbering examples and entity examples assume Cambridge's minutes
format? Check each against a sample of council #2's actual PDFs before
extraction, and generalise anything that assumes one CMS's layout.

**4.2 — `Investigator_prompt.txt` Part 0.** This is the concentration of
Cambridge specificity: "One council: the Town of Cambridge", the span, the
580/506/66 document counts, the named 2022–2023 CMS gap, the ~400-councillor
table count, the 100%-NULL planning dates. Part 0 already tells the reader to
prefer `council profile <council>` over its own prose. Finish that move:
Part 0 keeps the *meaning* of each field and why a caveat matters, and every
corpus-specific number becomes a pointer to `profile.<path>`. Per-council
caveats that can't be computed (a known CMS gap) belong in a per-council
notes file the prompt reads, not in the shared layer.

**4.3 — `Explorer_prompt.txt`.** "working from a 30-year corpus", the
Cambridge Authorised Inquiry reference in its era guidance, and the session
log's Cambridge-specific findings. The session log is history and stays; the
operative instructions should not assume one corpus's shape.

**4.4 — `Researcher_prompt.txt`.** Four Cambridge references in a prompt
whose Principle 0 firewall is that it must never make a claim about a specific
council. Check whether each is a legitimate "this project's first corpus"
orientation or a scope leak.

**4.5 — Record the review.** A dated entry (what was read, what changed, what
was deliberately left) in `docs/pipeline/PIPELINE.md` under the prompt-
generalisation bullet, so the next council's onboarding knows this ran.

**Gate:** review recorded; no prompt asserts a corpus fact it can't source
from `profile` or a per-council notes file.

---

## Phase 5 — Onboard the real council #2

Only after Phases 1–4. Follow `PIPELINE.md`'s **"Subsequent corpora
onboarded"** order exactly — it exists to control LLM spend, and the
battery-before-Explorer ordering is the point.

**5.1 — Pick the council.** `PRIVATE_ASSESSMENT.md` suggests Fremantle or
Subiaco (comparable size, public records, politically interesting). Selection
criteria that matter for the work: how far back the records go, whether the
site is the same OpenCities/ASP.NET CMS as Cambridge (which decides how much
of `CambridgeScraper` is reusable), and whether Elections WA covers it.

**5.2 — Registry + scraper.** Add the `COUNCILS` entry in `src/cli.py`, a
`Council` seed row (generalise `seed_cambridge()` in
`src/storage/database.py` into a per-council seed driven by the registry
rather than a second hardcoded function), and
`src/scraper/<council>.py`. If the CMS matches Cambridge's, factor the
OpenCities/Playwright discovery into a shared mixin rather than copying 700
lines. Scraper acceptance: a dry run discovers a document count consistent
with the council's own published index, and `classify_document_type()`
(Phase 1.5) labels a hand-checked sample correctly.

**5.3 — Terms seeding** before Level 0, per PIPELINE.md "Council Setup". If
the council is WA, this is the point to parameterise
`scripts/extract_cambridge_elections.py` into `extract_wa_elections.py
<COUNCIL NAME>` rather than copy it.

**5.4 — Run the sequence:** scrape → census → inventory → typology loop
(reads `DATA_ENRICHMENT.md`'s pattern layer; converge to
`other_content_rate ≤ 20%`) → Level 3 sample validate → full extraction →
dedup / build-relationships / geocode → **`council draft` (battery) before
Explorer** → Explorer scoped to what's novel → Refiner → Editor/Fixer →
human publish.

**5.5 — Checkpoints specific to this plan**, at the points they'd otherwise
be missed:
- After typology: does council #2 introduce meeting types absent from its
  `meeting_bodies.json` entry (Phase 1.4's diagnostic)?
- After the first `council draft`: read every battery verdict against council
  #2's numbers by hand. Phase 0.2's fixture proves the verdicts *vary*; only
  a human read proves they're *true*. This is the last gate before a real
  false claim about a real council can reach a draft.
- Does council #2 have an external-scrutiny window for `council_eras.json`,
  or none?

---

## Phase 6 — The payoff, and doc cleanup

Not readiness work — what a second council is *for*. Sequence after 5.

**6.1 — Cross-council scorecard comparison.** Every `test_id` is stable by
design and the registry is shared, so a two-council comparison view is a
join, not new analysis. This is the first genuine peer base rate the project
has ever had; `tests.py`'s `base_rate` field currently carries within-corpus
comparisons only.
**6.2 — `MapPage` with two live LGAs** (falls out of 3.6).
**6.3 — Doc updates:** correct `PRIVATE_ASSESSMENT.md`'s "the battery runs
out of the box"; add a `docs/MAP.md` row for this file and for
`config/council_eras.json` in the "flipping a gate" / "Where do I add X?"
tables; update `TESTING.md` for the new CI checks; log the publish-path change
in `CICD_DECISIONS.md` if it changes how `publish.yml` works.

---

## Dependency summary

```
Phase 0 (testability, incl. Testville as a dev council)
   ├─► Phase 1 (data layer)  ─┐
   ├─► Phase 2 (publish)      ├─► Phase 4 (prompt review) ─► Phase 5 (onboard) ─► Phase 6
   └─► Phase 3 (frontend) ────┘
            ▲
            └── 2.2 councils.json + 2.5 selector gate 3.2 / 3.6
```

Rough weighting: Phase 1.1 is the largest single body of work (~30 tests);
Phase 3 is the widest (~20 files, mostly small); Phase 5's scraper is the only
genuinely new subsystem and its size depends entirely on 5.1's CMS answer.
