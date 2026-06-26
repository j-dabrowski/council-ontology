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

The recipe, end to end (see `[INTERACT]` in `INVESTIGATIONS.md` Phase H):

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

### Cross-cutting behaviours — DONE (apply to every panel)
- [x] **Auto-scroll to opened detail** — `DrillDown` calls `scrollIntoView` on open.
- [x] **Back-link to the scorecard row** — `Card` takes a `backTo="sc-<panel>"`
  prop → "↑ Scorecard" link; scorecard rows carry `id="sc-<panel>"` and flash on
  `:target`. Wired on all 10 scorecard-linked panels.
- [x] **Scorecard → panel jump links** — each scorecard row links to `#panel-<snapshot>`.
- [ ] **Councillor cross-link (stretch)** — clicking a councillor name *anywhere*
  opens a unified profile (tenure + win rate + dissent + every declared interest +
  sponsorship ties). The natural endpoint; bigger build.

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
- [ ] **transparency** (TransparencyTrendPanel) — click a year point → the
  confidential items that year (kind, description where present, $).
  *Source: the four is_confidential tables (tenders, other_items, delegated_decisions,
  budget_items) by year. Export: per-year confidential-item lists onto
  `transparency.json`. Receipt: per source entity.*
- [ ] **mayoral** (MayoralAgendaPanel) — click a mayor bar → their contested carried
  motions (title, date, votes for/against).
  *Source: `motions.moved_by_id` + term. Export onto `mayoral.json`. Receipt: motions.*
- [ ] **dose** (ObjectionDosePanel) — click a bucket → the applications in it
  (reference, site address, #objectors, outcome) — incl. the 22-objector case.
  *Source: `planning_applications` + `community_submissions` counts. Export per-bucket
  app lists onto `planning.json` (`dose`). Receipt: planning_applications.*
- [ ] **divergence** (DivergencePanel) — make the existing exceptions table rows
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
