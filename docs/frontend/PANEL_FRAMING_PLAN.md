# Panel framing — fixed labels, one severity ladder, measure-stating headings

Status: **built** (Steps 1–9, 2026-09-04 through 2026-09-06). Written 2026-09-04.
Follows `TEST_REGISTRY_PLAN.md`, which is built through Step 11 — this plan
assumes `config/test_registry.json`, `resolveTests()` and `ResolvedTest` exist.
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

The goal in one line: **varied labels read as separately-generated text; fixed
labels read as a method.**

---

## Part A — What is actually there now

### A.1 Six of the seven headings in the brief no longer exist

`TEST_REGISTRY_PLAN.md` Step 8 replaced every bespoke panel's hardcoded
`<Card title="…">` with `test.title_technical`. Grepping the frontend today:

| Heading in the brief | Still present? |
|---|---|
| Lifers and Blow-ins | gone |
| Did the Council Go Dark? | gone |
| Declared, Then Stayed | gone |
| Who Wins — Power on a Split Council | gone |
| Where Cambridge's Tender Money Went | gone |
| How Many Objectors Does It Take to Sink | gone |
| The Inquiry is the hinge | **`OverviewPanel.tsx` only** — a synthesis panel with no registry row (A.7) |

The **rule** in the brief still applies in full — it just applies to the current
`title_technical` values, which are the battery's own question-form titles
("Career councillors vs one-term members", "How much business is taken behind
closed doors?"). Those state neither the measure cleanly nor a conclusion; Part
C.1 rewrites all 29.

### A.2 Two of the suggested titles carry corpus-specific content

The registry is council-agnostic — no council name, no number, no finding text
(`TEST_REGISTRY_PLAN.md` Part E standing context). Two suggestions break it:

- **"Confidential business, 1995–2026"** — that span is *this* corpus's, and
  `era` already renders in the meta line. Use "Share of decided items closed to
  the public".
- **"Change around the 2018–21 Authorised Inquiry"** — the Authorised Inquiry is
  a Town of Cambridge event. Use "Recusal rate before, during and after external
  scrutiny".

Noted honestly: `conflict.recusal_trend` is **already** Cambridge-coupled in its
shipped `question_technical` and `era` ("Did recusal compliance track the
Authorised Inquiry?"). That is a pre-existing second-council problem, not one
this work creates, and it is not this plan's job to fix. Generalising the title
is free; generalising the test is a Refiner job.

### A.3 The counter-argument prose is interpolated with computed values

This is the central obstacle and it decides the shape of the whole task. The
existing blocks are not static text — they carry per-run figures:

| Panel | Interpolated values in its counter-argument block |
|---|---|
| `PowerPanel` | `pct(topWinner.win_rate)`, `pct(bottom.win_rate)`, `losers.length`, `pct(fail)` |
| `TransparencyTrendPanel` | `data.pre_era_pct`, `data.peak_pct`, `data.peak_year` |
| `DivergencePanel` | `pct`, `data.diverged_count`, `data.total_matched` |
| `QuestionResponsivenessPanel` | `data.pre_pct`, `data.inquiry_pct`, `data.post_pct`, `data.peak_year` |
| `RecusalTrendPanel` | `byTE.inquiry.proximity`, `byTE.post.proximity`, `data.financial_post_n`, four more |
| `ConflictRecusalPanel` | `factor` |
| `TenderConcentrationPanel` | `fmtM(data.named_amount)`, `data.distinct_named` |

None of that can move into `config/test_registry.json` verbatim. See B.1.

### A.4 The blocks come in three shapes, not one

1. **Objection + response in one paragraph** — `PowerPanel`, `DivergencePanel`,
   `RecusalTrendPanel`.
2. **Response only, objection implicit** — `ConflictRecusalPanel`,
   `TransparencyTrendPanel`, `TenderConcentrationPanel`, `MayoralAgendaPanel`.
3. **A `Severity: …` clause welded onto the end of one of the above** —
   `ConflictRecusalPanel`, `TransparencyTrendPanel`, `TenderConcentrationPanel`,
   `MayoralAgendaPanel`, `SponsorshipNetworkPanel` (twice).

And one four-move exchange: `QuestionResponsivenessPanel` runs *objection →
response → second objection ("A councillor's defender would answer…") →
response*. Two slots cannot hold four moves; see B.4.

### A.5 Where severity renders today

- `ScorecardPanel.tsx` — `<span className="sc-row-grade">{t.severity}</span>`,
  raw text.
- `BatteryTestPanel.tsx` — `<span className="bt-grade">{t.severity}</span>`,
  raw text.
- Five panel bodies — free prose ("Severity: Governance-concern · Nolan
  Integrity, Objectivity").

No ladder anywhere; the seven grades render as whatever string the battery
produced.

### A.6 Bespoke panels do not render the finding at all

`Card` takes `title`, `subtitle`, `valence`, `backTo`. The generic
`BatteryTestCard` renders `test.finding` in its own `bt-headline` block; the 12
bespoke panels render only their body, so **the finding never appears on a
bespoke panel**. That matters for the brief's "subhead states the finding" —
see B.5.

### A.7 `OverviewPanel` has no registry row

Its "The honesty layer" paragraph is about the battery as a whole (the nulls
being load-bearing), not a counter-reading of one test. It cannot take
registry-sourced objection/response text. See B.6.

---

## Part B — Decisions

### B.1 Registry objection/response text is number-free. RECOMMENDED.

Three options were open:

- **(a) Number-free.** Each objection/response states the counter-reading of the
  *measure*, with no figure in it. The numbers stay where they already are, in
  the panel's other `chart-note` paragraphs.
- **(b) Placeholders** interpolated at render from `ResolvedTest`. Only partly
  workable — the figures in A.3 come from bespoke snapshots
  (`data.peak_pct`, `data.distinct_named`), which `ResolvedTest` does not carry.
  It would buy a template language and still not reach most of the values.
- **(c) Number-free in the registry, plus a separate numbers-bearing paragraph
  the panel keeps as ordinary body prose.**

**Take (a), with (c) available only as an explicit escape hatch.** An
objection/response pair is a *method* statement — the strongest counter-reading
of this way of measuring, and the answer to it. A method statement that depends
on this run's numbers is not one. Where a number in the current prose is
load-bearing, it is almost always restating a figure already on the panel; where
it genuinely is not, the sentence may stay in the panel body as an ordinary
`chart-note` — but it may **not** use any of the six retired labels, and it may
not sit inside the Objection/Response block.

**The constraint that governs every rewrite:** *do not soften or strengthen any
finding — only the framing changes.* Concretely: every concession the current
prose makes must survive, and every reservation it holds must survive. Part C.2
records both for each block so a reviewer can check the rewrite rather than
re-derive it.

### B.2 Author objection/response for all 29 entries; render for critical only.

The brief's rule is a **render** rule: `valence === "critical"` → render the
block. Valence is computed per run and per council, so a test that is neutral
today can be critical next month, and a registry that only covers today's seven
would render an empty block the first time that happens.

Authoring all 29 also costs less than it sounds: an objection for a clean test
is the honest-limits sentence that is currently missing everywhere ("a clean
threshold test only rules out the crudest form of gaming — a contract split
across two budget years would not show up here").

Sequenced as two steps: the 7 critical-today first (Step 3), the remaining 22
second (Step 4), with the CI assertion landing in Step 4 so intermediate commits
are not blocked.

### B.3 `severity` stays a computed field. It does not move into the registry.

The brief says "driven by the registry severity field". `severity` lives on
`ResolvedTest`, sourced from the snapshot's `grade`
(`TEST_REGISTRY_PLAN.md` B.2) — it is a per-run result, and moving it into
`config/test_registry.json` would freeze one council's grade into source. The
chip reads `test.severity` off the resolved test. Nothing to change; stated here
so nobody "corrects" it later.

### B.4 The four-move exchange collapses to two slots.

`QuestionResponsivenessPanel` carries two distinct objections. Do **not** add
`objection_2` / `response_2` fields for one panel. Take the stronger objection —
the one a reader is most likely to raise — into `objection`; fold the answer to
the weaker one into `response` as a subordinate clause, or leave it in the panel
body as an ordinary `chart-note`. The concession it makes (the peak year is
partly a remote-meeting artefact) is one of the concessions B.1 requires to
survive, wherever it ends up.

### B.5 The subhead becomes the finding. This is the one layout change.

The brief: *the heading states the measure, the subhead states the finding.*
Today the subhead is `question_technical` and the finding appears below it in
`bt-headline` — on generic panels only (A.6).

Change `Card` to take an optional `finding` and render it as the subhead:
heading = `title_technical` (the measure), subhead = `finding` (the result),
`question_technical` moves down into the meta line beside the principles. The
`bt-headline` block keeps the severity chip and drops the now-duplicated finding
text.

**Safety requirement, non-negotiable:** `finding` is currently rendered in
exactly two places, both of which run it through the named-individual redaction
guardrail (`frontend/src/guardrail.ts`). Making it a subhead adds twelve more
render paths. Do not hand each panel the raw string — add a single
`<RedactedText>` component (or a `useRedacted()` hook) that applies
`findNamedCouncillorsInText` + `redactNamedCouncillors` internally, and render
every finding through it, including the existing two. A guardrail that covers
some render paths is not a guardrail. See `docs/frontend/INTERACTIVITY.md`'s
hard rule and the 2026-08-06 incident behind it.

### B.6 One component, two modes, for `OverviewPanel`.

`ObjectionResponse` takes its text from a `ResolvedTest` in the normal case, and
accepts `objection` / `response` as direct props for the one caller with no
registry row. Same labels, same markup, same CSS — a seventh label vocabulary
for one panel is exactly what this work exists to remove.

### B.7 Keep the severity ladder's semantics. The chip is presentation only.

The seven `G_*` grades keep their meaning and no test is re-graded. The chip
groups them visually into four tiers, in a fixed order, so a reader can place
any grade on a scale at a glance:

| Tier | Grades | Reads as |
|---|---|---|
| strength | `Commendable`, `Good-governance strength`, `Sound practice` | positive |
| observation | `Observation` | neutral |
| concern | `Governance concern`, `Integrity flag` | negative |
| no data | `Not computable on this corpus` | muted |

`Integrity flag` sits above `Governance concern` in severity and `Commendable`
above `Good-governance strength` above `Sound practice`; the chip carries a
rank so the ladder is expressible, even though only five of the seven appear in
the current run.

---

## Part C — The content tables

### C.1 All 29 headings and public titles

`title_technical` states the **measure**. `title_public` is the plain-English
equivalent, resident-facing. Both are council-agnostic: no council name, no
number, no era, no finding. **The implementer may adjust any wording that reads
better or describes the underlying test more accurately — but may not change
what is measured.** Where the brief suggested a wording, it is marked †.

| id | title_technical (new) | title_public (new) |
|---|---|---|
| `procurement.threshold_gaming` | Tender values around the competitive-tender threshold | Contracts sized just under the tender limit |
| `procurement.incumbency` | Repeat winners and big-dollar incumbents | Firms that keep winning work |
| `procurement.single_source` | Single-source and direct-negotiation share | Contracts awarded without competition |
| `procurement.concentration` | Tender awards by contractor † | Who gets the council's contract money |
| `procurement.decider_supplier_conflict` | Declared interests on tender awards | Conflicts declared when contracts are awarded |
| `conflict.recusal_management` | Recusal following a declared interest † | When councillors declare a conflict, do they leave? |
| `conflict.recusal_trend` | Recusal rate before, during and after external scrutiny | Did behaviour change when outsiders were watching? |
| `conflict.delegate_body_conflict` | Declaration rate of council-appointed delegates | Councillors voting on bodies they sit on |
| `planning.big_dollar_leniency` | Approval rate by development value | Whether expensive developments get approved more easily |
| `planning.repeat_applicant` | Approval rate by applicant frequency | Whether regular applicants do better |
| `planning.objection_responsiveness` | Refusal rate by objection count † | Whether objecting changes the outcome |
| `governance.officer_ratification` | Departures from the officer recommendation | How often councillors overrule their staff |
| `governance.power_spread` | Outcomes on contested votes † | Who wins when the council disagrees |
| `governance.oversight_body_capture` | Oversight-committee membership against chamber win rates | Who sits on the committees that check the council |
| `governance.unanimity_trend` | Share of carried motions drawing dissent | How often councillors disagree with each other |
| `governance.chair_capture` | Dissent rate on the Mayor's motions against backbench motions | Whether the Mayor gets an easier ride |
| `governance.durable_faction` | Sponsorship and voting blocs across electoral terms | Whether the same group votes together year after year |
| `governance.incumbency` | Tenure and turnover † | How long councillors stay |
| `governance.freshman_effect` | Dissent rate in a councillor's first year against later years | Whether new councillors vote differently |
| `governance.election_cycle` | Dissent rate in the pre-election window | Whether councillors change behaviour before an election |
| `governance.attendance` | Absence from votes, split by recusal and non-attendance | How often councillors miss votes |
| `transparency.confidential_share` | Share of decided items closed to the public | What gets decided behind closed doors |
| `transparency.confidential_tender_size` | Tender values, confidential against open | Whether the secret contracts are the big ones |
| `transparency.confidential_topics` | Subject matter of confidential items | What kinds of things get kept confidential |
| `finance.eoy_spending` | Tender spend by month of the budget year | Whether spending rushes at the end of the budget year |
| `finance.reserve_trajectory` | Reserve balances over time | Whether the council's savings are running down |
| `engagement.participation` | Public questions, deputations and petitions over time | How much residents take part in meetings |
| `engagement.deputation_dissent` | Contested-vote rate at meetings with a deputation | Whether meetings get livelier when residents speak |
| `engagement.question_responsiveness` | Public questions taken on notice against answered in the meeting | Are residents' questions actually answered? |

### C.2 The existing counter-argument blocks — what must survive the rewrite

Ten blocks, in the order a reviewer should work through them. **Concession** and
**reservation** are the two things B.1 requires to come out the other side
unchanged in force. **Numbers** lists what must be dropped from the registry text
(and may stay in the panel body as ordinary prose).

| Panel · test | Current label | Objection it raises | Concession it makes | Reservation it holds | Numbers to drop |
|---|---|---|---|---|---|
| `ConflictRecusalPanel` · `conflict.recusal_management` | In the council's defence | (implicit) | declaring lifts recusal ~N×, so disclosure is real not cosmetic; many declarations are lawful impartiality interests the member may stay and vote on | the *manage* limb still breaks — staying and voting three times in four | `factor` |
| `RecusalTrendPanel` · `conflict.recusal_trend` | A hostile reader would say | the fall is an artefact of declarations shifting to impartiality interests | impartiality declarations did balloon | the collapse shows up *within* must-leave categories too | proximity pcts and n's, `financial_post_n`, three must-leave n's |
| `TransparencyTrendPanel` · `transparency.confidential_share` | In the council's defence | (implicit) | the two-decade baseline is genuinely open; an inquiry legitimately generates confidential business; it reverted afterward | the *scale* and the timing | `pre_era_pct`, `peak_pct`, `peak_year` |
| `DivergencePanel` · `governance.officer_ratification` | A hostile reader would say | if officers get their way N% of the time, debate is theatre and the decision is made upstream | exceptions are a genuine minority, not an absent check; every departure is listed and inspectable | divergence is rare | `pct`, `diverged_count`, `total_matched` |
| `PowerPanel` · `governance.power_spread` | A hostile reader would say | the same handful win most of the time, so debate is theatre for a fixed majority | the spread resets every election rather than calcifying; dissent is not merely symbolic | win rates span very wide; many members lose more than they win | four win-rate figures, `losers.length` |
| `QuestionResponsivenessPanel` · `engagement.question_responsiveness` | A hostile reader would say + A councillor's defender would answer | (i) nine in ten are still answered; (ii) the peak year was a remote-meeting artefact | the peak is partly a remote-meeting artefact; "on notice" is lawful and often appropriate | the rise began before the pandemic and persisted after it; this is a responsiveness concern, not impropriety | `pre_pct`, `inquiry_pct`, `post_pct`, `peak_year` |
| `TenderConcentrationPanel` · `procurement.concentration` | The credit, stated plainly | (implicit) | concentration is the nature of big civil contracts, not evidence of capture; three independent integrity tests come back clean | the redaction share is a transparency issue worth watching | `named_amount`, `distinct_named` |
| `MayoralAgendaPanel` · `governance.chair_capture` | Read as a strength | (implicit) | a chamber that dissents against its Mayor more than the backbench is the opposite of chair capture | — (states a strength) | — |
| `SponsorshipNetworkPanel` · `governance.durable_faction` | Severity: (×2) | (implicit) | descriptive structural history, not a significance test | cross-term persistence rests on too few high-lift edges to prove statistically | — |
| `OverviewPanel` · *(no registry row)* | The honesty layer | (implicit) | — | the nulls are load-bearing: the *absence* of a finding is itself reported | — |

---

## Part D — The steps

Nine steps. Steps 1–2 build components and change nothing visible; 3–5 move the
counter-argument and severity text; 6–8 rewrite copy; 9 is the acceptance gate
and docs.

Every step ends with `npm run lint && npm run build` from `frontend/`; steps
touching `config/test_registry.json` also need `pytest -q` from the repo root.

**Standing context for every step.** Read `docs/MAP.md`,
`docs/frontend/TEST_REGISTRY_PLAN.md` Parts B–C (the registry's shape and the
council-agnostic rule), and `docs/frontend/INTERACTIVITY.md`'s **hard rule** — no
`.tsx` file may carry a literal councillor name, a specific stat, or a narrative
claim about a named individual as a string constant, and the same applies to
`config/test_registry.json`.

**The rule that governs every copy change in this plan:** *do not soften or
strengthen any finding — only the framing changes.* Every concession and every
reservation in Part C.2 must survive its rewrite with the same force. If a
rewrite cannot preserve one without a number, say so and leave that sentence in
the panel body rather than quietly dropping it.

**One commit per step.** A step whose acceptance checks pass is committed before
the next starts; if they fail, do not commit — report. Subject names the plan and
step number, body at most a couple of sentences, e.g.

```
Panel framing step 3: Objection/Response for the seven critical tests

Moves the counter-argument prose out of six panel bodies into the registry's
objection/response fields, number-free, with every concession in the plan's
Part C.2 preserved. Before/after pairs in the handoff notes.
```

`docs/TESTING.md` "Commit conventions" applies in full: **no `Co-Authored-By:
Claude` trailer.**

---

### Step 1 — `SeverityChip`

New `frontend/src/components/SeverityChip.tsx`, modelled on the existing
`ValenceChip.tsx` (same size, same chip shape, same placement discipline).

- Props: `severity: Severity`. One fixed map from each of the seven `Severity`
  values to `{ tier, rank, label }` per B.7 — exhaustive over the union, so a
  new grade is a type error rather than a blank chip.
- Label text is the grade string itself, unchanged. **The chip must not render
  the word "Severity:"** — the acceptance grep in Step 9 forbids that string
  anywhere in `frontend/src`.
- CSS in `App.css` alongside `.valence-chip`, using the existing custom
  properties so it works in light and dark. No new colour literals that bypass
  the token system.

Replace the two raw severity spans: `sc-row-grade` in `ScorecardPanel.tsx` and
`bt-grade` in `BatteryTestPanel.tsx`. Panel-body severity prose is Step 5.

Acceptance: build + lint; scorecard and generic panels show a chip in place of
the plain grade text; all five grades present in the current draft render
correctly in both themes.

---

### Step 2 — `ObjectionResponse`

New `frontend/src/components/ObjectionResponse.tsx`. Two fixed labelled slots,
**"Objection"** and **"Response"**, rendered identically everywhere.

- Props: either `test: ResolvedTest` (reads `objection` / `response`) or
  `objection: string` + `response: string` directly (B.6).
- Renders `null` when either is missing, and `console.error`s naming the test id
  when a `critical`-valence test reaches it with a null field — the same shape
  `resolveTests()` already uses for drift.
- CSS in `App.css`. The two labels are visually fixed and identical in every
  instance; that repetition is the point, not a redundancy to design around.

Not wired into any panel yet — every registry `objection` is still `null`, so
nothing renders. Acceptance: build + lint; no visible change.

---

### Step 3 — Objection/Response for the seven critical tests

The seven with `valence: "critical"` in the current draft:
`conflict.recusal_management`, `conflict.recusal_trend`,
`governance.officer_ratification`, `governance.power_spread`,
`transparency.confidential_share`, `transparency.confidential_tender_size`,
`engagement.question_responsiveness`.

1. Author `objection` and `response` in `config/test_registry.json` for each,
   **number-free** (B.1), from Part C.2's inventory.
   `transparency.confidential_tender_size` has no existing block — write it
   fresh; its objection is the small-n one (its own `era` already says
   DIRECTIONAL, n<30).
2. Render `<ObjectionResponse test={t} />` for `valence === "critical"` in
   `BatteryTestCard`, and in each bespoke panel that has one, at the position
   its old paragraph occupied.
3. **Delete** the old paragraphs from `ConflictRecusalPanel`, `RecusalTrendPanel`,
   `TransparencyTrendPanel`, `DivergencePanel`, `PowerPanel`,
   `QuestionResponsivenessPanel`. Where a number-bearing sentence survives as
   ordinary body prose under B.1's escape hatch, it keeps no retired label.
4. `QuestionResponsivenessPanel`'s four-move exchange collapses per B.4.

**In the handoff summary, print the before/after text for all seven, side by
side**, with Part C.2's concession and reservation columns beside each. This is
copy that carries defamation exposure; it must be reviewed as copy, not skimmed
as a refactor.

Acceptance: build + lint; the seven critical panels each show one Objection /
Response block and no other counter-argument label; `pytest -q` green.

---

### Step 4 — Objection/Response for the remaining 22, and the CI assertion

Author the other 22 pairs (B.2). For a supportive or neutral test the objection
is the honest-limits statement — what this measure does *not* rule out — and the
response says why the test is still worth running. Same number-free rule.

Three already have prose to adapt, from Part C.2:
`procurement.concentration`, `governance.chair_capture`,
`governance.durable_faction`. Delete those paragraphs from their panels and move
the substance into the fields.

Extend `tests/test_test_registry.py`: every registry entry has non-empty
`objection` and `response`. (Deliberately all 29, not just the critical ones —
valence is per-run, and a test that flips to critical must already have its
pair.)

Acceptance: 29/29 non-empty; the new assertion fails if one is blanked; full
suite green.

---

### Step 5 — Remove the remaining ad-hoc severity prose

Strip the `Severity: …` clauses still standing in `MayoralAgendaPanel`,
`TenderConcentrationPanel` and `SponsorshipNetworkPanel` (twice). The severity is
already on the chip from Step 1; the principle mapping is already in the meta
line. Where a clause carried something that is *neither* — e.g.
SponsorshipNetworkPanel's "descriptive structural history, not a significance
test" — that is a caveat: put it in the registry's `caveats` array, not back into
prose. (`caveats` is currently `[]` for all 29 and is not rendered anywhere;
adding a renderer for it is **out of scope** — populate the field and note it in
Step 9's docs.)

Then `OverviewPanel`'s "The honesty layer" paragraph: re-label it through
`<ObjectionResponse objection=… response=… />` in props mode (B.6), keeping its
substance — the nulls are load-bearing, the absence of a finding is itself
reported.

Acceptance: build + lint; Step 9's grep already returns zero for `Severity:` and
`honesty layer`.

---

### Step 6 — Rewrite all 29 `title_technical`

Apply Part C.1's left column to `config/test_registry.json`. The heading states
the measure; no conclusion, no council name, no era, no number.

Adjust any wording that describes the underlying test better — but check the
test's `question_technical` and its generator in `src/analysis/tests.py` before
changing one, and **do not change what is measured**. Two entries in the table
are deliberate corrections of the brief's suggestions (A.2); do not revert them
to the corpus-specific forms.

Acceptance: build + lint; `pytest -q`; scorecard and analysis headings all read
as measures. Read the 29 in one column and confirm none states a result.

---

### Step 7 — Populate all 29 `title_public`

Apply Part C.1's right column. Plain English, resident-facing, no jargon, no
figures. `title_public` has **no consumer yet** — no lay-facing surface exists
(`TEST_REGISTRY_PLAN.md` Step 10's open list) — so this step populates the field
and renders nothing. Do not build a public page to justify it.

Extend `tests/test_test_registry.py`: every entry has non-empty `title_public`.

Acceptance: 29/29 non-empty; full suite green.

---

### Step 8 — The subhead becomes the finding

Per B.5, and read B.5's safety requirement before writing any JSX.

1. Add `<RedactedText>` (or `useRedacted()`) to `frontend/src/guardrail.ts` — one
   component that applies `findNamedCouncillorsInText` +
   `redactNamedCouncillors` internally and renders the flagged-for-review notice
   when it fires. **Migrate the two existing finding render paths onto it in the
   same commit**, so there is exactly one guarded path, not three.
2. `Card` takes an optional `finding: ReactNode`; when present it renders as the
   subhead in place of `subtitle`.
3. `BatteryTestCard` and all 12 bespoke panels pass
   `finding={<RedactedText text={test.finding} />}`; `question_technical` moves
   into the meta line beside the principles.
4. `bt-headline` keeps the severity chip and drops the now-duplicated finding
   text.

This is the only step that changes layout. Verify by hand at `npm run dev` in
DRAFT mode that every one of the 29 panels reads heading → finding → body, and
that a test whose finding names a councillor still redacts — check that
explicitly rather than assuming, since this step multiplies the render paths by
six.

Acceptance: build + lint; the redaction check above, demonstrated.

---

### Step 9 — Acceptance grep and documentation

The brief's acceptance test, run from `frontend/`:

```
grep -rn "hostile reader\|council's defence\|credit, stated plainly\|Read as a strength\|honesty layer\|Severity:" src/
```

**Zero hits.** Not "zero outside the shared component" — the shared component's
labels are "Objection" and "Response", so none of the six retired phrases should
survive anywhere, including inside it. Paste the command and its empty output
into the handoff summary.

Then:
- `docs/frontend/INTERACTIVITY.md` — a short section: counter-argument text is
  registry-sourced and rendered only through `ObjectionResponse`; severity is
  rendered only through `SeverityChip`; a panel body carries neither. Add the
  grep above as a pre-deploy check beside the existing hardcoded-name one.
- `docs/frontend/TEST_REGISTRY_PLAN.md` — Step 10's open list: `objection`,
  `response`, `title_public` and (partly) `caveats` are now populated; strike
  them and leave `question_public`, `method` and `public_interest` open.
- `docs/frontend/PRODUCT_ROADMAP.md` — `caveats` is populated but not rendered;
  `title_public` is populated with no lay-facing surface to use it.
- Mark this file's status **built**.

---

### Deliberately not in this plan

Rendering `caveats` · populating `question_public`, `method` or
`public_interest` · building the lay-facing page `title_public` is for ·
generalising `conflict.recusal_trend` away from the Authorised Inquiry (A.2 — a
Refiner job) · re-grading any test · changing any computed number.
