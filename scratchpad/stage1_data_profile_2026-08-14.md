# Stage 1 Data Profile — Explorer session, 2026-08-14

Corpus confirmed unchanged in shape from the 2026-07-19 profile (same row
counts on every table checked), with one addition since: `procurement.decider_supplier_conflict`
now live in the battery (27 test_ids total: 25 literal `test_id="..."` matches
in tests.py + 2 `_nodata()` not-computable rows — `procurement.single_source`,
`finance.reserve_trajectory` — confirmed by grep, not assumed).

## Row counts (2026-08-14, `data/council.db`)
councillors 400 · councillor_terms 58 (33 distinct councillors, 51 role=Councillor
/ 7 role=Mayor — sparser than the Part 0.1 prose suggests; only 33/400 councillors
have ANY term row) · motions 14,013 · votes 16,249 · tenders 840 · interest_declarations
2,015 · community_submissions 2,114 · planning_applications 3,116 · deputations 1,492 ·
petitions 383 · public_questions 3,478 · budget_items 3,978 · delegated_decisions 1,242 ·
committee_reports 881 · other_items 11,880 · appointments 944 · building_permits 667 ·
meetings 580 · extraction_evidence 71,486 · relationships 158.

## New-this-session table inspected in depth: `appointments`
Never previously mined (absent from INVESTIGATIONS.md phases A–M). Schema:
(id, meeting_id, councillor_id, role, body_name). 944 rows, 806 (85.4%) carry a
councillor_id, 141 distinct free-text `role` values (Member/Delegate/Presiding
Member/Deputy/Alternate — inconsistent casing, needs normalisation), 225
distinct `body_name` values. Spans 1995-06-13 to 2026-04-28 (full corpus).
128 distinct councillors ever appointed (of 203 who ever cast a vote — 63%).
No term_end column — an appointment is a point-in-time event, not an interval;
any before/after or "currently serving" window must be inferred (next
appointment to the same body, or a capped default window).

Top body_names by frequency: Town of Cambridge (49, likely a self-referential/
internal-committee artefact, not an external body), Mindarie Regional Council
(38), Development Committee (35), LGA Central Metro Zone (30), Community and
Resources Committee (30), CEO Performance Review Committee (28), Audit
Committee (24), Public Art Committee (23), Ocean Gardens (Inc) Board of
Management (23), Design Review Panel (22), Tamala Park Regional Council (17).

Caveat surfaced (new, add to standing checklist candidate list): **`role` free
text is inconsistent case/wording** ("member"/"Member", "delegate"/"Delegate",
"presiding member"/"Presiding Member") — any role-based aggregation must
normalise case before grouping or it will silently split one role into two
buckets.

## Other tables inspected but not built on this session
- `building_permits`: 667 rows, only 63 (9.4%) carry `estimated_value` — same
  near-total-NULL problem as `planning_applications.estimated_value` (90.8%
  NULL) documented in the standing checklist; too thin (n=63) for a
  value/leniency test to clear even DIRECTIONAL strength confidently. Only 3
  distinct `status` values (APPROVED 587, blank 62, REFUSED 15, DEFERRED 3) —
  refusal n=15 is too small for any bucketed comparison. Flagged, not tested
  this session (would need REFUSED n in the dozens per bucket to be worth the
  test budget).
- `committee_reports`: unchanged from the [32] finding (2026-07-19) — no
  committee-item-to-motion linkage exists; still structurally unable to
  support an "upstream settlement" test. Not re-tested (documented INFEASIBLE
  already).
- `other_items.item_type`: 20 distinct values (officer_report 7,881 dominant;
  confidential_item 479 is a literal type label, distinct from and not
  identical in coverage to the `is_confidential` boolean flag other rows also
  carry — a possible future data-quality angle, not pursued this session).

## CEO/officer-turnover events found in `motions.title` (new — Phase-2 lever #3, never used in this corpus before)
Searched `title LIKE '%Chief Executive Officer%'` (36 direct hits) plus a
broader 107-hit OR search. Datable CEO-related events:
- 2000-03-28 "Investment Strategy - CEO Selection" → 2000-12-07 "Censure of
  Chief Executive Officer" (a governance-dysfunction marker, not itself a
  turnover date).
- 2006-06-27 "Completion of Employment Contract Negotiations – CEO
  Appointment" — the cleanest standalone turnover event: not adjacent to the
  2018–21 Inquiry, but does sit roughly 8 months after the Oct-2005 election
  and 16 months before the Oct-2007 election (unavoidable given WA's
  biennial-election cadence relative to a single point event).
- 2018-04-10 "Interim Appointment of Acting CEO" → 2019-05-09 "Appointment of
  Town of Cambridge CEO" — this turnover is fully inside the already-heavily-
  mined 2018–21 Inquiry window ([9]/[19]/[37]/[39]), so it cannot serve as an
  independent, uncontaminated shock.
- 2025-04-08 "Recruitment of Chief Executive Officer – confidentiality" — too
  recent/thin post-window to test (< 1 year of "after" data in the corpus).
Verdict for Stage 2: only the 2006-06-27 event is usable as a clean,
uncontaminated CEO-turnover discontinuity — a single-event test, so any result
is capped at DIRECTIONAL/Observation regardless of effect size (n=1 shock).

## Election-cycle convention re-used (unchanged from [16]/[21]/tests.py)
Pre-election window = 1 Apr–31 Oct of odd years (WA biennial October
elections). `tests.py:742` confirmed as the canonical definition — reused
verbatim, not re-derived, for consistency with the shipped
`governance.election_cycle` battery test.

## Standing confound checklist — reconfirmed still live
All items in Explorer_prompt.txt's STANDING CONFOUND CHECKLIST reconfirmed
applicable and unchanged (item_reference fan-out, lowercase `position` enum,
197 zero-vote placeholders, `estimated_value` 90.8% NULL, `tenders.awarded_to`
45.6% NULL/blank). No new caveat needed for the tables queried this session
beyond the `appointments.role` case-inconsistency note above.
