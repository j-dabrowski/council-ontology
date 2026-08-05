# Panel Interactivity — Build Plan & TODO

A standing backlog for making every panel explorable. The goal: a reader can
click any data element (a bar, a slice, a point, a row, a cell) to reveal the
**underlying records**, each carrying its **verbatim minute quote** (the
"receipt") from `extraction_evidence`. This deepens trust and turns aggregates
into something a resident can inspect case by case.

Like the test battery, interactions should be **repeatable across councils** —
they read from the same snapshots/tables, so adding a council inherits them.

---

## The established pattern (proven on the conflict panel — reuse verbatim)

The recipe, end to end (see `[INTERACT]` in `../investigator/INVESTIGATIONS.md` Phase H):

1. **Export the granular records onto the snapshot** in `src/cli.py` (inline).
   Drive the detail off the *same* entity the chart element represents, so the
   drawer matches the bar. Attach **one `extraction_evidence` quote** per record
   (join `entity_table` + `entity_id`).
2. **Type it** in `frontend/src/api.ts` (a `*Detail` interface on the snapshot).
3. **Render with the shared components** in `frontend/src/components/DrillDown.tsx`:
   - `<DrillDown title subtitle onClose>` — the drawer (auto-scrolls into view on
     open; `scroll-margin-top` keeps it clear of the top edge).
   - `<SourceQuote quote=…>` — the collapsible verbatim-minute "receipt".
4. **Make the chart element clickable** — `onClick` on the recharts `<Bar>` /
   `<Cell>` / point (or a table row) sets a `selected` state; render `<DrillDown>`
   below the chart.

### Hard rule: never hardcode a councillor name or a specific finding in component source

**No `.tsx` file may contain a literal councillor name, a specific vote/dissent/
recusal number, or a narrative claim about a named individual as a string
constant.** Every name and every stat a panel renders must be computed from its
`data` prop (ultimately: the snapshot JSON, ultimately: the database) at render
time — e.g. "the councillor with the highest `dissent_n`," never `"Rod Bradley"`.

**Why this is a hard rule, not a style preference:** it's easy for a panel to be
written by turning a real investigation finding into an "illustrative" worked
example, using the real answer (a real name, a real dissent rate) directly in
JSX instead of computing it from data. Nothing catches that at build time —
`tsc`/`eslint` don't know what a councillor name is — and the draft/publish
gate (`docs/TESTING.md`) doesn't catch it either, because that gate controls
*data reaching `frontend/public/data/`*, not strings baked into component
source. A hardcoded name in a `.tsx` file ships in the compiled bundle on
every deploy regardless of which data file is loaded — including a
placeholder-data deploy explicitly built to contain zero real content. The
two are separate holes; closing one does nothing for the other, which is why
this needs to be an explicit, checked rule rather than an assumption.

**How to apply:** when building or reviewing a panel (by hand or via an agent),
every specific name/number in prose must trace to a `.sort()`/`.filter()`/`.find()`
over the `data` prop, computed in the component body, not typed as a literal. If a
narrative claim can't be derived from the fields the snapshot actually exposes
(e.g. "when the two sat opposite each other, X's side won 83% of the time" — no
such cross-reference exists in `PowerData`), drop the claim rather than hardcode
it — don't invent a data field just to justify keeping the sentence.

### Cross-cutting behaviours — DONE (apply to every panel)
- [x] **Auto-scroll to opened detail** — `DrillDown` calls `scrollIntoView` on open.
- [x] **Back-link to the scorecard row** — `Card` takes a `backTo="sc-<panel>"`
  prop → "↑ Scorecard" link; scorecard rows carry `id="sc-<panel>"` and flash on
  `:target`. Wired on all 10 scorecard-linked panels.
- [x] **Scorecard → panel jump links** — each scorecard row links to `#panel-<snapshot>`.
- [x] **Light/dark mode** — all panels must respect system appearance preference.
  Use CSS custom properties as the single source of truth for colours. Default
  `:root` defines the light theme; `@media (prefers-color-scheme: dark) { :root { ... } }`
  overrides to a dark theme. Cover: background, card surfaces, text, borders, chart
  colours (ensure contrast in both modes). Do not add a manual toggle — follow the
  system setting only.
- [x] **Councillor cross-link** — clicking a councillor name *anywhere*
  opens a unified profile (tenure + win rate + dissent + every declared interest +
  sponsorship ties). `councillors.json` snapshot; `CouncillorModal.tsx` (provider,
  link, SVG tick, right-side drawer); wired into PowerPanel, ConflictRecusalPanel,
  MayoralAgendaPanel, TenurePanel, RecusalTrendPanel, SponsorshipNetworkPanel.

### Infra already in place
`DrillDown.tsx` (`DrillDown` + `SourceQuote`); `Card` `valence` + `backTo` props;
`ValenceChip`; sc-row anchors; `extraction_evidence` quote counts by table —
motions 29 283 · other_items 16 332 · planning_applications 5 861 ·
public_questions 5 787 · budget_items 4 604 · interest_declarations 2 097 ·
deputations 1 553 · delegated_decisions 1 342 · tenders 1 326 · committee_reports
1 116 · appointments 980 · building_permits 755 · petitions 450. (`votes` has none
— use the related declaration/motion entity for the receipt.)

---

## Per-panel TODO

**Requirement (2026-06-26):** Every panel must have interactivity that leads the
reader to the underlying records and their verbatim `extraction_evidence` minute
quotes. Nothing in the UI should be unsourced — any aggregate must be inspectable
down to the original minute text. The Tier-1 pattern is the template for all Tier-2
and Tier-3 work.

Status: `[x]` done · `[ ]` queued. Each lists the **click target → reveal**, the
**data source**, the **export work**, and the **receipt** entity.

### Tier 1 — highest value
- [x] **declared** (ConflictRecusalPanel) — click councillor bar → their declared
  interests (type, "what it is", stayed/left), each with the minute quote.
  *Template implementation. `declared.json` profiles[].declarations inlined.*
- [x] **tenders** (TenderConcentrationPanel) — click a contractor bar → that firm's
  individual awards (date, description, $, reference, confidential?). Also click the
  redacted slice → the confidential awards.
  *Done. `tenders.json` contractors[].awards inlined; receipt entity_table='tenders'.*
  *Source: `tenders` (awarded_to normalised, amount, description, reference_number,
  meeting date). Export: per-contractor award lists onto `tenders.json` (already
  has top-15 contractors; add their awards). Receipt: `extraction_evidence`
  entity_table='tenders'.*
- [x] **power** (PowerPanel) — click a councillor (spectrum bar or scatter point) →
  their contested votes (motion title, date, their choice, outcome, margin); click a
  term point → motions that flipped that term.
  *Done (spectrum bar). `power.json` profiles[].votes inlined, capped 50 most recent
  (n_shown labels the cap); receipt entity_table='motions'.*
  *Source: `votes`×`motions` over contested motions. Export: per-councillor
  contested-vote list onto `power.json` (cap to ~50 most recent or paginate — can be
  large). Receipt: entity_table='motions'.*
- [x] **recusal** (RecusalTrendPanel) — click an era×type bar → the declarations
  behind that cell (councillor, item, type, description, stayed/left).
  *Done. recusal.json by_type_era[].declarations inlined, capped 60 most recent
  (n_shown labels the cap); receipt entity_table='interest_declarations'.*
  *Source: `recusal_compliance_trend` already does item-level linkage; extend it to
  emit the underlying declaration rows grouped by era×type. Receipt:
  entity_table='interest_declarations'.*

### Tier 2
- [x] **transparency** (TransparencyTrendPanel) — click a year point → the
  confidential items that year (kind, description where present, $).
  *Source: the four is_confidential tables (tenders, other_items, delegated_decisions,
  budget_items) by year. Export: per-year confidential-item lists onto
  `transparency.json`. Receipt: per source entity.*
- [x] **mayoral** (MayoralAgendaPanel) — click a mayor bar → their contested carried
  motions (title, date, votes for/against).
  *Source: `motions.moved_by_id` + term. Export onto `mayoral.json`. Receipt: motions.*
- [x] **dose** (ObjectionDosePanel) — click a bucket → the applications in it
  (reference, site address, #objectors, outcome) — incl. the 22-objector case.
  *Source: `planning_applications` + `community_submissions` counts. Export per-bucket
  app lists onto `dose.json`. Receipt: planning_applications.*
- [x] **divergence** (DivergencePanel) — make the existing exceptions table rows
  expandable → full motion text, officer rec vs outcome, quote.
  *Source: `officer_divergence` already returns the pairs; add `motion_text` + quote.
  Receipt: motions.*

### Tier 3 — descriptive panels
- [ ] **sponsorship** (SponsorshipNetworkPanel) — click an edge → the motions that
  pair co-sponsored (mover/seconder, dates, titles). *Source: motions moved/seconded.*
- [ ] **tenure** (TenurePanel) — click a councillor → first/last vote, span, vote
  count, roles. *Source: already computed; add first/last motion titles.*
- [ ] **alignment** (AlignmentHeatmap) — click a cell → the shared votes and the
  motions where that pair disagreed. *Source: pairwise `votes`.*
- [ ] **dissent-profiles** (DissentProfilesChart) — click a councillor → the carried
  motions they voted against. *Source: votes AGAINST on carried.*
- [ ] **dissent-coalitions** (DissentCoalitionsPanel) — click a coalition → their
  shared dissents. *Source: dissent_coalition_pairs detail.*
- [ ] **interests** (InterestsChart) — click a councillor → declarations by type
  (overlaps with `declared`; could reuse the same detail). *Source: interest_declarations.*
- [ ] **planning-trend / trends / co-mover / engagement** — lower priority; click a
  year/point → the items behind it.

---

## Update (2026-06-26): the page is now the battery (23 test panels)
Every battery test now has a panel — bespoke for the rich ones, the generic
`BatteryTestPanel` (renders the test's `chart` payload from `scorecard.json`) for
the rest. Eight descriptive non-test panels were retired (code kept). The
drill-down TODO below still applies to the **bespoke** panels; the **generic**
chart panels can get drill-downs later by the same recipe (export the records
behind each bar onto the scorecard test, or a sibling detail file).

## Notes / decisions
- **Inline vs sibling detail files:** inline for now (decided 2026-06-25) — simpler,
  files stay small. Revisit if a snapshot (e.g. `power`) gets large; then cap the
  list or split to a `*-detail.json` loaded on demand.
- **Big lists:** for high-volume drill-downs (power contested votes), cap to a
  sensible N and label ("showing 50 of 1,067") rather than ship everything.
- **Receipt fallback:** where the clicked entity has no `extraction_evidence` row
  (e.g. `votes`), join to the related entity that does (declaration / motion).

---

## BatteryTestPanel drill-downs — implementation plan (2026-06-26)

**Goal:** every BatteryTestPanel chart should be clickable, revealing the underlying
records + verbatim minute quotes — the same guarantee as the bespoke panels.

### Scope

10 of 12 BatteryTestPanel tests have charts. Two (`single-source`, `reserve`) are
`data_ok=False` with no chart — nothing to click, skip.

| slug | test_id | chart | click target → reveal | quote entity |
|------|---------|-------|-----------------------|--------------|
| threshold-gaming | procurement.threshold_gaming | bars (9 $ bins) | bin → tenders in that $-range (2015+) | tenders |
| incumbency | procurement.incumbency | bars (top-10 firms) | firm → its awards, year by year | tenders |
| repeat-applicant | planning.repeat_applicant | bars (4 freq. buckets) | bucket → applications in it | planning_applications |
| unanimity | governance.unanimity_trend | line (% by year) | year point → contested motions that year | motions |
| freshman | governance.freshman_effect | bars (2: early / later) | bar → dissenting votes in that period | motions |
| election-cycle | governance.election_cycle | bars (2: windows) | bar → dissenting votes in that window | motions |
| attendance | governance.attendance | line (% by year) | year point → absent vote rows that year | motions |
| big-dollar | planning.big_dollar_leniency | bars (4 quartiles) | quartile → applications in it | planning_applications |
| deputations | engagement.deputation_dissent | bars (2: with/without) | "with" bar → deputations in those meetings | deputations |
| eoy | finance.eoy_spending | bars (12 months) | month → tenders awarded that month | tenders |

### Data architecture — sibling detail files

**Sibling `*-detail.json` files**, one per test, loaded lazily on first bar/point
click (raw `fetch` in an onClick handler, result cached in component state). Keeps
`scorecard.json` clean. BatteryTestPanel derives the slug from `t.detail_panel`
(already on every `ScorecardTest`).

Standard shape for every detail file:
```json
{
  "meta": { "council_id": 1, "council_slug": "cambridge" },
  "data": {
    "by_label": {
      "<bar label or year-as-string>": {
        "total": 47,
        "n_shown": 30,
        "records": [
          { "label": "Aussie Concreting", "sub": "2019-03-15 · ref XYZ",
            "amount": "$245,000", "outcome": null,
            "quote": "That the tender from Aussie Concreting..." }
        ]
      }
    }
  }
}
```

Cap: **30 records per bar**. Label "showing N of total" when capped.

### Python changes (`src/analysis/tests.py` + `src/cli.py`)

**1. New `BatteryDetailRow` dataclass in `tests.py`:**
```python
@dataclass
class BatteryDetailRow:
    label: str
    sub: str | None = None
    amount: str | None = None
    outcome: str | None = None
    quote: str | None = None
```

**2. Three reusable row-builder helpers (in `tests.py`):**

- `_tender_detail_rows(session, council_id, filter_fn, cap=30)` — queries
  `Tender × Meeting × ExtractionEvidence(entity_table='tenders')`, applies
  `filter_fn(amount, name, year, month)`, returns `(rows: list[BatteryDetailRow], total: int)`.
- `_app_detail_rows(session, council_id, filter_fn, cap=30)` — queries
  `PlanningApplication × ExtractionEvidence(entity_table='planning_applications')`,
  applies filter, returns rows.
- `_motion_detail_rows(session, council_id, filter_fn, cap=30)` — queries
  `Motion × Meeting × ExtractionEvidence(entity_table='motions')`, applies filter,
  returns rows.

**3. Per-test detail builders — what each generates:**

- **threshold-gaming** — 9 bin ranges; for each bin call `_tender_detail_rows` filtered
  to that $-range (2015+). Row: awarded_to, sub = date + ref, amount = formatted $.
- **incumbency** — top-10 normalised firms; for each call `_tender_detail_rows` filtered
  to that firm name. Row: description, sub = year + ref, amount = formatted $.
- **repeat-applicant** — 4 frequency buckets (`1`, `2-3`, `4-6`, `7+`); group
  applicants by application count, then call `_app_detail_rows` per bucket. Row:
  applicant_name + ref, sub = address, outcome = Approved/Refused.
- **unanimity** — years with ≥30 carried motions; for each year call
  `_motion_detail_rows` filtered to contested (votes_against > 0) carried motions.
  Row: title (truncated 80 chars), sub = date + item_number.
- **freshman** — 2 bars (`First 12 months`, `Later service`); query `Vote(AGAINST) ×
  Motion(CARRIED) × Meeting`, split by `days_since_first_vote ≤ 365`. Join to motions
  for receipt. Row: councillor_name + title, sub = date.
- **election-cycle** — 2 bars; query `Vote(AGAINST) × Motion(CARRIED) × Meeting`,
  split by pre-election window flag. Row: councillor_name + title, sub = date.
- **attendance** — years; query `Vote(ABSENT) × Motion × Meeting`, group by year (cap
  30). Receipt via motions. Row: councillor_name + title, sub = date.
- **big-dollar** — 4 quartiles; compute value quartile boundaries first (same logic as
  the test), then `_app_detail_rows` per quartile. Row: description (truncated),
  sub = ref + address, amount = formatted estimated_value, outcome = Approved/Refused.
- **deputations** — 2 bars:
  - `"With a deputation"` → query `Deputation × Meeting`, include presenter_name,
    meeting_date, subject/summary, receipt from `ExtractionEvidence(entity_table='deputations')`.
  - `"Without"` → query the 30 most recent contested motions in meetings without
    deputations (so the "without" bar is also inspectable). Receipt via motions.
- **eoy** — 12 months; `_tender_detail_rows` filtered to `month == m` (all years). Row:
  awarded_to or "Confidential", sub = year + date + ref, amount = formatted $.

**4. Dispatcher `build_battery_detail(session, council_id, slug)` → `dict`:**
Routes by slug to the right builder, wraps in `{ "by_label": { ... } }`.

**5. In `cli.py` `cmd_publish`**, after the scorecard write, add 10 `_write` calls:
```python
from src.analysis.tests import build_battery_detail
for slug in [
    "threshold-gaming", "incumbency", "repeat-applicant", "unanimity",
    "freshman", "election-cycle", "attendance", "big-dollar", "deputations", "eoy",
]:
    _write(f"{slug}-detail", build_battery_detail(session, council_id, slug))
```
Add the 10 `"{slug}-detail"` names to the `snapshots` registry list.

### TypeScript changes

**`api.ts`** — add three new interfaces (no change to `api` object; the fetch is done
inline in the component):
```typescript
export interface BatteryDetailRow {
  label: string;
  sub?: string | null;
  amount?: string | null;
  outcome?: string | null;
  quote: string | null;
}
export interface BatteryDetailBucket {
  total: number;
  n_shown: number;
  records: BatteryDetailRow[];
}
export interface BatteryDetailData {
  by_label: Record<string, BatteryDetailBucket>;
}
```

**`BatteryTestPanel.tsx`** — 4 changes:

1. Add state: `selected: string | null`, `detail: BatteryDetailData | null`.
2. `handleBarClick(label: string)`: toggle-clears on same label; on new label, sets
   `selected` and — if `!detail && t.detail_panel` — fetches
   `/data/${t.detail_panel}-detail.json`, parses `.data`, caches in `detail` state.
3. `ChartView` gets an `onBarClick` callback prop; thread it to:
   - Bar charts: `<Bar onClick={(data) => onBarClick(data.label)}>`; `cursor="pointer"`
     on the `<Bar>`.
   - Line charts: `<Line activeDot={{ onClick: (_, p) => onBarClick(String(p.payload.x)) }}`
     (recharts passes the datum on activeDot click).
4. Below `<ChartView>`, when `selected` is set and `detail?.by_label[selected]` exists,
   render `<DrillDown>` + a row per record using existing `.decl-row` / `.decl-row-head`
   / `.decl-title` / `.decl-date` / `.decl-action` CSS classes + `<SourceQuote>`.

### Open question before build

**`deputations` "Without" bar** — no single entity type represents "a meeting without a
deputation". The plan above shows the 30 most recent contested motions in those meetings
(source: motions). Confirm this is the right call, or leave "Without" non-clickable.
