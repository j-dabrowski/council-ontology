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

## Status: v0.3, real chains run pre-narrowing; not yet run against v0.4's boundary

Real Conductor-loop chains ran against Editor v0.3 in August 2026 (see the
open-questions entries below, each citing a real
`defamation_review_<n>.md`) — the "never been run" framing of this section
in earlier versions is stale as of those runs. What's genuinely untested:
v0.4's narrowed scope (the S7 boundary, the four-semantic-class
recalibration, dimension 8). Treat every threshold below as a starting
point to be revised once a real chain runs under v0.4, not a settled
benchmark. The single most important thing a human does after that first
v0.4 run is check whether the editor's flags match their own judgment —
false negatives (missed real risk) are the failure mode that matters; false
positives (over-flagging) waste
iteration cycles but are safe.

## Scoring and thresholds

The eight dimensions are defined in `Editor_prompt.txt`'s "Score" output
block, not duplicated here (single source of truth — update the prompt, not
this doc, when a dimension's definition changes). Today they are all fixed at
pass/fail thresholds the prompt author (this session) judged reasonable —
100% on placement, proportionality/overclaim language, framing balance,
caveat integration, and risk-item re-verification; zero tolerance on
small-n exposure and (added 2026-08-23, per `docs/AGENT_DESIGN.md` §2)
false positives against claims S7 already passed; binary on the disclaimer.

**Why a false-positive dimension exists (added 2026-08-23):** once S7
(`src/invariant_gate.py`) gates `scorecard.json` claims mechanically before
Editor ever runs, Editor re-flagging one of those exact checks (small-n,
name-free schema, entity-resolution) isn't extra caution — it's the Editor
failing to use the boundary `Editor_prompt.txt` v0.4 now defines, and it
wastes a Fixer/Conductor cycle re-fixing something that was never actually
broken. Prediction to verify at the first post-narrowing run: total flag
volume drops enough that the 3-pass cap-outs seen in earlier real chains
stop being the norm (`docs/AGENT_DESIGN.md` §2's own stated prediction) —
record whether that holds in the calibration data below once it exists.

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

## Open questions

- **Superlative single-name call-outs near the n≤3 floor** — flagged
  2026-08-22 (Editor pass 1,
  `data/draft/cambridge/draft_20260822_144521/defamation_review_1.md`): a
  mayoral "least contested" callout named a single councillor at n=5, just
  above the BLOCKING small-n floor. Not a threshold violation under the
  rules at the time — no code change was made for this flag.

  **Resolved 2026-08-23, via `Investigator_prompt.txt` §4.6 (the strength
  ladder and superlative check).** This flag was exactly the gap it looks
  like: an n-floor alone can't catch a superlative claim that clears the
  floor but still singles out one name unfairly (a tie the wording papers
  over, a shared cause, a lawful exception). §4.6 makes `superlative` its
  own declared strength level, independent of n, and requires the
  ties/shared_cause/lawful_exception check whenever it's used — a
  superlative claim that fails any of the three drops to `comparative`
  (state the distribution, not the single name) rather than shipping
  clean. `Editor_prompt.txt` v0.4's Procedure step 3 now checks this
  explicitly under "overclaim language," independent of whatever n the
  claim happens to clear. Not retroactively re-run against the 2026-08-22
  mayoral callout specifically — that's a candidate for the next real
  Editor run, not something to hand-verify here.

- **`<n>` numbering: per run-directory or per-chain?** — flagged 2026-08-22
  (Editor pass 2's own review, `data/draft/cambridge/draft_20260822_152453/defamation_review_1.md`,
  and its fix reports; recurred in pass 3,
  `data/draft/cambridge/draft_20260822_154217/defamation_review_1.md`).
  `Editor_prompt.txt` says to "increment `<n>` on re-review... so the full
  chain is visible in one directory," which assumes re-review happens inside
  the *same* run directory. Under the Conductor's actual design, each
  dispatched Fixer round produces a brand-new `council draft` output in a
  brand-new directory, so every directory only ever holds one review — `<n>`
  as a directory-scoped filename counter is always 1, while `<n>` as a
  chain-scoped pass count (which is what `CONDUCTOR.md`'s pass-cap logic and
  the stage-contract's own `pass:` field track) climbs normally. Passes 2 and
  3 both resolved this ad hoc by naming the file `_1` but titling/stage-
  contracting it with the true chain pass number — workable, but it already
  caused one Fixer session (pass 2's pipeline round) to have to reason about
  which file was authoritative. Undecided as of this entry: either change
  `Editor_prompt.txt`'s filename instruction to explicitly say "chain-scoped,
  not directory-scoped" (so the file itself is named `defamation_review_3.md`
  even though it's the first file in its directory), or accept the
  directory-scoped filename permanently and drop the "chain visible in one
  directory" rationale, since the architecture doesn't deliver on it.

  **Resolved 2026-08-23: directory-scoped, `Editor_prompt.txt` unchanged.**
  Chain-scoping would have required Editor to know the Conductor's
  chain-wide pass count just to name a file correctly — a concept that
  doesn't exist for Editor's other real entry point (a standalone
  re-review of the same directory without a fresh draft, where
  directory-scoped `<n>` is exactly the right, meaningful behaviour
  `Editor_prompt.txt` already describes). Fixed on the *caller* side
  instead — `docs/agent_prompts/fixer.txt` no longer predicts the
  filename via a `<pass_num>` substitution; it now tells Fixer to find
  the highest-numbered `defamation_review_<n>.md` in the directory by
  listing it, the same lookup `_latest_review_record()` in
  `src/publish_gate.py` already uses. Both pass-2 and pass-3 Fixer
  sessions had already reasoned their way to the right file from content
  alone despite the wrong instruction — this closes the gap they were
  routing around rather than relying on that continuing to work.

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

- v0.3 (2026-08-23) — Recalibrated for `Editor_prompt.txt` v0.4's narrowed
  scope (`docs/AGENT_DESIGN.md` §2/§6 Step 5): added dimension 8
  (false-positive rate against S7-already-passed scorecard claims) and
  documented why it exists. Resolved the "superlative single-name
  call-outs near the n≤3 floor" open question via the new
  `Investigator_prompt.txt` §4.6 strength ladder — kept as a resolved
  entry, not deleted, since it's the concrete incident that motivated
  §4.6 existing at all.
- v0.2 (2026-08-10) — split loop/triggering content out to the new
  `docs/review/CONDUCTOR.md` as part of moving Editor and Fixer out of
  `docs/investigator/` into `docs/review/` (they were never investigator-owned
  — Editor reviews across all tracks, Fixer dispatches into three of them).
  Renamed from `DEFAMATION_AUDIT_PROTOCOL.md`. No behavioral change to the
  scoring/thresholds content itself.
- v0.1 (2026-08-10) — first draft, written alongside `Editor_prompt.txt` v0.1.
  No runs yet.
