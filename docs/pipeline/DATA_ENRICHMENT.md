# Data-Enrichment Wishlist — fields/entities that would unlock deeper investigation

Forward-looking notes (started 2026-06-24, session 6). Each entry is a candidate
for a **future re-extraction** (adapt the extraction prompts, re-run over the
existing minutes/agenda PDFs) or an **external-data join**. The corpus and PDFs
we already hold are not changing; this is the backlog for *if/when* we decide a
deeper question is worth a re-extraction pass.

**Restructured 2026-08-20** (`DISCOVERY_LOOP_DESIGN.md` Component B) — every
entry now carries two layers, not one:
- **Pattern** — the council-agnostic, abstracted signal shape: what kind of
  thing this is and why it matters, phrased without Cambridge specifics. This
  is the layer a *different* council's typology stage can actually use (see
  `PIPELINE.md` §Level 1→2 — the typology loop now cross-references this
  layer before generating its schema-update prompt).
- **Instance (Cambridge)** — the concrete example that surfaced it here, with
  the original Unblocks/Now/Want/Payoff/Effort fields unchanged in substance.

One pattern can accumulate instances from multiple councils over time — that
accumulation, not a longer Cambridge-specific list, is the actual
compounding-knowledge mechanism this file is part of.

How to read each entry:
- **Unblocks** — the investigation(s) (INVESTIGATIONS.md ids) or taxonomy genre
  (Investigator_prompt Part 3) it enables or sharpens.
- **Where it lives** — whether the raw signal is already in the PDFs (so a prompt
  change captures it) or needs data we don't hold.
- **Effort / confidence** — rough cost and how sure we are the signal is there.

Legend: 🟢 in-corpus re-extraction (prompt change) · 🟡 in-corpus but lossy/uncertain
· 🔴 needs external data we don't have.

---

## A. Re-extraction targets (signal is already in the PDFs)

### 1. 🟢 Structured financial-report line items (reserves / investments / transfers)
- **Pattern:** Councils routinely report periodic financial/reserve-position
  statements in free text (investment schedules, budget-review reports) that
  are structurally repeated meeting to meeting but never captured as a typed
  time series — blocking any trend analysis of financial resilience even
  though the raw figures are demonstrably present.
- **Instance (Cambridge):**
  - **Unblocks:** [24] financial-resilience arc (3.1); the s.114-precursor early-warning genre.
  - **Now:** the monthly "Investment Schedule" and budget-review reports are in the minutes
    (1995–2026) as free text in `budget_items.description`, with `amount` sometimes parsed.
    ~24 irregular portfolio snapshots are recoverable by regex but not comparable.
  - **Want:** a typed `financial_reports` (or enriched `budget_items`) with: `report_as_at_date`,
    `fund_type` (municipal / reserve / endowment-lands / trust / total), `balance`, and a
    `reserve_transfers` notion (`from_fund`, `to_fund`, `amount`, `purpose`). The Endowment Lands
    Account (Perry Lakes / City Beach land-sale windfall) should be its own fund_type.
  - **Payoff:** a clean EOFY-normalised reserve trajectory; ability to classify the 2018→2022
    drawdown as planned (matched to capital program / transfers-out with stated purpose) vs
    distress. This is the single highest-value re-extraction for an unbuilt finding.
  - **Effort/confidence:** medium / high — the figures are demonstrably present.

### 2. 🟢 Tender competitive-field metadata
- **Pattern:** Procurement records typically capture the award value and
  awardee but omit the competitive-field context (bidder count, procurement
  method) — exactly the metadata an integrity-genre analysis needs, and
  exactly what redaction/summarisation drops first when a record goes
  confidential.
- **Instance (Cambridge):**
  - **Unblocks:** single-source / direct-negotiation share over time (3.3); rescues the
    dollar-weighted angle that killed [25]; threshold context (3.3).
  - **Now:** `tenders` has `awarded_to`, `amount`, `is_confidential`. No bidder count, no
    procurement method; `amount` is missing on ~83% of confidential tenders (the redaction
    swallows the dollar value too — that is exactly what made [25] a null).
  - **Want:** `num_submissions` / bidder count, `procurement_method` (public tender / panel /
    direct / sole-source / quote), and a determined effort to capture `amount` even when the
    awardee is redacted (the value is often stated even when the winner is "Respondent N").
  - **Payoff:** "share of tender dollars/contracts let without competition, over time" — a clean
    integrity-genre trend that the current schema cannot support.
  - **Effort/confidence:** medium / medium — bidder counts are sometimes in the award report,
    sometimes not.

### 3. 🟢 Officer recommendation captured on MINUTES motions (not just agendas)
- **Pattern:** The officer's recommendation is conventionally restated
  immediately before a council's resolution text, but extraction schemas
  built agenda-first often only capture it from agenda documents (thinner,
  later-era coverage) rather than the fuller minutes record — an
  extraction-*source* blind spot, not a data-absence one.
- **Instance (Cambridge):**
  - **Unblocks:** officer-capture / "visible contest is theatre" (3.2); deepens divergence.py.
  - **Now:** `officer_recommendation` is populated only on agenda motions (391 rows, 2021+), so
    divergence analysis is limited to 42 agenda+minutes paired dates — too thin for a 30-year
    story. Minutes items, however, almost always restate the officer recommendation ("OFFICER
    RECOMMENDATION: That Council…") immediately before the resolution.
  - **Want:** extract the officer recommendation embedded in each *minutes* item into the motion
    row, plus an `amended_from_officer_rec` flag (divergence.py notes it currently can't detect
    "amended before carrying").
  - **Payoff:** officer-vs-council divergence across the full corpus; where ratification breaks is
    the story. Likely the strongest *new* governance finding available from re-extraction.
  - **Effort/confidence:** medium / high — the text is structurally present in minutes.

### 4. 🟢 Meeting-unique interest-declaration ↔ motion linkage
- **Pattern:** Item/agenda reference numbers are commonly reused across
  meetings (annual or termly numbering resets), so any linkage keyed on item
  reference alone silently cross-contaminates unless explicitly scoped to
  the meeting — a generic key-design trap for any minutes-derived schema,
  not a Cambridge idiosyncrasy.
- **Instance (Cambridge):**
  - **Unblocks:** sharpens [1], [19]; revives the [23] must-leave-pivotal version that died on
    cross-meeting `item_reference` bleed.
  - **Now:** `interest_declarations.item_reference` (e.g. '13.3.4', '10.4') is NOT unique across
    meetings, so declarations from other meetings join in; the type×outcome conflict analysis is
    unreliable as a result.
  - **Want:** scope `item_reference` to `meeting_id`, and link each declaration directly to the
    specific `motion_id` it concerns.
  - **Payoff:** trustworthy "declared a *financial* (must-leave) interest and still cast a
    decisive vote" analysis — the genuine integrity flag [23] couldn't stand up.
  - **Effort/confidence:** low-medium / high — it's a linkage/key fix, the data is present.

### 5. 🟡 Full individual-vote roster (reconcile tally vs named votes)
- **Pattern:** Minutes conventionally name only the dissenting side of a
  vote and state a bare tally for the rest, so any per-member analysis built
  on "who is recorded as voting" will systematically under-count the
  majority side unless the roster-vs-tally distinction is modelled
  explicitly — a generic minutes-drafting-convention trap.
- **Instance (Cambridge):**
  - **Unblocks:** all per-councillor vote work ([18], [23], dissent/power); reliable pivotality.
  - **Now:** minutes often state a tally ("carried 7/1") but name only the dissenters, so the
    FOR side is under-extracted — `votes_for/votes_against` disagree with counted vote rows on
    104 contested motions.
  - **Want:** capture the full FOR roster where the minutes list it; otherwise flag the motion as
    "dissenters-only recorded" so analyses can treat it correctly instead of silently miscounting.
  - **Payoff:** removes a systematic bias from every per-councillor metric.
  - **Effort/confidence:** medium / medium — depends on how often minutes name the full roster.

### 6. 🟡 Confidential-item REASON code (the cited closing ground)
- **Pattern:** Confidentiality/closed-session status is commonly modelled
  as a bare boolean, discarding the specific statutory ground cited — this
  loses the ability to test whether closure grounds are applied
  consistently or used as a catch-all, in any jurisdiction with a
  ground-enumerated closed-meeting statute.
- **Instance (Cambridge):**
  - **Unblocks:** deepens [9] transparency-trend and the confidentiality-overuse genre (3.4).
  - **Now:** `is_confidential` is a bare boolean. WA LG Act s.5.23(2) enumerates specific grounds
    for closing an item; minutes usually cite the clause.
  - **Want:** a `confidential_reason` / cited-clause field per confidential item.
  - **Payoff:** test whether confidentiality grounds are applied appropriately or as a catch-all,
    and whether the *mix* of grounds shifted around the Inquiry — a sharper transparency story
    than count-share alone.
  - **Effort/confidence:** medium / medium.

### 7. 🟢 Senior-officer / CEO tenure & events timeline
- **Pattern:** Leadership appointment/departure/acting-arrangement events
  typically appear in minutes as one-off motions rather than a modelled
  timeline entity, so leadership-churn-as-early-warning-signal (the Golden
  Triangle genre, Part 1.4) is invisible by default in any minutes-derived
  schema that doesn't deliberately model it.
- **Instance (Cambridge):**
  - **Unblocks:** Golden-Triangle / leadership-instability genre (Part 1.4); a governance
    early-warning signal.
  - **Now:** CEO appointments, departures, acting arrangements, and performance reviews appear in
    minutes (we saw "CEO Performance Review approval" motions) but aren't modelled as a timeline.
  - **Want:** a `senior_officer_events` entity (role = CEO / Director / Monitoring-equivalent;
    event = appointed / departed / acting / review; date).
  - **Payoff:** test leadership churn as a precursor/correlate of governance turbulence (it tracks
    the Inquiry-era thread running through [9]/[11]/[19]).
  - **Effort/confidence:** medium / medium.

### 8. 🟡 Deputation / petition → item → outcome linkage
- **Pattern:** Public-input records (deputations, petitions) are typically
  captured as standalone entities without a link to the specific decision
  they addressed, so "did public input change the outcome" can't be tested
  without fuzzy matching — a generic gap wherever public-input entities are
  extracted independently of the motions they concern.
- **Instance (Cambridge):**
  - **Unblocks:** deepens [3], [13]; the information-suppression genre (3.4).
  - **Now:** `deputations`/`petitions` aren't linked to the specific motion/outcome they concern,
    so "public input that vanishes without resolution" can't be traced.
  - **Want:** a link from each deputation/petition to the `motion_id`/`planning_application` it
    addressed, plus its outcome.
  - **Payoff:** test whether public engagement changes outcomes once properly matched (the [3]
    null was confounded by exactly this missing linkage).
  - **Effort/confidence:** medium / low-medium — matching is fuzzy.

### 9. 🟡 Revenue composition over time (rates / fees / commercial / grants)
- **Pattern:** Budget/financial entities often capture line items without a
  clean typed revenue-source dimension, blocking any "over-reliance on one
  income stream" early-warning analysis — a recognised financial-resilience
  indicator (Part 1.5) in general, not something specific to this corpus.
- **Instance (Cambridge):**
  - **Unblocks:** "over-reliance on one income stream" early-warning indicator (Part 1.5 / 3.1);
    complements [24].
  - **Now:** budget items exist but income composition isn't separable into a clean series.
  - **Want:** typed annual revenue lines by source.
  - **Payoff:** the CIPFA Financial Resilience Index style signal — detect structural reliance on
    a windfall/commercial income before it bites.
  - **Effort/confidence:** medium / medium.

### 10. 🟡 Planning application lodgement & decision dates
- **Pattern:** A minutes-only corpus records the decision date but not
  necessarily the lodgement date, because minutes record the decision
  night, not the application's paper trail — a generic "field that looks
  missing but may be structurally absent from the source, not just
  unextracted" trap worth checking on a sample before committing
  re-extraction effort, on any corpus.
- **Instance (Cambridge):**
  - **Unblocks:** processing-latency analysis (currently pre-killed — 100% NULL).
  - **Now:** `planning_applications.application_date` / `decision_date` are 100% NULL.
  - **Want:** capture them IF present in the source. Caveat: they may genuinely be absent from
    minutes (minutes record the decision night, not the lodgement date), so this could stay
    infeasible even after re-extraction — verify on a sample before committing.
  - **Effort/confidence:** medium / low — may not exist in the source at all.

---

## B. External-data joins (needs data the corpus does not contain)

### 11. 🔴 Councillor ↔ external-entity relationship graph
- **Pattern:** Any minutes-only corpus can see *declared* interests but
  never the *absence* of a declaration where an undisclosed relationship
  existed — the highest-value integrity signal structurally requires an
  external join, in any jurisdiction, because the thing being tested is
  precisely what the primary source wouldn't record.
- **Instance (Cambridge):**
  - **Unblocks:** the highest-value integrity genre we currently *cannot* touch — **undeclared**
    conflict between a decider and a supplier/applicant (the IBAC Operation Royston signature,
    Part 2.4 / 3.3). Our data can only see *declared* interests; the dangerous case is the
    *absence* of a declaration where a relationship existed.
  - **Needs:** external sources — ASIC company directorships/shareholdings, electoral donation
    returns / annual financial-interest returns, land-titles ownership — joined to `councillors`
    and to `tenders.awarded_to` / `planning_applications.applicant`.
  - **Payoff:** detect relationships that *should* have triggered a declaration and didn't. This is
    the difference between "declared-but-stayed" (which we can already study) and genuine hidden
    conflict.
  - **Effort/confidence:** high / high-value but data-acquisition- and privacy-sensitive; treat as
    a distinct project, and apply the Part 4 defensibility bar with maximum caution.

### 12. 🔴 Cross-council comparison corpus
- **Pattern:** Every finding on a single-council corpus carries an
  unanswered "is this normal?" — base rates only exist once a second/third
  council runs through the same pipeline. This isn't a per-council gap at
  all; it's the structural cost of n=1, and it resolves automatically as
  more councils are processed rather than needing its own re-extraction.
- **Instance (Cambridge):**
  - **Unblocks:** every finding's "is this normal?" question — base rates against peer councils
    (the CIPFA benchmarking / peer-review logic, Part 2.3).
  - **Needs:** load a second (and third) WA metro council through the same pipeline (the
    architecture already supports it; PIPELINE.md "Longer term" notes the 2-line addition).
  - **Payoff:** turns "Cambridge does X" into "Cambridge does X *more/less than peers*" — a far
    stronger, more defensible register.
  - **Effort/confidence:** high / high-value.

---

## Notes on method
- Any re-extraction should be **validated on a sample first** (does the signal actually exist at
  the rate we hope?) before a full batch — several of the 🟡 items may degrade to nulls.
- Re-extraction is cheap relative to its analytical payoff, but **re-run dedup, build-relationships
  and publish** afterward, and re-baseline any affected built panels.
- External-data joins (Section B) carry the heaviest Part 4 (Briginshaw / defamation) risk —
  any finding from them stays a risk-flag, never an assertion of motive.
- **New entries from any future corpus** should be written pattern-first: ask whether the
  signal shape is genuinely council-agnostic before writing the instance underneath it. If it
  isn't (the shape only makes sense for this specific council), it probably belongs in that
  council's own investigation notes, not here.
