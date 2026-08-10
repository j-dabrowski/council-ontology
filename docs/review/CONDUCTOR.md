# The Conductor

Governs the orchestrator role that chains Editor and Fixer together: how it's
actually triggered today, the stage-contract every worker's output must
carry, the loop itself, the pass cap, and — the one rule that must survive
every future change to this doc — what it is never allowed to do.

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
            pass < 3 (cap)?
                    │
        ┌───────────┴───────────┐
       yes                      no
        │                        │
        ▼                        ▼
  dispatch Fixer modes    escalate to human —
  for the tracks present   3 passes failed,
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

**Loop cap: 3 Editor passes.** Chosen, not derived — a starting point to
revise once there's real data on how many passes a typical FAIL actually
takes to clear. If pass 3 still has blocking flags, the Conductor stops and
escalates rather than attempting pass 4. Per `Editor_prompt.txt`'s own
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

## The one rule that must survive every future version of this doc

**The Conductor never calls `council publish`.** Not "unless a human
pre-authorizes bypassing review" — never, structurally, regardless of
verdict. Mechanically nothing stops an agent from typing a `--confirm`
string; the constraint is a project convention, not a code-enforced one (see
`docs/TESTING.md`: `--confirm` is supposed to encode genuine human vouching).
Both exits from the loop above — clean PASS and cap-hit escalation — lead to
the same human sign-off node. The Conductor's job ends at "here's a draft and
its full review trail, ready for a decision." Publish is always the
separately, manually invoked command.

## Changelog

- v0.1 (2026-08-10) — first draft. Absorbs and corrects the loop/triggering
  content that used to live in `EDITOR_PROTOCOL.md` (née
  `DEFAMATION_AUDIT_PROTOCOL.md`), which described FAIL routing to "the next
  investigator pass" — wrong once Fixer's three track-scoped modes were
  designed. Never run.
