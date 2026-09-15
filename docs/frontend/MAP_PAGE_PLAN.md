# The Map page — implementation plan

**Status:** plan only, nothing built. Written 2026-09-15 against the tree at
commit `70b80ee`, from a read of the publish pipeline, the test battery, the
geocode step and the current `MapPage.tsx`, plus measurements taken against
the live `data/council.db` and the newest Cambridge draft
(`draft_20260915_022213`). Every figure quoted in Part B was measured, not
estimated.

**Scope:** a draggable, zoomable map of Perth/WA where each council in the
system is drawn to its own boundary and coloured by an **overall governance
rating** — and everything that rating needs, because it does not exist yet.
Cross-track: it touches the analysis layer (the rating), the pipeline
(boundaries as an onboarding artifact, the geocode step), publish, and the
frontend.

**Read before starting:** `docs/MAP.md`, then `docs/SECOND_COUNCIL_PLAN.md`
(being implemented in parallel — see "Coordination" at the end of this file,
which names three places the two plans touch the same code),
`docs/frontend/INTERACTIVITY.md` (its hard rule on hardcoded content in
component source applies to every component here) and
`docs/frontend/PRODUCT_ROADMAP.md` F1 (this plan builds that section's
Surface B; Surface A stays open).

---

## Decisions settled 2026-09-15 — not open for re-litigation

Five decisions were taken in design conversation with evidence in front of
them. An implementing session should build them, not re-open them:

1. **The rating rule is a severity floor over a stable base, gated on
   coverage** — not an average of any kind. Part B.2 has the simulation that
   ruled the averages out.
2. **The rating appears as a full-width band above the fold on the
   Overview**, above `LatestMeetingStrip`, carrying the verdict word, the
   counts and a scripted reason.
3. **No 0–100 score anywhere on the band** — confirmed 2026-09-15. The
   colour and a score are computed differently and can disagree on screen: a
   floor can force a band to red on one finding while the share stays high,
   so a council with one integrity flag and everything else clean would
   render "GOVERNANCE CONCERNS — 96/100" and read as a bug. The three-colour
   scale also makes 100 gradations fake precision. The counts are derived
   from the same fields as the colour, so they can never contradict it, and
   they say *what* was measured, which a score does not.
4. **Boundaries are a per-council onboarding artifact** —
   `config/council_boundaries/<key>.geojson`, git-tracked, authored when a
   council is added — merged at publish time into one served file. Not a
   runtime fetch, and not one giant state file doing both jobs.
5. **`/map` stays a top-nav tab and is the discovery surface** — click a
   council, land in that council's Report. It does not become the landing
   page and it does not move under the council subnav.

---

## How to execute this plan

- **One step at a time, in order.** Each step names its files, its change and
  an acceptance check.
- **Stop on any plan-vs-codebase contradiction.** If a file, symbol or
  behaviour described here isn't what you find, stop and ask — every time,
  not just the first time. Symbols move; this was written against `70b80ee`.
- **Stop and ask at every point marked `STOP:`.** Each is a place where this
  plan would widen, or depend on, a rule another doc owns.
- **Commit after each numbered step** — 1.1, then 1.2, and so on — once that
  step's acceptance check passes. Standing authorization for this plan only;
  it does not extend to `council publish`, to a push, or to any other work.
  Rules for those commits:
  - **Never a `Co-Authored-By` trailer, and no mention of Claude, an agent or
    an AI anywhere in the message** (`docs/TESTING.md`, "Commit conventions").
    Write the message as the person who made the change.
  - **Stage only the files that step touched.** `git add -A` is wrong here:
    another agent is working the second-council plan in the same tree and has
    uncommitted changes of its own. Check `git status` before every commit and
    stage by path.
  - Match the repo's message style — a short subject line, then a body saying
    what changed and *why*, with the acceptance-check result where there is
    one. Read a recent `git log` entry before writing the first one.
  - A step that ends blocked at a `STOP:`, or that fails its acceptance check,
    **does not get committed**. Leave the tree dirty and ask.
- Before any deploy, **grep component source** for hardcoded council names,
  claims, era labels and corpus spans. The data-layer publish gate does not
  cover component source — that is the standing lesson of the 2026-08-06
  hardcoded-names incident, and Phases 2 and 5 both add components.

---

## Part A — What's already here

Most of the map's substrate exists; almost none of it is wired up correctly.

- **Leaflet is installed and styled.** `leaflet@1.9.4` + `react-leaflet@4.2.1`
  in `frontend/package.json`, `leaflet/dist/leaflet.css` imported in
  `main.tsx`, and `frontend/src/index.css` already carries `.map-page`,
  `.map-legend*`, `.map-hover-*` and `.map-setup-*` rules plus the
  `.leaflet-*` z-index overrides. Pan and zoom come free from `MapContainer`.
- **A WA boundary file exists locally.**
  `frontend/public/data/wa_lga.geojson` — ABS ASGS Edition 3 (2021) via
  `scripts/download_wa_lga.sh`, 7.6 MB, 139 features, 384,525 vertices.
- **The geocode step exists and works.** `council geocode <key>`
  (`scripts/geocode_sites.py`, Nominatim). Verified live 2026-09-15: two of
  three sample addresses resolved correctly.
- **The battery is already council-agnostic in shape.** Every `TestResult`
  carries `valence`, `grade`, `data_ok` and a stable `test_id`; the registry
  (`config/test_registry.json`) carries the `category`. The rating needs
  nothing from the pipeline that isn't already there.
- **`scorecard` is claim-derived and currently public tier**
  (`CLAIM_DERIVED_SNAPSHOTS` / `derive_claim_tier`, `src/cli.py`), and
  `SNAPSHOT_TIER` is the established way to add a public snapshot.
- **The config-file-plus-loader pattern is established** —
  `config/agent_switches.json` + `src/agent_config.py`. `config/rating.json`
  in Phase 1 follows it exactly.

---

## Part B — What's broken or missing

### B.1 — `MapPage.tsx` is dead code, not merely single-council

It fetches `/data/scorecard.json` and reads `d.summary.supportive` /
`d.summary.critical`. The real shape is
`{published_at, data: {summary: {n_supportive, n_neutral, n_critical,
n_not_computable}, tests: [...]}}` — so `d.summary` is `undefined`, the
property access throws, and the throw lands in the page's own
`.catch(() => {})`. `scores` stays `{}` and **every polygon renders grey,
including Cambridge's**. No error surfaces anywhere.

`docs/SECOND_COUNCIL_PLAN.md` B7 records this file as having a hardcoded
`LGA_TO_KEY` — true, but it undersells the state: the hardcoded entry has
never resolved to a colour.

Two further wrong things in the same file: `scoreColor()` and `scoreLabel()`
invent a supportive-share rating inline (the thing Phase 1 builds properly),
and the legend hardcodes `137`.

### B.2 — There is no overall rating, and the obvious ways to build one are wrong

`battery_summary()` (`src/analysis/tests.py`) returns four counts and nothing
else. Cambridge's newest draft: **10 supportive, 10 neutral, 7 critical, 2
not computable**, across 29 tests.

Four candidate schemes were simulated against that real battery and against
seven synthetic councils — A = severity-weighted index, B = valence ratio
(`critical / (supportive + critical)`), C = worst-finding, D =
category-balanced average:

| Scenario | A | B | C | D |
|---|---|---|---|---|
| Cambridge (real) | 53 | 59 | yellow | 52 |
| **1 integrity flag, all else strength** | **80** | **96** | red | **81** |
| Cambridge + 8 extra mild concerns | 43 | 42 | yellow | 46 |
| **Sparse corpus, passes what it can run (45% computable)** | **67** | **100** | **green** | **67** |
| Cambridge + 10 new Observation tests | 52.3 | 59 | yellow | 51.4 |
| Cambridge + 6 new supportive integrity tests | 59 | 70 | yellow | 54 |
| Everything clean | 83 | 100 | green | 83 |
| **Everything a concern** | 17 | **undefined** | **yellow** | 17 |

What the bold rows establish:

- **Averaging cannot represent "one thing is badly wrong."** A council with a
  live `Integrity flag` — the most serious grade the battery can emit —
  scores green under A, B *and* D, because the other 26 tests dilute it. On a
  choropleth that is the worst available outcome, and it is structural to any
  mean rather than a tuning problem.
- **Green-because-unmeasurable is the sleeper failure.** A council too
  thinly recorded to run half the battery scores 100/100 under B and green
  under all four. This is the *likely* shape of council #2, whose corpus will
  be shorter than Cambridge's 30 years. No formula can see it; coverage has
  to gate the rating from outside.
- **Grade-weighted schemes drift as the battery grows.** Ten purely
  descriptive tests move A from 53.1 to 52.3 and D from 52.0 to 51.4 for a
  council whose conduct did not change. Refiner codifies new tests
  continuously, so a published rating would silently re-colour over time.
  Ignoring neutrals removes this entirely — and 11 of Cambridge's 29 tests
  are `Observation`, so it is a large share of the battery, not a rounding
  effect.
- **B is undefined at the extreme.** The worst possible council divides by
  zero and gets no rating at all.

Two facts about the grade scale, found while simulating, that any implementer
needs:

- **`Integrity flag` and `Commendable` are used by zero of 29 tests.** The
  seven-grade scale is a five-grade scale in practice. The severity floor
  below is therefore **inert today** — correct, and dormant until a test
  grades `Integrity flag`. Do **not** reassign grades to make it fire: that
  is a per-test Refiner-track judgment (`docs/investigator/
  REFINEMENT_PROTOCOL.md`), not something this plan may smuggle in.
- **`governance.power_spread` is `valence=critical` with `grade=Observation`** —
  the one test where the two axes disagree. Phase 1 reads valence for the
  base share and grade for the floor, so this test counts as critical but
  triggers nothing. That is defensible, but it must be asserted rather than
  assumed, so it cannot spread silently.

### B.3 — The boundary file has never reached production

`frontend/.gitignore` ignores `public/data/wa_lga.geojson`. It is not in
`git ls-files`. Vercel has therefore never had it, and production has only
ever rendered the "Map data not loaded" setup overlay — a developer
instruction ("run `bash scripts/download_wa_lga.sh`") shown to the public.

Sizes measured for the decision in Phase 3:

| Variant | Features | Vertices | Size |
|---|---|---|---|
| Raw ABS, all WA | 139 | 384,525 | 7.6 MB |
| Perth-metro subset, raw | 40 | — | 1.02 MB |
| All WA, RDP ε=0.001 | 137 | 49,424 | 1.00 MB |
| All WA, RDP ε=0.002 | 137 | 30,931 | 0.63 MB |
| All WA, RDP ε=0.005 | 137 | 15,420 | 0.32 MB |
| **Cambridge alone, raw** | 1 | 549 | **11.8 KB** |

The 139 → 137 drop is not data loss: the ABS file carries two pseudo-LGAs
with `null` geometry — `No usual address (WA)` and
`Migratory - Offshore - Shipping (WA)`. `MapPage`'s hardcoded `137` happens
to be right, but it should be derived from the file rather than typed.

**One epsilon cannot serve both jobs.** At ε=0.002 Cambridge falls from 549
vertices to **27** — unusable for a council roughly 9 km across, while being
exactly right for a backdrop of remote shires. That measurement is the whole
argument for Phase 3's two-layer split.

### B.4 — The geocode step is sound but half-finished, and is not the boundary source

State of `sites` in `data/council.db` (2,454 rows, all Cambridge):

- **1,828 have coordinates (74.5%)**; 626 do not.
- Of the geocoded, **1,785 (97.6%) fall inside Cambridge's real ABS
  polygon** on a point-in-polygon test. The 43 outside are a mix of genuine
  external sites (Subiaco Oval; Lot 118, Tamala Park, Mindarie — a regional
  joint venture) and real misgeocodes.
- **`sites.suburb` is NULL for all 2,454 rows.** The column exists and is
  never populated, so there is no fallback and no per-council query context.

The 626 failures fall into measured classes:

| Class | Example | Count signal |
|---|---|---|
| Multi-site strings joined by `;` or `&` | `104 Branksome Gardens, City Beach; 2 Adina Way, City Beach` | 162 contain `&`/`and` |
| Ranged street numbers | `Lot 4 (Nos 346-350) Cambridge Street, Wembley` | — |
| Compound numbers | `Lot 37 (No. 77A and 77B) Lake Monger Drive` ; `(No. 94/5)` | — |
| Reversed lot/number order | `No 15 (Lot 301) Bernard Street, Leederville` | — |
| Trailing plan notation | `20 Norbury Crescent, City Beach (Lot 5 on Deposited Plan 27017)` | — |
| Precinct / place names | `Floreat Activity Centre` | — |
| Intersections | `Jersey Street and Grantham Street intersection, Wembley` | — |
| Road reserves | `Salvado Road, road reserve adjoining …` | — |

`_clean_address()` handles exactly two shapes — `Lot N (No. M) …` and
`Lot N …` — so every row above falls through to Nominatim unchanged and
fails. There is also no cache, no record of *why* a row failed, and no
provenance on a coordinate once written.

**The step is worth fixing, but it is not where boundaries come from.** It
produces points *inside* a council; the council's outline comes from ABS /
data.wa.gov.au. The two are different data sources solving different
problems. What geocoding gives this plan is a **validator**: the 97.6%
point-in-polygon figure above is how you know a committed boundary is the
right one. Phase 4 is therefore independent of the map and not a
prerequisite for it.

---

## Phase 1 — The overall rating (data layer)

Nothing in this phase touches the frontend. It ends with a new public-tier
snapshot every council produces on `council draft`.

**1.1 — `config/rating.json`, the rule as data.**
The bands, the floors and the coverage gate live in config, not code,
because **they cannot be calibrated until a second council exists** — one
council is one data point and every threshold below is a judgment call. Say
that in the file's own comment field. Suggested shape:

```json
{
  "version": 1,
  "provisional": true,
  "bands": [
    { "id": "green",  "label": "Broadly clean",       "max_critical_share": 0.20 },
    { "id": "yellow", "label": "Mixed record",        "max_critical_share": 0.45 },
    { "id": "red",    "label": "Governance concerns", "max_critical_share": 1.00 }
  ],
  "floors": [
    { "when": "any_grade", "grade": "Integrity flag", "force_band": "red",
      "reason": "one integrity flag" },
    { "when": "grade_count_in_category", "grade": "Governance concern",
      "min": 2, "force_band": "yellow",
      "reason": "two or more concerns in one category" }
  ],
  "coverage_gate": {
    "min_computable_share": 0.60,
    "min_decisive_tests": 8,
    "band_id": "insufficient",
    "label": "Insufficient record"
  }
}
```

Loader: `src/rating_config.py`, modelled on `src/agent_config.py` — a
dataclass, validation of band ids and monotonic thresholds, a clear error
rather than a silent default on a malformed file.

**1.2 — `src/analysis/rating.py`.**
One pure function:

```python
def compute_rating(battery: list[TestResult], categories: dict[str, str],
                   config: RatingConfig) -> Rating
```

The algorithm, exactly:

1. `computable` = tests with `data_ok`. `decisive` = computable tests whose
   `valence` is `supportive` or `critical`. Neutrals are excluded from the
   denominator — that is what makes the rating stable when the battery grows
   (B.2, row 5).
2. If `len(computable) / len(battery) < min_computable_share` **or**
   `len(decisive) < min_decisive_tests`, return band `insufficient` with
   `band_reason` naming which of the two tripped. Stop here — no share, no
   floor.
3. `critical_share = n_critical_decisive / len(decisive)`. Pick the first
   band whose `max_critical_share` it fits.
4. Apply floors in order. **A floor may only move the band downward**
   (green→yellow→red); a floor that would improve a band is a bug, and the
   function must assert that rather than silently apply it.
5. Return `Rating(band, band_label, band_reason, critical_share,
   n_supportive, n_neutral, n_critical, n_not_computable, n_decisive,
   computable_share, config_version)`.

Two constraints on this function, both deliberate:

- **It reads claim *metadata* only** — `valence`, `grade`, `data_ok`,
  `test_id` (for its category). It must never read `headline`, `verdict`,
  `named_entities` or any prose. That is what makes its output safe at
  public tier no matter what the battery's own claim-derived tier comes out
  as (1.4).
- **`band_reason` is scripted, never authored.** It is assembled from
  `config/rating.json`'s `reason` strings and the counts — the same
  convention `watch.json`'s `why` field already uses and for the same
  reason: it is a sentence about a named council that ships verbatim to the
  public, so no one gets to write it by hand.

**1.3 — Wire it into `council draft`.**
In `_generate_snapshots()` (`src/cli.py`), immediately after the existing
`run_test_battery(...)` call that builds `scorecard`:

- call `compute_rating()` once,
- `_write("rating", asdict(rating))`,
- and include the same object at `scorecard`'s `summary.rating`.

One call, two destinations — never two computations, so the two files cannot
disagree.

**1.4 — `SNAPSHOT_TIER`: `"rating": "public"`.**
Add it with a comment saying why this is safe and why it is deliberately
*not* claim-derived: `rating.json` is a projection of claim metadata with no
name, no quote and no prose in it by construction (1.2), so unlike
`scorecard` it does not need to drop to full tier when one claim turns out to
be individual-unit. This matters concretely — `scorecard`'s tier is derived
per run, so a future battery emitting one named claim would pull the entire
scorecard (and with it every council's colour) off the public site. The map
must not be able to go grey for that reason. Same per-claim-rather-than-
whole-batch carve-out `watch.json` already makes, with the same
justification.

**1.5 — `tests/test_rating.py`.**
Build the eight scenarios from B.2's table as fixtures (they are what the
rule was designed against) and assert band + reason for each. Expected:

| Fixture | Band | Reason |
|---|---|---|
| Cambridge-shaped (7 crit / 17 decisive) | yellow | base |
| 1 integrity flag, all else strength | red | integrity-flag floor |
| + 8 extra mild concerns | red | base |
| Sparse corpus (45% computable) | insufficient | coverage gate |
| + 10 new Observation tests | yellow | base — *unchanged*, the drift test |
| + 6 new supportive integrity tests | yellow | base |
| Everything clean | green | base |
| Everything a concern | red | base |

Plus three invariants:
- a floor never improves a band (property test over generated batteries),
- a battery of zero computable tests returns `insufficient`, never a crash
  or a division by zero,
- **valence/grade consistency** across the real `config/test_registry.json` +
  battery: every `supportive` test grades in the supportive set, every
  `critical` in the critical set. Land this with `governance.power_spread`
  as a single named, commented exception rather than a weakened assertion,
  so the known mismatch is visible in the diff and a second one fails CI.

**Acceptance:** `council draft cambridge --only rating,scorecard` writes a
`rating.json` whose band is `yellow`, reason `base`, `n_decisive` 17,
`critical_share` ≈ 0.41, `computable_share` ≈ 0.93 — and whose block is
byte-identical to `scorecard.json`'s `summary.rating`.

**Gate:** `pytest` and `ruff` green; the eight scenarios pass; no other
snapshot's bytes changed.

---

## Phase 2 — The rating band on the Overview

**2.1 — `frontend/src/api.ts`.** A `RatingData` interface mirroring the
`Rating` dataclass field for field, and `rating: () => getSnapshot<RatingData>("rating")`.

**2.2 — `frontend/src/components/RatingBand.tsx`.**
Renders: the band colour block, the band label, the four counts, the scripted
`band_reason`, and a "How this is calculated" link. Under
`INTERACTIVITY.md`'s hard rule, **every word except the fixed count labels
comes from the `data` prop** — the band label and the reason are config-sourced
strings arriving through the snapshot, never typed into JSX. No council name
appears in this file.

Three rendering rules that fall out of the design:

- **No score on the band — this is settled, not a preference** (Decision 3).
  The band renders the verdict word, the counts, the scripted reason, and
  nothing numeric beyond the counts. Magnitude, where it is wanted, is the
  counts phrased as a ratio — "7 of 17 decisive tests critical" — derived
  from the same fields as the colour, so the two cannot disagree. Do not add
  a 0–100 index, a percentage, a letter grade or a star rating, here or on
  the map hover card (5.3), which reuses this rendering.

  `critical_share` stays in `rating.json` (Phase 1.2): the band is computed
  from it and an auditor needs to see the number the band was derived from.
  It is snapshot data, not a thing the band displays.
- **`insufficient` is a distinct visual state**, not a shade of grey that
  reads as "unknown but probably fine": its own treatment, with the reason
  ("only 13 of 29 tests could be run on this corpus") stated plainly.
- Light/dark via the existing `prefers-color-scheme` tokens in `index.css`,
  default light. The three band colours must stay distinguishable in both,
  and must not be the *only* signal — the label carries the meaning for a
  colour-blind reader.

**2.3 — Place it.** `OverviewPage.tsx`, above `<LatestMeetingStrip />`.

**2.4 — A dev-mode cross-check.** Mirroring `ScorecardPanel`'s existing
`deriveSummary()` pattern: when `scorecard.json` is also available, re-derive
the band in the browser and `console.error` on disagreement with
`rating.json`. Same idea, same reason — two sources of one number that can
drift.

**2.5 — `STOP:` the "How this is calculated" target.**
The natural home is a `/method` section. But `docs/frontend/
METHOD_PAGE_PLAN.md` B.6 requires every figure on that page to trace to one
of the five files under `data/` or the live database, each with its own
`generated_at` — and the rating traces to the battery and to
`config/rating.json` instead. That is a different provenance class, so
widening the rule is a decision for that plan's owner, not this one.
**Stop and ask** before adding the section; until then, link to
`/analysis` (the scorecard) as the honest, already-existing explanation of
where the counts come from.

**Gate:** `npm run lint` and `npm run build` green; the band renders for
Cambridge in both Draft and Publish mode; grep `RatingBand.tsx` for council
names, era labels and corpus spans — expect none.

---

## Phase 3 — Council boundaries as an onboarding artifact

The two-layer split, justified by B.3's measurement that no single
simplification epsilon serves both jobs:

| Layer | File | Fidelity | Purpose |
|---|---|---|---|
| Council | `config/council_boundaries/<key>.geojson` | full (ε ≤ 0.0002) | the precise, hoverable, coloured region |
| Backdrop | `config/wa_lga_backdrop.geojson` | ε = 0.002, ~0.63 MB | grey context, "N of 137 analysed" |

Both git-tracked. Cambridge's council-layer feature is ~12 KB, so the
per-council cost is negligible and stays that way as councils are added.

**3.1 — `scripts/build_boundaries.py` + two CLI entry points.**

`council boundary <key> [--source <path-or-url>] [--lga-name <name>]`
writes `config/council_boundaries/<key>.geojson`: a single `Feature` whose
`properties` carry `council_key`, `lga_name`, `source`, `source_licence`,
`retrieved_at`, `simplify_epsilon` and `n_vertices`. Provenance travels with
the polygon — the same discipline `/method` applies to every other figure on
the site.

`council boundary --backdrop` regenerates
`config/wa_lga_backdrop.geojson`: all real WA LGAs, RDP-simplified at
ε=0.002, coordinates rounded to 4 decimals, **pseudo-LGAs with `null`
geometry dropped** (B.3), properties reduced to the LGA name only.

Fold `scripts/download_wa_lga.sh`'s ABS query into this script as the fetch
step rather than leaving two ways to get the same file; delete the shell
script once the Python path works.

**3.2 — The boundary is validated before it can be committed.**
`council boundary <key>` runs a point-in-polygon check of that council's
already-geocoded sites against the polygon it just wrote, prints the share
inside, and **fails below a configurable floor (suggest 0.90)**. Cambridge
scores 97.6% today (B.4), so this passes on the council we have and would
catch a polygon keyed to the wrong LGA — the failure mode most likely to
survive a code review, because a wrong-but-plausible outline looks fine on
screen. If a council has no geocoded sites, skip the check and say so in the
output; do not pass silently.

**3.3 — `cmd_publish` serves them.** After the existing snapshot copy, write:
- `frontend/public/data/councils.geojson` — a `FeatureCollection` of the
  council-layer features for councils present in `councils.json`,
- `frontend/public/data/wa_lga_backdrop.geojson` — copied from config.

**State plainly in a comment that these two files are config-sourced, not
draft-sourced**, and therefore sit outside the draft manifest's hash check.
The gate verifies that published snapshot bytes match what was reviewed; it
says nothing about these. Someone will otherwise assume it does.

**3.4 — Testville needs no special case.** A synthetic council has no
`config/council_boundaries/testville.geojson`, so it contributes no feature
and simply does not appear on the map. Leave a one-line comment saying so, so
the next reader doesn't add a guard that isn't needed.

**3.5 — Clean up the old file.** Remove the `public/data/wa_lga.geojson` line
from `frontend/.gitignore`, delete the stale 7.6 MB
`frontend/public/data/wa_lga.geojson` and the `frontend/dist/data/` copy.

**3.6 — Record it as an onboarding step.** Add `council boundary <key>` to
`docs/pipeline/PIPELINE.md`'s "Council Setup" / corpus-onboarding order,
alongside terms seeding. Adding a council should mean sourcing its boundary,
the same way it means sourcing its terms.

**Acceptance:** `council boundary cambridge` writes a ~12 KB file and reports
97.6% of sites inside; `council boundary --backdrop` writes ~0.63 MB with 137
features; a publish produces both served files and `git status` shows the
config files tracked.

---

## Phase 4 — The geocode step: repair and repurpose

**Independent of the map.** It is not a prerequisite for any other phase —
it is worth doing because B.4 shows a quarter of Cambridge's sites are
missing coordinates for reasons that are all fixable, and because it is what
validates a boundary in 3.2. It can be worked before, during or after the
rest.

**4.1 — Extend `_clean_address()` to the measured patterns.** One regex per
class from B.4's table, each with the real example from the corpus as its
docstring/test case: ranged numbers (`(Nos 346-350)` → first), compound
numbers (`(No. 77A and 77B)`, `(No. 94/5)` → first), reversed order
(`No 15 (Lot 301) X` → `15 X`), trailing plan notation
(`… (Lot 5 on Deposited Plan 27017)` → stripped).

**4.2 — Split multi-site strings.** Addresses joined by `;` or ` & ` are
several sites in one row. Geocode the first component and record that the row
was split; do not silently present one site's coordinates as if the row had
one address.

**4.3 — Populate `sites.suburb`.** NULL on all 2,454 rows. Derive it from the
address tail during geocoding. It gives a fallback (suburb centroid for an
unaddressable row) and a better Nominatim context string than the current
fixed `"WA Australia"`.

**4.4 — Record provenance.** New nullable columns on `sites`:
`latitude_source` (`nominatim` / `manual` / `suburb_centroid`),
`geocoded_at`, `geocode_note`. There is no migration framework here —
follow `src/storage/database.py`'s existing ad-hoc `ALTER`-on-startup
convention and say in a comment that that is what this is.

**4.5 — Cache, including negatives.** `data/<key>/geocode_cache.json`, keyed
by the cleaned query string, storing hits *and* misses. Today a re-run
re-queries every failed row against Nominatim forever at 1.1 s each; caching
misses is both faster and better manners under Nominatim's usage policy.
(Note the `data/<key>/` prefix — it matches `SECOND_COUNCIL_PLAN` 1.3's
namespacing of per-corpus artifacts. If that step hasn't landed, use it
anyway; it is where the file belongs.)

**4.6 — `--report`.** Write `data/<key>/geocode_report.json`: coverage,
failures grouped by the classes in 4.1–4.2, and the point-in-polygon result
against the council's boundary. This is the artifact that makes the step
auditable and the one 3.2 reuses.

**4.7 — Accept an irreducible remainder.** Precinct names, intersections and
road reserves are not street addresses and should not be forced through a
street geocoder. Record them as `unaddressable` and stop. **Target ≥90% of
address-shaped rows, not 100%** — a plan that implies otherwise will produce
a session inventing coordinates.

**Acceptance:** a `--dry-run` shows the new cleaners resolving the B.4
examples; a real run raises coverage from 74.5% toward 90%+ of
address-shaped rows; `geocode_report.json` classifies every remaining
failure; the in-boundary share does not fall below 97.6%.

---

## Phase 5 — The Map page

Needs Phase 1 (the rating), Phase 3 (the boundaries) and
`SECOND_COUNCIL_PLAN` 2.2's `councils.json`.

**`STOP:` read "Coordination" below before starting.** This phase
**supersedes** `SECOND_COUNCIL_PLAN` step 3.6, and it cannot begin until that
plan's `councils.json` exists — building a second council list instead would
be exactly the duplication that plan exists to prevent.

**5.1 — Rewrite the data layer.** Delete `LGA_TO_KEY`, `scoreColor()`,
`scoreLabel()` and the `/data/scorecard.json` fetch. `MapPage` reads exactly
three files:
- `/data/councils.json` — key, display name, and each council's `rating`
  block,
- `/data/councils.geojson` — the council layer, each feature carrying its own
  `council_key`, so features join by key and **no name-matching table
  exists**,
- `/data/wa_lga_backdrop.geojson` — the grey context layer.

**5.2 — Two `<GeoJSON>` layers.** Backdrop underneath, single grey style,
non-interactive (no hover, no click, no cursor change). Council layer on top,
filled from `rating.band`, interactive.

**5.3 — Hover and click.** Hover shows the band colour, the band label, the
counts and the scripted `band_reason` — reusing Phase 2's rendering, so the
map and the Overview can never say different things about the same council.
Click sets the active council and navigates to its Report. Per
`SECOND_COUNCIL_PLAN` 3.2 the selected council lives **in the route**, not in
component state, so the link is shareable and survives a reload.

**5.4 — Derive the legend.** "N of M analysed" comes from the two files'
lengths, not the literal `137`. Four entries: the three bands plus
`Insufficient record` — the fourth state is meaningless to a reader unless
the legend names it.

**5.5 — Default view.** Fit bounds to the union of the council layer's
features, so the map opens on Perth while there is one Perth council, and
opens correctly on whatever set exists later — no hardcoded metro bounding
box. Zooming out reveals the WA backdrop. Keep `WA_CENTER`/`WA_ZOOM` only as
the empty-council-list fallback.

**5.6 — Replace `MapSetupOverlay`.** The boundary files now ship, so the
"run the download script" instruction is wrong and was always public-facing.
Replace it with a real error state for a genuinely failed fetch.

**5.7 — Touch and small screens.** The hover card needs a tap equivalent;
the map needs a sensible height inside the site layout at phone width.

**5.8 — A keyboard-navigable list beneath the map.** Every council with a
rating, as links, with band and label as text. A Leaflet polygon is not
keyboard-reachable, so without this the discovery surface is unusable for
some readers — and it doubles as the fallback when tiles fail to load.

**Gate:** `npm run lint` and `npm run build` green; Cambridge renders yellow
and clicking it lands on its Report; grep every touched `.tsx` for council
names, era labels and corpus spans before any deploy.

---

## Phase 6 — Docs, CI and the roadmap

**6.1 — `docs/MAP.md` "Where do I add X?" rows:**
- changing what the overall rating means → `config/rating.json` (the bands,
  floors and coverage gate), with `src/analysis/rating.py` owning the
  computation — same split as `test_registry.json` vs `tests.py`
- adding or replacing a council's boundary → `council boundary <key>` →
  `config/council_boundaries/`
- building or changing the map → this file

**6.2 — `docs/frontend/PRODUCT_ROADMAP.md` F1.** Mark Surface B built and
correct the line describing "the existing Leaflet map on `/map`" — B.1 shows
it never rendered a colour. Surface A (the per-council static graphic with
tender dots) stays open, and Phase 4 is what unblocks it.

**6.3 — `docs/frontend/INTERACTIVITY.md`.** Register `RatingBand` and the map
hover card as components under the hard rule (widened by
`SECOND_COUNCIL_PLAN` 3.1 to cover council names, narrative conclusions, era
labels and corpus spans).

**6.4 — `docs/TESTING.md`.** The new tests, and the fact that
`config/council_boundaries/` → `frontend/public/data/` is a publish path that
the draft hash check does not cover (3.3).

**6.5 — `CICD_DECISIONS.md`.** A dated entry only if publishing the two new
served files changes how `publish.yml` works.

**6.6 — Read the prose back before committing each doc change** in this phase
(and any prose written in earlier phases) for stock phrasing that diverges
from this project's doc voice, per the standing note on AI voice tells. The
same applies to the commit messages themselves.

---

## Coordination with `docs/SECOND_COUNCIL_PLAN.md`

Both plans are live. Three places they touch the same code, and one where
they disagree:

1. **`MapPage.tsx` — this plan supersedes `SECOND_COUNCIL_PLAN` 3.6.** That
   step says to build `LGA_TO_KEY` and the score objects from the council
   list; Phase 5.1 deletes `LGA_TO_KEY` outright, because per-council
   features carry their own `council_key` and there is nothing to match by
   name. Whichever lands second must not re-introduce it. If 3.6 has already
   been done when you reach Phase 5, treat it as the starting point and
   remove the name-matching table.
2. **`councils.json` is owned by `SECOND_COUNCIL_PLAN` 2.2.** This plan adds
   two fields to each row — the `rating` block and a `has_boundary` flag — it
   does not create a parallel file. **If 2.2 has not landed when you reach
   Phase 5, stop and ask.** Building a second council list would be exactly
   the kind of duplication that plan exists to prevent.
3. **`STOP:` publish paths.** `SECOND_COUNCIL_PLAN` 2.1 moves public snapshots to
   `frontend/public/data/<key>/`. `rating.json` moves with them.
   `councils.json`, `councils.geojson` and `wa_lga_backdrop.geojson` stay at
   the top level — they are cross-council indexes, not one council's data.
   If 2.1 has landed, follow it; if it has not, ask rather than guessing
   which shape to write, because a published path is expensive to move once
   a deploy has served it.
4. **`SECOND_COUNCIL_PLAN` Phase 1.1 will change Cambridge's band.** Deriving
   ~30 hardcoded verdicts from data will change some valences, and therefore
   the critical share. That is expected and correct. Phase 1.5's tests use
   fixtures rather than Cambridge's live numbers precisely so they don't
   break when it happens — but the Overview band and the map will change
   colour, and that should not be mistaken for a regression.

---

## Dependency summary

```
Phase 1 (rating: config + rating.py + rating.json snapshot)
   ├─► Phase 2 (Overview band)
   └─► Phase 5 (Map page) ◄── Phase 3 (boundaries: config + publish)
                           ◄── SECOND_COUNCIL_PLAN 2.2 (councils.json)

Phase 4 (geocode) — independent; 3.2 reuses its point-in-polygon check,
                    which already works against today's 1,828 geocoded sites
Phase 6 (docs/CI) — last
```

Rough weighting: Phase 1 is small and fully specified (the algorithm is eight
numbered lines and the test table is written). Phase 3 is the one new
subsystem, and its size is mostly the RDP simplifier and the CLI wiring.
Phase 5 is a rewrite of a 270-line file that currently does nothing correct,
so there is little to preserve. Phase 4 is the longest tail and the least
urgent.
