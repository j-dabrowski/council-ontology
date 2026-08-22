# Stage 2 Hypothesis List — Explorer session, 2026-08-22

Full PREDICTION/MECHANISM/REFUTES/IDENTIFICATION/CONFOUND template and
results are in `INVESTIGATIONS.md` Phase O (Session 11), hypotheses
[46]–[49] — not duplicated here. This file records the enumerate-before-
testing step per `EXPLORATION_PROTOCOL.md` Stage 2.

| # | Genre | Question | Tables |
|---|-------|----------|--------|
| 46 | F — Effectiveness | Are declared trials/pilots evaluated against their own stated purpose before becoming permanent, discontinued, or lapsing? | motions (title, motion_text, outcome), meetings |
| 47 | A — Financial | Does budget/finance business cluster at the WA fiscal year-end (30 June)? | budget_items, meetings |
| 48 | B — Governance / E — Strength (dual) | Is membership on the council's own oversight bodies (Audit Committee, CEO Performance Review Committee) captured by the powerful, or does it draw broadly? | appointments, votes, motions |
| 49 | C — Integrity | Is the `is_confidential` flag applied consistently, independent of `item_type`? | other_items |

Domains covered: A, B, C, E, F (5/6 — D deliberately skipped, see
Session 11 `[STAGE 9]` entry for rationale).

Genres considered and explicitly NOT advanced to testing (with reason):
- 3.6–3.9 (budget-optimism/savings-target, capitalisation-dependency,
  senior-officer severance, unaudited-accounts) — each already has a
  Researcher-sourced Pattern in `pipeline/DATA_ENRICHMENT.md` (#11–#14)
  confirming the corpus lacks the needed structural linkage; two quick
  confirmatory queries (motions title search, other_items text search)
  found zero senior-officer exit-payment events, ruling out even a partial
  test of 3.8. See `stage1_data_profile_2026-08-22.md`.
- Ward-based voting alignment (`councillor_terms.ward`) — only 58 term
  rows carry a ward value at all (33 distinct councillors of 400), too
  sparse to power any per-ward comparison. Noted, not tested.
- Building-permit repeat-applicant capture (mirror of [20]) —
  `building_permits` has no applicant-name field at all (checked schema
  directly), so the test is structurally impossible on this table, unlike
  the [20] planning-applications version. Noted, not tested (correctly
  caught at Stage 1, not spent at Stage 4 — doesn't count against the
  structural-kill dimension).
- `tenders.description` single-source/direct-negotiation keyword search —
  only 1/840 rows mention "sole"/"single tender"/"direct negotiation";
  confirms (rather than newly discovers) the existing `data_ok=False`
  status of `procurement.single_source` in the battery. Two-query check,
  not a full hypothesis.
