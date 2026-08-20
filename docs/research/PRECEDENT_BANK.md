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

---

## Pending human review

*(none yet — this is where a file-review-mode session logs a candidate that
passed its four-dimension self-check. Each entry here should point at its
matching file in `docs/research/pending_merges/`; move the entry to
`## Merged` or `## Rejected` above/below once a human has acted on that file,
and delete the pending file at the same time.)*

---

## Rejected

*(none yet — a rejected candidate is logged straight here regardless of gate
mode, since it never touches `Investigator_prompt.txt`/`DATA_ENRICHMENT.md`
either way)*
