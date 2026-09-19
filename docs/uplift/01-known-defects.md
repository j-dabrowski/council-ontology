# 01 — Known Defects in the Live Report

Every item below was observed in the published Town of Cambridge report. For each,
trace it to the code, query, prompt, or config that produced it. Several will turn
out to share a root cause; note where they do.

Severity key: **P0** legal/credibility exposure · **P1** wrong finding ·
**P2** wrong presentation · **P3** cosmetic

---

## A. Arithmetic and data errors

### D-01 (P1) — Budget-year panel anchored on the wrong month
"Tender spend by month of the budget year" flags December and asks whether dollars
"cluster into the final months of the budget cycle". The Australian local government
financial year ends **30 June**. July shows the largest bar ($24M), consistent with
annual contract and panel renewals at the *start* of the year. The use-it-or-lose-it
test is May/June vs rest.
- Find where the fiscal-year boundary is defined. It is probably a hardcoded
  January anchor or an unconfigured default.
- Check whether the same anchor is used anywhere else (quarterly aggregations,
  era boundaries).

### D-02 (P2) — Twelve-month chart renders eleven values
Same panel. Rendered values: 5.6, 11, 12.5, 3.6, 13.4, 4.8, 24, 12.2, 6.7, 18, 16.9
against twelve month labels. One month is missing or two are merged.

### D-03 (P1) — Tender totals do not reconcile
Month panel values sum to ~$128.7M. Contractor panel states $119.6M total tendered.
Reconcile, or determine which population each uses and declare it.

### D-04 (P0) — Corpus denominators do not reconcile across panels
Observed: 15,942 (15,346 + 596), 15,881, 12,839, 12,274, 10,867, 2,649, 2,557.
Some of these are legitimately filtered populations. None of them declare their
filter on the face of the panel. Produce a reconciliation table: for each figure,
the exact population definition and the filter chain from the base table.
This is the single most attackable thing in the report.

### D-05 (P1) — Two contractor normalisation schemes in one report
Top-15 chart: "Leo Heaney", "Total Eden Watering Systems", "Downer EDI Works".
Repeat-winners chart: "Leoheaney", "Totaleden", "Cjdequipment", "Connellwagner",
"Majormotors". Two different normalisation functions are being applied. The panels
cannot be cross-read and dedup consistency cannot be verified.

### D-06 (P1) — A bucket is ranked among named firms
Top-15 chart contains a bar literally labelled
`Various contractors: Total Eden Watering Systems, Elliotts Irrigation, Malua
Reticulation, Hugall and Hoile`. Total Eden appears both inside this bucket and as
its own entry, so its dollars are double-counted or split arbitrarily.

### D-07 (P1) — Duplicate entity in a chart that grades individuals
"Carr" appears twice in the contested-vote ranking (71% and 75%). Either two
distinct Carrs (needs initials/disambiguation) or an entity-resolution failure.
Check against the councillor-terms table.

### D-08 (P1) — Implausibly low objector counts
"5 or more objectors" bucket is n=10 across 31 years for a council covering
Wembley and City Beach. Strongly suggests submissions extraction is under-counting.
Audit the submission parser against a sample of known-contentious applications.

### D-09 (P1) — Suspect ABSENT baseline
0.3% genuine non-attendance (48 / 15,346) is implausibly low for real council
attendance. Likely ABSENT is only recorded when minutes explicitly mark it, which
is disproportionately the declaration case. This makes the 83× figure partly
circular (see D-12). Determine how ABSENT is populated and whether non-attendance
is inferrable from attendance lists rather than vote rows.

---

## B. Statistical defects

### D-10 (P0) — Grades assigned without confidence intervals
Panel: "Must-leave recusal fell from 87.1% before scrutiny to 66.7% after",
graded **▲ Critical**. Post-period n = 12. 66.7% = 8/12, 95% CI ≈ 35–90%, which
contains 87.1%. The finding is not distinguishable from noise and carries the
report's most severe grade.

### D-11 (P0) — Underpowered nulls graded as positive findings
- $250k threshold panel: n=69, graded **✓ Supportive**. A density-discontinuity
  test at n=69 cannot detect anything short of blatant manipulation.
- Delegate panel: Tamala Park 0/2, Mindarie 0/15, graded **✓ Supportive /
  Sound practice**.
Absence of evidence is being rendered as evidence of absence.

### D-12 (P1) — The 83× comparison is structurally invalid
Numerator A = councillor did not attend (illness, travel, leave).
Numerator B = councillor left the room on a declared item.
These are different events. You cannot be recorded as recusing without a
declaration, by construction, so the baseline is not the same behaviour under
different conditions. Replace with the raw figure: *of 596 declared interests,
members left the room 149 times.*

### D-13 (P1) — Clustering ignored throughout
n=12,839 (freshman dissent), n=10,867 (oversight), n=12,274 (deputations) are
vote-rows, not independent observations. The oversight comparison has an effective
n of 31 councillors and is reported as 73.28% vs 73.13%. Cluster by councillor and
by meeting.

### D-14 (P2) — Reported precision exceeds interval width
"75.0%" (CI ≈ ±3.5pp), "100.0%" on n=1, "73.28%" vs "73.13%", "66.7%" on n=12.
Rule: significant figures must not exceed what the CI supports.

### D-15 (P1) — No multiple-comparison correction on the sponsorship network
~46 councillors → ~1,000 pairs per era. Ranking by lift and publishing the top
twelve guarantees "alliances" even in permuted data. Needs a permutation null:
shuffle seconding within councillor-term, recompute the lift distribution, report
how many of the twelve survive.

### D-16 (P1) — "Win rate" measures dissent propensity, not power
The panel states that voting yes on everything scores 76%. The two red bars (41%,
49%) are therefore the chamber's most frequent dissenters, relabelled as losers.
The term-by-term chart on the same panel shows win rates swinging every election,
directly undercutting the era-pooled ranking above it.

### D-17 (P1) — Selection bias unaddressed
Value-quartile panel uses n=235 of ~2,649 decided applications — those with a
recorded dollar value. Whatever determines recording is likely correlated with
size and formality.

### D-18 (P2) — "Flat" applied to non-flat data
Applicant frequency: 82 / 72 / 84 / 83. The 2–3 bucket is 12pp below. Correct
description is "no monotonic trend".

### D-19 (P1) — Causal language on observational comparisons
- "It isn't the act of objecting that moves council — it's the numbers."
  Alternative: non-compliant applications attract both objectors and refusals.
- "a declared-interest vote leans toward letting the matter through" (19.9% vs 26%)
  — declared-interest items skew to planning/sponsorship/funding, which have
  different base approval rates.

### D-20 (P1) — COVID confound handled inconsistently
The public-questions panel correctly caveats the 2020 remote-meeting artefact.
The confidentiality panel attributes the 2020 peak (17.2%) to the Inquiry era with
no mention of emergency procurement, hardship policy, or remote meetings. Same
year, same confound, two treatments.

### D-21 (P1) — Inquiry used as a natural experiment with no comparator
Pre/during/post appears in at least four panels. With no control council, any
WA-wide shift (remote meetings, 2021 Model Code of Conduct, regulatory change) is
indistinguishable from a Cambridge effect. Highest-value single upgrade: add two
neighbouring councils.

---

## C. Framing and grading defects

### D-22 (P0) — Headline quotes a rate the panel's own footnote disowns
Recusal panel headline: "members still stay and vote 75.0% of the time" — the
blended rate. The footnote below states the blended rate is misleading and that
the chart is graded on must-leave only. Lead with must-leave.

### D-23 (P0) — Lawful behaviour presented as an adverse finding
"0% recusal on the 225 post-2022 'impartiality' declarations", inside a ▲ Critical
panel. The report's own footnotes state members are entitled to stay and vote on
impartiality interests. Remove.

### D-24 (P1) — Panel contradicts itself on its face
Scrutiny panel headline says must-leave recusal **fell** 87.1 → 66.7. The callout
inside the same panel renders "100% → 100%" and says it **held**. Different
denominators (all must-leave vs financial only) with no flag for the switch.

### D-25 (P1) — Officer-recommendation panel probably graded backwards
Three stacked problems:
1. Admits motion-text amendments are not detected. Amendments are the most common
   form of WA council departure, so 97% is a known **upper bound on conformity**,
   flagged Critical.
2. Five of six "exceptions" are *deferrals*, which are delays, not departures. On
   a strict reading there is one genuine departure (99.5%).
3. Direction is contestable: frequent departure from officer recommendations on
   planning matters is generally the risk signal, not the reverse, because officer
   recommendations encode statutory requirements and overrides get overturned at
   SAT.

### D-26 (P0) — Unminuted briefing forums not caveated anywhere
Cambridge, like every WA council, holds unminuted briefing/concept forums.
Deliberation happens there. A high officer-adoption rate, a 9.1% contestation
rate, and low visible contest may reflect deliberation moving off the record
rather than an absent check. This single caveat reframes at least three panels
and its absence is the largest structural gap in the report.

### D-27 (P1) — No Goodhart caveat on the recusal metric
The metric can only see councillors honest enough to declare. A member who never
declares scores perfectly. The cheapest way to go green is to stop declaring.

---

## D. Legal and jurisdictional (see also `04-jurisdiction.md`)

### D-28 (P0) — UK frameworks applied to a WA council
Nolan principles and CIPFA codes throughout. Applicable instruments are the
Local Government Act 1995 (WA), Administration Regulations, Functions and General
Regulations, Rules of Conduct Regulations 2007, Model Code of Conduct 2021.

### D-29 (P0) — s5.68 not detected
Council may resolve to permit a member with a disclosed financial interest to
remain and vote. If the pipeline does not detect that resolution, an unknown share
of amber/red bars are **lawful conduct labelled as non-compliance**, on named
individuals. Highest-priority single check in the whole plan.

### D-30 (P1) — Delegate panel asserts an unsupported legal conclusion
"Institutional delegates declare ~0% on their own body's business (public role,
correctly)". Under reg 34C an association-based impartiality interest arguably
arises from a delegate appointment. Grading 0% as correct practice needs a cited
basis.

---

## E. Exposure and trust

### D-31 (P0) — Surname-collision panel names individuals on a name match
"2 raw decider↔winner surname collision(s) across 412 named awards", names in the
drill-down, qualifier "unconfirmed". Two fixes:
- Compute the expected collision count under a name-frequency null. With 412
  awards against 198 surnames, two collisions may be *below* chance, making this
  a null result that should be reported as one.
- Until then it should not name anyone.

### D-32 (P0) — Byline / subject collision undisclosed
Footer reads "Jo McAllister". A councillor named McAllister appears as the worst
performer on the recusal chart and second-most-outvoted on the win-rate chart.
Either a surname coincidence that must be stated, or a conflict requiring
prominent disclosure. A reader who notices before the report addresses it will
discount everything else.

### D-33 (P0) — No accuracy statement
"Data extracted via Anthropic Claude" is the entire method claim. No precision,
no recall, no model version, no extraction date, no audited sample. Every named
adverse finding is downstream of extraction quality. See `05-verification.md`.

### D-34 (P1) — No corrections mechanism, right of reply, or evidence of contact
Add all three. A "sent to the Town on [date]; response here" line is worth more
than any statistical fix in this document.

---

## F. Presentation

### D-35 (P2) — Axis label collisions in at least six charts
Observed rendered strings: `036912`, `2279547429`, `14948`,
`051015203813517`, `0 yrs2 yrs4 yrs6 yrs8 yrs`. Tick labels and data labels are
overlapping. Nothing in the pipeline currently looks at a rendered image.

### D-36 (P2) — No plain-English verdict
Every panel links "↑ Scorecard" but there is no summary of what the scorecard
says. A resident's question — "is my council OK?" — is unanswered anywhere.

### D-37 (P2) — Undefined jargon, no glossary or hover definitions
CIPFA-A..G, Nolan principles, lift, ×7.3, DIRECTIONAL, base rate, matched votes,
must-leave, impartiality interest, recusal, blended rate.

### D-38 (P3) — Misleading funnel styling
The `0.3% → 25% → 596` row is styled as a sequence with an arrow, implying the 596
flow through the earlier figures. They are three different denominators.

### D-39 (P3) — Jurisdiction ambiguity at a glance
"cambridge" + Nolan + CIPFA reads as Cambridge UK on first sight.

---

## Cross-cutting root causes to test for

When tracing the above, check specifically whether these single causes explain
clusters:

| Suspected root cause | Would explain |
|---|---|
| No declared grain on aggregate tables | D-04, D-13, D-17 |
| No claim object; panel text authored alongside stats | D-14, D-22, D-24, D-18 |
| Grade assigned by prompt rather than by rule | D-10, D-11, D-25 |
| Entity resolution applied at render time, not in silver | D-05, D-06, D-07 |
| No rendered-image inspection in the loop | D-35, D-38 |
| Framework hardcoded in prompt text rather than config | D-28, D-30 |
| No per-claim provenance to a source span | D-31, D-33, D-34 |
