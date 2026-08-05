# Testing & CI

Cross-cutting infrastructure doc — not owned by one track (see `docs/MAP.md`),
since it covers the Python pipeline, the frontend, and the CI/automation
workflows that connect them. Added 2026-07 alongside `.github/workflows/ci.yml`;
`.github/workflows/publish.yml` added shortly after.

## What's tested, and why

`tests/` has two files:

- **`test_extractor.py`** — the extraction/storage layer: `_resolve_offset`
  (finds a quote's character offset in source text) and `save_extraction`
  (writes an `ExtractedMeeting` to the DB, including hallucination flagging
  when a quote doesn't resolve). Runs against `sqlite:///:memory:`.
- **`test_validation_core.py`** — the eval framework's `PASS`/`REVIEW`/`FAIL`
  gate: `determine_status()` and the metric functions that feed it
  (`_classify_quotes`, `compute_paraphrase_rate`, `compute_coverage`,
  `compute_inventory_agreement`, `compute_keyword_gaps`), all from
  `src/validation/core.py`.

Both files test **pure functions only** — same inputs always produce the
same outputs, no network/DB/filesystem side effects (`test_extractor.py`'s
DB tests use an in-memory SQLite engine created fresh per test, which is
still deterministic and hermetic). Nothing in `tests/` requires
`ANTHROPIC_API_KEY` or hits the network. That's a deliberate boundary, not
an oversight — see "Why no LLM calls in CI" below.

`determine_status()` in particular is worth calling out: it's the function
that decides whether an extraction is trustworthy, and it's a plain state
machine — six scalar inputs, one string output, no I/O. `test_validation_core.py`
has one test per branch (`FAIL` on zero quotes, `FAIL` on low completeness,
the two coverage-based `FAIL`/`REVIEW` branches, the paraphrase/gap/completeness
`REVIEW` branch, the agenda document-type carve-out, the happy `PASS` path).
That's the highest-value test coverage in the repo relative to its cost:
free to write, instant to run, and it directly protects the thing the whole
eval framework exists to produce.

## Why no LLM calls in CI

The pipeline has three layers that could plausibly be "tested" against a
live or cached API response, and they're not equivalent:

1. **`src/extraction/extractor.py`** (the Haiku/Sonnet/Opus-tiered structured
   extraction) — has no caching layer at all. Every call hits the API live.
2. **`scripts/inventory.py`** (a lighter "L1" sanity pass) — caches raw
   responses by `sha256(pdf_bytes)[:16] + prompt_version` in
   `.cache/llm_responses/`, so a cache hit is genuinely offline-replayable.
3. **`src/validation/core.py`**'s `determine_status()` gate — operates on
   data already in `data/council.db`, compared against source PDF text and
   (optionally) the L1 inventory. Needs a populated DB + PDF text + census —
   none of which are committed (`data/raw/cambridge/*.pdf`, `data/council.db`,
   `data/census.json` are all gitignored).

We considered (and deferred) two additional test layers:

- **Cache-replay smoke test**: commit 2-3 tiny PDF fixtures plus their
  pre-baked `.cache/llm_responses/` JSON, assert `cache_hit=True` with zero
  live calls. This is a real, useful pattern (the "recorded fixture /
  cassette" idea, same principle as VCR.py for HTTP) — but the cache key
  includes `prompt_version`, and the prompt is under active iteration
  (`.cache/llm_responses/` already has `inventory-v1`/`-v2`/`-v3` entries
  coexisting). A committed fixture goes stale the moment the version bumps,
  turning "prompt actively improved" into "CI red for a reason unrelated to
  a bug." Revisit once the inventory prompt stabilizes.
- **Live-API canary**: a scheduled (not PR-blocking) job that runs the real
  extractor against known documents and diffs against expected output,
  behind a repo secret. Same staleness problem if it diffs exact output
  during active prompt development — the fix is to check structural
  invariants instead (valid Pydantic model, quote offsets resolve, entity
  counts in a sane range) rather than exact-match, so it survives
  intentional prompt changes and only fires on real breakage (API/schema
  drift, model deprecation). Worth building once extraction is in
  maintenance mode rather than active development — not now.

So today's CI tests the deterministic core (the gate, the storage layer)
and leaves the nondeterministic, cost-bearing LLM calls untested in the
required path. That's the standard shape for testing an LLM pipeline: test
the business logic directly, don't pay to re-verify a network call on every
push.

## Ruff

Configured in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 110
target-version = "py311"

[tool.ruff.lint]
select = ["E9", "F", "E7"]
```

`select` is deliberately **ruff's own built-in default rule set**
(`E4, E7, E9, F` minus `E4`, which we exclude — see below) — not a
hand-tuned list. That's a defensible "boring" choice: no cosmetic style
opinions baked in on day one, just real-bug categories:

- **`F`** (pyflakes) — unused imports, unused variables, undefined names,
  pointless f-strings. Actual dead code / likely-bug signals.
- **`E7`** — multiple statements on one line (`if x: return y`, `a; b; c`).
  Cheap readability wins that occasionally hide logic.
- **`E9`** — syntax errors. Free to include, never a false positive.

**`E4` (import position/formatting) and `E501` (line-too-long) are
excluded on purpose.** `E402` fired 30 times, almost all from deliberate
`sys.path` manipulation or function-local imports in `scripts/` (CLI
startup-time imports) and `api/main.py` (route-scoped lazy imports) — fixing
those would mean fighting an existing, reasonable pattern, not catching
bugs. `E501` fired 98 times at a 110-char limit; with no autoformatter
(no `ruff format` / `black`) wired in yet, enforcing a line-length ceiling
means manual line-wrapping busywork with no tooling to do it for you. Both
are candidates to revisit if the project adopts `ruff format`, which would
make wrapping free.

`I` (import sorting) and `UP` (pyupgrade / modernize syntax) were tried and
reverted: together they accounted for 213 of an initial 442 violations,
100% cosmetic, zero bug-catching value — turning on ruff for the first time
shouldn't also be a drive-by 200-line style refactor across unrelated files.

Run locally:

```bash
ruff check src/ scripts/ api/ tests/
ruff check src/ scripts/ api/ tests/ --fix   # auto-fixes what it safely can
```

## CI workflow

`.github/workflows/ci.yml` — two independent jobs, on `push` to `main` and
every `pull_request`:

- **`python`** — `pip install -e ".[dev]"`, `ruff check`, `pytest tests/ -q`.
- **`frontend`** — `npm ci`, `npm run lint` (eslint), `npm run build`
  (`tsc -b && vite build` — typecheck and production bundle in one step).

Both use dependency caching (`actions/setup-python` with `cache: pip`,
`actions/setup-node` with `cache: npm`) and a `concurrency` group that
cancels superseded runs on the same branch. `permissions: contents: read`
at the workflow level — CI only reads and checks, never writes, so the
default `GITHUB_TOKEN` is scoped down accordingly.

Reproduce either job locally:

```bash
# python job
pip install -e ".[dev]"
ruff check src/ scripts/ api/ tests/
pytest tests/ -q

# frontend job
cd frontend
npm ci
npm run lint
npm run build
```

## Publish workflow

`.github/workflows/publish.yml` — the last mile from a finished local
extraction run to the live site: running `council publish` and committing
the result, without needing a full local checkout with the 176MB
`data/council.db` up to date. It's `workflow_dispatch`-triggered, not
scheduled: publishing reflects a finished extraction/investigation pass,
not the passage of time.

### ⚠ Known gap: no defamation-review gate yet — do not run this against real data

`frontend/public/data/*.json` (the snapshots this workflow commits) is
**currently gitignored, deliberately, and not yet committed.** Don't assume
"curated JSON battery output" implies "reviewed and safe to publish" — it
doesn't. This project's own private risk assessment
(`docs/strategy/PRIVATE_ASSESSMENT.md` — gitignored, not in this doc on
purpose, read it directly rather than any summary) rates defamation
exposure MODERATE-to-HIGH, specifically from named-individual claims that
imply legal non-compliance and are rendered at headline/chart-note level
rather than behind a drill-down. That assessment's action item #1 — a WA
media lawyer consult — isn't done yet. Checked directly against the actual
(uncommitted) snapshot content: the pattern that doc warns about is present
verbatim in the current data, not just a theoretical risk.

This workflow, as built, has **no review step between "generate JSON" and
"commit it to a public repo."** That's fine for the tooling itself to
exist (the workflow file contains no council data), but it must not be
triggered for real until at least one of:

1. `docs/strategy/PRIVATE_ASSESSMENT.md`'s prioritized mitigations are done
   (see that doc's "Immediate next steps" section — still the accurate
   priority order); or
2. A defamation-auditor pass (in development) has cleared a given publish
   run and gates the commit step itself.

Until then, treat this as **git history is forever**: even a same-day
correction doesn't remove the original from `git log`, commit permalinks,
or anyone's existing clone — unlike a live site, which can be fixed in
place. "Commit now, review before the next one" is not a mitigation.

**Why GCS, not a GitHub Release:** `council.db` is the _raw_ extraction —
every entity and quote across the whole corpus, not just the curated subset
that made it into the vetted JSON battery on the live site. This repo is
public; a GitHub Release asset would be too. Publishing the full,
unreviewed DB publicly skips the editorial/liability review this project
already treats as a real concern (see `docs/strategy/PRIVATE_ASSESSMENT.md`
and the future defamation-auditor idea below) — so it lives in a **private**
GCS bucket instead, readable only by this workflow.

**Why OIDC, not a service account key:** a downloaded JSON key is a
long-lived credential — if it ever leaks (committed by accident, logged,
exfiltrated from a compromised dependency), it's valid until someone
notices and revokes it. Workload identity federation instead lets GitHub
mint a short-lived OIDC token describing the run ("this is a `workflow_dispatch`
run of `j-dabrowski/council-ontology`"), which GCP exchanges for temporary
credentials _only if_ that identity matches a condition you configured —
here, "the repository is exactly this one." Nothing secret is stored in
GitHub at all; there's no key to leak.

### One-time GCP setup

You'll need the `gcloud` CLI (`brew install --cask google-cloud-sdk` on
macOS) and a GCP project with billing linked. Run these yourself — project
creation and billing are tied to your own GCP identity:

```bash
# 1. Authenticate (opens a browser)
gcloud auth login

# 2. Create the project (IDs are globally unique — pick your own)
export PROJECT_ID="council-ontology-684562"
gcloud projects create "$PROJECT_ID" --name="council-ontology"
gcloud config set project "$PROJECT_ID"

# 3. Link billing
gcloud billing accounts list
gcloud billing projects link "$PROJECT_ID" --billing-account=<YOUR_BILLING_ACCOUNT_ID>

# 4. Enable the APIs this setup needs
gcloud services enable storage.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# 5. Create the private bucket (uniform bucket-level access = no per-object
#    public ACLs are possible, even by accident)
export BUCKET="${PROJECT_ID}-pipeline-data"
gcloud storage buckets create "gs://${BUCKET}" \
  --location=australia-southeast1 \
  --uniform-bucket-level-access

# 6. Upload the DB (repeat this after every re-extraction)
gcloud storage cp data/council.db "gs://${BUCKET}/council.db"

# 7. A dedicated, minimal-privilege service account for this workflow only
gcloud iam service-accounts create publish-workflow \
  --display-name="GitHub Actions: publish.yml"
export SA_EMAIL="publish-workflow@${PROJECT_ID}.iam.gserviceaccount.com"

# 8. Grant it read-only access to just this bucket — not the whole project
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"

# 9. The trust boundary: a Workload Identity Pool GCP will accept GitHub's
#    OIDC tokens through
gcloud iam workload-identity-pools create github-pool \
  --location=global --display-name="GitHub Actions"

# 10. An OIDC Provider inside it, restricted to this exact repo
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='j-dabrowski/council-ontology'"

# 11. Allow ONLY workflow runs from that repo to impersonate the service account
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/j-dabrowski/council-ontology"

# 12. Wire the results into the repo as Variables (not Secrets — see why below)
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER \
  --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
gh variable set GCP_SERVICE_ACCOUNT --body "$SA_EMAIL"
gh variable set GCP_BUCKET --body "$BUCKET"
```

`GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` / `GCP_BUCKET` are
repo **Variables**, deliberately not **Secrets**: they're just identifiers.
Knowing the provider path or service account email grants nothing on its
own — access is only possible from a GitHub Actions run whose OIDC token
satisfies the attribute condition set in step 10 (this exact repository).

**Trigger the publish** (only once the review gap above is closed):

```bash
gh workflow run publish.yml
```

**What it does:** checks out the repo, installs the package (`pip install
-e .` — `council publish` touches no Anthropic/extractor code, so no API
key is needed on the runner — confirmed by reading `cmd_publish` in
`src/cli.py` before writing this), authenticates to GCP via
`google-github-actions/auth` (OIDC exchange, no key), downloads
`council.db` from the bucket with `gcloud storage cp`, runs
`council publish cambridge`, then commits `frontend/public/data/` with a
bot identity and pushes — guarded by a `git diff --cached --quiet` check so
a no-op publish (nothing changed) doesn't create an empty commit.

**Permissions:** `contents: write` **and** `id-token: write` at the
workflow level, in contrast to `ci.yml`'s `contents: read` only. `id-token:
write` is what lets the workflow mint the OIDC token in the first place —
without it, `google-github-actions/auth` has nothing to hand GCP. Same
least-privilege principle as `ci.yml`, different answer because this job
actually needs to push a commit and authenticate outward.

**A subtlety worth knowing cold:** a `git push` made from a workflow step
using the default `${{ github.token }}` does **not** trigger other
workflows in the repo (including `ci.yml`'s `push: branches: [main]`) —
GitHub suppresses this deliberately to prevent infinite loops. Vercel still
deploys, because its GitHub App watches pushes directly, independent of
Actions events. If you ever want the bot's own commit to also run through
`ci.yml`, that requires a personal access token instead of the default
token — a real trade-off (broader, longer-lived credential) not worth
making unless there's a concrete reason to lint/test a pure-data commit.

**Where this goes next:** the OIDC trust relationship set up here (steps
9-11) is reusable, not single-purpose — the eventual Cloud Run API deploy
authenticates to GCP the same way, via the same kind of provider/pool,
rather than a second, separate credential story. This workflow's shape
(trigger → do work → commit output) also generalizes: once Cloud Run Jobs
exist for the scraper/extractor/investigator, "run `council publish`"
becomes "authenticate via OIDC, trigger the Cloud Run Job, wait, download
its output" instead of running directly on the GitHub runner — same
interface, swapped internals. Also the natural home for a later autonomous
defamation-auditor pass: same trigger pattern, reading published JSON
instead of writing it, flagging issues (plausibly as GitHub Issues — no new
infra needed) and triggering the investigator to re-run.

## Adding coverage

- New pure logic (parsing, scoring, gating, matching) → unit test it
  directly with synthetic inputs, same pattern as `test_validation_core.py`.
  No fixtures, no DB, no API key.
- New DB-touching logic → follow `test_extractor.py`'s pattern:
  `sqlite:///:memory:` engine + `Base.metadata.create_all`.
- Anything that needs a real LLM call → don't add it to `tests/`. Revisit
  the cache-replay or live-canary options above once the relevant prompt
  has stabilized.
