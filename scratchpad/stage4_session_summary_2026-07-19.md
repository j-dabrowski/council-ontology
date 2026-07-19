# Stage 3–4 Session Summary — Session 9 / Phase L (2026-07-19/20)

City of Cambridge (WA) · Explorer_prompt.txt v2.3 · EXPLORATION_PROTOCOL Stages 3–4.
Read-only investigation. Frontend/panel build (Stage 5/6) deferred to a later session.

## Stage 3 — Standard battery: CONFIRMED, no discrepancy

`run_test_battery()` (scratchpad/stage3_run_battery.py) returned **23 tests,
6 supportive / 10 neutral / 5 critical / 2 not-computable** — an EXACT match to the
documented [BATTERY] entry (Phase I). No test changed valence, grade or n. Confirms
Stage 1's verdict that the corpus is byte-for-byte unchanged since session 8. Did NOT
regenerate scorecard.json / did NOT publish (verification run only).

## Stage 4 — 12 hypotheses [29]–[40], final classification

| # | Hypothesis (short) | Genre | Verdict | Headline result |
|---|---|---|---|---|
| 29 | Fiscal-year-end (30 Jun) spend spike | A Financial | ✗ Null | May+Jun 13.2% of tender $ vs 16.7% even — no spike at fiscal OR calendar boundary; upgrades finance.eoy_spending to a strength |
| 30 | Confidential tenders = larger $? | A/D | ◐ Banked | Confidential median $313k vs open $109k (~3×), Mann-Whitney p=0.002, n=16 directional; leak-bias runs toward null |
| 31 | Absenteeism vs recusal decomposition | B Governance | ◐ Banked | ABSENT 1.2%; 76% is lawful recusal, 24% (48 votes) genuine; attendance a non-issue; resolves battery caveat |
| 32 | Committee vs full-council decision | B Governance | ✗ INFEASIBLE | committee_reports has NO motion-linkage field; only 22 contested committee motions — structural kill |
| 33 | Delegation creep | B Governance | ✗ Null | Delegated share FALLS (9.7→5.2%) not rises; extraction coverage collapses (51→11%) — confounded |
| 34 | Declaration consistency (missing-decl) | C Integrity | ✗ Null | No stable cross-meeting matter key; item_number collisions — linkage null |
| 35 | Tender decider × supplier conflict | C Integrity | ✗ Null | Award-vote declaration 1.74% < 3.75% base; 0 genuine councillor↔winner links — clean, a 4th integrity credit |
| 36 | What gets closed (topical) | D Transparency | ◐ Banked | Confidentiality tracks lawful grounds (commercial 23%, tenders 11.5%); developments LEAST closed (1.6%) — openness credit |
| 37 | Public-question responsiveness | D Transparency | ✓ Finding | On-notice tripled 4.4→15.8% (Inquiry), held at 11.2%; tracks the Inquiry hinge; build-worthy |
| 38 | Petitions that vanish | D Transparency | ✗ Null | No outcome field; free-text link 97% = noise — linkage null |
| 39 | Durable-improvement hunt | E Strength | ◐ Banked | No durable improvement where it counts (recusal V-reverts, responsiveness worse); only disclosure rose (hollow) — sharpens [19] |
| 40 | Deputations flip outcomes? | E Strength | ✗ Null | Raw 11% vs 6.3% dissolves to 27.4 vs 24.8% once contentiousness controlled ([3] confound) |

Legend: ✓ Finding (build-worthy) · ◐ Banked (real, clear build/battery path) · ✗ Null · INFEASIBLE (structural kill).

## Benchmark scores

- **Finding rate** (Findings + Banked with build path) / 12 tested = (1 + 4) / 12 =
  **41.7% ≥ 25% → PASS.** (Findings: [37]. Banked: [30], [31], [36], [39].)
- **Structural kill rate** = INFEASIBLE / 12 = 1 / 12 = **8.3% ≤ 10% → PASS.** Only
  [32] died structurally; the two pre-flagged candidates were checked FIRST — [37]
  survived (response_summary 93% populated) and became the session's Finding, while
  [32]'s committee↔motion linkage is genuinely absent. Six other negatives are
  *tested* nulls (data present, clean/confounded negative), not structural kills.
- Null rate: 6/12 = 50% — high, but every null is a genuine tested negative that
  protects the credibility of the findings (Reference 0.5); three ([35],[36],[29])
  are affirmative *credits* to the council, not dead ends.

## Recommendations for Stage 5/6 (frontend build — next session)

Priority order:
1. **[37] PublicQuestionResponsivenessPanel** (the Finding) — new axis, tracks the
   Inquiry hinge, extends synthesis insight 1. Also add battery test
   `engagement.question_responsiveness`.
2. **[30] confidential-tender-size** — best directional build; pairs with [2]/[9].
   Add battery test `transparency.confidential_size` (median conf vs open + rank-sum).
   Ship with the n=16 DIRECTIONAL label prominent.
3. **[36] confidential-topics** — companion to the [9] TransparencyTrend panel (the
   WHAT axis) or battery test `transparency.confidential_topics`; a real openness credit.
4. **[31]** — refine `governance.attendance` to split ABSENT into recusal vs genuine
   (resolves its shipped caveat).
5. **[39]** — fold into the OverviewPanel/FINDINGS_SUMMARY synthesis (insight 1: the
   Inquiry hinge; "gains did not hold where it counts") — no standalone panel.

Battery-refinement backlog for a future Refiner session (do NOT edit tests.py in an
Explorer session): finance.eoy_spending → add weeks-to-30-June fiscal check ([29]);
new tests `transparency.confidential_size` [30], `transparency.confidential_topics`
[36], `engagement.question_responsiveness` [37], `procurement.decider_supplier_conflict`
[35]; governance.attendance split [31].

DATA_ENRICHMENT targets surfaced: committee item→motion linkage ([32]); a matter-id /
planning-reference on interest_declarations ([34]); a petition disposition/outcome
field ([38]); stable delegated_decisions extraction coverage across eras ([33]).

## Scripts (Stage 4 deliverables, retained in scratchpad/)

stage3_run_battery.py · h29_fiscal_yearend.py · h30_confidential_size.py ·
h31_absent_decomp.py · h32_committee_check.py · h33_delegation_creep.py ·
h34_decl_consistency.py · h35_tender_decider_supplier.py · h36_confidential_topics.py ·
h37_public_q_response.py · h38_petitions.py · h39_durable_improvement.py ·
h40_deputation_outcomes.py

INVESTIGATIONS.md updated in place: new "# Phase L — Session 9" section appended with
the [STAGE-3 BATTERY] confirmation + all 12 classified entries. Stage 2 status lines
updated Queued → final symbol.
