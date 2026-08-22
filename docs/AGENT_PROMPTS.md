# Agent Prompts — Fixed Invocation Strings

Cross-cutting infra doc (see `MAP.md`) — not owned by one track, since it
indexes every agent role across all four. Every prompt below is the
complete, unmodified string you type (or a harness sends) to start a fresh
session in that role — no per-call customization, no hypothesis number or
target named. Where a role used to need one (Refiner, before v1.1), that's
been fixed in the prompt file itself, not worked around here — see each
row's note.

If a role's underlying `*_prompt.txt`/`*.md` file is version-bumped, this
file doesn't need to change — every string below points at the file, it
doesn't inline its content. Only touch this file when a role's *reading
order* changes (a new file added to its "Read first" list, or removed).

**A fixed prompt is only as reliable as the state it reads.** These
strings assume every prior session's output is written down accurately —
if a human fixes something out-of-band (raw SQL against `data/council.db`
in a terminal, a one-off script, anything outside a documented CLI stage)
and doesn't update the doc that described the problem in the same turn,
the next cold session reads stale state and can only stop and ask, not
proceed autonomously. See `Investigator_prompt.txt` §0.5's "State hygiene"
note for the incident this was written from and the rule it sets.

## Investigator (3 modes, one shared reference layer)

**Explorer — generate and test novel hypotheses.**
```
Read docs/investigator/Investigator_prompt.txt in full (Parts 0–5), then
docs/investigator/Explorer_prompt.txt as your operating mode. Read
docs/investigator/INVESTIGATIONS.md first per the prompt's own instruction.
```
Self-directing already: Explorer always generates fresh hypotheses from the
Phase 1 genre taxonomy and the current DB state, never needs a target
named. Ends with a Stage 9 self-score against `EXPLORATION_PROTOCOL.md`; if
any benchmark dimension fails, it proposes (but does not apply) a prompt
edit for a human to review.

**Refiner — codify a validated finding into the permanent battery.**
```
Read docs/investigator/Investigator_prompt.txt Part 0 in full (schema, data
caveats, verification workflow), then docs/investigator/REFINEMENT_PROTOCOL.md
(the six-dimension benchmark), then docs/investigator/Refiner_prompt.txt as
your operating mode.
```
Self-directing as of v1.1 (2026-08-22): Step 0 scans `INVESTIGATIONS.md`
itself, picks the oldest not-yet-`REFINED` eligible candidate (FIFO), and
exits with a clean `NOTHING QUEUED` stage-contract block if nothing
qualifies — never idles or guesses. Before v1.1 this required a
human-named hypothesis in the prompt itself; that's now the file's job, not
the caller's.

**Runner — execute the frozen battery in production (no hypothesis work).**
```
Read docs/investigator/Investigator_prompt.txt Part 0 in full, then
docs/investigator/Runner_prompt.txt as your operating mode.
```
Runner's own "Read first" list pulls in `src/analysis/tests.py`, the most
recent `AUDIT_<date>.md` (or `INVESTIGATIONS.md` as fallback), and
`REFINEMENT_PROTOCOL.md` for context — not repeated here, same principle as
above. Targets whichever council(s) `src/cli.py`'s `COUNCILS` dict lists;
name one explicitly once a second council exists and you want just one run.

## Research (council-agnostic, no per-corpus cadence)

**Researcher — grow the failure/effectiveness taxonomy from real-world precedent.**
```
Read docs/research/RESEARCH_PROTOCOL.md, docs/research/PRECEDENT_BANK.md,
docs/investigator/Investigator_prompt.txt Part 3, and
docs/pipeline/DATA_ENRICHMENT.md, then docs/research/Researcher_prompt.txt
as your operating mode.
```
Gated by default (`researcher_gate_mode` in `config/agent_switches.json`,
currently `file-review`): a passing candidate gets a ready-to-apply file in
`docs/research/pending_merges/` for a human to apply by hand, never a
same-session edit to `Investigator_prompt.txt`/`DATA_ENRICHMENT.md`, unless
you explicitly add "run in auto-merge mode" to the invocation.

## Review stage (Editor, Fixer, and the Conductor that chains them)

**Conductor — drive the draft → Editor → Fixer loop end to end.**
```
Read docs/review/REVIEW.md for orientation, then docs/review/CONDUCTOR.md in
full — you are acting as the Conductor for this session: drive the loop,
spawn Editor and Fixer as subagents, decide what runs next. Read
config/agent_switches.json first (conductor_max_passes).

Run the chain starting from a fresh `council draft cambridge`. Dispatch
Editor (docs/review/editor/Editor_prompt.txt, defamation-review mode) on
that draft. If Editor returns FAIL: dispatch only the Fixer mode(s)
(docs/review/fixer/) the flags actually tagged, re-run `council draft
cambridge` (fresh run_id — never re-review a stale one), and re-run Editor.
Repeat up to conductor_max_passes. If the cap is hit with blocking flags
still open, stop and escalate to a human rather than continuing.

Do not run `council publish` under any circumstances, in any gate profile —
that is a human sign-off action per CONDUCTOR.md's one invariant, not
something you do. Stop once you have either a clean Editor PASS or a
cap-hit escalation, and report which, plus the exact `council publish`
command that would run next if it PASSed.
```
This is the one prompt on this page that isn't just "read these files" —
Conductor is a role a session adopts by being told to drive the loop
(`docs/review/CONDUCTOR.md`: "not a separate program... whichever Claude
Code session is currently driving the loop"), so the invocation has to
state the loop and its one invariant explicitly, not just point at a file.
Self-directing in the sense that matters here: it never needs a specific
draft/finding named, it always starts from the current DB state.

**Editor alone — defamation-review a specific draft, without the loop.**
```
Read docs/review/REVIEW.md, then docs/review/CONDUCTOR.md (the loop this
mode runs inside of when chained), then docs/investigator/Investigator_prompt.txt
Part 4, then docs/strategy/PRIVATE_ASSESSMENT.md (gitignored, read
directly), then docs/review/editor/Editor_prompt.txt as your operating
mode. Review the most recent data/draft/cambridge/<run_id>/.
```
Use this only when you deliberately want a single review pass with no
Fixer/re-draft loop attached — normally the Conductor prompt above is what
you want, since it already dispatches Editor as its first step.

**Fixer (frontend / pipeline / doc modes) — apply Editor's tagged flags.**
Not really a standalone, context-free invocation — a Fixer mode only does
something meaningful when it's acting on a specific Editor FAIL's tagged
flags, which is inherently per-call, not a fixed string. Normally the
Conductor dispatches this automatically. To run one by hand:
```
Read docs/review/REVIEW.md, then docs/review/CONDUCTOR.md's "stage
contract" section, then docs/review/editor/Editor_prompt.txt in full (the
review that produced the flags you're acting on), then
docs/review/fixer/FIXER_PROTOCOL.md, then docs/review/fixer/Fixer_prompt.txt
(shared layer) and docs/review/fixer/<frontend|pipeline|doc>_mode.txt (your
specific mode) as your operating mode. Act only on flags tagged
[<track>] in <the specific Editor review file/run_id>.
```

## What's still manual (not a queued prompt — a human action)

**`council publish`** — never run by Conductor, Editor, or any agent under
any gate profile (`CONDUCTOR.md`'s "one invariant"). This is the CLI
command you run yourself once a draft has cleared review:
```bash
council publish cambridge --from-draft data/draft/cambridge/<run_id> \
  --confirm "reviewed by <you>, <date>, <summary>"
```
See `docs/TESTING.md` "Draft & publish workflow" for the `--gate-profile
auto` alternative.
