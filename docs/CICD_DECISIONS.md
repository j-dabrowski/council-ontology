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

## Open decisions (not yet made / not yet built, as of 2026-08-17)

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
