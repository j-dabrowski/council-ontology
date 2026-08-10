# Fixer Protocol

Governs `Fixer_prompt.txt` and its three modes: what "done" means per mode,
how a fourth mode gets added, and how this role is calibrated. Mirrors
`docs/investigator/REFINEMENT_PROTOCOL.md` in spirit — Fixer's job (verify
and correct against a known-good source) is structurally close to Refiner's.

Related: `Fixer_prompt.txt` (shared layer), `frontend_mode.txt` /
`pipeline_mode.txt` / `doc_mode.txt` (the three modes), `docs/review/
CONDUCTOR.md` (dispatches this role and defines the stage contract its output
must satisfy), `docs/MAP.md` (the track vocabulary the modes are named after).

---

## Status: v0.1, untested

No mode has run yet. There's no calibration data, and — unlike Editor, which
at least has one real dry-run's worth of flags to react to as of this
writing — Fixer has never been dispatched against a real flag. Treat
everything below as a starting structure, not a settled process.

## What "done" means, per mode

A mode's report (see the stage-contract block in `Fixer_prompt.txt`) claims
`status: DONE` only when:

- **frontend** — `tsc --noEmit` and `npm run lint` both clean, the specific
  flagged name/number no longer appears as a literal string (for hardcoding
  flags) or is confirmed gated (for placement flags) by reading the changed
  component, not just by having made an edit.
- **pipeline** — the corrected number is confirmed by an independent
  hand-derived query against `council.db`, not just by the code producing a
  different output than before.
- **doc** — the new claim traces to a cited source, and the old claim is
  struck through or quoted rather than deleted, per the append-only
  convention in `doc_mode.txt`.

A mode that can't fully address a flag (needs a product decision, needs a
follow-up in another track, turns out not to be a bug at all) should report
that honestly as `status: DONE` with the flag marked "not fixed — see
observations," not force a claim it can't back up. `CONDUCTOR.md`'s loop
handles this correctly already — a partially-addressed flag simply
re-appears (or doesn't, if the Editor agrees it's not actually a defect) on
the next Editor pass.

## Adding a fourth mode

The design goal (see `docs/review/REVIEW.md`) is that this is additive:

1. Confirm the new track doesn't already fit one of the three existing modes
   — check `docs/MAP.md`'s "Where do I add X?" table first, since Fixer's
   track vocabulary is meant to mirror it exactly.
2. Write `<track>_mode.txt` in this directory, same shape as the existing
   three: scope, brief (point at that track's own governing doc — don't
   restate it), verification bar, common flag shapes.
3. Add the track name to `Editor_prompt.txt`'s tagging instructions and to
   this doc's mode list.
4. No change needed to `Fixer_prompt.txt` (the shared layer) or
   `CONDUCTOR.md` (the dispatch logic already routes by tag, generically) —
   if either needs to change to add a mode, that's a sign the new mode isn't
   actually additive and needs more thought.

## What "done" looks like for this protocol

Same discipline as every other protocol doc in this project: run each mode
for real at least once, then check whether a human independently agrees the
fix was correct and complete. Specific things to watch for on the first
runs:
- Did a mode stay inside its declared scope, or drift into "helpfully" fixing
  something adjacent? (See `Fixer_prompt.txt`'s explicit warning against
  this — if it happens anyway, the warning needs to be stronger, not just
  present.)
- Did the verification bar actually catch a bad fix, or did a mode claim
  `DONE` on something that didn't hold up? A missed verification is the
  priority fix, the same way a missed flag is Editor's priority fix.
- Cross-track follow-ups (a pipeline fix that needs a frontend fix once the
  number changes) — did the mode correctly flag the follow-up rather than
  either attempting it out-of-scope or silently dropping it?

## Changelog

- v0.1 (2026-08-10) — first draft, written alongside `Fixer_prompt.txt` and
  its three modes. No runs yet.
