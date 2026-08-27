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
spawn-a-session pattern this doc extends to two more roles),
`docs/render/Renderer_prompt.txt` + `digest_mode.txt` (the period product
Editor's period-claim review reads, once rendered).

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

## The S7 and S9 boundary

Added 2026-08-23 (`docs/AGENT_DESIGN.md` §3 Q3), once S7 (the invariant
gate, `src/invariant_gate.py`, scripted, runs inside `council draft`) and
S9 (right of reply, `src/reply_packets.py`, `council reply-packets
<council>`) existed to draw a boundary against.
**The Conductor's authority starts at `council draft`'s output and ends at
the S8 flag loop below — it owns neither of the stages next to that loop:**

- **It does not own S7.** A gate failure inside `council draft` is not a
  review finding — it's a blocked draft, full stop. It never enters the
  chain loop below: no Editor call, no pass count, no Fixer dispatch. This
  is the same logic as the existing rule that a FAIL never triggers an
  idle track's Fixer (only the tagged tracks run) — extended one step
  earlier: a gate failure never even reaches Editor to tag anything.
  `gate_report.json`'s violations route straight back to whichever
  generator produced the offending claim, as ordinary engineering work,
  not as a Conductor-mediated review cycle.
- **It does not own S9.** Right of reply (packet assembly, sending,
  response ingestion) is human-paced by design — a reply window measured
  in days can't sit inside a loop with a pass cap, and sending words to a
  real person is a human act under every autonomy level
  (`docs/AGENT_DESIGN.md` §5). S9 is a separate, later stage the Conductor
  never spawns or waits on.
- **The publish invariant is untouched by either.** S7 and S9 only ever
  *add* prerequisites to the authorization record the "one invariant"
  section below describes — a clean S7 gate and (for the deep tier) a
  complete `reply` field become more things `check_clearance()` can
  verify, never an alternative path that skips the record entirely.

In short: the Conductor's whole domain is the box between "a draft exists"
and "a human (or `--gate-profile auto`) decides to publish it" — S7 sits
just before that box, S9 sits beside it, and the box itself is exactly the
loop below, unchanged.

**Restated for period claims (added 2026-08-27, once Editor v0.8 brought
`local/period_digest.json`/`local/digest_summary.md` into scope): the
boundary holds, but S7's own shape at this call site is different, and
that difference matters to how the loop actually behaves.**

- **S7's digest call site is diagnostic, not blocking** — unlike the
  corpus call site above. `cmd_draft` runs `run_invariant_gate` a second
  time, over the digest's own claims, and writes
  `local/digest_gate_report.json`, but it never `sys.exit`s on a failure
  there (`src/cli.py`) — a period digest is *expected* to routinely
  contain `UNIT_INDIVIDUAL` claims (an unexplained absence, a declared
  conflict) that this pass will flag, and that's exactly the signal
  per-claim tier derivation (`src/invariant_gate.py`'s `derive_claim_tiers`)
  consumes to decide what may enter the *public* candidate pool. So a
  digest never gets blocked from reaching Editor the way a corpus S7
  failure blocks the corpus draft — every `council draft` run's digest
  artifacts reach Editor's period-claim review unconditionally (once
  Renderer digest mode has actually run — see the chain-loop note below),
  regardless of what `digest_gate_report.json` says.
- **S9 does not apply to the public digest — structurally, not just
  procedurally.** Renderer digest mode reads only `tier=="public"`
  candidates and only their `public` field (`docs/render/digest_mode.txt`'s
  hard gate) — no `individual`-unit claim, complete-reply or not, can ever
  reach `digest_summary.md`. This is a stronger guarantee than the
  synthesis-mode case S9 was originally written for (where a reply gate is
  actively checked per claim): here there is nothing for a reply gate to
  check, because the claim class it would gate never appears in the
  rendered output at all. The raw `local/period_digest.json` still carries
  the `deep` view (with names) for a human reading it directly under the
  Draft switch — S9 doesn't apply there either, since that surface is
  local-only and never reaches `council publish` regardless of tier.

## The chain loop

```
council draft <council>                         (deterministic — S7 runs
        │                                         here; a gate failure
        │                                         blocks the draft and
        │                                         never reaches the loop
        │                                         below, see the S7/S9
        │                                         boundary section above)
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

**A flag from Editor's period-claim review (jigsaw identification,
body-matched baselines, digest fidelity — `EDITOR_PROTOCOL.md` dimension 9)
enters this exact same loop, no special-casing.** It's a flag like any
other: same PASS/FAIL mechanics, same pass cap, same re-draft-before-
re-review rule. The one honest gap: none of the three Fixer tracks
(frontend/pipeline/doc) currently has authority to *fix* rendered digest
prose — there's no scripted or LLM path yet that takes a digest-fidelity
flag and produces a corrected `digest_summary.md` the way `frontend-fix`
corrects a `.tsx` file. Until one exists, expect Editor's own track-tagging
discipline (`Editor_prompt.txt`'s "When used inside the Conductor's loop")
to route a period-claim flag to `human` by default — the holistic-flag
outlet's own rule already covers this ("the owning track... or `human`
when none could"), so this isn't a gap in the loop, it's a gap in what a
human is asked to do next: re-run `council render digest` with the flag's
detail as guidance, by hand, rather than a Fixer mode doing it
unattended. A fourth Fixer mode that closes this (`FIXER_PROTOCOL.md`'s
"Adding a fourth mode") is plausible future work, not built here.

**A FAIL carrying a `human`-track flag escalates immediately, no Fixer
dispatched.** Added 2026-08-24 for the holistic-flag outlet
(`docs/GENERATION_SCORING_SPLIT.md` §2.2): a review-wide concern Editor
can't pin to one claim, and can't route to any Fixer mode, is still a flag
— tagged `human` instead of `frontend`/`pipeline`/`doc`. This escalates on
the exact same path as a Fixer BLOCKED report (below): the run stops, no
pass is spent, and no Fixer runs for that pass — including for any
co-flagged ordinary tracks, since the human's decision may change what
those fixes should be.

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

- v0.5 (2026-08-27) — Restated the S7/S9 boundary for period claims, now
  that Editor v0.8 brought `local/period_digest.json`/`digest_summary.md`
  into scope: S7's digest call site is diagnostic, not blocking (unlike the
  corpus call site), so a digest's claims always reach Editor once
  rendered, regardless of `digest_gate_report.json`'s own verdict; S9
  doesn't apply to the public digest structurally, since Renderer digest
  mode never renders an `individual`-unit claim in the first place. Added a
  note to "The chain loop" confirming a period-claim flag runs through the
  identical PASS/FAIL/pass-cap loop, with an honest gap noted: no Fixer
  mode yet has authority to fix rendered digest prose, so such a flag
  currently routes to `human` by default under Editor's own existing
  track-tagging rule, not a new loop mechanic. No change to the chain-loop
  diagram, the pass cap, or gate profiles themselves.
- v0.4 (2026-08-24) — Added the `human`-track escalation sentence to "The
  chain loop" (`docs/GENERATION_SCORING_SPLIT.md` §2.2/§2.4's holistic-flag
  outlet): a FAIL carrying a `human`-track flag now escalates immediately,
  same path as a Fixer BLOCKED report, before any pass-cap check. No change
  to the loop mechanics, pass cap, or gate profiles themselves —
  `scripts/conductor_loop.py`'s `VALID_TRACKS` gained `"human"` to match.
- v0.3 (2026-08-23) — Added "The S7 and S9 boundary" section
  (`docs/AGENT_DESIGN.md` §3 Q3): the Conductor owns the S8 flag loop only,
  not S7 (a gate failure blocks the draft mechanically, never entering the
  loop) or S9 (right of reply, human-paced, not built yet). Annotated the
  chain-loop diagram's first step to note S7 runs inside `council draft`.
  No change to the loop mechanics, pass cap, or gate profiles themselves.
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
