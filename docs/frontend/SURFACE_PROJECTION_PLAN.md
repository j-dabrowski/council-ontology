# Scorecard and Analysis as pure registry projections

Status: **built** (Steps 1–6, 2026-09-06). Written 2026-09-06.
Third in the sequence: `TEST_REGISTRY_PLAN.md` (built) established the registry;
`PANEL_FRAMING_PLAN.md` (built) fixed the labels, the severity chip and the
headings. This plan makes the two surfaces projections of the registry rather
than pages that happen to read it.
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

---

## Part A — What is already true, and what is not

### A.1 The scorecard is already most of what the brief specifies

`ScorecardPanel.tsx` today resolves the snapshot through `resolveTests()`,
groups with `groupByCategory`, renders every row including the two
not-computable ones, and shows the four valence counts at the top. "Every
registry row, corpus scope, compact rows, grouped by category, with valence
counts at the top" is a description of the current page.

What is actually left to do there is small and specific: counts derived from the
rendered rows rather than from the snapshot's own summary (B.4), two stale
sentences (A.5), and the comparability paragraph (Step 5). Steps 4 and 5 are
correspondingly short. **Do not rebuild what already holds** — this plan's
weight is in Steps 1–3.

### A.2 `has_deep_dive` means something narrower than the brief assumes

The brief: *Analysis = registry rows where `has_deep_dive` is true.* Applied to
the registry as it stands, that renders **13 panels, not 29** — because
`TEST_REGISTRY_PLAN.md` B.4 defined `has_deep_dive` as "has an entry in
`BESPOKE_PANELS`", and 13 tests do.

The other 16 split cleanly, and the split is what decides the question:

| | count | what they have |
|---|---|---|
| registered bespoke component | 13 | a dedicated panel |
| no bespoke component, **but a chart payload** | **14** | render today through the generic `BatteryTestPanel` |
| no component, no chart | 2 | `procurement.single_source`, `finance.reserve_trajectory` — both `data_ok: false` |

So every test either has a panel component, or has a chart, or is not
computable. Taking the brief literally drops those 14 charts off the site. See
B.1 — this is the one decision to settle before Step 1.

### A.3 The cross-page deep links are broken today, not merely hand-written

The brief asks for links that "resolve through registry ids, not hand-written
hrefs". They are hand-written — `href={`#panel-${t.detail_panel}`}` on the
scorecard row, `href={`#${backTo}`}` from `Card` — but the more important fact
is that **neither direction can work at all**, and has not since the
Overview/Analysis split:

`App.tsx` uses `HashRouter`. The route lives in the hash (`/#/analysis`), so a
fragment href like `#panel-declared` does not scroll — it replaces the route
with `/panel-declared`, which matches none of the seven `<Route>`s and has no
catch-all, so `<Routes>` renders nothing below the header. The same applies to
the `↑ Scorecard` back-link (`#sc-declared`).

The `.sc-row:target` highlight in `index.css:1475` is the tell: it was written
when the scorecard and the panels shared one page (the since-deleted
`HomePage.tsx`), and nothing replaced it when they were split across routes.

**Step 2 verifies this in the dev server before designing around it.** If the
links turn out to work, the step gets simpler; do not skip the check.

### A.4 The shared components from the framing work are not applied uniformly

`PANEL_FRAMING_PLAN.md` populated `objection`/`response` for all 29 rows and
built `SeverityChip`. The panels have not caught up:

- **`ObjectionResponse` is missing from 4 of the 13** bespoke panels —
  `TenurePanel`, `EngagementChart`, `ObjectionDosePanel`, `ContestationChart`
  (`TrendsChart.tsx`) — even though their registry rows carry the text.
- **`SeverityChip` appears in none of the 13.** It is rendered only by
  `ScorecardPanel` and the generic `BatteryTestPanel`, so a bespoke panel shows
  no severity at all.

Both are call-site omissions, and both disappear if the page composes the shared
blocks instead of each panel remembering to (B.3).

### A.5 Two sentences on the scorecard describe the pre-split layout

Its intro says "Unlike the panels **below**…", and its closing note says "where a
panel **below** explores it in depth, the row says so". The panels have not been
below the scorecard since Analysis became its own route. Both need correcting in
Step 5, alongside the comparability paragraph.

---

## Part B — Decisions

### B.1 `has_deep_dive` becomes "renders a panel". 27 rows, not 13. RECOMMENDED.

Two readings are available, and the brief supports the wider one:

- **27** — `has_deep_dive` means *an analysis panel exists for this test*, which
  is how the field was defined in the original registry brief ("whether an
  analysis panel exists"). The component registry gains an entry for each of the
  14 chart-bearing tests, pointing at the generic `BatteryTestPanel`. Analysis
  renders 27; the 2 not-computable rows appear on the scorecard only. **Nothing
  is lost.**
- **13** — `has_deep_dive` keeps `TEST_REGISTRY_PLAN.md` B.4's narrower meaning
  ("has a *bespoke* component"). Analysis becomes a curated set of 13 rich
  panels and the scorecard is the complete index. A legitimate product shape —
  but 14 charts leave the site.

Take **27**. Besides matching the field's original definition, it is the only
reading consistent with this brief's own constraint that no displayed figure may
change: the 14 charts in A.2 are displayed figures, and dropping them changes
what the site shows. The bespoke-vs-generic distinction is not lost — the
component registry itself records it, one line per test.

If the curated 13 is what is wanted, that is a one-word change to Step 1 and the
14 tests in A.2's middle row are exactly what disappears. Decide before Step 1;
do not let it be settled by an implementation detail later.

### B.2 Links resolve through one anchor module. Query param, not fragment.

`HashRouter` owns the hash, so a fragment anchor cannot coexist with a route
(A.3). Deep-link through a search param on the hash route instead —
`#/analysis?test=<id>` and `#/?test=<id>` — which `useSearchParams` reads
normally, and which is shareable.

One module, `frontend/src/registry/anchors.ts`, is the only place either
direction is expressed:

```ts
analysisHref(testId): string   // "#/analysis?test=<id>"
scorecardHref(testId): string  // "#/?test=<id>"
useScrollToTest(): void        // reads ?test=, scrolls the match into view, flags it
```

The anchor hook on the element is `data-test-id={t.id}` — the raw registry id,
selected with `[data-test-id="…"]`. Do **not** derive an HTML `id` by
substituting characters in the test id: ids contain dots, `querySelector("#a.b")`
parses the dot as a class, and any escaping scheme is a second identifier
namespace to keep in step with the first. One attribute, one id, no encoding.

`.sc-row:target` is replaced by a class the scroll effect applies, since
`:target` cannot fire without a fragment.

No component writes an href by hand after Step 2. That is the testable form of
the brief's "resolve through registry ids".

### B.3 The analysis page composes; a panel only draws its chart.

Today each of the 13 bespoke panels renders its own `<Card title subtitle
valence finding backTo>` — thirteen identical prop blocks, all computed from the
same `test` — and then remembers (or forgets, per A.4) to add
`ObjectionResponse`.

Invert it. `AnalysisPage` renders one shell per row: `<Card>` with the props
taken from the registry entry, the `SeverityChip`, the registered component's
output as the body, then `<ObjectionResponse test={t} />`. Each panel becomes
body-only and stops importing `Card`, `SeverityChip` and `ObjectionResponse`.

This is what "pure projection" means in practice, it removes the 13 duplicated
prop blocks, and it makes A.4's omissions structurally impossible rather than
fixed-for-now. It is also the largest single diff in this plan — 13 files —
which is why it is its own step with a per-panel checklist (C.2).

`ObjectionResponse` keeps its own null-guard, so a row without the pair renders
nothing and the shell needs no conditional.

### B.4 Valence counts are derived from the rendered rows, and asserted.

The header counts come from `data.summary`, computed in Python
(`battery_summary()`). If the registry and the snapshot ever diverge — a row
`resolveTests()` skips — the header would disagree with the rows underneath it.

Derive the four counts from the resolved rows, and `console.error` when they
differ from `data.summary`. Deriving alone would let a number change silently,
which the brief forbids; asserting alone would leave the header describing a
different set than the page. Both together mean the number can only be right or
loudly wrong.

### B.5 "Compact rows" describes the current row. Do not trim fields.

The scorecard row renders title, severity chip, finding, verdict, category,
principles, n, era and the panel link — compact relative to a panel, which is
the contrast the brief is drawing. Dropping any of them would remove displayed
content mid-refactor.

If fields should come out of the row, that is a separate instruction naming
them. An implementer must not decide which of `verdict`, `principles` or `era`
is surplus while doing this work.

---

## Part C — Tables

### C.1 What renders where, after Step 1

Under B.1's recommended 27. `component` is the entry in the new registry map.

| id | component | analysis | scorecard |
|---|---|---|---|
| `procurement.threshold_gaming` | `BatteryTestPanel` | ✓ | ✓ |
| `procurement.incumbency` | `BatteryTestPanel` | ✓ | ✓ |
| `procurement.single_source` | — (not computable) | — | ✓ |
| `procurement.concentration` | `TenderConcentrationPanel` | ✓ | ✓ |
| `procurement.decider_supplier_conflict` | `BatteryTestPanel` | ✓ | ✓ |
| `conflict.recusal_management` | `ConflictRecusalPanel` | ✓ | ✓ |
| `conflict.recusal_trend` | `RecusalTrendPanel` | ✓ | ✓ |
| `conflict.delegate_body_conflict` | `BatteryTestPanel` | ✓ | ✓ |
| `planning.big_dollar_leniency` | `BatteryTestPanel` | ✓ | ✓ |
| `planning.repeat_applicant` | `BatteryTestPanel` | ✓ | ✓ |
| `planning.objection_responsiveness` | `ObjectionDosePanel` | ✓ | ✓ |
| `governance.officer_ratification` | `DivergencePanel` | ✓ | ✓ |
| `governance.power_spread` | `PowerPanel` | ✓ | ✓ |
| `governance.oversight_body_capture` | `BatteryTestPanel` | ✓ | ✓ |
| `governance.unanimity_trend` | `ContestationChart` | ✓ | ✓ |
| `governance.chair_capture` | `MayoralAgendaPanel` | ✓ | ✓ |
| `governance.durable_faction` | `SponsorshipNetworkPanel` | ✓ | ✓ |
| `governance.incumbency` | `TenurePanel` | ✓ | ✓ |
| `governance.freshman_effect` | `BatteryTestPanel` | ✓ | ✓ |
| `governance.election_cycle` | `BatteryTestPanel` | ✓ | ✓ |
| `governance.attendance` | `BatteryTestPanel` | ✓ | ✓ |
| `transparency.confidential_share` | `TransparencyTrendPanel` | ✓ | ✓ |
| `transparency.confidential_tender_size` | `BatteryTestPanel` | ✓ | ✓ |
| `transparency.confidential_topics` | `BatteryTestPanel` | ✓ | ✓ |
| `finance.eoy_spending` | `BatteryTestPanel` | ✓ | ✓ |
| `finance.reserve_trajectory` | — (not computable) | — | ✓ |
| `engagement.participation` | `EngagementChart` | ✓ | ✓ |
| `engagement.deputation_dissent` | `BatteryTestPanel` | ✓ | ✓ |
| `engagement.question_responsiveness` | `QuestionResponsivenessPanel` | ✓ | ✓ |

**27 analysis panels · 29 scorecard rows · 2 scorecard-only.**

### C.2 Step 3's per-panel checklist

Each of the 13 loses its `<Card>` wrapper and its own copies of the shared
blocks, and returns its body as a fragment. Tick every column per file.

| Panel | drops `<Card>` | drops `ObjectionResponse` | keeps chart + drill-downs |
|---|---|---|---|
| `ConflictRecusalPanel` | ✓ | ✓ | ✓ |
| `RecusalTrendPanel` | ✓ | ✓ | ✓ |
| `TenderConcentrationPanel` | ✓ | ✓ | ✓ |
| `DivergencePanel` | ✓ | ✓ | ✓ |
| `PowerPanel` | ✓ | ✓ | ✓ |
| `SponsorshipNetworkPanel` | ✓ | ✓ | ✓ |
| `MayoralAgendaPanel` | ✓ | ✓ | ✓ |
| `TransparencyTrendPanel` | ✓ | ✓ | ✓ |
| `QuestionResponsivenessPanel` | ✓ | ✓ | ✓ |
| `TenurePanel` | ✓ | — (never had it) | ✓ |
| `EngagementChart` | ✓ | — | ✓ |
| `ObjectionDosePanel` | ✓ | — | ✓ |
| `ContestationChart` (`TrendsChart.tsx`) | ✓ | — | ✓ |

`BatteryTestPanel` also loses its own `Card`/chip/`ObjectionResponse` and becomes
the body-only generic renderer. `DigestPage` still needs the card-wrapped form —
it renders meeting-scoped tests outside the analysis shell — so keep
`BatteryTestCard` as the wrapped variant and have the shell use the body only.
`OverviewPanel` keeps its own `ObjectionResponse` in props mode; it has no
registry row and is not part of this projection.

---

## Part D — The steps

Six steps. Step 1 is data and wiring; 2 fixes the links; 3 is the large one; 4–5
are the scorecard; 6 verifies and documents.

Every step ends with `npm run lint && npm run build` from `frontend/`; steps
touching `config/test_registry.json` also need `pytest -q` from the repo root.

**Standing context for every step.** Read `docs/MAP.md`,
`docs/frontend/TEST_REGISTRY_PLAN.md` Parts B–C,
`docs/frontend/PANEL_FRAMING_PLAN.md` Part B, and
`docs/frontend/INTERACTIVITY.md`'s **hard rule**.

**The constraint that governs every step:** *no displayed figure may change.* If
a number differs from the current page after a change, **stop and report the
discrepancy — do not accept it.** The mechanism, since none of this touches the
data path, is omission rather than alteration: before editing a component, write
down every field of `ResolvedTest` its JSX renders; after editing, diff that
list. A field that stopped rendering is a discrepancy and gets reported, not
absorbed.

**Chart components stay where they are.** The registry references them; it does
not absorb them. No chart code moves into `registry/`, and no chart is rewritten
in this plan.

**One commit per step.** A step whose acceptance checks pass is committed before
the next starts; if they fail, do not commit — report. Subject names the plan and
step number, body at most a couple of sentences. `docs/TESTING.md` "Commit
conventions" applies in full: **no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — The component registry, and `has_deep_dive` widened

Settle B.1 first; this step assumes the recommended 27.

1. Rename `frontend/src/bespokePanels.tsx` to
   `frontend/src/registry/components.tsx`, exporting `PANEL_COMPONENTS`. Keep
   every import pointing at `components/` — the map references the chart
   components where they live and absorbs none of them.
2. Register `BatteryTestPanel` for the 14 chart-bearing tests in A.2, so the map
   has 27 entries. Update the module comment: an entry means "this test renders
   a panel on /analysis", and the value says which component draws it.
3. Set `has_deep_dive: true` for those 14 rows in `config/test_registry.json`
   (27 true, 2 false).
4. Update `tests/test_test_registry.py` — it asserts `has_deep_dive` ⟺
   `BESPOKE_PANELS` keys in both directions. Repoint it at
   `PANEL_COMPONENTS` in the new file and confirm it still bites: flip one row,
   see red, revert.

No page changes yet — `AnalysisPage` still renders all 29 through its own fork.
Acceptance: 27/2 split; `pytest -q` green; build + lint.

---

### Step 2 — Anchors, and the broken deep links

**Verify first.** Run `npm run dev`, open `/#/`, click a scorecard row's
"↓ jump to full panel", and record what happens. Then from `/#/analysis` click a
panel's "↑ Scorecard". Report both observations before writing code — A.3 says
both blank the page, and the fix below assumes it; if the behaviour differs,
stop and say so.

Then build `frontend/src/registry/anchors.ts` per B.2: `analysisHref`,
`scorecardHref`, `useScrollToTest`. Wire it:

- scorecard rows carry `data-test-id={t.id}`; the "jump to full panel" link uses
  `analysisHref(t.id)` and appears for every row where `has_deep_dive` is true;
- analysis sections carry `data-test-id={t.id}`; `Card`'s `backTo` takes a test
  id and builds its href with `scorecardHref`, replacing the `sc-` string it
  takes today;
- both pages call `useScrollToTest()`, which scrolls the matching
  `[data-test-id]` into view and applies a highlight class;
- delete `.sc-row:target` from `index.css` and add the class-based highlight in
  its place.

Grep for a surviving hand-written link when done:
`grep -rn '#panel-\|#sc-\|href="#' frontend/src` should return nothing but the
anchors module.

Acceptance: both directions demonstrably scroll to the right test, across pages,
in the dev server. Say which tests you clicked.

---

### Step 3 — The analysis page composes the shell

The large step (B.3, checklist C.2). Work in two passes and commit once.

**Pass 1 — the shell.** `AnalysisPage` filters to `has_deep_dive`, groups with
`groupByCategory`, and renders per row: `<Card>` (title `title_technical`,
subhead `finding` through `RedactedText`, valence, `backTo` the test id) →
`<SeverityChip severity={t.severity} />` → the `PANEL_COMPONENTS[t.id]` body →
`<ObjectionResponse test={t} />`. `question_technical` stays in the meta line
where `PANEL_FRAMING_PLAN.md` Step 8 put it.

**Pass 2 — the panels.** Take the 13 through C.2's checklist: each drops its
`<Card>` wrapper and returns a fragment; the nine that render
`ObjectionResponse` drop it; nothing inside a card body changes — charts,
drill-downs, `SourceQuote` receipts and `CouncillorLink`s are untouched.
`BatteryTestPanel` gets the same treatment while `BatteryTestCard` keeps the
wrapped form for `DigestPage`.

The named-individual guardrail must still cover every path that renders
`finding` — the shell now owns that render, so confirm `RedactedText` wraps it
there, and that no panel lost a guarded path in the process.

Acceptance: build + lint; `/analysis` shows **27** panels, each with a severity
chip and an Objection/Response block, in the same category order as before; the
2 not-computable tests are absent from `/analysis` and present on the scorecard.
Report the field-list diff the standing constraint asks for, per panel.

---

### Step 4 — Scorecard counts derived and asserted

Per B.4: compute the four valence counts from the resolved rows;
`console.error` naming both figures when they differ from `data.summary`.
Confirm the rendered numbers are unchanged against the current page —
10 supportive / 10 neutral / 7 critical / 2 not computable on
`draft_20260904_082327`. Any difference is a discrepancy to report, not to fix
by adjusting the derivation.

Nothing else about the row changes (B.5).

Acceptance: same four numbers; a deliberately mismatched registry produces the
console error; build + lint.

---

### Step 5 — The comparability paragraph, and the stale sentences

Replace the scorecard's intro paragraph with one short paragraph stating the
comparability claim explicitly. It must say three things, plainly:

1. this battery runs unmodified on any WA council whose minutes yield the
   required schema;
2. test ids are stable across councils, so results line up test by test;
3. "not computable" is itself a comparable signal — about a council's
   record-keeping, not about its conduct.

Keep it short; keep the existing point that clean results are shown rather than
hidden. Then fix the two sentences in A.5 that still say "the panels below" —
the panels are on `/analysis` now, so link there rather than gesturing
downward.

The third claim is the one to get right: "not computable" says the corpus lacks
the fields, which is a statement about records, and the paragraph must not let
it read as a finding about the council's behaviour.

Acceptance: build + lint; paste the new paragraph into the handoff summary for
review as copy.

---

### Step 6 — Figure parity and documentation

Walk `/` and `/analysis` in DRAFT mode against the pre-refactor pages and
confirm, test by test, that every figure is unchanged: the four header counts,
and per row/panel the finding, n, base rate and era. Report the walk — which
surfaces, how many rows, what you compared. If anything differs, report it and
stop; do not reconcile it.

Then:
- `docs/frontend/INTERACTIVITY.md` — a panel is a body-only component; the
  analysis page owns the card, the severity chip and the Objection/Response
  block; cross-surface links go through `registry/anchors.ts` and nowhere else.
- `docs/frontend/TEST_REGISTRY_PLAN.md` — note `has_deep_dive`'s widened meaning
  (B.1) against B.4, which defined it narrowly, and that `bespokePanels.tsx` is
  now `registry/components.tsx`.
- `docs/MAP.md` — the "building a panel or a drill-down" row: panels are
  registered in `registry/components.tsx` and render body-only.
- Mark this file's status **built**.

---

### Deliberately not in this plan

Trimming any scorecard row field (B.5) · moving chart code into `registry/` ·
migrating off `HashRouter` (B.2 works within it) · the lay-facing surface
`title_public` is still waiting for · rendering `caveats` · re-wiring the four
individual-implicating orphan panels (`TEST_REGISTRY_PLAN.md` Step 12) · any
change to a computed number, anywhere.
