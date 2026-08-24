# CI/CD Decision Log

Cross-cutting infra doc (see `docs/MAP.md`) — companion to `TESTING.md`, not
a replacement for it. **`TESTING.md` is the current-state reference**: what's
true right now, kept accurate as things change, rewritten/pruned when a
design is superseded (it already lost the single-`publish.yml` shape this
log still remembers). **This file is a chronological log of the decisions
themselves** — what was considered, what was rejected, and why — kept even
after the reference doc moves on. Modeled on `investigator/INVESTIGATIONS.md`
("the detective's notebook"), same reasoning: a living doc that gets edited
down over time is the wrong place to preserve *why* an earlier design was
rejected.

Written to be pulled from directly for an article and for interview prep —
each entry should stand alone: decision, alternatives, trade-off. New entries
go at the bottom, oldest first, so it reads as a build log.

---

## 2026-07-27 — CI scope: pure-function tests only, no LLM calls in the required path

**Decision:** `.github/workflows/ci.yml` runs `ruff check` + `pytest tests/`
against deterministic, offline code only — the eval gate's state machine
(`determine_status()`) and the extraction/storage layer (`_resolve_offset`,
`save_extraction`), both tested with synthetic inputs or an in-memory
SQLite engine. Nothing in `tests/` touches the network or needs
`ANTHROPIC_API_KEY`.

**Alternatives considered:**
- *Cache-replay smoke test* — commit 2-3 tiny PDF fixtures plus their
  pre-baked `.cache/llm_responses/` JSON (keyed on
  `sha256(pdf_bytes)[:16] + prompt_version`), assert a cache hit with zero
  live calls. Same idea as VCR.py cassettes for HTTP.
- *Live-API canary* — a scheduled, non-blocking job running the real
  extractor against known documents, gated behind a repo secret.

**Trade-off / why deferred, not rejected:** both options break the moment
the prompt changes, because the cache key includes `prompt_version` and the
inventory prompt was under active iteration (`.cache/llm_responses/` already
had `-v1`/`-v2`/`-v3` entries coexisting at the time). A committed fixture or
an exact-match canary would turn "prompt got better" into "CI is red for a
reason unrelated to a bug" — the opposite of what CI is for. The canary
option specifically would need to check structural invariants (valid
Pydantic model, quote offsets resolve, entity counts in range) instead of
exact output to survive intentional prompt changes — worth building once
extraction is in maintenance mode, not during active development.
Standard shape for testing an LLM pipeline: test the business logic
directly, don't pay to re-verify a network call on every push.

**Still true as of 2026-08-17.**

---

## 2026-07-27 — Ruff: ship the built-in default rule set, not a hand-tuned list

**Decision:** `[tool.ruff.lint] select = ["E9", "F", "E7"]` — pyflakes
(unused imports/vars, undefined names), multi-statement-per-line, and
syntax errors. This is ruff's own default set minus `E4`.

**Alternatives considered:** a hand-picked "reasonable" rule list; adding
`I` (import sorting) and `UP` (pyupgrade) for modernization.

**Trade-off / why:** `I` + `UP` were turned on, tested, and reverted —
together they accounted for 213 of an initial 442 violations, all cosmetic,
zero bug-catching value. Turning on a linter for the first time shouldn't
also be a drive-by 200-line style refactor across unrelated files. `E501`
(line-too-long) was excluded too: it fired 98 times at the chosen 110-char
limit, and with no `ruff format`/`black` wired in, enforcing it means manual
line-wrapping busywork with no tooling to do it for you — revisit if/when
`ruff format` is adopted, which makes wrapping free. `E402` (import
position) was excluded because it fired 30 times almost entirely from
deliberate patterns (`sys.path` manipulation, function-local imports in
`scripts/` and route-scoped lazy imports in `api/main.py`) — fixing it means
fighting an existing, reasonable pattern instead of catching bugs. Net
effect: real-bug categories only, no cosmetic opinions baked in on day one.

**Still true as of 2026-08-17** (briefly drifted and was reverted back to
this — see `e3232aa`, 2026-08-09, "Revert ruff select to match documented
config").

---

## 2026-07-27 — Two independent CI jobs, minimal permissions, dependency caching

**Decision:** `ci.yml` has a `python` job (`ruff check`, `pytest`) and a
`frontend` job (`npm ci`, `npm run lint`, `npm run build` — `tsc -b` +
`vite build` in one step), both on `push: [main]` and every `pull_request`.
`permissions: contents: read` at the workflow level. A `concurrency` group
keyed on `${{ github.workflow }}-${{ github.ref }}` cancels superseded runs.
Both jobs use dependency caching (`actions/setup-python` `cache: pip`,
`actions/setup-node` `cache: npm`).

**Alternatives considered:** one job running both stacks sequentially.

**Trade-off / why:** the two stacks have nothing in common (different
runtimes, different failure modes) and splitting them means a Python-only PR
doesn't wait on `npm ci`, and either job's log is scoped to one stack. `contents:
read` follows least-privilege: CI only reads and checks at this stage, never
writes, so there's no reason for the default `GITHUB_TOKEN` to have more.

**Still true as of 2026-08-17.**

---

## 2026-08-05 — GCS for `council.db`, not a GitHub Release asset

**Decision:** the raw extraction database is uploaded to a private GCS
bucket and pulled down at the start of `draft.yml`, never published as a
repo artifact.

**Alternatives considered:** a GitHub Release asset (simpler — no GCP
project needed at all for this one thing).

**Trade-off / why:** `council.db` is *every* entity and quote across the
whole corpus, not the curated subset that clears review into the public
JSON. This repo is public, so a Release asset would be too — publishing the
full, unreviewed DB skips the editorial/liability review the project
already treats as a real concern (`docs/strategy/PRIVATE_ASSESSMENT.md`,
gitignored; `docs/review/editor/Editor_prompt.txt`). A private bucket,
readable only by the workflow's service account, keeps "raw extraction" and
"reviewed-and-public" as two genuinely different trust levels instead of
relying on nobody clicking the wrong link.

**Still true as of 2026-08-17.**

---

## 2026-08-05 — Workload identity federation (OIDC), not a service account key

**Decision:** `draft.yml`/`publish.yml` authenticate to GCP via
`google-github-actions/auth@v2` using workload identity federation — a
workload identity pool + OIDC provider trusting `token.actions.githubusercontent.com`,
restricted by an attribute condition to `assertion.repository ==
'j-dabrowski/council-ontology'`. No JSON key is downloaded or stored
anywhere.

**Alternatives considered:** a downloaded service-account JSON key stored
as a GitHub secret (the "traditional" approach, and what the user's Azure
DevOps background would default to).

**Trade-off / why:** a downloaded key is a long-lived credential — if it
leaks (committed by accident, logged, exfiltrated via a compromised
dependency), it's valid until someone notices and revokes it, and it isn't
scoped to *this specific workflow run*. OIDC instead has GitHub mint a
short-lived token asserting facts about the run itself (repo, workflow,
ref), which GCP exchanges for temporary credentials only if that identity
matches the configured condition. Nothing secret is stored in GitHub at
all — `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_BUCKET`
are repo **Variables**, not Secrets, because knowing them grants nothing on
their own. The service account itself is also scoped minimally: read-only
on the bucket, plus write access restricted to two path prefixes
(`drafts/`, `published/full/`) via a resource-name condition, so
`council.db` itself stays read-only even to the workflow that uses it.

**Reusability noted at the time (2026-08-05), still open as of
2026-08-17:** the trust relationship (pool + provider) is meant to be
reused for the eventual Cloud Run API deploy rather than standing up a
second credential story — see "Open decisions" below.

---

## 2026-08-05 — Single `publish.yml` committing straight to `main` (superseded eight days later)

**Decision (superseded):** the first version of the publish workflow ran
`council publish` and committed the result directly to `main`, with a
comment warning not to actually trigger it yet.

**Why it didn't survive:** there was no review step between "generate JSON"
and "commit it to a public repo," and the project's own private risk
assessment rates defamation exposure MODERATE-to-HIGH from exactly that
pattern — named-individual claims implying legal non-compliance, rendered
at headline level, published without anyone checking them. Recorded here
specifically *because* it was live for a short window and then replaced —
worth being able to say in an interview "we shipped something, found the
gap ourselves before it caused a problem, and closed it structurally" (see
the next entry) rather than pretending the safer design was there from day
one.

**Superseded by:** the entry below, same day gap closed within the week
(`a51756a`, 2026-08-05).

---

## 2026-08-05 — Draft → review → publish split; gate enforced in the CLI, not just the workflow

**Decision:** `council publish` was split into `council draft` (writes to
gitignored `data/draft/<council>/<run_id>/`, never touches git or the
public directory) and `council publish --from-draft <path> --confirm
"<note>"` (the actual gate). Both flags are `required=True` at the argparse
level in `src/publish_gate.py` — there is no code path that publishes
without them. `publish` copies the draft's JSON **verbatim** rather than
recomputing from `council.db`, and re-hashes every draft file against the
hashes recorded at draft time before copying; any drift aborts the publish.
Matched by two separate workflow files instead of one two-job workflow —
`draft.yml` stays `contents: read` since it never touches git, `publish.yml`
needs `contents: write`; the inputs differ too (`publish.yml` requires
`draft_gcs_path` + `confirm_note`, `draft.yml` needs neither); and they're
independent human actions in time — drafting might happen today,
publishing (after review) days later — not one pipeline run.

**Alternatives considered:** keeping the gate as a documented convention
("don't run this without reviewing first") rather than a structural one;
keeping gitignore on `frontend/public/data/` as the safety mechanism;
one workflow file with two jobs.

**Trade-off / why:** a documented convention is exactly what failed in the
previous entry — the CLI *could* run without review, so eventually it
would. Making both flags required moves the guarantee from "the docs say
so" to "the code refuses." Gitignore can't express "reviewed vs.
not-reviewed" as a distinction — it's binary (tracked or not) — so once
`frontend/public/data/` needed to hold real, tracked placeholder data, it
stopped being able to double as the safety mechanism at all. Recomputing
from the DB instead of copying bytes was rejected because the DB can change
between review and publish — copying verbatim (plus the hash check) means
what was reviewed is provably what ships. Splitting into two workflow files
means each file's permission scope matches exactly what it does, rather
than one file carrying the union of both jobs' permissions.

**Still true as of 2026-08-17.**

---

## 2026-08-05 — `python-dotenv` moved to main dependencies (a CI failure, not a design choice, but worth logging)

**What happened:** `src/extraction/extractor.py` calls `load_dotenv()` at
import time; `council draft`/`council publish` pull that module in
transitively via CLI arg-parsing setup even though neither command uses it.
A bare `pip install -e .` (no `[dev]` extra) had no `python-dotenv`
installed at all, so `draft.yml` failed on its first real run.

**Fix:** `python-dotenv>=1.0` moved from nowhere-in-particular to the
main `dependencies` list in `pyproject.toml`, since `api/main.py` and the
pipeline CLI need it at runtime, not just in dev.

**Why this is worth keeping in the log:** it's the concrete example of
*why* a workflow that only ever ran in a dev environment (`pip install -e
".[dev]"`, always) can hide a missing-dependency bug that only shows up
once something installs with production dependencies alone — which is
exactly what a fresh CI runner does. Good illustration for "what does CI
actually catch that local testing didn't."

---

## 2026-08-10 — Frontend deploy: Vercel, repo-connected, no CI/CD YAML

**Decision:** the frontend deploys via Vercel's GitHub App watching the
repo directly — no `.github/workflows/*.yml` job builds or deploys it.
`frontend/vercel.json` sets `"ignoreCommand": "git diff --quiet HEAD^ HEAD
-- ."` so Vercel skips a redeploy when a push touched nothing under
`frontend/` (e.g. a docs-only or pipeline-only commit).

**Alternatives considered:** none seriously — a GitHub Actions job that
builds and deploys the frontend on merge, the originally-sketched shape.

**Trade-off / why:** `ci.yml`'s `frontend` job already proves the build is
correct (typecheck + `vite build`) on every push/PR; Vercel's own build
(triggered independently by its GitHub App) is what actually serves it.
Running a *third* build inside a GitHub Actions deploy job would duplicate
work Vercel already does, for no extra safety — CI already gates
correctness, Vercel already gates deployment. The one thing that needed
fixing was Vercel's default "rebuild on every push to the branch," which
was rebuilding on pipeline/docs/investigator commits that never touch
`frontend/` at all; `ignoreCommand` scopes that down to the paths that
matter, without introducing a deploy workflow file to maintain.

**Still true as of 2026-08-17.**

---

## 2026-08-23 — Two new workflows, `workflow_dispatch` only; scheduling gated behind a written activation checklist, not a decision made now

**Decision:** built `discovery.yml` (Flow A/B — Explorer, optionally
chaining Refiner) and `maintenance.yml` (Flow C/D — `council draft` → the
Editor/Fixer loop via `scripts/conductor_loop.py` → optionally `council
publish --gate-profile auto`), per `docs/AGENT_DESIGN.md` §6 Step 7. Both
are real, mergeable-if-desired workflow files, not stubs. Neither runs on
a schedule. `discovery.yml` never will, by design (`docs/AGENT_DESIGN.md`
§5 — discovery changes the instrument, so it stays a deliberate trigger
permanently). `maintenance.yml` carries a commented-out `cron:` block
directly above its `workflow_dispatch` trigger, with an explicit
activation checklist stated in the file itself (four conditions, all
tracked in `EDITOR_PROTOCOL.md`'s calibration log — see
`AUTOMATION_ARCHITECTURE.md` Part 3, Flow D, for the checklist verbatim)
and `maintenance.yml`'s `publish=true` input defaults to **false** for the
same reason.

**Alternatives considered:**
1. Build the workflows without the commented-out cron block at all,
   leaving scheduling as a documented future step. Rejected (explicit
   project-owner direction, mid-session): a commented block with a
   written activation condition makes turning on scheduling a one-line PR
   later, and makes the precondition legible in the file a future session
   would actually read, not only in a doc that file doesn't reference at
   read-time.
2. Build the full maintenance run exactly as `docs/AGENT_DESIGN.md` §5
   describes it (including Flow 0 — scrape/extract/dedup) in this same
   step. Rejected: Flow 0 is a substantially larger, still partially
   undecided piece of infrastructure (GCS staging/promotion, a typology
   convergence loop, real extraction API cost) that predates this redesign
   and isn't really about "Renderer + reply pipeline... workflow wiring"
   specifically — S2 profile is the only redesign-specific piece Flow 0
   would need, and it's a one-line addition whenever Flow 0 itself gets
   built. Left as a design sketch, unchanged.
3. Wire Editor's auto-publish (`publish=true`) as the default once the
   loop reaches a clean PASS. Rejected: `docs/AGENT_DESIGN.md` §5's own
   stated precondition for autonomous publish (Editor calibration data)
   isn't met — Editor v0.4 has never completed a real PASS/FAIL cycle as
   of this decision. Defaulting to publish would mean the first real use
   of this workflow could autonomously publish on unproven judgment.

**Trade-off / why:** the alternative to a written, in-file checklist is an
implicit "someone will remember to check before enabling this" — exactly
the failure mode `docs/investigator/Investigator_prompt.txt` §0.5's "state
hygiene" rule already exists to prevent for a different kind of
out-of-band state. A checklist inside the workflow file itself means a
future session (human or agent) deciding whether to uncomment the
schedule reads the condition in the same file it's about to change, not a
separate doc it has to already know to consult. The cost is a small
duplication (the checklist appears in both `maintenance.yml` and
`AUTOMATION_ARCHITECTURE.md`) — accepted deliberately, flagged in both
places as needing to stay in sync manually, rather than a single source
that's one file away from the point of action.

**Still true as of 2026-08-23** (same day — no runs yet, so nothing to
report from real use).

---

## 2026-08-24 — A maintenance run holds publish when Fixer has touched source

**Decision:** in `maintenance.yml`, any git-tracked change the Editor/Fixer
loop makes outside `frontend/public/data` opens its own PR, and the publish
step is skipped while that PR exists. Publishing then happens by hand once
it merges (the job summary prints the exact command). Surfaced by the
2026-08-24 code review of the redesign build: the workflow as first written
staged only `frontend/public/data`, so Fixer's repairs died with the runner
while the data they justified was published — the deployed frontend would
have kept rendering an Editor-flagged component against fresh data.

**Alternatives considered:**
- *Publish anyway, let the fixes PR land later.* Keeps a maintenance run
  fully autonomous even when Fixer intervenes, which is the whole point of
  autonomy level 1. Rejected: it publishes into a known-flagged surface and
  relies on a human merging promptly to close a window the Editor opened
  deliberately.
- *Commit Fixer's edits directly to `main` alongside the snapshots.* One
  commit, no held publish, no PR to chase. Rejected: it pushes unreviewed
  agent code edits straight to `main`, against
  `AUTOMATION_ARCHITECTURE.md` Part 3's uniform rule (a git-tracked change
  opens a PR, never a direct commit) — the rule exists precisely for
  changes an agent authored.
- *Fail the whole run when Fixer edits source.* Loud, but throws away a
  perfectly good draft and the review work that produced it.

**Trade-off:** a maintenance run that needed any repair will not
auto-publish, even at autonomy level 1 — so the cadence of unattended
publishing is bounded by how often Editor finds nothing, not by the
schedule. Accepted knowingly: the alternative is publishing data whose
accompanying fix is still in review, which is the exact pairing the review
stage exists to prevent. Revisit if real runs show Fixer intervening so
often that the held-publish path becomes the norm rather than the
exception — that would be evidence about Editor calibration (the
`maintenance.yml` activation checklist) rather than a reason to loosen this.

---

## 2026-08-24 — Escalations become PRs into a `staging` branch; approval-by-merge resumes the run (accepted design, not built)

**Decision:** `AUTOMATION_ARCHITECTURE.md` Part 4 revised. A pipeline
invocation becomes a **logical run** executed as a chain of working-branch
**segments**, each ending in one PR: to `main` on successful completion,
to a long-lived `staging` branch on an escalation. Merging an escalation
PR is the approval that resumes the run — the next segment branches off
`staging`, so approved partial work (including any amendments the human
pushed before merging) is what the continuation builds on. Dispatch
offers **fresh** (reset `staging = main`) or **resume** (keep `staging`,
merge `main` in, continue from `run_state.json` at `staging` HEAD —
approved work never recomputed). Declining an escalation PR ends the run
with no automatic retry; approved segments survive in `staging` for a
later resume dispatch. Instrument fixes go to `main`, run-scoped fixes to
`staging`; resume's unconditional `main → staging` merge picks up either.
Nothing is built yet — both existing workflows keep the old shape (one PR
to `main`, escalation = job summary) until rewired per Part 5's list.

**Alternatives considered:**
- *Status quo: escalation ends the workflow with a job summary; retry is a
  full re-dispatch.* Rejected: no reviewable diff at the escalation point,
  no approval record, and a re-dispatch recomputes everything — including
  expensive, already-good scrape/extraction work — because nothing marks
  where approved work ends.
- *A GitHub request-changes review driving an in-place revision agent* (a
  third response between approve and decline). Rejected: it shifts the
  development environment onto GitHub — review-comment conventions, a
  revision session, a re-review cycle — when "amend the branch in your own
  tools, then merge" already covers the need. GitHub stays the trigger and
  approval surface only.
- *Always reset `staging` at every dispatch (no resume mode).* Rejected:
  a decline followed by a manual fix would force re-running everything,
  wasting tokens on stages a human had already approved.
- *Auto-retry on decline.* Rejected: a decline carries no information to
  retry with, so a blind re-run reproduces the same failure at full cost —
  same principle as the Conductor's existing pass cap.
- *Per-run staging branches instead of one shared lane.* Rejected: gives
  up the clean merge-event trigger and the accumulated approval ledger;
  concurrency is instead handled by a workflow concurrency group (one
  logical run at a time).

**Trade-off:** more PRs per logical run (one per segment instead of one
total), and `main`'s protection now partly depends on `staging` discipline
— an instrument fix committed only to `staging` is hostage to that run
succeeding, which is why fix placement is stated as a rule rather than
left to habit. Accepted because each escalation PR is small, focused, and
arrives exactly when a human decision is needed anyway; the pre-revision
shape had the same human act (read the job summary, fix, re-dispatch)
with less to show for it and full recomputation after.

---

## 2026-08-24 — `--setting-sources project,local` on every agent-role `claude -p` call (real incident, not a hypothetical)

**Decision:** Every `claude -p` invocation this project makes for an
agent role (`scripts/conductor_loop.py`'s `run_claude()` — shared by
Explorer, Refiner, Researcher, Renderer, Editor, Fixer, `editor-score`,
inventory-refine, extraction-refine, and Conductor's own draft/editor/
fixer dispatch — plus `discovery.yml`'s two direct calls) now passes
`--setting-sources project,local`, excluding the "user" Claude Code
settings source from being read at all.

**What actually happened:** the first real `council editor` / `council
editor-score` dispatch of this build (`docs/GENERATION_SCORING_SPLIT.md`'s
Step 1 live demo) drew on an org's API credits and burned the balance out,
despite `run_claude()` already stripping `ANTHROPIC_API_KEY` from the
child process's OS environment before launching it. Root cause: Claude
Code can also inject `ANTHROPIC_API_KEY` via an `env` block in a
**user-level** settings file (`~/.claude/settings.json`), and does so on
every invocation regardless of the child process's own environment — a
mechanism `env.pop(...)` on the Python side cannot see or stop, since it
operates one layer below where Claude Code actually resolves auth.
Verified directly, not inferred: with the shell variable explicitly
unset, a bare `claude -p` call still authenticated via the
settings-injected key (visible in the CLI's own warning, "ANTHROPIC_API_KEY
or another auth source is set and takes precedence over your claude.ai
login"); with `--setting-sources project,local` added, the identical call
cleanly used subscription auth instead.

**Alternatives considered:**
- *Keep only the OS-env stripping, treat the incident as a one-off
  misconfiguration on one machine.* Rejected — the whole point of this
  project's billing discipline is that it must hold regardless of which
  machine or account runs it; a fix that depends on nobody's `~/.claude/
  settings.json` ever carrying an `env` block is not a guarantee, it's
  luck.
- *Override the key explicitly via `--settings '{"env":
  {"ANTHROPIC_API_KEY": ""}}'` instead of excluding the source.* Rejected
  as more fragile: it assumes CLI-provided settings always win a merge
  against user settings, which isn't documented behaviour to rely on,
  versus `--setting-sources` simply not reading the file that could leak
  the key in the first place.
- *Exclude "local" too, not just "user".* Rejected — this repo's own
  `.claude/settings.json` / `.claude/settings.local.json` carry no `env`
  block (verified), and `local` may legitimately carry project-scoped
  permission conveniences later; excluding only the source that actually
  caused the incident is the minimal fix, not the maximal one.

**Trade-off:** an agent-role `claude -p` session run this way no longer
sees any user-level customization (personal hooks, themes, global model
default) — irrelevant for a headless `-p` session with its own explicit
`--permission-mode`/`--allowedTools`, but worth knowing if a future role
ever wants to rely on something the user's global settings would have
provided. Does not touch `src/extraction/extractor.py`, which is *meant*
to bill via `ANTHROPIC_API_KEY` through the Anthropic SDK directly for
real, cost-tracked extraction — a separate code path this decision
doesn't apply to.

---

## Open decisions (not yet made / not yet built, as of 2026-08-22)

Logged now, before they're decided, specifically so the eventual entry can
say what was actually weighed rather than reconstructing it after the fact.

- **API → Cloud Run deploy.** No Dockerfile exists yet, no deploy workflow
  for `api/`. The original design sketch: a GitHub Actions job deploys to
  Cloud Run on merge to `main`, reusing the same OIDC trust relationship
  already built for `draft.yml`/`publish.yml` (steps 9-11 in `TESTING.md`'s
  "One-time GCP setup") rather than standing up a second credential story.
  Still open: whether to bake `council.db` into the image (simple, but
  means a new image build + deploy on every re-extraction) or pull it from
  GCS at container startup (decouples data refresh from deploy, but adds
  a cold-start step and a runtime GCS dependency). Per the original
  plan, decide by checking actual `.db` / image size first, not on
  priors.
- **Out-of-band DB fix detection once `council.db` lives in GCS.** Surfaced
  2026-08-22, alongside `Investigator_prompt.txt` §0.5's new "State
  hygiene" rule (a fresh agent session has no way to know a human fixed
  something via raw SQL in a terminal unless a doc says so — and docs can
  be wrong, see that rule's own worked example of catching its own
  inaccurate claim). The rule solves the *documentation* half; this entry
  is the *detection* half, for once agent sessions no longer share a
  local filesystem with the human running manual fixes — GitHub Actions
  runners today, a possible Cloud Run job/service later.
  - **What was validated locally, works, costs nothing new:** SQLite
    itself keeps no query/change history (no server process, no built-in
    audit log; the `sqlite3` CLI's `~/.sqlite_history` only covers
    interactive sessions, isn't stored in the DB file, and wouldn't travel
    with it regardless). But `ATTACH DATABASE` lets one connection diff
    two `.db` files directly — tested against
    `data/council.db.bak-walkerfix-20260822` (the backup taken
    immediately before the Colin Walker/Walker Colin merge) and it
    reproduced the exact change (one `councillors` row removed, one
    `appointments.councillor_id` reassigned) with no false positives.
    This works on any two local SQLite files regardless of where they
    came from — a GitHub Actions runner or Cloud Run job downloading both
    the live DB and a backup from GCS onto its own ephemeral disk, then
    running the same diff, is architecturally identical to running it on
    a laptop.
  - **What's missing today, concretely:** nothing uploads a backup to GCS
    at all right now. The one-time setup only uploads `council.db` itself
    ("repeat this after every re-extraction" — a manual, local
    `gcloud storage cp`, not part of any workflow), and the service
    account's write access (`storage.objectAdmin`) is scoped by a
    resource-name condition to exactly `drafts/` and `published/full/` —
    `council.db` itself is read-only even to the workflow. Read access
    needs no change (`storage.objectViewer` is granted bucket-wide, no
    prefix condition, so a workflow can already read a hypothetical
    `backups/` prefix today). Write access for backups is the one open
    question, and it forks on *who* creates them: staying a manual
    `gcloud storage cp` step (same habit as `council.db` itself today, no
    IAM change) vs. an automated pipeline stage creating its own backup
    before writing (needs `backups/` added to the existing prefix-scoped
    `objectAdmin` condition — the exact same pattern already used for the
    other two prefixes, not a new design).
  - **A cloud-native alternative to the `.bak-<label>-<date>` filename
    convention, worth preferring over replicating it in GCS:** enable
    Object Versioning on the bucket and always upload `council.db` to the
    same path. GCS then retains every prior version automatically on
    overwrite — no naming convention to invent or remember, no separate
    upload-a-backup step at all. Fetch a specific prior version to diff
    against via `gcloud storage cp gs://$BUCKET/council.db#<generation>
    ./before.db` (`gcloud storage objects list --all-versions` to find
    generation numbers). The local `.bak-*` convention exists only because
    a local SQLite file doesn't version itself; that reason disappears
    once the canonical copy lives in GCS.
  - **Compatible with a later Cloud Run migration without redesign** — this
    is the same "pull from GCS at startup, do the work" shape
    `CICD_DECISIONS.md`'s Cloud Run entry above is already weighing for
    `api/`, reusing the same OIDC trust relationship; the backup-diff step
    is one more thing that pull-and-run shape does, not a different
    architecture for a different compute target.
  - **Cost/lifecycle, not yet decided:** `council.db` is ~176MB as of
    2026-08-22 (confirmed from the local backup file size), so each
    version is a full copy, not a delta — only ever fetch the single most
    recent backup/version for diffing, never the whole history, and set a
    GCS lifecycle rule to expire old versions after some retention window
    (undecided) so storage cost doesn't creep silently regardless of which
    approach (named backups vs. Object Versioning) is chosen.
  - Still entirely undecided: named-backup-upload vs. Object Versioning:
    the retention window; and whether this becomes a documented manual
    pre-flight step for a human-triggered session or an automatic first
    action every agent session takes before reasoning about anything else.
- **Scheduled/automated extraction.** The original plan had a Cloud Run
  Job on a schedule. What got built instead is `workflow_dispatch`-only —
  see `TESTING.md`, "publishing reflects a deliberate, reviewed decision,
  not the passage of time." Whether *drafting* (not publishing) should
  eventually run on a schedule, feeding a human review queue instead of
  requiring someone to remember to trigger it, is still an open question —
  noted in `TESTING.md`'s "Where this goes next" as the natural home for a
  headless Conductor once Editor/Fixer are calibrated.
- **An authenticated draft viewer, to make the final publish approval
  PR-gated without exposing draft content.** Proposed by the project owner
  2026-08-24, alongside the staging escalation model (see that entry
  above) — deliberately parked for a future session, not designed now.
  The problem it solves: `AUTOMATION_ARCHITECTURE.md` Flow E's open
  question (should publish's gate become a PR?) has always been blocked
  on a real conflict — a PR is the approval surface the segment model
  standardises on, but Part 3's hard rule keeps named-individual draft
  content out of anything PR-visible, and the draft JSON itself is
  private GCS. So "approve the final draft via PR" would mean approving
  content the PR cannot show. The proposal: the completed draft's final
  segment PR stays the approval surface, and a **viewer** becomes the
  review surface — run locally, it checks out the PR's branch and pulls
  the draft's private JSON from GCS under the human's own authenticated
  session (`gcloud auth` — read access is already bucket-wide, no IAM
  change needed for the local form), rendering the draft exactly as the
  site would, visible only inside that session until the human approves
  the PR. Explicitly compatible with a later hosted form: a non-public
  preview instance of the site, built for draft review, accessible only
  to authenticated admins.
  - **Most of the local form already exists in pieces:** the frontend dev
    server renders the same snapshot JSON shapes the draft directory
    holds, and Flow C's `ref`-aware preview-draft idea ("checked out
    against the PR's own branch") is the same concept one step earlier
    in the pipeline. The likely build is small: a `council preview
    <council> <run_id>` that pulls the draft dir from GCS to a local
    gitignored path and points the dev server's data source at it.
  - **The hosted form is the larger, separate build** (an auth layer in
    front of a second deployment, credential story for its GCS reads) —
    same class of undecided infrastructure as the Cloud Run entry above,
    and probably the same OIDC/service reuse answer when it's designed.
  - **If adopted, this resolves Flow E** in the direction Part 5's item 4
    sketches (publish rides the final segment PR; merge = publish
    authorization) — the hash-verification question remains: keep the
    existing draft-integrity hash check as a merge-triggered validation
    rather than dropping it, so "what was reviewed is provably what
    ships" survives the gate change. Not decided here.
- **README CI status badge.** Not added yet — small, but Actions history
  already has a real success/failure story worth surfacing (the
  `python-dotenv` failure above, fixed same day) rather than starting from
  a green badge with no history behind it.
