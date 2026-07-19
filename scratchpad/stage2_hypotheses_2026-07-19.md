# Phase L — Session 9 (2026-07-19): hypothesis generation (Stage 2)

Protocol: EXPLORATION_PROTOCOL.md Stage 2 · Explorer_prompt.txt v2.3 PHASE 1/2.
Anchored to Stage 1 data profile `scratchpad/stage1_data_profile_2026-07-19.md`
(corpus UNCHANGED since session 8). These are QUEUED candidates only — not yet
tested. Numbering continues from [28]. Each carries the full
PREDICTION / MECHANISM / REFUTES / IDENTIFICATION / CONFOUND template, the
table(s) it needs, and its additionality (Thurrock) justification.

Standing data constraints applied during generation (from Stage 1 §8 + Explorer
confound checklist): `community_submissions.position` is LOWERCASE; 197 zero-vote
placeholder councillor records contaminate any naive mover/seconder count;
`estimated_value` 90.8% NULL (n≈241 decided → directional only);
`tenders.awarded_to` 45.6% NULL (never read NULL winner as "redacted");
`tenders.amount` 58.2% NULL; `budget_items` has NO typed fund/reserve schema;
`motions.officer_recommendation` 97.2% empty (use `src/analysis/divergence.py`);
planning `application_date`/`decision_date` 100% NULL. Structurally-blocked
threads ([24], [17], [6], [latency], [25]) are NOT re-queued.

---

## [29] Does spending spike at the *Australian* fiscal-year end (30 June), not December? [✗]

  Status: [✗] Null — no fiscal-year-end spike (upgrades finance.eoy_spending to a strength)
  Genre: **A — Financial failure** (3.1 end-of-year "use it or lose it")
  PREDICTION: Tender awards and budget-item spend cluster in the final weeks
    before 30 June (the WA local-government fiscal-year end), i.e. a May–June
    bump, distinct from the December calendar bump [4] already noted.
  MECHANISM: "Use it or lose it" pressure keys on the FISCAL year boundary —
    departments commit uncommitted budget before it lapses on 30 June. A council
    with tight budgetary control shows no such bunching (a *strength* read).
  REFUTES: A flat month-by-fiscal-week distribution, OR a spike that sits only in
    December (a calendar/pre-Christmas artefact, not fiscal-year-end dumping),
    would refute the fiscal-end mechanism and instead *support* budgetary control.
  IDENTIFICATION: Rule-change / calendar boundary (PHASE 2 lever #4). Re-bin
    `tenders`/`budget_items` amounts by month AND by *weeks-to-30-June*, split
    pre/post the Oct-2015 procurement-threshold regime and by era to avoid pooling
    two institutions. This is a *re-specification* of the existing eoy test, whose
    prior result may be wrong: **[4] and the `finance.eoy_spending` battery test
    keyed on December/calendar-year; if so they measured the wrong boundary for an
    Australian council** — June is where genuine fiscal dumping would show.
  CONFOUND: Meeting cadence (no January ordinary meeting; sparse winter sittings)
    mechanically shifts award dates; must normalise by number of meetings per
    month, not raw award counts. December pre-Christmas contract-letting is a real
    non-fiscal driver to separate out.
  Tables: `tenders` (amount, date via meeting join), `budget_items` (amount),
    `meetings` (meeting_date, document_type='minutes').
  Additionality: [4] and `finance.eoy_spending` measured the CALENDAR year-end;
    neither tested the 30-June fiscal boundary that actually governs "use it or
    lose it" in WA. Either outcome is publishable — a June spike sharpens [4] into
    a real control-weakness signal; a clean null upgrades it to a Principle-F
    *strength* (no fiscal-year-end dumping). No existing panel distinguishes these.

## [30] Are the *confidential* tenders systematically the larger-dollar ones? [◐]

  Status: [◐] Banked — confidential tenders ~3x larger median, p=0.002, n=16 directional; build/battery candidate
  Genre: **A — Financial failure** / D transparency convergence (3.1 + 3.4)
  PREDICTION: Among tenders that carry an extractable amount, confidential
    (`is_confidential=1`) awards have a higher median/mean dollar value than open
    awards — redaction concentrates on the big money.
  MECHANISM: The larger and more commercially/politically sensitive a contract,
    the more likely it is let under a closed "Respondent N" report — so
    confidentiality and dollar size co-move even if the *trend* over time is
    unmeasurable.
  REFUTES: No dollar difference (confidential median ≈ open median), OR the
    confidential set skews *small* (routine sensitive HR/legal buys), refutes
    "the big ones get hidden" and is a mild transparency *credit*.
  IDENTIFICATION: Pooled cross-sectional comparison (weakest lever — declared as
    such), n≈22 confidential-with-amount vs n≈329 open-with-amount → **DIRECTIONAL
    ONLY**. Report median + IQR + a rank-sum, never a point estimate.
  CONFOUND: The 22 confidential-with-amount are a *leaked* subset (Stage 1 §4: only
    ~20% of confidential tenders carry an amount) — they may be systematically
    unrepresentative (small ones leak, big ones stay fully dark), which would bias
    toward the null. Report the missingness explicitly; do NOT treat NULL-amount
    confidential tenders as "the big ones" (that is the [25] trap).
  Tables: `tenders` (amount, is_confidential).
  Additionality: [25] killed the confidential DOLLAR *trend* (per-year n too thin);
    [9] measured confidential *item-count* share over time; [2] measured overall
    concentration. None asked the pooled cross-sectional question "is redaction
    correlated with contract SIZE?" — routes around [25]'s time-axis kill by
    dropping the time axis entirely.

## [31] Genuine absenteeism vs recusal — who actually shows up once conflicts are stripped out? [◐]

  Status: [◐] Banked — resolves the attendance caveat; 76% of ABSENT is recusal; underpowered per-person
  Genre: **B — Governance / cultural dysfunction** (3.2 capacity/attendance)
  PREDICTION: Per-councillor ABSENT rate splits cleanly into (a) recusal (ABSENT
    with a declared interest on that item) and (b) genuine non-attendance (ABSENT
    with no declaration). Some councillors' high ABSENT rate is almost all recusal
    (diligent), others' is almost all genuine absence (disengaged) — the battery's
    single ABSENT number hides both.
  MECHANISM: There is no ABSTAIN; recusal shows up as ABSENT (Reference 0.4). The
    `governance.attendance` battery test explicitly flags that it *conflates
    recusal*. Using `votes.declared_interest` on the same motion legally partitions
    the ABSENT rows into "stepped out for cause" vs "wasn't there."
  REFUTES: If declared-interest ABSENTs are a negligible share of all ABSENTs, the
    conflation caveat is immaterial and there is nothing to add. If genuine-absence
    rates are uniformly low, that is an attendance *strength*.
  IDENTIFICATION: Within-person decomposition + within-council split by interest
    presence. Partition each ABSENT vote by whether that councillor declared an
    interest on that motion (join `votes` ↔ `interest_declarations` via the [19]
    item link); rank councillors by the two components separately, by era.
  CONFOUND: The [23] caveat — `interest_declarations.item_reference` is NOT
    meeting-unique, so cross-meeting bleed can mis-tag an ABSENT as recusal. Use
    the vote-level `declared_interest` flag as primary (it is per motion×councillor
    by UNIQUE constraint), not the item_reference join, for the partition.
  Tables: `votes` (choice=ABSENT, declared_interest), `interest_declarations`
    (interest_type), `meetings`.
  Additionality: `governance.attendance` battery test ships a single ABSENT share
    WITH a stated "conflates recusal" caveat. This hypothesis *resolves* that
    caveat — the exact refinement [19] performed on [1] (adding the legal-type/era
    dimension the pooled version collapsed). No panel currently separates diligence
    (recusal) from disengagement (absence).

## [32] Committee vs full council — where is contentious business actually decided? [✗]

  Status: [✗] INFEASIBLE — structural kill: committee_reports has no motion linkage; 22 contested committee motions
  Genre: **B — Governance / cultural dysfunction** (3.2 "decision made upstream")
  PREDICTION: Contentious items are disproportionately routed through committee
    (or arrive at full council pre-settled), so full-council votes on
    committee-originated items are near-unanimous while member-initiated items
    carry more dissent — the real contest happens off the main-chamber record.
  MECHANISM: If committees pre-digest and pre-agree items, the council vote is
    ratification theatre (Part 3.2). `meeting_type` and the `committee_reports`
    table let us see which channel an item travelled and whether contest survives
    to the recorded council vote.
  REFUTES: Comparable contestation on committee- vs council-originated items (no
    routing effect), OR committee items drawing MORE dissent (contest is preserved,
    a transparency *strength*), refutes upstream-settlement.
  IDENTIFICATION: Between-channel comparison keyed on `meeting_type` /
    `committee_reports` provenance; stratify by era (the Inquiry surge changed
    contestation baselines) and by topic where taggable.
  CONFOUND: Extraction/linkage risk — committee_reports↔motions linkage density is
    unverified (Stage 1 did not profile it); if sparse this is a **structural kill
    candidate** (flag for early Stage-4 schema check before spending budget). Also
    selection: routine consent items naturally go to committee AND are naturally
    uncontested — control for item type before claiming a routing effect.
  Tables: `meetings` (meeting_type), `committee_reports`, `motions`
    (outcome, votes_against), `votes`.
  Additionality: `governance.officer_ratification` measures officer→outcome
    adoption; `governance.unanimity_trend` measures contestation over time. Neither
    uses the COMMITTEE channel. This asks a distinct upstream-decision question —
    is the chamber ratifying its own committees? — on a table (`committee_reports`)
    and field (`meeting_type`) no prior hypothesis has touched.

## [33] Delegation creep — is decision-making drifting out of the elected chamber? [✗]

  Status: [✗] Null — delegation share falls not rises, and extraction coverage collapses (confounded)
  Genre: **B — Governance / cultural dysfunction** (3.2 officer capture / upstream)
  PREDICTION: The share of decisions taken under delegated (officer) authority
    rises over the 30-year span — especially post-Inquiry — as more routine (and
    some non-routine) matters move off the council agenda.
  MECHANISM: Delegation is legitimate for volume management but, unchecked, hollows
    out elected oversight (CIPFA-A/G, Best Value). A rising `delegated_decisions`
    share relative to council `motions` is the datable footprint of that drift.
  REFUTES: A flat or falling delegated share (chamber retains its decisions), OR a
    rise fully explained by the known 2016+ volume surge / extraction-coverage
    growth, refutes creep and may be a governance *strength* (proportionate
    delegation).
  IDENTIFICATION: Time series with the Inquiry (2018–21) as a shock boundary
    (PHASE 2 lever #1); normalise delegated count against council decision volume
    per year, NOT raw counts (coverage is uneven 1995–2003 vs 2016–2026).
  CONFOUND: Extraction coverage of `delegated_decisions` may itself have grown over
    time (more recent minutes list delegated registers more fully), manufacturing a
    spurious rise. Must confirm coverage is stable across eras before reading the
    trend as behaviour — otherwise **structural kill**. The 2022–2023 corpus gap
    undercounts those years.
  Tables: `delegated_decisions` (date via meeting join), `motions` (denominator),
    `meetings` (document_type='minutes').
  Additionality: No prior hypothesis or battery test has measured the DELEGATED
    channel at all. `governance.officer_ratification` is about how the chamber
    votes on what reaches it; this is about how much NEVER reaches it — a distinct
    dimension of the "decision made upstream" genre.

## [34] Declaration consistency — does a councillor who declares an interest declare *every* time the matter recurs? [✗]

  Status: [✗] Null — data-linkage: no stable cross-meeting matter key (item_number collisions)
  Genre: **C — Integrity / conflict** (3.3 undeclared conflict — the ABSENCE signal)
  PREDICTION: There exist cases where a councillor declares an interest on a given
    applicant / site / recurring matter at one meeting but is SILENT (no
    declaration) on a later motion touching the same applicant/site — the silent
    instance being the internally-detectable "missing declaration" red flag.
  MECHANISM: A genuine interest (property, relationship, external role) does not
    lapse between meetings. If it is declared once and not again on the same
    matter, either the interest ended or the declaration was omitted — and the
    omission is exactly the Part 3.3 "absence of a declaration where a relationship
    existed" signal, detectable WITHOUT external data by using the councillor's own
    prior declaration as the evidence the relationship existed.
  REFUTES: High consistency (councillors who declare on a matter keep declaring
    every time it recurs) refutes the concern and is a strong Nolan-Integrity
    **credit** (dual valence — this is also an E strength candidate). Recurrences
    too rare to measure = data-linkage null (log honestly, à la [17]).
  IDENTIFICATION: Within-person, within-matter longitudinal consistency. For each
    councillor×(applicant OR site OR recurring item reference) with ≥1 declaration,
    check every later vote by that councillor on the same key for a matching
    declaration. Anchor on the strongest linkable key (site_id / applicant_name in
    planning; item_reference stem in motions).
  CONFOUND: (a) `interest_declarations.item_reference` is not meeting-unique ([23]
    caveat) — key on the most reliable join and cross-check vote-level free text;
    (b) an interest legitimately ending between meetings is an innocent explanation
    (PROMOTER) — frame silent instances as "warrants explanation," never as proof
    of concealment (Briginshaw: ceiling = Integrity flag, and only where the
    relationship is unambiguous); (c) generic item labels reused across unrelated
    matters could create false "same matter" matches — verify via
    `extraction_evidence`.
  Tables: `interest_declarations` (councillor_id, item_reference, interest_type),
    `votes` (declared_interest, choice), `motions` (item_number),
    `planning_applications` (applicant_name, site_id), `extraction_evidence`.
  Additionality: Every prior conflict finding ([1],[19],[23]) tested what happens
    WHEN an interest is declared (recusal, staying, decisiveness). NONE tested the
    *consistency* of declaring — the missing-declaration angle Part 3.3 names as
    the core integrity signal. First test of the "absence is the signal" grammar on
    this corpus, and its own positive mirror (consistency = Integrity upheld).

## [35] Are conflicts ever declared when Council awards tenders — and do winners match declared connections? [✗]

  Status: [✗] Null — clean; decider x supplier join empty; a 4th converging procurement-integrity credit
  Genre: **C — Integrity / conflict** (3.3 undeclared conflict: decider × supplier)
  PREDICTION: Tender-award decisions attract very few interest declarations
    relative to their dollar stakes; and where a councillor has a known declared
    connection to a firm elsewhere in the record, that firm's awards carry no
    declaration on the award vote.
  MECHANISM: Procurement is the highest-value integrity surface (IBAC Op. Royston).
    The Part 3.3 test is the join `interest_declarations × tenders.awarded_to ×
    votes` looking for the *absence* of a declaration where a decider↔supplier link
    exists — never computed on this corpus.
  REFUTES: If award votes carry declarations at or above the base declaration rate,
    OR no councillor↔supplier links are detectable at all, the concern dissolves —
    and a clean, competitively-tendered, declaration-covered award record is a
    Principle-F/A **strength** (converges with the [2]/[15]/[26] "procurement comes
    back clean" story).
  IDENTIFICATION: Convergence join (PHASE 2 — two lenses on one pattern). (1) Rate
    of any declaration on tender-award motions vs the chamber base rate; (2)
    name-match `tenders.awarded_to` against councillor surnames / declared
    connection strings (directional, fuzzy) to flag decider↔winner pairs with no
    declaration on the award vote.
  CONFOUND: `tenders.awarded_to` is 45.6% NULL (Stage 1) — a NULL winner is an
    extraction gap, NOT concealment; restrict the match test to the 457 named
    awards and state that ceiling. Name-matching yields FALSE positives (common
    surnames) — every flagged pair must be provenance-checked and framed as
    "warrants explanation," never asserted. Most award votes may simply not be
    recorded as separate motions (procurement often consent-agenda'd) — possible
    thin-linkage null.
  Tables: `tenders` (awarded_to, amount, is_confidential), `interest_declarations`,
    `votes` (declared_interest), `motions` (item/outcome), `councillors`,
    `extraction_evidence`.
  Additionality: [2]/[15]/[26] tested tender concentration, incumbency and
    threshold-gaming — the SUPPLIER side. [1]/[19]/[23] tested declarations on
    the DECIDER side. No hypothesis has JOINED them (decider × supplier), which is
    the Part 3.3 core integrity test. High convergence value; a clean null is a
    genuine additional procurement-integrity credit.

## [36] What gets closed, not just when — is confidentiality aimed at particular subject matter? [◐]

  Status: [◐] Banked — topical transparency strength; confidentiality tracks lawful grounds, developments least closed
  Genre: **D — Process / transparency abuse** (3.4 confidentiality overuse)
  PREDICTION: Confidential items concentrate in specific subject clusters (land
    dealings, named developments, legal/HR) beyond the legitimate baseline — and
    some clusters (e.g. a contentious development) are closed at rates that a
    "commercial/legal necessity" story does not fully explain.
  MECHANISM: Legitimate confidentiality tracks statutory grounds (contracts, legal,
    personnel). Abuse shows up as closure clustered on *politically contentious*
    topics (Part 3.4). Classifying the `description`/tags of confidential items
    reveals the WHAT that [9]'s time trend cannot.
  REFUTES: If confidential items map cleanly onto legitimate grounds (tenders,
    legal, personnel, land contracts) with no contentious-topic excess, that
    refutes abuse and is an Openness **credit** — confidentiality used lawfully.
  IDENTIFICATION: Topical decomposition (not temporal). Bucket the confidential
    rows across `tenders`/`other_items`/`delegated_decisions` by keyword/tag theme;
    compare the confidential-share of each theme against its share of all business;
    cross-reference contentious developments already surfaced in [13].
  CONFOUND: Keyword bucketing is noisy ([13] false-positive lesson — "reserve"/
    "green" over-broad); verify clusters via `extraction_evidence`. Legitimate
    grounds genuinely dominate (tenders drove [9]'s spike) — the finding is only
    the *residual* contentious-topic excess after lawful grounds are accounted for,
    or there is no finding.
  Tables: `tenders`, `other_items`, `delegated_decisions` (is_confidential,
    description/tags), `extraction_evidence`.
  Additionality: [9] answered WHEN business went confidential (temporal share,
    Inquiry spike). This answers WHAT gets closed (topical concentration) — the
    orthogonal axis [9] and `transparency.confidential_share` do not compute.
    [25] (dollar share) is a third, killed axis; this topical axis is untested.

## [37] Public-question responsiveness — answered, or quietly "taken on notice"? [✓]

  Status: [✓] Finding — on-notice tripled during Inquiry (4.4->15.8%) and held; build-worthy
  Genre: **D — Process / transparency abuse** (3.4 engagement theatre)
  PREDICTION: A rising share of public questions are deferred / "taken on notice" /
    left without a recorded answer over time, i.e. the appearance of engagement
    without the substance of response.
  MECHANISM: Public question time is a statutory engagement channel (CIPFA-B). If
    answers are increasingly deferred rather than given in-meeting, engagement
    becomes theatre (Part 3.4) — a datable responsiveness-decay signal in a
    3,478-row table no prior hypothesis has touched.
  REFUTES: A stable or high in-meeting answer rate refutes decay and is a
    Principle-B engagement **strength**. If the table lacks an answered/deferred
    field, this is a structural null (log and move on).
  IDENTIFICATION: Time series with the Inquiry shock (PHASE 2 #1); share of
    questions with a recorded/immediate response vs deferred, by year, coverage-
    normalised.
  CONFOUND: **Schema unverified** — Stage 1 did not profile `public_questions`
    fields; if there is no response/status column this is a **structural kill
    candidate** (flag for an early Stage-4 schema check before budget is spent).
    Extraction may under-capture verbal answers (making answered look like
    unanswered) — validate against `extraction_evidence` before reading a decline.
  Tables: `public_questions` (+ any response/status field — CONFIRM FIRST),
    `meetings`, `extraction_evidence`.
  Additionality: `engagement.participation` and `engagement.deputation_dissent`
    measure engagement VOLUME and its correlation with dissent. Neither measures
    whether questions are actually ANSWERED — a distinct responsiveness dimension
    on a completely unmined table.

## [38] Petitions that vanish — does a petition ever produce a traceable outcome? [✗]

  Status: [✗] Null — data-linkage: no petition outcome field; free-text matching unreliable
  Genre: **D — Process / transparency abuse** (3.4 petitions vanishing)
  PREDICTION: Most of the 383 petitions are received-and-noted with no traceable
    downstream motion or decision — engagement absorbed without resolution.
  MECHANISM: A petition is a formal resident instrument; if petitions routinely
    dead-end at "received," the channel is symbolic (Part 3.4). Linking a petition
    to any later motion on the same subject tests whether resident pressure
    converts to action.
  REFUTES: A meaningful share of petitions linking to a later motion/outcome
    (especially one that changes a decision) refutes "vanishing" and is an
    engagement **strength** (converges with the E [40] "engagement moves outcomes"
    hypothesis).
  IDENTIFICATION: Linkage from `petitions` (topic/subject) to `motions` on the
    same matter; descriptive resolution-rate by era.
  CONFOUND: **Linkage risk is high** — mirrors killed [17] (deferred-motion
    linkage sparse) and [6] (submitter placeholders). Petition→motion linkage is
    likely thin and free-text; likely a data-linkage null. Lower priority; keep as
    a cheap descriptive check, not a budget sink. "Received and noted" is often the
    lawful correct disposition — absence of a follow-up motion is NOT itself abuse.
  Tables: `petitions`, `motions`, `meetings`, `extraction_evidence`.
  Additionality: `petitions` is entirely unmined. Even a clean data-linkage null
    (à la [6]/[17]) is an honest additional result documenting that resident-
    petition efficacy is not measurable on this corpus — useful negative knowledge.

## [39] The durable-improvement hunt — did ANY conduct tighten during the Inquiry and *hold*? [◐]

  Status: [◐] Banked — no durable improvement where it counts; sharpens [19] (synthesis-level)
  Genre: **E — Strength** (responsiveness under scrutiny that stuck)
  PREDICTION: At least one governance behaviour that tightened during the 2018–21
    Inquiry stayed tight afterward — the converse of [19]'s recusal collapse — and
    is a demonstrable, datable good-governance strength.
  MECHANISM: Phase-1.E: "behaviour that tightened during the Inquiry AND held
    afterward is a strong, datable good-governance result." [19] found conduct
    reverting; a systematic sweep asks whether ANY domain (confidential share
    reverting to baseline and staying low; genuine attendance; dissent openness;
    officer pushback) improved durably rather than snapping back.
  REFUTES: If every scrutiny-era improvement reverted post-2022 (like recusal
    [19] and the confidential spike [9] partly did), the honest finding is "no
    durable improvement" — which sharpens the [19] concern rather than crediting
    the council.
  IDENTIFICATION: Before / during / after the Inquiry (PHASE 2 lever #1) applied
    as a SWEEP across the already-computed era series (transparency [9], recusal
    [19], attendance, unanimity), looking specifically for the L-shape (step down
    and stay) vs the V-shape (dip and rebound).
  CONFOUND: 2022–2023 corpus gap thins the "after" window — a flat post-period may
    be undercount, not durability; require ≥2 solid post-Inquiry years before
    claiming "held." Regression to the mean can mimic durability; state n per era.
  Tables: reuses existing era series — `tenders`/`other_items` (is_confidential),
    `votes` (choice, declared_interest), `interest_declarations`, `meetings`.
  Additionality: The Inquiry-shock lens has only ever surfaced REVERSION findings
    ([19], and [9]'s partial rebound). No hypothesis has systematically hunted the
    POSITIVE converse — a durable improvement — which Phase-1.E names as a
    first-class strength. Fills the balance gap the calibration log flags.

## [40] Engagement that moves outcomes — do deputations / questions ever visibly flip a decision? [✗]

  Status: [✗] Null — [3] contentiousness confound explains the raw effect; deputations don't add efficacy
  Genre: **E — Strength** (deputations that visibly change an outcome)
  PREDICTION: On a measurable minority of items, an in-person deputation against
    the officer/mover's line coincides with the item being amended, deferred or
    refused — resident voice occasionally converting to outcome change, the
    positive mirror of the transparency-abuse genre.
  MECHANISM: Phase-1.E lists "petitions/deputations that visibly change an outcome"
    as a publishable strength. Unlike the written-objection dose-response [12]
    (planning only), a spoken deputation is a distinct, higher-effort channel; does
    it move NON-planning business too?
  REFUTES: If deputation presence has no association with outcome divergence from
    the expected line (beyond [3]'s weak dissent correlation), engagement is not
    visibly efficacious here — a null, honestly logged, not a manufactured credit.
  IDENTIFICATION: Link each deputation to the item it addressed (meeting + topic
    match), then compare that item's outcome (deferred/amended/refused vs
    carried-as-recommended) against the base rate for comparable items.
  CONFOUND: Reverse causality — deputations are DRAWN to already-contentious items
    that were going to be contested anyway (the [3] busy-meeting confound); control
    for baseline item contentiousness. Deputation↔item linkage is free-text and
    noisy ([13] lesson) — provenance-check every "flipped" case. Small n of clear
    flips → directional/illustrative, not a rate claim.
  Tables: `deputations`, `motions` (outcome, votes_against), `meetings`,
    `extraction_evidence`.
  Additionality: [3] tested deputations→dissent (weak, in battery); [12] tested
    written objections→refusal (planning only). Neither tested whether a SPOKEN
    deputation flips an outcome across ALL business types — the positive-mirror,
    strength-genre question, and the efficacy counterpart to [37]/[38].

---

## Stage 2 self-check — domain breadth (EXPLORATION_PROTOCOL.md dimension 1)

- **A — Financial:** [29], [30] (≥1 ✓)
- **B — Governance:** [31], [32], [33] (≥1 ✓)
- **C — Integrity:** [34], [35] (≥1 ✓)
- **D — Transparency:** [36], [37], [38] (≥1 ✓)
- **E — Strength:** [39], [40] present, + [34] carries a dual strength valence (✓)

Total: 12 hypotheses. A/B/C/D each ≥1, E present → **domain-breadth benchmark
clears**. All live inside the Stage-1 supported-data envelope; the two flagged
structural-kill candidates ([32] committee linkage, [37] public_question schema)
carry an explicit "confirm schema first" instruction so they are caught before
Stage-4 budget is spent (protecting dimension 3, structural kill rate ≤10%).
