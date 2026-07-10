# Refinement Protocol

The benchmark-gated plan for improving `Refiner_prompt.txt` and the test
harness (`src/analysis/tests.py`, `src/analysis/queries.py`). Governs how
a validated finding from `INVESTIGATIONS.md` is codified into a permanent,
council-agnostic, reproducible battery test.

Related: `Refiner_prompt.txt` (the prompt this protocol improves),
`EXPLORATION_PROTOCOL.md` (the upstream protocol that produces the findings
being codified), `src/analysis/tests.py` (the output artefact).

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

### Benchmark (TBD)

The refinement benchmark is not yet defined. It should be set by running
the first end-to-end refinement session (taking one confirmed finding and
codifying it under `Refiner_prompt.txt`) and asking: what would a fully
refined test look like, and what gaps did the session leave?

**Candidate dimensions** (to be confirmed after the first refinement run):

| Dimension | Candidate threshold | How to measure |
|-----------|---------------------|----------------|
| Verification accuracy | Result matches hand-verified number within rounding | Compare `run_test_battery()` output to INVESTIGATIONS.md stated figure |
| Council-agnosticism | Test runs on a second council's DB with `council_id` change only | Point at a second council DB; no code changes required |
| Query encapsulation | Test calls a named function in `queries.py`; no ad-hoc SQL in `tests.py` | Grep for raw SQL strings in `tests.py` |
| Chart completeness | `TestResult.chart` payload populated and renders in BatteryTestPanel | `council publish` + playwright verify |
| Drill-down export | Flagship tests have inlined source quotes in snapshot JSON | Check `frontend/public/data/*.json` for populated drill-down arrays |

**Do not begin iterative improvement of `Refiner_prompt.txt` until the
benchmark is defined here.**

---

### Improvement loop (once benchmark is defined)

1. Run a refinement session under `Refiner_prompt.txt` for one confirmed finding
2. Score the output against the benchmark dimensions above
3. If all pass → the test is fully refined; mark it in `INVESTIGATIONS.md`
4. If any fail → identify the failing dimension, update `Refiner_prompt.txt`
   to address it, increment the version, repeat from step 1

---

### Open questions

- **Batch vs. single-finding sessions.** Should a refinement session codify
  one finding or several? Batching is efficient but risks cross-contamination
  (a query fix for one test may break another). Resolve by experience.
- **Who owns the `queries.py` function?** The Refiner writes it; the Explorer
  may call it in future sessions. The function signature should be stable
  (council-agnostic parameters) before the Explorer relies on it.
- **Second-council validation.** The council-agnosticism check requires a
  second council DB. Until one is loaded, this dimension is `data_ok=False`
  and should be noted but not block the benchmark.
