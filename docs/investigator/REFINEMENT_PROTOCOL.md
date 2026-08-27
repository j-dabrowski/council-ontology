# Refinement Protocol

The benchmark-gated plan for improving `Refiner_prompt.txt` and the test
harness (`src/analysis/tests.py`, `src/analysis/queries.py`). Governs how
a validated finding from `INVESTIGATIONS.md` is codified into a permanent,
council-agnostic, reproducible battery test.

Related: `Refiner_prompt.txt` (the prompt this protocol improves),
`EXPLORATION_PROTOCOL.md` (the upstream protocol that produces the findings
being codified), `src/analysis/tests.py` (the output artefact),
`docs/investigator/AUDIT_2026-08-14.md` (first real calibration data — see
below).

---

### What this protocol governs

The Refinement loop has a different character from the Exploration loop:
- **Input:** a confirmed `[✓]` Finding in `INVESTIGATIONS.md`, with a
  hand-verified number (n, base rate, era) and a scratchpad query script.
- **Output:** a permanent entry in `run_test_battery()` that any future
  AI session can call without writing ad-hoc SQL — council-agnostic,
  parameterised, and verified against the original number.
- **Improvement target:** the *code* (`queries.py`, `tests.py`, the CLI
  pipeline) and the *Refiner prompt* — not the investigative methodology.

The Refiner prompt is improved when a refinement session produces a test
that fails verification (number doesn't match, or the test breaks on a
second council's DB). The improvement is surgical: fix the specific query
or prompt instruction that caused the failure.

---

### Benchmark (defined 2026-08-14; dimension 7 added 2026-08-23)

Seven dimensions, mirroring how `EXPLORATION_PROTOCOL.md` scores Explorer:
numbered, each with a declared threshold, hard gates that cannot be
averaged away. Dimension 2 (caveat/join safety) didn't exist in the original
candidate table — it was added directly in response to the first real
calibration data (below), the same way Editor's per-claim BLOCKING gate was
added to `docs/review/editor/Editor_prompt.txt` after its own first run.
Dimension 7 (declaration completeness) was added the same way, in response
to `docs/AGENT_DESIGN.md` §6 Step 5 rather than a calibration incident — S7
(the invariant gate, `src/invariant_gate.py`, built Step 1) can only gate a
claim's fields if a Refiner session actually declared them on purpose.

| # | Dimension | Threshold | How to measure |
|---|-----------|-----------|-----------------|
| 1 | **Verification accuracy** | 100% — a single mismatch fails the test | Independently hand-derive the number via fresh SQL against `council.db` (not by reading and trusting the existing function), compare to the shipped value |
| 2 | **Caveat/join safety** | 100%, zero violations — hard gate, same severity as #1 | Check the query against every relevant `Investigator_prompt.txt` §0.4 caveat: any join touching `item_reference`/`item_number` anchors on `votes.declared_interest=1` (or an equivalently unique key) first; UPPERCASE enum comparisons used correctly; `document_type='minutes'` filtering applied where required; placeholder-councillor exclusion; NULL-vs-redacted conflation; and — the general form both known incidents share — no aggregation sums/joins rows without confirming the same real-world fact can't appear as more than one row (duplicate extraction, multiple document types) |
| 3 | **Query encapsulation** | 0 violations | No ad-hoc SQL string in `tests.py`; all logic in a named `queries.py` function; raw SQL inside `queries.py` permitted only where the join graph is provably fan-out-safe (single anchor table, or an independent `UNION ALL`), with a comment stating why |
| 4 | **Council-agnosticism** | 100% for newly-refined tests; existing tests graded, failures logged as backlog, not blocking | Function signature takes only `council_id` (+ generic `from_year`/`to_year`); no council-specific literal (a specific year, name, or corpus-tuned threshold) baked into the logic without being a parameter with a documented default |
| 5 | **Chart & drill-down completeness** | 100% for flagships; chart populated for all battery tests | `TestResult.chart` renders in `BatteryTestPanel`; flagships carry drill-down arrays with ≥1 source quote |
| 6 | **Independent reproducibility** | Pass/fail per test | Can a fresh reader explain what the test measures and why its join is safe from the function's own docstring/comments alone, without consulting `INVESTIGATIONS.md`'s narrative? |
| 7 | **Declaration completeness** | 100% for newly-refined generators — hard gate; pre-2026-08-23 generators graded as backlog for `unit`/`MIN_N`/`strength`/`principle` only, not blocking (same asymmetry as dimension 4) — `scope` (added 2026-08-26) and `stat`/`digest_floor` (added 2026-08-27) carry no such backlog: all 29 pre-existing generators were tagged with `scope` directly in code alongside the prompt update that introduced it, and all 14 `_MEETING_BATTERY` members already carry `stat`/`digest_floor` from the digest Phase 1 build | A one-line declaration comment sits directly above the `TestResult(...)` call stating `unit`/`MIN_N`/`strength`/`principle`/`scope` (plus the superlative check if `strength=superlative`), and its stated values match what the `TestResult` call actually sets; the matching `docs/investigator/coverage_register.json` row lists the new `test_id`. **If `scope` includes `single_meeting`**: the meeting-scoped variant function must actually exist and be a member of `_MEETING_BATTERY` (`src/analysis/tests.py`) — a `scope` tag with no matching function is a dimension-7 failure on its own, regardless of every other field being correct — and its declaration also states `stat` (`{value, denominator, unit}`) and `digest_floor` (1.0 for a discrete always-reportable event, 0.0 for novelty-only), matching what the meeting-scoped `TestResult` call actually sets. `stat`/`digest_floor` are "n/a" for a `whole_corpus`-only generator. |

**One rule that should never become adjustable without an explicit, logged
decision** (same principle as `EDITOR_PROTOCOL.md`'s BLOCKING-flag rule):
dimensions 1, 2, and (for newly-refined generators) 7 are hard gates. A test
that fails any of them is not refined, regardless of how well it scores on
the rest — averaging away a wrong, unsafe, or undeclared number against
several clean tests is exactly the failure mode a per-test gate exists to
prevent.

The benchmark is now defined — iterative improvement of `Refiner_prompt.txt`
(still a stub) may begin.

---

### Improvement loop

1. Run a refinement session under `Refiner_prompt.txt` for one confirmed finding
2. Score the output against the benchmark dimensions above
3. If all pass → the test is fully refined; mark it in `INVESTIGATIONS.md`
4. If any fail → identify the failing dimension, update `Refiner_prompt.txt`
   to address it, increment the version, repeat from step 1

---

### Calibration data

**2026-08-14 — first real data, retroactive (not a `Refiner_prompt.txt` session — the prompt is still a stub).**
Before this date, no test in `src/analysis/tests.py` had ever gone through
anything resembling the Refiner gate: every existing battery test and
flagship query was written directly by an Explorer session (or, for the
earliest panels, by hand before the Explorer/Refiner split existed). Two
sessions produced the first real calibration data by applying dimensions 1
and 2 retroactively against the full existing battery:

- An Editor pass (a separate, unrelated review pipeline — `docs/review/`)
  cross-checking two snapshots against each other caught `recusal_compliance_trend()`
  failing dimension 2: an `item_reference` join fanning out without a
  `votes.declared_interest=1` anchor, fabricating a named councillor's
  compliance record. Fixed same-day (`_linked_declared_votes`, shared by
  `recusal_compliance_trend` and `_populate_declaration_details`).
- A full retroactive audit (`docs/investigator/AUDIT_2026-08-14.md`) then
  ran dimension 1 against **every** shipped flagship (9) and battery test
  (24) — not a sample — independently re-deriving each by fresh SQL against
  `council.db`. Result: **32/33 confirmed exactly**; one further dimension-2
  violation found in `tender_concentration()` (missing `document_type='minutes'`
  filter + no dedup by `reference_number`, inflating a named contractor's
  reported spend 3×). Also fixed same-day.
- Dimension 4 (council-agnosticism) was spot-checked, not formally scored:
  no hardcoded `council_id` or councillor name found in `queries.py`/`tests.py`
  (good), but the 2018–2021 Authorised-Inquiry era window is hardcoded as a
  literal in **two independent places** (`_recusal_era`/`_RECUSAL_ERAS` and
  `public_question_responsiveness`'s `inquiry_window`), not parameterised —
  a confirmed, unfixed dimension-4 failure. Logged as backlog, per the
  benchmark's own threshold note (existing tests don't block on dimension 4
  yet) — but it's the concrete reason that threshold exists, not a
  hypothetical.

**Reading this calibration point:** dimension 1 (accuracy) is strong — the
existing battery is mostly sound despite never having passed through a
formal gate. Dimensions 2 and 4 are where the real risk concentrates: both
already-found violations are *join/aggregation safety* (dimension 2), and
the one located dimension-4 failure is a real second-council blocker, not a
style nit. A first live `Refiner_prompt.txt` session should prioritise
writing the operating layer's dimension-2 and dimension-4 checks concretely
enough that a session can run them without re-deriving the method from
scratch each time — both were done ad hoc this session, not from a
documented procedure.

---

**2026-08-22 — first live entry-point-A session (Refiner_prompt.txt v1.1,
Step 0 self-selection).** Every previous calibration point was retroactive
(auditing already-shipped code) or ran entry point A on a human-named
target. This session ran unnamed: Step 0 scanned `INVESTIGATIONS.md`,
correctly excluded every other `[◐] Banked` entry by its own disqualifying
text ("folded into...", "not standalone", "methodology needs tightening",
already shipped as a panel), and landed on [48] as the sole qualifying
candidate. Result: **dimension 1 FAIL, verdict NOT REFINED** — the
finding's actual substantive claim (appointee win rate statistically
indistinguishable from non-appointees: 73.4% vs 73.1%, spread and two named
examples all reproduced to the vote) held exactly, but the "33 distinct
councillors" headline count hand-derived to 32 (31 once a newly-found
split councillor identity, Colin Walker/Walker Colin, is merged — now
logged in `Investigator_prompt.txt` §0.4). See `[48 REFINEMENT ATTEMPT]`
in `INVESTIGATIONS.md` for the full write-up. Two things this confirms
about the operating layer as written: (a) Step 0's disqualification
language matching works on real, messy Banked-entry prose, not just the
clean cases it was designed against; (b) the dimension-1 hard gate does its
job on a genuinely new (not retroactive) case — a plausible, internally-
consistent-looking headline number was caught before any code shipped,
exactly the failure mode this protocol exists to prevent. A side-finding
(the incidentally-discovered gap in `voting_power()`'s caveat safety,
§0.4's `document_type='minutes'` filter) was logged as backlog rather than
fixed in-session, since it belongs to a different, already-shipped
flagship ([18]) than the one this session was scoped to.

### Open questions

- **Batch vs. single-finding sessions.** Should a refinement session codify
  one finding or several? Batching is efficient but risks cross-contamination
  (a query fix for one test may break another). Resolve by experience.
- **Who owns the `queries.py` function?** The Refiner writes it; the Explorer
  may call it in future sessions. The function signature should be stable
  (council-agnostic parameters) before the Explorer relies on it.
- **Second-council validation.** The full council-agnosticism check (running
  unchanged against a second council's DB) still requires a second council
  DB that doesn't exist yet — that part of dimension 4 stays `data_ok=False`
  until one is loaded. But the *static* half of dimension 4 (grep for
  hardcoded council-specific literals) needs no second DB and already found
  a real violation (the Inquiry-window hardcoding above) — don't wait on a
  second council to start applying that half.
- **Retroactive vs. session-based scoring.** This calibration point was
  produced by two ad hoc audit/fix sessions, not a `Refiner_prompt.txt` run —
  the prompt is still a stub. Once it's written, the first real session
  should re-score at least one already-"confirmed" test end-to-end to check
  the documented procedure reproduces this session's ad hoc result, before
  trusting the prompt for new codification work.

---

## Changelog

- v0.6 (2026-08-27) — Dimension 7 closes the gap `scope` left open at v0.5:
  a `single_meeting` scope tag proved nothing on its own — nothing checked
  whether the matching `_meeting` function existed. Now requires it exist
  and be a member of `_MEETING_BATTERY` (`src/analysis/tests.py`), and
  requires the meeting-scoped `TestResult` call to declare `stat`
  (`{value, denominator, unit}`) and `digest_floor` (1.0 for a discrete
  always-reportable event, 0.0 for novelty-only descriptive claims) — both
  "n/a" for a `whole_corpus`-only generator. No backlog exception, same as
  `scope` itself: all 14 `_MEETING_BATTERY` members already carry both
  fields from the digest Phase 1 build. `Refiner_prompt.txt` bumped to
  v1.4 (new Procedure step 6, declaration-block template, score-block
  `meeting_variant` line, Step 8's forward-compatible register-granularity
  sentence — the granularity axis schema itself is Explorer v3.1's job,
  not built here).
- v0.5 (2026-08-26) — Dimension 7 gains a fifth declared field, `scope`
  (`whole_corpus`/`single_meeting` — declares which granularity a
  finding-type is *meaningful* at, ahead of a possible future per-meeting
  digest section; no generator computes at single-meeting granularity yet).
  `Refiner_prompt.txt` bumped to v1.3 (Step 5/6, score-block line). Unlike
  the original four declaration fields, `scope` has no pre-existing-generator
  backlog exception — all 29 shipped tests were tagged directly in
  `src/analysis/tests.py` alongside this change, so the dimension-7 hard
  gate applies to `scope` on every generator, old and new, immediately.
- v0.4 (2026-08-23) — Added dimension 7 (declaration completeness, hard
  gate for newly-refined generators) per `docs/AGENT_DESIGN.md` §6 Step 5.
  `Refiner_prompt.txt` v1.2 emits the declaration block and updates the
  coverage register as new Procedure steps 6–7. No calibration data yet for
  this dimension — it hasn't run on a real session.
- v0.3 (2026-08-22) — recorded the first live entry-point-A calibration
  point (Refiner_prompt.txt v1.1, Step 0 self-selected target [48]):
  dimension-1 hard gate caught a headline-count mismatch (33 claimed vs
  32/31 hand-derived) before any code shipped, while the finding's
  substantive win-rate claim reproduced exactly. No benchmark changes —
  the six dimensions and two hard gates worked as designed on a real,
  non-retroactive case for the first time.
- v0.2 (2026-08-14) — defined the benchmark (6 dimensions, 2 hard gates),
  ending the "do not begin improvement until defined" hold from v0.1.
  Recorded the first real calibration data (`AUDIT_2026-08-14.md`): 32/33
  shipped tests confirmed accurate on retroactive dimension-1/2 checks, one
  dimension-2 violation found and fixed (`tender_concentration()`), one
  dimension-4 violation found and logged as backlog (hardcoded Inquiry-window
  literal in two functions). Both fixes and the audit predate a real
  `Refiner_prompt.txt` session — the prompt itself is still a stub; this
  data was produced by direct, ad hoc verification work, which is itself the
  reason dimension 2 exists as a named benchmark dimension rather than
  staying folded into "verification accuracy."
- v0.1 — first draft, alongside the three-prompt architecture split. Benchmark
  left `TBD`; no calibration data.
