# Pending merges

Files here are candidate taxonomy genres that a `Researcher_prompt.txt`
session drafted, self-checked against `RESEARCH_PROTOCOL.md`'s four
dimensions, and passed — but has not merged into `Investigator_prompt.txt`
or `pipeline/DATA_ENRICHMENT.md`, because file-review mode (the default) is
what wrote it. See `Researcher_prompt.txt` Phase 4 for exactly what a session
puts in one of these files and `RESEARCH_PROTOCOL.md`'s "Merge flow" section
for the two-mode design this directory exists to support.

An empty directory is the normal steady state between Researcher sessions —
it means nothing is currently awaiting a decision, not that nothing has ever
run.

## What's in a pending-merge file

Named `P<n>_<slug>.md`, matching the candidate's id in
`docs/research/PRECEDENT_BANK.md`. Each one is self-contained: the candidate
id/date/session, its four-dimension score, and two ready-to-paste text
blocks — one for `Investigator_prompt.txt` Part 3, one for
`pipeline/DATA_ENRICHMENT.md`'s pattern layer — plus explicit apply/reject
instructions. You should not need to re-read the originating session to act
on it.

## To apply one

1. Open the file, read both blocks and the four-dimension score.
2. Paste the `Investigator_prompt.txt` block in as the next numbered Part
   3.x sub-section.
3. Paste the `DATA_ENRICHMENT.md` block in as a new Pattern entry (tagged
   `source: Researcher, not corpus-derived`).
4. Update the candidate's entry in `PRECEDENT_BANK.md` from `status:
   candidate — pending human review` to `status: merged`, noting the Part 3
   section number it landed at.
5. Delete this file — `PRECEDENT_BANK.md`'s `## Merged` section is the
   permanent record from here on, not this directory.

## To reject one instead

1. Update the candidate's `PRECEDENT_BANK.md` entry to `status: rejected`,
   with the specific failing reason (even if it's "a human judgement call,
   not a dimension failure" — say so; this is what stops a future Researcher
   session re-proposing the same idea).
2. Delete this file.
