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
| **Investigator** | Explorer / Refiner / Runner | `docs/investigator/` (unchanged — genuinely track-owned) |
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

## Status (2026-08-10)

Nothing in this directory has ever been run. `Editor_prompt.txt` has one
dry-run's worth of design discussion behind it but zero real invocations at
the time this index was written. Treat every doc here as an untested first
structure — the thing to do next with this directory isn't more design, it's
a real run.

## Where this sits in the larger pipeline

```
council draft  →  [this directory's loop]  →  human sign-off  →  council publish
```

See `docs/TESTING.md` "Draft & publish workflow" for the deterministic
stages either side of this one, and `docs/strategy/PRIVATE_ASSESSMENT.md`
(gitignored) for why this stage exists at all — the defamation-exposure
analysis this whole subsystem operationalises.
