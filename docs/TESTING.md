# Testing & CI

Cross-cutting infrastructure doc — not owned by one track (see `docs/MAP.md`),
since it covers the Python pipeline, the frontend, and the CI/automation
workflows that connect them. Added 2026-07 alongside `.github/workflows/ci.yml`;
`.github/workflows/publish.yml` added shortly after; `publish.yml` was later
split into `draft.yml` + `publish.yml` (2026-08) once `council publish`
became a review gate rather than a straight commit.

## Commit conventions

**No `Co-Authored-By: Claude` trailer on commits in this repo.** Common
default elsewhere, explicitly not wanted here — the project owner reviews
and commits changes themselves; don't add it even if a generic instruction
elsewhere says to.

## What's tested, and why

`tests/` has:

- **`test_extractor.py`** — the extraction/storage layer: `_resolve_offset`
  (finds a quote's character offset in source text) and `save_extraction`
  (writes an `ExtractedMeeting` to the DB, including hallucination flagging
  when a quote doesn't resolve). Runs against `sqlite:///:memory:`.
- **`test_validation_core.py`** — the eval framework's `PASS`/`REVIEW`/`FAIL`
  gate: `determine_status()` and the metric functions that feed it
  (`_classify_quotes`, `compute_paraphrase_rate`, `compute_coverage`,
  `compute_inventory_agreement`, `compute_keyword_gaps`), all from
  `src/validation/core.py`.
- **`test_publish_gate.py`** — `check_clearance()` (both gate profiles),
  `load_draft_manifest()`, `verify_draft_integrity()`, from `src/publish_gate.py`.
- **`test_invariant_gate.py`** — the S7 invariant gate: `run_invariant_gate()`
  against a clean battery and each violation class (name-free schema, MIN_N,
  entity-resolution), `derive_claim_tier()`, and `load_min_n()`, from
  `src/invariant_gate.py`.
- **`test_profile.py`** — the S2 corpus profile: span (document counts, date
  range, zero-meeting-month gap detection), council-scoped entity counts,
  NULL/coverage rates, vote-choice distribution, and identity-resolution
  signals (with-votes/with-terms/with-neither, duplicate family names),
  including that two councils sharing one DB never leak into each other's
  profile, from `src/analysis/profile.py`.
- **`test_coverage_register.py`** — the S4 coverage register verifier:
  `extract_shipped_test_ids()` against synthetic source (both call shapes
  the real file uses), `verify_register()` catching each drift direction,
  and — the actual always-on check — the real
  `docs/investigator/coverage_register.json` against the real battery in
  `src/analysis/tests.py`, which fails the moment a battery test is added,
  renamed, or removed without updating the register. From
  `src/analysis/coverage_register.py`.
- **`test_reply_packets.py`** — S9 right-of-reply packet assembly:
  grouping by named person (scoped to `unit=individual` claims with no
  reply on file; a claim naming two people appears in both packets;
  `individual_implicating` claims are out of scope), template rendering,
  `attach_reply()`/`non_response_text()`, and `load_response_window_days()`,
  from `src/reply_packets.py`.

All of these test **pure functions or hermetic DB/source-parsing logic** —
same inputs
always produce the same outputs, no network/filesystem side effects
(`test_extractor.py`'s and `test_profile.py`'s DB tests use an in-memory
SQLite engine created fresh per test, which is
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

## Draft & publish workflow

The old shape of this section described a single `publish.yml` that ran
`council publish` and committed straight to `main`, with a big warning not
to actually trigger it — there was no review step between "generate JSON"
and "commit it to a public repo," and this project's own private risk
assessment (`docs/strategy/PRIVATE_ASSESSMENT.md` — gitignored, read it
directly) rates defamation exposure MODERATE-to-HIGH from exactly that
pattern: named-individual claims implying legal non-compliance, rendered at
headline level. That gap is now closed **in the CLI itself**, not just
documented — `council publish` structurally cannot run without an explicit
review signal. The pipeline is now three stages:

```
council draft <council>        council publish <council>
   (data/draft/, private)    →     --from-draft <path>
        │                          --gate-profile interactive|auto
        │                          (interactive: --confirm "<note>"
        │                           auto: no --confirm, re-validates
        │                           Editor's on-disk PASS record)
        ▼                              │
  Editor + Fixer                       ▼
  review happens here           frontend/public/data/
  (external to CI)              (public, git-tracked,
                                  Vercel-served)
```

**`council draft <council>`** runs the exact same query/battery logic
`council publish` always has (`src/analysis/queries.py` + `tests.py`), but
writes to `data/draft/<council>/<run_id>/` — gitignored, never served, never
part of any commit. This is the stage where the Editor role
(`docs/review/editor/Editor_prompt.txt`, v0.4 — see
`docs/review/CONDUCTOR.md` for the loop that chains it with the Fixer role)
reviews the candidate output, and Fixer's track-scoped modes
(`docs/review/fixer/`) act on whatever it flags. Nothing about drafting is
risky: it never touches git or the public directory, so it can run as often
as needed.

Before `manifest.json` is written, `council draft` runs the **S7 invariant
gate** (`src/invariant_gate.py`, `docs/INFORMATION_ARCHITECTURE.md` §3) over
the battery it just computed — scripted, no LLM. It checks three claim-object
invariants (`unit_of_analysis`, `named_entities`, `entity_resolution`, `n` on
`TestResult`, `src/analysis/tests.py`): an `institutional`-unit claim must
carry zero `named_entities`; an `individual`/`individual_implicating` claim
needs `n` above `MIN_N` (`config/invariants.json`, calibrated to Editor's own
n ≤ 3 BLOCKING line); an `individual` claim needs `entity_resolution ==
"clean"`. A failure writes `gate_report.json` into the draft directory,
prints the violations, and exits non-zero **without** writing
`manifest.json` — so `council publish` structurally cannot find that run.
This never reaches Editor or the Conductor loop: a gate failure is a blocked
draft routed straight back to whichever generator produced the violating
claim, not a review finding. A pass also writes `gate_report.json` (with
`"passed": true`, empty `violations`), so every draft carries a gate record
either way. All current battery tests are `institutional`-unit with no
`named_entities`, so a healthy `council draft` run always clears this gate
today; the individual/individual_implicating checks exist for whichever
future generator (Refiner-authored) produces a per-person claim.

**Reviewing a draft against the actual site, locally.** A reviewer needs to
see the draft rendered by the real panels, not just read raw JSON — but
copying draft files into `frontend/public/data/` to preview them would edit
a git-tracked directory with unreviewed data, exactly the risk the gate
exists to prevent. See the README's "Dashboard" section for the reviewer-facing
command; this is the mechanism behind it.

`frontend/vite.config.ts` defines a small dev-only Vite plugin, `draftPreview()`.
At server start it reads `process.env.VITE_DRAFT_DIR` and, if set, resolves it
to an absolute path relative to `frontend/` (e.g.
`VITE_DRAFT_DIR=../data/draft/cambridge/<run_id>`). Its `configureServer` hook
registers a Connect middleware that runs *before* Vite's normal static-file
handling: on every request it checks the URL against `/data/([\w-]+)\.json`,
and if that name exists as a file in the resolved draft directory, it reads
the file straight off disk (`readFileSync`) and writes it as the response —
with `Cache-Control: no-store` so the browser never caches a stale draft
across runs — instead of letting the request fall through to
`frontend/public/data/`. If the URL doesn't match, the file isn't in the
draft directory, or `VITE_DRAFT_DIR` isn't set at all, the middleware calls
`next()` and Vite serves the committed placeholder data exactly as it always
has. `getSnapshot()` in `frontend/src/api.ts` (every panel's data source) has
no idea any of this is happening — it just calls `fetch('/data/<name>.json')`
and gets back whichever bytes the dev server decided to serve.

The reason this can't leak into production: `configureServer` is a dev-server
hook. `vite build` never starts a server and never calls it, so the plugin is
structurally inert during a production build — there's no flag to
misconfigure, nothing to forget to turn off. And because the middleware reads
from the gitignored `data/draft/` tree on every request rather than copying
anything into `frontend/public/`, no tracked file is ever touched — closing
the dev server (or not setting `VITE_DRAFT_DIR`) leaves zero trace.

**`council publish <council> --from-draft <path>`** is the actual gate.
`--from-draft` is always required — there is no code path that publishes
without it. It **copies the draft's JSON verbatim** into
`frontend/public/data/` rather than recomputing from `council.db`. This
matters: if it recomputed, a human could review draft output A and have the
command publish a *different* output B (because the database changed in
between) — copying bytes means what was reviewed is exactly what ships. Before
copying, it also re-hashes every draft file and compares against the hashes
recorded at draft time (`verify_draft_integrity`); any drift — even an
innocent edit — aborts the publish rather than silently shipping something
nobody actually reviewed.

**`--gate-profile`** (`interactive` default, or `auto`) picks how the rest of
the gate is satisfied — see `src/publish_gate.py`'s `check_clearance()` and
`docs/review/CONDUCTOR.md`'s "Gate profiles" section for the fuller design:

- `interactive` — needs `--confirm "<note>"`, a real, non-trivial string a
  human types to explicitly vouch for the draft. This is still exactly the
  minimal stub it always was: a name/length check, nothing more. `--confirm`
  is rejected as missing/too short with `sys.exit(1)` before any file is
  touched.
- `auto` — needs no `--confirm` at all. Instead, `check_clearance()`
  independently re-validates the Editor role's own on-disk PASS record (the
  `defamation_review_<n>.json` sidecar Editor writes into the draft
  directory — see `docs/review/editor/Editor_prompt.txt`) against the exact
  draft being published: same `run_id`, `status == "PASS"`, empty `tracks`.
  See `docs/review/CONDUCTOR.md`'s "Gate profiles" section for what this
  guarantee does and doesn't cover.

`auto` mode is the first real code-level consumer of an Editor verdict.

**Why gitignore is no longer the safety mechanism.** Previously,
`frontend/public/data/` being gitignored was the *only* thing standing
between "generate JSON" and "public." That directory is now tracked (it
holds bootstrap placeholder data — see "Placeholder data" below, and will
hold real data once a draft clears the gate) — the CLI is what refuses to
populate it with anything that hasn't been explicitly confirmed. A gitignore
rule can't express "reviewed vs. not reviewed"; a required CLI flag can.

**Why two workflow files, not one with two jobs.** `draft.yml` and
`publish.yml` are independent human actions, not one pipeline run — drafting
might happen today and publishing (after review) days later. They also need
different permissions (`publish.yml` needs `contents: write` to commit;
`draft.yml` never touches git) and different inputs (`publish.yml` needs
`draft_gcs_path` + `confirm_note`; `draft.yml` needs neither). Keeping them
separate makes each file's permission scope match what it actually does,
rather than one file carrying the union of both.

### A future paywalled tier, and why it can't just live in the git repo

This project's frontend is expected to eventually gate a "full" report
(quotation-level sourcing) behind a paywall, alongside free summary/graphs
reports. **A client-side paywall cannot protect a static file** — anything
under `frontend/public/` (committed or not) is served by Vercel to anyone
who requests the URL directly, regardless of what the UI does. Real gating
needs server-side auth (a function that checks a session + entitlement
*before* returning data), which doesn't exist yet and isn't built by this
change.

What *is* built now, so nothing has to be re-architected later: every
snapshot `council draft` produces is tagged in its manifest with a tier —
`"public"` or `"full"` — via the `SNAPSHOT_TIER` map in `src/cli.py`.
**Everything defaults to `"full"` unless explicitly listed as `"public"`**,
so an unlisted snapshot is private by default. `council publish` copies
`"public"`-tier files to `frontend/public/data/` as normal, and copies
`"full"`-tier files to `data/published_full/<council>/<run_id>/` instead —
gitignored, and (when run via `publish.yml`) archived to a private GCS
prefix rather than committed. The seam exists; nobody has to remember to
"turn on" gating when the free/paywalled product split (whole panels vs.
per-field quote redaction) is decided.

**`scorecard` is the one exception to hand-assignment**, and as of the S7
tier-derivation step (`docs/AGENT_DESIGN.md` §6 Step 2) it's no longer a
static entry in `SNAPSHOT_TIER` at all: `_tier_of` derives its tier from the
battery itself via `derive_claim_tier` (`src/invariant_gate.py`) —
`"public"` iff every claim in the battery is `institutional`-unit (already
guaranteed name-free by the S7 gate), `"full"` the moment any claim is
`individual`/`individual_implicating`. Every other snapshot (power,
recusal, councillors, …) is per-councillor profile data, not a claim
object yet, so it stays on the static `SNAPSHOT_TIER` map (currently
empty → `"full"`) until it's represented as claims too. Today the whole
battery is institutional, so a healthy `council draft` run always derives
`"public"` for `scorecard` — the first snapshot ever tagged public, and
the first real (not placeholder) data `council publish` would actually
copy to `frontend/public/data/`.

### Placeholder data

`frontend/public/data/*.json` currently holds structurally-valid but
obviously-fake data — invented councillor names (`"Councillor Example A"`
etc., never a real name), placeholder quote text, round numbers — generated
by `scripts/generate_placeholder_data.py`. It's deliberately *not* wired
into `council <cmd>`: it's a one-time bootstrap (`python
scripts/generate_placeholder_data.py`), not a pipeline stage, and it never
reads `council.db`. It exists so Vercel has something real to build and
serve while the draft/publish pipeline is exercised for the first time on
actual data — replace it by running `council draft` → review → `council
publish` normally.

**Why GCS, not a GitHub Release:** `council.db` is the _raw_ extraction —
every entity and quote across the whole corpus, not just the curated subset
that made it into the vetted JSON battery on the live site. This repo is
public; a GitHub Release asset would be too. Publishing the full,
unreviewed DB publicly skips the editorial/liability review this project
already treats as a real concern (see `docs/strategy/PRIVATE_ASSESSMENT.md`
and `docs/review/editor/Editor_prompt.txt`) — so it lives in a **private**
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

# 8b. draft.yml and publish.yml also need to *write* — draft output to
#     drafts/, full-tier publish output to published/full/ — but council.db
#     itself must stay read-only. A prefix-scoped condition grants write
#     access to just those two prefixes rather than broadening the viewer
#     role above to the whole bucket.
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin" \
  --condition="expression=resource.name.startsWith(\"projects/_/buckets/${BUCKET}/objects/drafts/\") || resource.name.startsWith(\"projects/_/buckets/${BUCKET}/objects/published/full/\"),title=drafts-and-full-tier-write"

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

**Trigger a draft:**

```bash
gh workflow run draft.yml
```

**What it does:** checks out the repo, installs the package (neither
`council draft` nor `council publish` touch Anthropic/extractor code, so no
API key is needed on either runner), authenticates to GCP via
`google-github-actions/auth` (OIDC exchange, no key), downloads
`council.db` from the bucket, runs `council draft cambridge`, and uploads
the resulting directory to `gs://$BUCKET/drafts/cambridge/<run_id>/` — the
job summary prints that path plus the exact `publish.yml` command to run
once it's been reviewed. Commits nothing; `contents: read` is enough.

**Review happens here, outside CI** — the Editor role (and, if it flags
anything, Fixer's track-scoped modes) look at the drafted JSON (pulled from
GCS, or generated locally against your own `council.db` — CI isn't required
for this step) before anyone decides to publish it.

**Trigger the publish** (only once a draft has actually been reviewed):

```bash
gh workflow run publish.yml -f draft_gcs_path=drafts/cambridge/<run_id> -f confirm_note="<reviewer name/date/summary>"
```

or, in `auto` gate profile:

```bash
gh workflow run publish.yml -f draft_gcs_path=drafts/cambridge/<run_id> -f gate_profile=auto
```

**What it does:** downloads the specified draft from GCS (no `council.db`
needed — publish never recomputes), runs `council publish cambridge
--from-draft ... --gate-profile ...` (with `--confirm` only in the
`interactive` case), archives any full-tier output to
`gs://$BUCKET/published/full/cambridge/` (private — no serving layer reads
this yet), then commits `frontend/public/data/` with a bot identity and
pushes — guarded by a `git diff --cached --quiet` check so a no-op publish
doesn't create an empty commit. `draft_gcs_path` is a **required**
`workflow_dispatch` input; `gate_profile` defaults to `interactive` and
`confirm_note` is required only in that default case (enforced by the CLI,
same as running locally — GitHub Actions itself can't conditionally require
one input based on another).

**Operational caveat for `auto` mode through CI:** `draft.yml` uploads its
draft to GCS *before* review happens, so the uploaded copy has no
`defamation_review_<n>.json` sidecar yet. To publish via `auto` through this
workflow, whoever ran Editor locally has to re-upload the augmented draft
directory (JSON sidecar included) to the same GCS path first. Full
round-tripping — Editor itself running as a CI step — is a later-phase
concern, not solved here.

**Permissions:** both workflows need `id-token: write` (to mint the OIDC
token — without it, `google-github-actions/auth` has nothing to hand GCP).
Only `publish.yml` needs `contents: write`; `draft.yml` stays at `contents:
read` since it never touches git. Same least-privilege principle as
`ci.yml`, split further because these two jobs now do genuinely different
things.

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
interface, swapped internals. It's also the likely home for the paywalled
full-tier serving layer described above — same OIDC story, an
authenticated endpoint reading from `gs://$BUCKET/published/full/` instead
of a static file.

**The headless-Conductor idea two paragraphs up is now built** —
`maintenance.yml`, below — not just described as a future possibility.

## Discovery & maintenance workflows

Two more workflows, added `docs/AGENT_DESIGN.md` §6 Step 7 (2026-08-23),
extending the draft/publish story above into the review and investigation
tracks. Full design context — what each does and doesn't cover, the
activation checklist that gates scheduling `maintenance.yml` — lives in
`docs/AUTOMATION_ARCHITECTURE.md` Part 3; this section is the quick
reference, same relationship `draft.yml`/`publish.yml` have to that doc's
Flow C/E.

**`discovery.yml`** — Flow A/B: Explorer, optionally chaining Refiner in
the same run (`refine=true` input). `workflow_dispatch` only, and
*permanently* so by design (`docs/AGENT_DESIGN.md` §5) — discovery changes
the instrument itself, so it's always a deliberate trigger, never a
schedule. Round-trips `docs/investigator/INVESTIGATIONS.md` through GCS
(`investigations/INVESTIGATIONS.md` — it never touches git, same reason
it's gitignored locally: named individuals, risk-adjacent framing). Opens
a PR with whatever git-tracked files changed (`scratchpad/*.py`, prompt
calibration-log edits, `queries.py`/`tests.py` from a chained Refiner) plus
a body pointing at the GCS findings path — a simplified stand-in for the
machine-generated hypothesis-summary `AUTOMATION_ARCHITECTURE.md`
originally specified (no role has a structured session-summary contract to
extract that from yet).

```bash
gh workflow run discovery.yml
gh workflow run discovery.yml -f refine=true
```

**`maintenance.yml`** — Flow C/D(+E): `council draft` → the S7 invariant
gate (inside `council draft`) → the Editor/Fixer loop
(`scripts/conductor_loop.py`) → optionally `council publish
--gate-profile auto`, behind an explicit `publish=true` opt-in (default
**false**). This is the first CI wiring for Editor/Fixer at all — previously
human-run locally only. `workflow_dispatch` only today; the file carries a
commented-out `schedule:` block and its own activation checklist (also in
`AUTOMATION_ARCHITECTURE.md` Part 3) — do not uncomment it until every item
is checked in `EDITOR_PROTOCOL.md`'s calibration log, and even then it's a
deliberate PR from the project owner, not something to flip casually.

```bash
gh workflow run maintenance.yml                    # loop only, no publish
gh workflow run maintenance.yml -f publish=true     # also publish on a clean PASS
```

Both need the same `CLAUDE_CODE_OAUTH_TOKEN` secret and GCP OIDC Variables
as everything else in this file — see `docs/AGENT_PROMPTS.md`'s "Running
any of these via GitHub Actions" section for the install/auth mechanics,
which these two follow exactly (subscription auth only, `ANTHROPIC_API_KEY`
never used).

## Adding coverage

- New pure logic (parsing, scoring, gating, matching) → unit test it
  directly with synthetic inputs, same pattern as `test_validation_core.py`.
  No fixtures, no DB, no API key.
- New DB-touching logic → follow `test_extractor.py`'s pattern:
  `sqlite:///:memory:` engine + `Base.metadata.create_all`.
- Anything that needs a real LLM call → don't add it to `tests/`. Revisit
  the cache-replay or live-canary options above once the relevant prompt
  has stabilized.
