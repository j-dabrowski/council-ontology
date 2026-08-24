# Agent Prompts — Fixed Invocation Commands

Cross-cutting infra doc (see `MAP.md`) — not owned by one track, since it
indexes every agent role across the tracks and the cross-cutting review/
render stages. The actual prompt text for each
role lives in its own file under `docs/agent_prompts/` — same pattern this
project already uses for every mode prompt (`Investigator_prompt.txt`,
`Refiner_prompt.txt`, etc. are all separate `.txt` files, never inlined
into a doc); this just extends it one level up, to the invocation strings
themselves. **This doc never inlines prompt text** — only ready-to-run
commands that read the real file, so there is never a second copy of a
prompt to let drift out of sync with `docs/agent_prompts/*.txt`.

If a role's underlying `*_prompt.txt` file is version-bumped, neither this
doc nor its `docs/agent_prompts/*.txt` file needs to change — both just
point at the file, they don't inline its content. Only touch
`docs/agent_prompts/<role>.txt` when a role's *reading order* changes (a
new file added to its "Read first" list, or removed).

**A fixed prompt is only as reliable as the state it reads.** These
commands assume every prior session's output is written down accurately —
if a human fixes something out-of-band (raw SQL against `data/council.db`
in a terminal, a one-off script, anything outside a documented CLI stage)
and doesn't update the doc that described the problem in the same turn,
the next cold session reads stale state and can only stop and ask, not
proceed autonomously. See `Investigator_prompt.txt` §0.5's "State hygiene"
note for the incident this was written from and the rule it sets.

**Two ways to run any command below:**
- **Headless** (shown as written) — runs to completion, no TUI, no
  interruption. This is the CI shape; see "Running any of these via
  GitHub Actions" below for the auth/install setup it needs.
- **Interactive, local** — drop `claude -p "$(cat ...)" ...` and instead
  copy the prompt to your clipboard to paste into an already-running
  session: `cat docs/agent_prompts/<role>.txt | pbcopy` (macOS).

## Pipeline (inventory-refine / extraction-refine — new 2026-08-24)

The two prompt-convergence loops `docs/pipeline/PIPELINE.md` has always
documented as a manual recipe (run, check a quality metric, hand-edit a
prompt file, repeat) — same shape as Editor/Fixer's review loop, so
scripted the same way (`scripts/inventory_loop.py`/`extraction_loop.py`
compose standalone commands rather than dispatching privately, mirroring
`conductor_loop.py`). The prompt-editing step in each is the one piece
that still needs an agent; everything around it (run, measure, check
against the target, decide whether to keep iterating) is scripted.

**Inventory refine — apply the improvement instructions `council typology`
just generated.**
```bash
council inventory-refine cambridge
```
No-ops (no `claude` call, no cost) if `other_content_rate` is already at or
below the 20% target. `council inventory-loop cambridge` calls this
internally, once per pass — this exists standalone for re-running just this
step, or debugging it in isolation. No simple raw-form equivalent here
unlike Editor/Fixer/Renderer above: `docs/agent_prompts/inventory_refine.txt`'s
one placeholder (`<instructions>`) is filled with freshly-generated
multi-paragraph analysis, not a fixed token, so the CLI command is the
only practical way to run this one.

**Extraction refine — apply the issue diagnosis `council validate-sample`
just wrote to `report.txt`.**
```bash
council extraction-refine cambridge
```
No-ops if `data/sample_validation/summary.json` says `converged: true`.
`council extraction-loop cambridge` calls this internally, once per pass —
standalone for the same reasons as inventory-refine above. Raw form
(`docs/agent_prompts/extraction_refine.txt` has no placeholders — it
points the session at `report.txt` directly rather than substituting its
content):
```bash
claude -p "$(cat docs/agent_prompts/extraction_refine.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```

**The loops themselves are scripted, not agent roles** —
`council inventory-loop cambridge [--limit N] [--max-passes N] [--dry-run]`
and `council extraction-loop cambridge [--max-passes N] [--dry-run]`. Real
API calls once run for real (cheap/Haiku for inventory, extraction-tier
for extraction) — `--dry-run` costs nothing. See
`docs/pipeline/PIPELINE.md`'s "Iteration loop" sections (Level 1 and
Level 3) for the full recipe each one automates.

## Investigator (2 active modes, one shared reference layer)

**Explorer — generate and test novel hypotheses.**
```bash
council explore
```
A thin CLI wrapper (`src/cli.py`) around exactly the command below — reuses
`load_prompt`/`run_claude` from `scripts/conductor_loop.py`, so there's one
implementation of "invoke a `claude -p` prompt," not two. No `council`
argument: the prompt has no `<council>` placeholder and self-directs from
`Investigator_prompt.txt` Part 0. Prefer this locally; `discovery.yml`
(CI) calls the raw form directly, shown here for reference and for the
"interactive, local" clipboard path above:
```bash
claude -p "$(cat docs/agent_prompts/explorer.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
Self-directing already: Explorer always generates fresh hypotheses,
seeded from the coverage register's worst open gap (v3.0, discovery-only
as of 2026-08-23), never needs a target named. Ends with a Stage 3
self-score against `EXPLORATION_PROTOCOL.md`; if any benchmark dimension
fails, it proposes (but does not apply) a prompt edit for a human to
review.

**Refiner — codify a validated finding into the permanent battery.**
```bash
council refine
```
Same wrapper shape as Explorer — no `council` argument, prefer this
locally; `discovery.yml` (CI, `refine=true`) calls the raw form:
```bash
claude -p "$(cat docs/agent_prompts/refiner.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
Self-directing as of v1.1 (2026-08-22): Step 0 scans `INVESTIGATIONS.md`
itself, picks the oldest not-yet-`REFINED` eligible candidate (FIFO), and
exits with a clean `NOTHING QUEUED` stage-contract block if nothing
qualifies — never idles or guesses. Before v1.1 this required a
human-named hypothesis in the prompt itself; that's now the file's job, not
the caller's. As of v1.2 (2026-08-23) also emits the declaration block
(unit/MIN_N/strength/principle) the S7 invariant gate enforces, and
updates `coverage_register.json`.

**Runner — retired 2026-08-23** (`docs/AGENT_DESIGN.md` §2, §6 Step 6).
Its duties are all scripted now: battery execution and snapshot export are
`council draft`; regression spot-checks are the S7 invariant gate plus CI;
"clean run as input to the human publish decision" is the draft manifest +
`gate_report.json`, which the publish gate already consumes.
`docs/investigator/Runner_prompt.txt` is archived, not deleted, and
`docs/agent_prompts/runner.txt` removed — there is no invocation command
for this role any more.

## Research (council-agnostic, no per-corpus cadence)

**Researcher — grow the failure/effectiveness taxonomy from real-world precedent.**
```bash
claude -p "$(cat docs/agent_prompts/researcher.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
Gated by default (`researcher_gate_mode` in `config/agent_switches.json`,
currently `file-review`): a passing candidate gets a ready-to-apply file in
`docs/research/pending_merges/` for a human to apply by hand, never a
same-session edit to `Investigator_prompt.txt`/`DATA_ENRICHMENT.md`, unless
you explicitly add "run in auto-merge mode" to the invocation (append it to
`docs/agent_prompts/researcher.txt`'s content for that one run, or type it
as an extra sentence after `-p "$(cat ...)"` — either way it's a deliberate
per-call override, never this file's default).

## Review stage (Editor, Fixer, and the Conductor that chains them)

**Conductor — drive the draft → Editor → Fixer loop end to end.**
```bash
claude -p "$(cat docs/agent_prompts/conductor.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
Conductor is a role a session adopts by being told to drive the loop
(`docs/review/CONDUCTOR.md`: "not a separate program... whichever Claude
Code session is currently driving the loop"), so
`docs/agent_prompts/conductor.txt` states the loop and its one invariant
explicitly, not just a reading order. Self-directing in the sense that
matters here: it never needs a specific draft/finding named, it always
starts from the current DB state. **`scripts/conductor_loop.py` is a
scripted alternative to this command** — see the note under "Running any
of these via GitHub Actions" below.

**Editor alone — defamation-review a specific draft, without the loop.**
```bash
council editor cambridge draft_20260822_120000
```
`council editor-loop` is what you want in the normal case — it calls this
exact command internally, once per pass, so this exists standalone for
re-reviewing a draft without re-drafting it, or debugging Editor in
isolation. Equivalent raw form (`docs/agent_prompts/editor.txt` has two
placeholders, `<council>`/`<run_id>`, that the wrapper fills):
```bash
claude -p "$(sed \
    -e "s/<council>/cambridge/g" \
    -e "s/<run_id>/draft_20260822_120000/g" \
    docs/agent_prompts/editor.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```

**Editor scorer — score a completed review, two layers, never run by
Editor itself.**
```bash
council editor-score cambridge draft_20260822_120000
```
Not a self-directing role and not a fourth worker role — a per-run
follow-on (`docs/GENERATION_SCORING_SPLIT.md` §2.3) invoked after Editor
has already produced a `defamation_review_<n>` pair for the draft named.
Layer 1 (`src/editor_score.py`, a deterministic script — contract hygiene,
flag routability, verdict integrity, the dimension-8 false-positive
cross-check against `gate_report.json`) always runs first and costs
nothing; its result is embedded into Layer 2's prompt as the
`<layer1_json>` placeholder. Layer 2 is a real `claude -p` call, in a
fresh context that never reads `Editor_prompt.txt` or shares any state
with the review session it's scoring — its whole point is independence
from what it judges. Writes `editor_score_<n>.json`/`.md` into the same
draft directory, never touching the `defamation_review_<n>` files it
scored. Exits non-zero if the combined result is FAIL (a Layer-1
structural problem, or a Layer-2 false negative — a real risk the review
missed). Equivalent raw form
(`docs/agent_prompts/editor_scorer.txt` has four placeholders,
`<council>`/`<run_id>`/`<n>`/`<layer1_json>`, that only the CLI wrapper can
fill, since `<layer1_json>` is Layer 1's freshly-computed output, not a
fixed token — same shape as `inventory_refine.txt`'s `<instructions>`
placeholder above. No practical raw-form equivalent for that reason; use
the CLI command.)

**Fixer (frontend / pipeline / doc modes) — apply Editor's tagged flags.**
Not really a standalone, context-free invocation — a Fixer mode only does
something meaningful when it's acting on a specific Editor FAIL's tagged
flags, which is inherently per-call, not a fixed string.
```bash
council fixer frontend cambridge draft_20260822_120000
```
`council editor-loop` calls this exact command internally, once per
flagged track — this exists standalone for re-running one track's fix, or
debugging a mode in isolation. No pass number, deliberately: Fixer finds
its review file by listing the draft directory (Editor's own `<n>` there
is directory-scoped, always `_1` under this design's one-draft-per-pass
architecture, not the Conductor's chain-wide pass count — see
`EDITOR_PROTOCOL.md`'s "`<n>` numbering" entry for the incident this was
fixed from). Equivalent raw form (`docs/agent_prompts/fixer.txt` has three
placeholders, `<track>`/`<council>`/`<run_id>`, that the wrapper fills):
```bash
claude -p "$(sed \
    -e "s/<track>/frontend/g" \
    -e "s/<council>/cambridge/g" \
    -e "s/<run_id>/draft_20260822_120000/g" \
    docs/agent_prompts/fixer.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```

## Renderer (S10, two modes, one shared layer — new 2026-08-23)

Neither mode is self-directing about *which* draft to render. Both modes
read a draft that's already cleared S7/S8 (and, for synthesis mode's
`individual`-unit claims, S9) — see `docs/render/Renderer_prompt.txt` for
what each mode may and may not do.

**Plain-language mode — institutional product → resident-facing summary.**
```bash
council render plain_language cambridge draft_20260822_120000
```
Checks the draft directory exists (fails fast if not) and warns — without
blocking — if `manifest.json` is missing, meaning the S7 gate never
passed on that draft.

**Synthesis mode — deep product → cross-claim prose (the FINDINGS_SUMMARY /
Overview successor).**
```bash
council render synthesis cambridge draft_20260822_120000
```
Both are thin CLI wrappers around the same `load_prompt`/`run_claude`
pattern as Explorer/Refiner above. `docs/agent_prompts/renderer.txt` has
three placeholders (`<mode>`, `<council>`, `<run_id>`) that the wrapper
fills; the equivalent raw form (useful for the "interactive, local"
clipboard path, or if invoking outside the CLI):
```bash
claude -p "$(sed \
    -e "s/<mode>/plain_language/g" \
    -e "s/<council>/cambridge/g" \
    -e "s/<run_id>/draft_20260822_120000/g" \
    docs/agent_prompts/renderer.txt)" \
  --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
Not yet wired into any workflow, and never run for real — no calibration
data exists (`docs/render/RENDERER_PROTOCOL.md`). The CLI wrapper exists
so a human can run it by hand today; that's not the same as CI running it.

## Running any of these via GitHub Actions

Every command above is unchanged whether run locally or in CI — see
`AUTOMATION_ARCHITECTURE.md` Part 3's chaining/branch/PR rules for what
wraps around them. This section is the CLI mechanics of the wrapping
itself: installing Claude Code on a runner and authenticating it without
touching pay-per-token API billing.

**Install:**
```bash
npm install -g @anthropic-ai/claude-code
```

**Authenticate — subscription-based, never `ANTHROPIC_API_KEY`, by
deliberate choice (this project's runs must never bill against API
credits).** Generate a token once, locally, logged into the account whose
subscription should cover these runs:
```bash
claude setup-token
```
This opens a browser OAuth flow (same as `/login`). After approving,
the token prints directly in the terminal — copy it immediately, it is
not saved anywhere. Store it as a GitHub Actions **secret** (not a
Variable — this is a real credential, unlike the GCS `vars.*` values
elsewhere in this project, which deliberately aren't secret):
```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN
# paste the token when prompted
```
or via the web UI: repo → Settings → Secrets and variables → Actions →
New repository secret, named exactly `CLAUDE_CODE_OAUTH_TOKEN`.

**Two caveats worth knowing before relying on this, not fully documented
by Anthropic as of this writing:**
- **The token is tied to the person who ran `claude setup-token`, not a
  service account.** Anthropic's own docs point toward API keys instead
  for org-wide CI/CD, precisely because a `setup-token` credential is a
  personal subscription token, not shared infrastructure. Practical
  consequence: CI usage draws from the *same* usage pool as that
  person's own interactive Claude Code sessions, and if their
  password/session changes or the subscription lapses, every scheduled
  run breaks at once. A deliberate trade-off for this project (avoiding
  metered billing was the explicit priority), not an oversight.
- **Rate limits and the exact expiry/renewal mechanism under repeated
  automated use aren't documented anywhere verifiable.** The token is
  described as a "one-year OAuth token," but whether it warns before
  expiring, and whether CI-style repeated calls hit different throttling
  than interactive use, isn't stated. No proactive warning to build
  against — treat a workflow that starts failing on an auth error as the
  signal to regenerate it.
- **Unsetting `ANTHROPIC_API_KEY` in the child process's own OS
  environment is not sufficient on its own to guarantee subscription-only
  billing.** Claude Code can also inject `ANTHROPIC_API_KEY` via an `env`
  block in a **user-level** settings file (`~/.claude/settings.json`), on
  every invocation, regardless of the child process's own environment —
  a bare `env.pop("ANTHROPIC_API_KEY", None)` can't see or stop that.
  Every `claude -p` invocation in this project (`run_claude()`,
  `scripts/conductor_loop.py`; the two direct calls in `discovery.yml`)
  therefore also passes `--setting-sources project,local`, excluding the
  "user" settings source entirely — this repo's own `.claude/
  settings.json` / `.claude/settings.local.json` carry no `env` block, so
  excluding only "user" costs nothing here. See `docs/CICD_DECISIONS.md`'s
  2026-08-24 entry for the incident this closed and the alternatives
  considered.

**In a workflow step**, the commands above become:
```yaml
- name: Run Refiner
  env:
    CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
  run: |
    claude -p "$(cat docs/agent_prompts/refiner.txt)" \
      --permission-mode dontAsk --allowedTools "Read,Edit,Write,Bash,Grep,Glob"
```
`-p` removes the interactive TUI; `dontAsk` auto-denies anything not in
`--allowedTools` rather than stopping to ask (there's nobody there to
answer). See `AUTOMATION_ARCHITECTURE.md` Part 3 for the full workflow
shape this drops into (branch creation before the call, commit/PR after).

**The draft → Editor → Fixer loop specifically has a scripted
alternative to the Conductor command above: `scripts/conductor_loop.py`,
with its own CLI wrapper:**
```bash
council editor-loop cambridge --max-passes 3
```
`--dry-run` prints the plan (council, pass cap) and exits — no draft, no
`claude` calls, no cost — useful to check the invocation before spending
anything. It reads Editor's machine-readable `defamation_review_<n>.json`
sidecar directly and handles the pass-counting/dispatch-by-track
mechanically, dispatching every stage — `council draft`, `council editor`,
`council fixer` — by shelling out to that exact standalone command, the
same one a human would run by hand, rather than a private duplicate of
"how do I invoke this role." The two that need real judgment (Editor's
review, Fixer's fix) reach a real `claude -p` call one hop inside those
commands — see that script's own docstring for why this is a legitimate
replacement for an agent-driven loop specifically (Editor's verdict is
already structured data) and not a shortcut around the parts that still
need real judgment. It applies the same subscription-only billing
discipline as this section (both layers — see the caveat above), and
never calls `council publish`, same as Conductor itself.

**`scripts/conductor_loop.py` is exactly what `.github/workflows/
maintenance.yml` runs** (added `docs/AGENT_DESIGN.md` §6 Step 7,
2026-08-23) — a real, `workflow_dispatch`-only CI wiring of this section's
pattern, not just a documented possibility. `.github/workflows/
discovery.yml` is the same for Explorer(+Refiner) — see
`docs/TESTING.md`'s "Discovery & maintenance workflows" for the quick
reference and `AUTOMATION_ARCHITECTURE.md` Part 3 for the full design,
including what each workflow deliberately doesn't do yet (auto-publish,
scheduling, a standalone Refiner-only dispatch, PR-gated Fixer edits).

## What's still manual (not a queued command — a human action)

**`council publish`** — never run by Conductor, Editor, or any agent under
any gate profile (`CONDUCTOR.md`'s "one invariant"). This is the CLI
command you run yourself once a draft has cleared review:
```bash
council publish cambridge --from-draft data/draft/cambridge/<run_id> \
  --confirm "reviewed by <you>, <date>, <summary>"
```
See `docs/TESTING.md` "Draft & publish workflow" for the `--gate-profile
auto` alternative.
