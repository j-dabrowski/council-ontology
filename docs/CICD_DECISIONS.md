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
- **README CI status badge.** Not added yet — small, but Actions history
  already has a real success/failure story worth surfacing (the
  `python-dotenv` failure above, fixed same day) rather than starting from
  a green badge with no history behind it.
