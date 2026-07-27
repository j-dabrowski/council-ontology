# Testing & CI

Cross-cutting infrastructure doc — not owned by one track (see `docs/MAP.md`),
since it covers the Python pipeline, the frontend, and the CI workflow that
gates both. Added 2026-07 alongside `.github/workflows/ci.yml`.

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

## Adding coverage

- New pure logic (parsing, scoring, gating, matching) → unit test it
  directly with synthetic inputs, same pattern as `test_validation_core.py`.
  No fixtures, no DB, no API key.
- New DB-touching logic → follow `test_extractor.py`'s pattern:
  `sqlite:///:memory:` engine + `Base.metadata.create_all`.
- Anything that needs a real LLM call → don't add it to `tests/`. Revisit
  the cache-replay or live-canary options above once the relevant prompt
  has stabilized.
