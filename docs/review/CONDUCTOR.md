# The Conductor

Governs the orchestrator role that chains Editor and Fixer together: how it's
actually triggered today, the stage-contract every worker's output must
carry, the loop itself, the pass cap, and — the one invariant that must
survive every future change to this doc — what publish authorization always
requires, under every gate profile.

Related: `docs/review/REVIEW.md` (how this fits with Editor/Fixer),
`docs/review/editor/Editor_prompt.txt` + `EDITOR_PROTOCOL.md`,
`docs/review/fixer/Fixer_prompt.txt` + `FIXER_PROTOCOL.md`,
`docs/TESTING.md` "Draft & publish workflow" (where this whole stage sits),
`docs/investigator/EXPLORATION_PROTOCOL.md` "Current approach" (the
spawn-a-session pattern this doc extends to two more roles).

**Naming note:** this role was called "the runner" through most of the
design conversation that produced this doc. Renamed to **Conductor** before
anything shipped, because `docs/investigator/Runner_prompt.txt` already names
an *Investigator mode* (the production-battery run) — same word, unrelated
concept. If you find "runner" used to mean this orchestrator anywhere outside
this doc's own history, it's a leftover from before the rename; treat
`Editor_prompt.txt`/`Fixer_prompt.txt`/this doc as current.

---

## What the Conductor actually is

Not a separate program. **The Conductor is whichever Claude Code session is
currently driving the loop.** There is no `council conduct` command and no
background daemon. When a human asks a session to "run the chain," that
session becomes the Conductor for as long as the loop runs — it spawns
Editor and Fixer as subagents (via the Agent tool, each carrying its prompt
file as its brief), reads their output, and decides the next call. This
mirrors how Investigator work has always been done here
(`EXPLORATION_PROTOCOL.md`, "Current approach": a session given a prompt
file, working autonomously with subagents) — extended to two more roles
rather than inventing new infrastructure.

A future headless version (a script that shells out to `claude -p` or the
Agent SDK instead of a human starting an interactive session) is a plausible
later step, once there's enough real chain data to know the interface is
right. **Don't build it before that** — automating a dispatch policy nobody
has run yet just moves the unproven part somewhere harder to inspect.

For the fuller picture of *why* a headless Conductor eventually matters — not
just "it could work," but the actual operational pressure that would make it
worth building — see `docs/pipeline/PIPELINE.md` "Longer term → Production
scale": once this project watches many councils on a recurring schedule
rather than one council manually, a human reading every draft in full stops
scaling, and the Conductor's whole job is shrinking that per-cycle human
effort without ever removing the checkpoint itself.

## The stage contract

Every worker's output — Editor's review, each Fixer mode's report — ends
with a short machine-readable block, not just prose, so the Conductor (or a
human) can act on it without re-reading and re-interpreting the reasoning
trail each time:

```
status: PASS | FAIL | DONE
pass: <n>                      (Editor only — which review pass this is)
tracks: [<track tags present>]  (Editor: tags found; Fixer: the track it ran as)
next: <the literal next action>
```

This isn't a new convention — `council draft`'s real CLI output already ends
with exactly this shape in prose form: *"Review this output ... then run:
council publish cambridge --from-draft ... --confirm ..."* The stage-contract
block just makes that machine-parseable for the two roles that didn't
previously have a deterministic exit, without changing what the deterministic
stages already do.

## The chain loop

```
council draft <council>                         (deterministic)
        │
        ▼
Editor — defamation-review mode, pass 1 (agent)
        │
        ├── PASS ─────────────────────────────────────► human sign-off
        │
        └── FAIL, flags tagged [frontend|pipeline|doc]
                    │
                    ▼
            pass < max_passes (cap)?
                    │
        ┌───────────┴───────────┐
       yes                      no
        │                        │
        ▼                        ▼
  dispatch Fixer modes    escalate to human —
  for the tracks present   cap passes failed,
  (only the tagged ones —  stop iterating
   e.g. a frontend-only
   FAIL never touches
   pipeline-fix)
        │
        ▼
  council draft <council>        (deterministic re-run — new run_id)
        │
        ▼
  Editor pass 2 ──── loop ────────────────────────────► (same branch as above)
```

**Loop cap: `conductor_max_passes` in `config/agent_switches.json`
(currently 3).** Chosen, not derived — a starting point to revise once
there's real data on how many passes a typical FAIL actually takes to
clear. If the cap is hit and blocking flags remain, the Conductor stops and
escalates rather than attempting another pass. Per `Editor_prompt.txt`'s own
instruction: persistent failure across multiple targeted fixes is a signal
the underlying claim may not be publishable in *any* framing — a judgment
call for a human (and eventually a lawyer), not something to keep automating
around. A human can explicitly authorize more passes if the flags are
trending toward resolution (fewer blocking flags each round) rather than
stuck — that's a deliberate override, not the default.

**Only dispatch the Fixer modes a FAIL actually tagged.** A frontend-only
FAIL should never trigger `pipeline-fix` — running an idle track wastes a
call and gives it an opportunity to "fix" something that was never broken.

**Every pass's draft must be freshly generated.** The publish gate's
integrity check (`verify_draft_integrity`, `src/publish_gate.py`) hashes
draft files at draft time — reviewing a stale `run_id` after a Fixer mode has
changed the underlying files means the bytes being reviewed don't reflect the
fix. Re-draft after every dispatched Fixer round, even though it's
mechanically wasteful — reviewing stale output defeats the entire point of
the gate.

## The one invariant that must survive every future version of this doc

**Publish always requires a verifiable authorization record, never any
single agent's self-assessment.** Two profiles satisfy this today (see
"Gate profiles" below):

- **`--gate-profile interactive` (default).** A human types `--confirm`
  directly — the record *is* their own action, in the moment. The Conductor
  never calls `council publish` in this profile, full stop; both exits from
  the loop above (clean PASS and cap-hit escalation) lead to the same human
  sign-off node, exactly as before.
- **`--gate-profile auto` (opt-in, see "Gate profiles").** `check_clearance()`
  (`src/publish_gate.py`) independently re-validates Editor's own on-disk
  PASS record against the exact draft being published — the record isn't
  the Conductor's claim, it's Editor's file, re-derived by code. **In this
  profile, and only this profile, the Conductor is permitted to invoke
  `council publish --gate-profile auto`** — its authority to do so comes
  from that independent re-validation succeeding, not from the Conductor
  asserting anything about its own review.

What must never happen, in either profile: an agent publishing on its own
say-so, with no record independent of that agent to check against.

## Gate profiles

Every checkpoint in this loop — sign-off after PASS, escalation at the pass
cap — runs in one of two modes today, chosen once, by whoever starts the
run; no stage decides its own mode or escalates its own permissions
mid-run. This mirrors how `docs/research/Researcher_prompt.txt` already
does session-level mode selection for its own merge gate.

- **`interactive`** (default) — every checkpoint above is exactly what it's
  always been: PASS routes to a human, cap-hit routes to a human, publish
  needs a human-typed `--confirm`.
- **`auto`** — PASS still requires the same 7-dimension, zero-blocking-flags
  bar (nothing about Editor's own scoring loosens); the difference is what
  happens *after* a real PASS is on disk — `council publish --gate-profile
  auto` can re-validate it and proceed without a human typing anything.
  Cap-hit escalation is **not** made autonomous by this profile — 3 failed
  automated fix attempts stays a stop, not a proceed, in every profile;
  what changes with a profile is only whether *clearing* moves forward
  unattended, never whether *failing* does.
- **`async:<channel>`** (e.g. email) — designed, not built. A profile where
  a checkpoint pauses and notifies a human out-of-band instead of either
  blocking interactively or clearing automatically. Deferred to a later
  phase; noted here so a future version of this doc has a named slot for it
  rather than needing another rule reframe.

**What the `auto` guarantee actually covers:** it's *structural*, not
adversarial. It stops an accidental publish of stale, regressed, or
non-PASS content, because the verdict is re-derived from Editor's own file
rather than trusted from the Conductor's report of it. It does **not** stop
a compromised or malicious agent from writing a fake PASS record directly —
every role in this pipeline runs with the same repo write access today, so
that's not a boundary code can enforce yet. A genuinely adversarial
guarantee needs a signer distinct from whatever writes the draft — that's
what the deferred `async` profile is for, not a security control `auto`
provides on its own.

## Changelog

- v0.2 (2026-08-20) — reframed "the Conductor never calls `council publish`"
  around the real invariant it was standing in for (a verifiable
  authorization record, never an agent's self-assessment), now that
  `council publish` has a second, code-enforced authorization path.
  In `--gate-profile auto` the Conductor is now permitted to invoke publish
  itself, because clearance comes from `check_clearance()` independently
  re-validating Editor's on-disk PASS record, not from the Conductor's
  own claim. Added the "Gate profiles" section (`interactive`/`auto` built,
  `async:<channel>` designed but deferred) and an explicit honesty note
  that `auto`'s guarantee is structural, not adversarial. See
  `src/publish_gate.py` and `docs/review/editor/Editor_prompt.txt` v0.3 for
  the code/prompt sides of this same change.
- v0.1 (2026-08-10) — first draft. Absorbs and corrects the loop/triggering
  content that used to live in `EDITOR_PROTOCOL.md` (née
  `DEFAMATION_AUDIT_PROTOCOL.md`), which described FAIL routing to "the next
  investigator pass" — wrong once Fixer's three track-scoped modes were
  designed. Never run.
