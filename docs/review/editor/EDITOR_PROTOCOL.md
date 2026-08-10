# Editor Protocol

Governs `Editor_prompt.txt` specifically: its scoring thresholds, what
"calibrated" means for this role, and how it's improved. Mirrors the
structure of `docs/investigator/EXPLORATION_PROTOCOL.md`; read that first if
this is unfamiliar territory. **This doc does not own the loop** — how Editor
is chained with Fixer, how many passes are allowed, and what happens on PASS
vs. FAIL vs. cap-hit is `docs/review/CONDUCTOR.md`'s job, not this file's.
Keeping that split is what lets Editor and the loop mechanics be improved
independently of each other.

Related: `Editor_prompt.txt` (the prompt this protocol governs),
`docs/investigator/Investigator_prompt.txt` Part 4 (the defensibility rules
being audited), `docs/strategy/PRIVATE_ASSESSMENT.md` (gitignored — the risk
analysis this whole stage exists to operationalise), `docs/review/CONDUCTOR.md`
(the loop this prompt runs inside of), `docs/TESTING.md` "Draft & publish
workflow" (where this stage sits in the larger pipeline).

---

## Status: v0.1, untested

There is no calibration data yet — this protocol and the prompt it governs
have never been run. Treat every number below as a starting point to be
revised after the first real run, not a settled benchmark. The single most
important thing a human does after the first run is check whether the
editor's flags match their own judgment — false negatives (missed real risk)
are the failure mode that matters; false positives (over-flagging) waste
iteration cycles but are safe.

## Scoring and thresholds

The seven dimensions are defined in `Editor_prompt.txt`'s "Score" output
block, not duplicated here (single source of truth — update the prompt, not
this doc, when a dimension's definition changes). Today they are all fixed at
pass/fail thresholds the prompt author (this session) judged reasonable —
100% on placement, proportionality, framing balance, caveat integration, and
risk-item re-verification; zero tolerance on small-n exposure; binary on the
disclaimer.

**These thresholds are explicitly user-adjustable** — nothing here is fixed
policy. If, after a few real runs, 100%-on-everything proves to reject drafts
over genuinely trivial issues (e.g. an advisory-only miss on a low-stakes
panel), a human can loosen a specific dimension's threshold. Do that by
editing the threshold table in `Editor_prompt.txt` directly and noting the
change (with reasoning) in that file's changelog — not by asking the editor
agent to grade itself more leniently mid-run.

**One rule that should never become adjustable without an explicit, logged
decision:** the BLOCKING-flag-fails-regardless-of-score rule. Averaging away
a single serious risk against several clean claims is exactly the failure
mode a per-claim gate exists to prevent.

## Track-tagging is part of what's being calibrated

`Editor_prompt.txt` now requires every flag to carry a `track` tag
(`frontend` / `pipeline` / `doc`, matching `docs/MAP.md`'s own vocabulary) so
`CONDUCTOR.md` can route it to the right Fixer mode. This is a second thing
to check on the first real run, alongside the flags themselves: did the
editor tag correctly? A flag routed to the wrong Fixer mode either fails
loudly (the mode has no authority over the named file) or, worse, succeeds
quietly by touching something adjacent — check tagging accuracy the same way
you'd check flag accuracy.

## Logging

Every pass writes `data/draft/<council>/<run_id>/defamation_review_<n>.md` —
gitignored, colocated with the draft it reviewed. Because `data/draft/` is
cleaned up over time, a chain run worth keeping as a record (e.g. the one
that led to an actual publish decision) should have its reviews copied into
`docs/investigator/INVESTIGATIONS.md` or a dedicated append-only log
(not yet created — add one if/when the first real chain completes and this
turns out to matter) before the draft directory disappears. Nothing
currently does this automatically.

## What "done" looks like for this prompt

Same discipline as `EXPLORATION_PROTOCOL.md`: run it for real, then compare
the editor's flags against a human's independent read of the same draft.
- If the editor's blocking flags match what a human would flag: the prompt
  is doing its job — promote from "v0.1, untested" to a calibrated version.
  It doesn't need to be perfect; it needs to catch what a hasty human
  reviewer would miss, which is a lower bar than a lawyer's judgment.
- If the editor misses something a human catches: that's the priority fix —
  update `Editor_prompt.txt`'s procedure to add the missed check,
  version-bump, re-run.
- If the editor over-flags heavily (many advisory flags a human would wave
  through): loosen the relevant threshold per the adjustment process above,
  rather than training the editor to just flag less — a chatty editor a
  human has to triage is safer than a quiet one that misses something.
- If the track tags are frequently wrong: that's also a priority fix, since
  a misrouted flag either goes nowhere or reaches the wrong Fixer mode.

## Changelog

- v0.2 (2026-08-10) — split loop/triggering content out to the new
  `docs/review/CONDUCTOR.md` as part of moving Editor and Fixer out of
  `docs/investigator/` into `docs/review/` (they were never investigator-owned
  — Editor reviews across all tracks, Fixer dispatches into three of them).
  Renamed from `DEFAMATION_AUDIT_PROTOCOL.md`. No behavioral change to the
  scoring/thresholds content itself.
- v0.1 (2026-08-10) — first draft, written alongside `Editor_prompt.txt` v0.1.
  No runs yet.
