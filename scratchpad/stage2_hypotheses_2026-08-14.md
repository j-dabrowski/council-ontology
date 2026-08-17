# Stage 2 Hypothesis List — Explorer session, 2026-08-14

Generated after the Stage 1 profile above. Continues numbering from [40]
(INVESTIGATIONS.md's last entry). Full PREDICTION/MECHANISM/REFUTES/
IDENTIFICATION/CONFOUND template per Explorer_prompt.txt Phase 1.

## [41] Genre C — Integrity — undeclared conflict via external-body appointment
PREDICTION: councillors appointed as Council's representative/delegate/board
member on an external body (via the untouched `appointments` table) vote on
Council business substantively concerning that body without declaring an
interest — the Part 3.3 "absence is the signal" test, never run before.
MECHANISM: a councillor who sits on another body's board has an ongoing
relationship (reputational, sometimes financial) with that body; WA law
requires disclosure where the relationship could reasonably be seen to
influence a vote.
REFUTES: appointment-holders declare at a rate no lower than non-appointed
colleagues on the same motions, OR the "undeclared" cases are institutional
role-delegation (not a personal interest) rather than a personal stake.
IDENTIFICATION: within-motion comparison — appointed-rep votes vs all other
councillors' votes on the SAME motions mentioning the body (controls for the
motion's own declaration-worthiness). Three bodies with enough appointment +
motion volume: Mindarie Regional Council, Tamala Park Regional Council, Ocean
Gardens (Inc) Board of Management.
CONFOUND flagged in advance: free-text body-name matching against
`motion.title`/`motion_text` risks the [13]/[38] false-positive problem
(a body name mentioned in passing inside an unrelated omnibus motion).

## [42] Genre A — Financial — election-cycle tender/pork-barrel spending
PREDICTION: tender dollars cluster in the ~7-month pre-election window
(Apr–Oct, odd years) — a "spend to be seen delivering" pattern distinct from
the already-tested December/fiscal-year-end dumping ([4]/[29]).
MECHANISM: incumbents time visible capital works to land before voters go to
the polls.
REFUTES: the pre-election share of tender dollars sits at or below the
window's calendar-time share (7/24 months ≈ 29.2% of the biennial cycle).
IDENTIFICATION: elections as discontinuities (Phase-2 lever #2), reusing the
exact pre-election window definition already shipped in
`governance.election_cycle` (tests.py:742).
CONFOUND: uneven vote/tender coverage by era (Part 0.4) — check the pre-2018
subset separately since modern-era n is thinner.

## [43] Genre B — Governance/culture — CEO/officer turnover as a discontinuity
PREDICTION: measurable governance behaviour (contestation rate, confidential
share) shifts at a CEO turnover boundary, independent of the electoral cycle
and independent of the 2018–21 Inquiry (Phase-2 lever #3, never used on this
corpus — every prior discontinuity used the Inquiry or an election).
MECHANISM: "council ratifies officer recs" ([32]/officer_ratification, 97%) —
so who drafts the rec (which CEO) plausibly matters more than who votes.
REFUTES: no shift, or a shift that is fully explained by the adjacent
election cycle (the confound this hypothesis pre-registers).
IDENTIFICATION: before/after the single clean, Inquiry-uncontaminated CEO
turnover event found in Stage 1 (2006-06-27 appointment), at three window
widths (±12/18/24 months) to check robustness.
CONFOUND (pre-registered, expected to bind): only ONE usable clean turnover
event exists in the corpus (the 2018–19 one is Inquiry-contaminated, the 2025
one is too recent) — n=1 shock, and its window unavoidably sits between the
Oct-2005 and Oct-2007 elections, so any effect cannot be cleanly separated
from ordinary electoral-cycle dynamics.

## [44] Genre D — Transparency — CEO/personnel-matter confidentiality
PREDICTION: `other_items` rows whose description concerns the CEO
(performance review, employment, recruitment) are confidential at a rate
well above the corpus base rate (4.6%, per [36]), consistent with lawful
personnel-matter closure, and that rate moved with the Inquiry / CEO-turnover
turbulence.
MECHANISM: CEO employment/performance matters are one of the WA statutory
grounds for closing an item (personnel) — [36] already found the
personnel/HR theme at 10.6% (lift 2.3×) against the 4.6% base; a
CEO-specific slice should be a plausible extreme case of that same lawful
category, sharpened around the known 2018–19 CEO-turnover turbulence.
REFUTES: CEO-related items are confidential at or near the base rate, or show
no relationship to the Inquiry/turnover era.
IDENTIFICATION: keyword filter (`description LIKE '%Chief Executive
Officer%' OR '%CEO%'`) × era (pre-2018/inquiry/post-2022), same era boundaries
as [9]/[19]/[37].
CONFOUND: keyword bucketing is noisy ([13] lesson) — but as with [36], a false
positive here would only DILUTE the specific CEO signal toward the general
personnel-theme rate, biasing toward the null, not manufacturing the effect.

## [45] Genre E — Strength — external-body representation: renewal or capture?
PREDICTION: appointment to Council's external bodies (delegate/board seats,
the same `appointments` table as [41]) is broadly distributed across the
chamber over time, mirroring [8]'s tenure-with-renewal and [27/28]'s
"no durable modern faction" findings on a third, independent channel — rather
than being captured by a small entrenched clique regardless of who is
appointed vs who merely serves the longest.
MECHANISM: if appointments are a genuine democratic/administrative process
(reshuffled with council composition), representation should track the whole
active chamber, not a fixed handful.
REFUTES: appointment volume is concentrated in a persistent few names at a
rate exceeding what tenure alone would predict — i.e., a high
appointments-per-year-served figure sustained by the SAME small group across
multiple council terms.
IDENTIFICATION: appointments-per-year-served (normalises for tenure, so
"more years served, more appointments accumulated" isn't mistaken for
capture), plus the share of appointment slots held by the top-10 appointees
vs the total distinct pool who were ever appointed at all.
CONFOUND: short-tenure councillors can show spuriously high per-year rates
off a tiny denominator (e.g., 1 year served, 3 appointments = 3/yr) — report
median/mean across the >=20-vote cohort, not the single top name, and flag
any denominator < 2 years as noise.
