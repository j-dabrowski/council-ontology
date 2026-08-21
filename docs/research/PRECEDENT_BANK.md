# Precedent Bank

The growing, council-agnostic artifact `Researcher_prompt.txt` writes to and
merges from. As of v1.2 (2026-08-20), the default is **file-review mode**:
Researcher drafts a candidate, self-scores it against `RESEARCH_PROTOCOL.md`'s
four dimensions, and if all four pass, writes a ready-to-apply pending-merge
file to `docs/research/pending_merges/` rather than editing
`Investigator_prompt.txt`/`DATA_ENRICHMENT.md` directly — logged here as
`status: candidate — pending human review` until a human opens that file and
applies (or rejects) it by hand. **Auto-merge mode** — direct, same-session
merge with no file and no human read first — is still available, but only
when a human explicitly declares it at session start; entries produced that
way are logged straight to `status: merged`. This file is the audit log of
the whole process (`merged` / `candidate — pending human review` /
`rejected`), not itself a place to approve anything — approval of a pending
entry happens by acting on its linked file in `pending_merges/`. Rejected
entries are never deleted; they're the record that stops the Researcher
re-proposing the same idea.

Each entry: failure/effectiveness mode → real precedent → data signature —
the same row-shape `Investigator_prompt.txt` Part 3 already uses, so a
merged entry is a near-direct copy-paste into that file.

---

## Merged

### P1 — Policy / programme effectiveness
- **Status:** `merged` — landed as `Investigator_prompt.txt` Part 3.5,
  2026-08-20.
- **Provenance note:** this entry pre-dates `Researcher_prompt.txt` and
  `RESEARCH_PROTOCOL.md` existing — it was identified in design conversation
  (`DISCOVERY_LOOP_DESIGN.md` Component A) and merged directly rather than
  through a Researcher session. Logged here retroactively so the bank has
  one worked example of the format, and so a future Researcher session
  doesn't waste a cycle re-discovering it independently. It does **not**
  yet have a matching `DATA_ENRICHMENT.md` Pattern entry (that requirement
  was added in v1.1, after this entry was merged) — a first Researcher
  session should backfill one if it re-touches this genre.
- **Failure mode:** declared council interventions are approved with a
  stated goal but never evaluated afterward against that goal.
- **Precedent:** UK Local Audit and Accountability Act 2014 (the "value for
  money" arrangements duty on local auditors — economy/efficiency/
  **effectiveness**); CIPFA/SOLACE *Delivering Good Governance* Principles
  C and D (defining outcomes; determining interventions to optimise their
  achievement).
- **Data signature:** a stated commitment (approval motion with a declared
  goal) + an implementation record (was it done, cost, timeline) + an
  outcome measurement (was it checked afterward) — the three-part shape
  written out in full in Part 3.5.
- **Dimension scoring (retroactive, informal):** 1 non-duplication — pass,
  no existing Part 3.x genre covers effectiveness; 2 grounded precedent —
  pass, both citations are real and checkable; 3 translatability — pass,
  see the worked traffic-calming example in Part 3.5; 4 defamation safety —
  pass, genre-level only, no claim about any specific council.

### P2 — Budget-balancing through perpetually deferred savings targets
- **Status:** `merged` — landed as `Investigator_prompt.txt` Part 3.6 and
  `DATA_ENRICHMENT.md` #11, 2026-08-22 (human-applied from the pending-merge
  file, same day as the session that drafted it).
- **Session:** first-ever `Researcher_prompt.txt` run, 2026-08-22,
  file-review mode (v1.3).
- **Failure mode:** a named savings/efficiency target is approved as part of
  balancing the budget, then reappears — same or larger, same
  description/category — in a subsequent year's budget with no intervening
  record that it was achieved.
- **Precedent:** Croydon LBC external audit findings (Grant Thornton, via
  Institute for Government / Accountancy Daily, Aug–Nov 2020) — "insufficient
  challenge" from members on savings-plan deliverability, real failure to
  deliver social-care savings; Slough BC Grant Thornton Section 24 report
  (May 2021) — up to 50% of the 2021/22 savings programme (£15.576m) not
  achieved, many lines with no costed delivery plan.
- **Data signature:** a `budget_items`/`motions` savings line that reappears
  in a later year's budget at the same/increased figure with no intervening
  delivery record, or explicitly minuted as not delivered/re-profiled/slipped.
- **Dimension scoring:** all four passed.

### P3 — Capital receipts used to plug recurring revenue deficits (capitalisation dependency)
- **Status:** `merged` — landed as `Investigator_prompt.txt` Part 3.7 and
  `DATA_ENRICHMENT.md` #12, 2026-08-22 (human-applied from the pending-merge
  file, same day as the session that drafted it).
- **Session:** first-ever `Researcher_prompt.txt` run, 2026-08-22,
  file-review mode (v1.3).
- **Failure mode:** proceeds from an asset disposal (a capital receipt), or a
  formal permission to treat revenue costs as capital, applied to cover a
  recurring operating/revenue shortfall rather than capital expenditure,
  repeating across consecutive budget cycles.
- **Precedent:** UK "capitalisation direction" mechanism — councils on the
  public record as recipients include Croydon (£70m), Nottingham City
  Council, Wirral (£9m), Bexley (£3.87m), Eastbourne (£6.8m), Luton (£35m),
  Peterborough (£4.8m).
- **Data signature:** a `budget_items`/`motions` record where a disposal-tied
  receipt or capitalisation is applied against an operating/revenue line
  rather than a capital-project line, recurring year to year.
- **Dimension scoring:** all four passed.

### P4 — Senior-officer exit payments used to avoid a dispute becoming public
- **Status:** `merged` — landed as `Investigator_prompt.txt` Part 3.8 and
  `DATA_ENRICHMENT.md` #13, 2026-08-22 (human-applied from the pending-merge
  file, same day as the session that drafted it).
- **Session:** second `Researcher_prompt.txt` run, 2026-08-22, file-review
  mode (v1.3).
- **Failure mode:** a payment to a departing senior officer beyond ordinary
  contractual entitlement, approved confidentially with a generic rationale
  and no matching disciplinary/performance record, at an approval level or
  disclosure standard inconsistent with the payment's size.
- **Precedent:** UK statutory guidance, "Statutory guidance on the making
  and disclosure of Special Severance Payments by local authorities in
  England" (DLUHC, May 2021) — full-council approval required ≥£100,000,
  named sign-off £20,000–£100,000, mandatory annual-accounts disclosure.
- **Data signature:** a confidential/exempt `motions` record tied to a
  senior officer's departure (cross-referenced against `senior_officer_events`,
  DATA_ENRICHMENT #7) where the recorded approval level doesn't match the
  statutory threshold, or the payment is absent from that year's accounts
  disclosure.
- **Dimension scoring:** all four passed. Flagged at draft time as sitting
  closer to existing genres (3.1's confidential spend, 3.4's confidentiality
  overuse, 3.3's threshold-gaming) than P2/P3 were — reviewed against that
  concern specifically before being applied; held up as genuinely distinct
  (a named payment-type mechanism with its own statutory guidance, not a
  restatement of any of the three).

### P5 — Unaudited or disclaimed accounts as a meta-signal (audit backlog)
- **Status:** `merged` — landed as `Investigator_prompt.txt` Part 3.9 and
  `DATA_ENRICHMENT.md` #14, 2026-08-22 (human-applied from the pending-merge
  file, same day as the session that drafted it).
- **Session:** second `Researcher_prompt.txt` run, 2026-08-22, file-review
  mode (v1.3).
- **Failure mode:** the council's annual Statement of Accounts is presented
  substantially after the statutory deadline and/or receives a qualified or
  disclaimed audit opinion for one or more consecutive years, meaning other
  financial signals for that period are unverified rather than merely bad.
- **Precedent:** England-wide local audit backlog — 771 audits overdue as of
  31 December 2023 (peak 918); statutory backstop dates (13 December 2024
  for years to 2022/23; 27 February 2026 for 2024/25); 200+ councils
  received disclaimed opinions on 2023/24 accounts as a result.
- **Data signature:** a `budget_items`/reports record of the Statement of
  Accounts being received, capturing opinion type and the gap between the
  statutory deadline and the actual presentation date, tracked across years.
- **Dimension scoring:** all four passed.

**Note on `DATA_ENRICHMENT.md` renumbering:** applying P2–P5 inserted four
new entries (#11–14) into section A, which pushed the two pre-existing
section-B entries from #11/#12 to #15/#16 — relevant if a future session's
non-duplication check (Principle 1) needs to cite a `DATA_ENRICHMENT.md`
entry by number, since #11–14 are new as of this session.

---

## Pending human review

*(none currently — this is where a file-review-mode session logs a
candidate that passed its four-dimension self-check. Each entry here should
point at its matching file in `docs/research/pending_merges/`; move the
entry to `## Merged` or `## Rejected` above/below once a human has acted on
that file, and delete the pending file at the same time.)*

---

## Rejected

*(none yet — a rejected candidate is logged straight here regardless of gate
mode, since it never touches `Investigator_prompt.txt`/`DATA_ENRICHMENT.md`
either way)*
