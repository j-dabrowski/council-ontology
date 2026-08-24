# The Review Stage

Index for `docs/review/` — the AI-assisted review/fix stage that sits
between `council draft` and `council publish`. Cross-cutting infrastructure
(see `docs/MAP.md`), not owned by any single track: Editor reviews output
from every track, Fixer dispatches fixes into three of them.

## Three worker roles, one orchestrator

This is 3 roles, not 5 agent types — read
[`docs/investigator/EXPLORATION_PROTOCOL.md`](../investigator/EXPLORATION_PROTOCOL.md)
first if the mode-vs-role distinction below is unfamiliar; it's the same
pattern Investigator already uses (one shared reference layer, several
mode-specific operating layers).

| Role | Modes today | Home |
|------|-------------|------|
| **Investigator** | Explorer / Refiner (Runner archived 2026-08-23) | `docs/investigator/` (unchanged — genuinely track-owned) |
| **Editor** | defamation-review | `docs/review/editor/` |
| **Fixer** | frontend / pipeline / doc | `docs/review/fixer/` |

Plus the **Conductor** — not a fourth worker role, a different kind of thing:
the orchestrator that spawns the other three as subagents and decides what
runs next. See [`CONDUCTOR.md`](CONDUCTOR.md).

## Why Editor and Fixer live here, not in `docs/investigator/`

Neither is investigator-owned. Editor reviews output from every track, not
just Investigator's; Fixer's three modes dispatch fixes into frontend,
pipeline, and doc tracks specifically. Ownership follows scope, the same
logic `docs/MAP.md` already applies to `docs/TESTING.md` — infrastructure
that touches every track lives in its own cross-cutting location rather than
inside the track it happens to have been designed alongside.

## Reading order

1. This file, for orientation.
2. [`CONDUCTOR.md`](CONDUCTOR.md) — the loop, the stage contract, the one
   rule (never calls `council publish`) that must survive every future
   change.
3. [`editor/Editor_prompt.txt`](editor/Editor_prompt.txt) +
   [`editor/EDITOR_PROTOCOL.md`](editor/EDITOR_PROTOCOL.md) — if you're
   running or improving the review stage.
4. [`fixer/Fixer_prompt.txt`](fixer/Fixer_prompt.txt) + the three
   `*_mode.txt` files + [`fixer/FIXER_PROTOCOL.md`](fixer/FIXER_PROTOCOL.md)
   — if you're running or improving a fix stage.

## Status (2026-08-22)

Two real Editor chains have now run to completion, both ending the same way:
a 3-pass cap-out with a blocking flag still open, escalated to a human per
`CONDUCTOR.md`'s rule rather than continued. The first was the Aug 10 chain
(`defamation_review_1.md` in `draft_20260810_065408`, `_161747`, `_180259`),
pre-dating the JSON sidecar. The second — `draft_20260822_144521` (pass 1, 7
blocking + 12 advisory) → `draft_20260822_152453` (pass 2, 3 blocking + 3
advisory) → `draft_20260822_154217` (pass 3, 1 blocking + 3 advisory) — is
the first to run under `Editor_prompt.txt` v0.3's `defamation_review_<n>.json`
sidecar, and the first real test of the frontend/pipeline/doc Fixer split:
two full Fixer rounds ran, closing 9 of 10 blocking flags across three
tracks, before the pass cap hit on the one flag (a split-identity data
problem across `councillors` records) that every pass correctly identified
as requiring a human merge decision, not another automated attempt. The six
Aug 14 drafts still have no review of either format.

## Status (2026-08-23/24)

Both chains above ran under `Editor_prompt.txt` v0.3, reviewing everything —
mechanical and semantic findings alike. As of 2026-08-23's redesign, Editor
is v0.4, scope narrowed to four semantic classes only (overclaim language,
innocent-explanation search, singling-out fairness, misleading blended
statistics); the S7 invariant gate (`src/invariant_gate.py`,
`docs/INFORMATION_ARCHITECTURE.md` §3) now catches everything mechanical —
small-n, gating schema and text, entity-resolution — inside `council draft`
itself, before Editor ever sees a draft. A code review of the redesign build
(2026-08-24) confirmed five of the v0.3 chains' seven Aug 22 blocking flags
were exactly this class, mechanically detectable — the evidence the
narrowing was built from.

**2026-08-24 — Editor v0.4's first real run.** `python
scripts/conductor_loop.py cambridge --max-passes 3` → `draft_20260823_171209`,
pass 1: **FAIL — 3 blocking, 5 advisory**. Useful evidence for the narrowing
itself, not just a first data point: two of the three blocking flags were
outside S7's reach by construction, not by luck. Flag 1 (a named councillor's
must-leave recusal rate computed from two records whose stored action
contradicted their own extracted quote) is a data-derivation bug — S7's
claim-schema checks have nothing to check it against. Flag 2 (four likely
split councillor identities) sits in
`councillors.json`, not a battery/scorecard snapshot, so S7 never looks
there at all. Only flag 3 (`OverviewPanel.tsx` reintroducing overclaim
framing already removed elsewhere) is the kind of judgment call v0.4 is
actually scoped to — and it landed in exactly that class.

Fixer[pipeline] root-caused flag 1 beyond what Editor named: a
`setdefault`-first-quote bug in `_linked_declared_votes` was silently
dropping a "left the meeting" sentence whenever it wasn't the first
extraction-evidence row for a declaration, understating compliance for two
more councillors besides the two records Editor
flagged. Fixed at the root, verified by hand against `council.db` and two
clean `council draft` re-runs. Fixer[frontend] closed flag 3 plus all 5
advisories (`tsc`/lint clean). Fixer[pipeline] correctly declined flag 2
(`status: BLOCKED`) — a `councillors.json` identity merge is a hard-to-reverse
shared-data write, same precedent as an earlier real identity merge — and the chain
escalated to a human after pass 1 rather than continuing, per this doc's
rule that a single BLOCKED flag stops it regardless of pass count.

This is the first of the ≥ 3 real v0.4 PASS/FAIL cycles
`maintenance.yml`'s scheduling activation checklist requires; two more
(plus real false-positive data and zero missed real risks across all of
them) are still needed before its `cron:` block can be uncommented.

**2026-08-24 — pass 2, on the re-draft (`draft_20260823_173842`) that
followed pass 1's Fixer round.** FAIL — 1 blocking, 3 advisory. The
councillor-identity flag (pass 1's BLOCKING #2) is unresolved — `council.db`
is unchanged, so it reproduces identically — but this time tagged `human`
directly rather than `pipeline`, since Fixer[pipeline] already reported
`status: BLOCKED` on the exact same flag last pass; re-dispatching it would
just reproduce that report. Per the `human`-track escalation rule above, the
chain stops here with no Fixer dispatched this pass, including for the 3
co-flagged advisories (a new ungated claim in `TrendsChart.tsx`, an internal
`sponsorship.json` inconsistency about a councillor's old-guard membership
that `PRIVATE_ASSESSMENT.md` item 7 currently relies on, and two supportive
`scorecard.json` verdicts using causal/intent-denying wording).
Independently re-verified (not just re-read from the fix reports): pass 1's
pipeline fix (the recusal-miscoding correction) against raw `council.db`
rows directly, and all 5 pass-1 frontend fixes against current component
source — all correct and complete, no regressions. This is now the second
of the ≥ 3 real v0.4 cycles the `maintenance.yml` activation checklist
requires; the councillor-identity merge decision above is the open item
blocking a third clean cycle.

**2026-08-24 — correction to the pass-2 count above, via `Editor_prompt.txt`
v0.6.** `council editor-score`'s first live run against pass 2 found a real
false negative: a named-individual claim at n=1, reachable only via a
`DrillDown` click target, that pass 2's own `claims[]` had already logged by
location but never checked against the small-n floor (gating behind a click
satisfies placement, not small-n — two separate checks). `Editor_prompt.txt`
v0.6 closed the gap (the small-n check is now stated as unconditional and
independent of placement, explicitly including click-gated locations). A
fresh Editor re-review of the same draft under v0.6 found the identical
issue and correctly added it as a second BLOCKING flag, tagged `frontend`
— **pass 2 was actually FAIL, 2 blocking, 3 advisory**, not the "1 blocking"
recorded above. With a `human`-track flag also present, the loop's own rule
would block any Fixer dispatch this pass; the project owner explicitly
authorized a standalone override to fix the independent `frontend` flag
only, leaving the councillor-identity merge untouched and still open. Both
the BLOCKING small-n fix (same `SMALL_N_FLOOR` pattern as
`ConflictRecusalPanel.tsx`/`InterestsChart.tsx`) and the co-flagged
`TrendsChart.tsx` advisory were applied; `tsc -b`, `eslint`, and
`vite build` all clean; no hardcoded name introduced (grepped). The
councillor-identity merge remains the sole open item blocking a third clean
cycle.

## Where this sits in the larger pipeline

```
council draft  →  [this directory's loop]  →  human sign-off  →  council publish
```

See `docs/TESTING.md` "Draft & publish workflow" for the deterministic
stages either side of this one, and `docs/strategy/PRIVATE_ASSESSMENT.md`
(gitignored) for why this stage exists at all — the defamation-exposure
analysis this whole subsystem operationalises.
