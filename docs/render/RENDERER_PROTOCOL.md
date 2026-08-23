# Renderer Protocol

Governs `Renderer_prompt.txt` and its two modes: what "done" means per
mode, the fidelity benchmark both are scored against, and how this role is
calibrated. The sixth instance of the established protocol pattern this
project uses for every LLM role (`EXPLORATION_PROTOCOL.md`,
`REFINEMENT_PROTOCOL.md`, `EDITOR_PROTOCOL.md`, `FIXER_PROTOCOL.md`,
`RESEARCH_PROTOCOL.md`) — deliberately nothing novel in shape, per
`docs/AGENT_DESIGN.md` §2.

Related: `Renderer_prompt.txt` (shared layer), `plain_language_mode.txt` /
`synthesis_mode.txt` (the two modes), `docs/INFORMATION_ARCHITECTURE.md`
§5 (the audience/verification-standard table this role serves),
`src/reply_packets.py` (the reply-completeness gate synthesis mode enforces).

---

## Status: v1.0, untested

Neither mode has run yet. There is no calibration data — treat every
threshold below as a starting point to be revised after the first real
run, not a settled benchmark. Unlike every risk-editorial role in this
pipeline (Editor, Fixer), Renderer's failure mode is never a defamation
exposure — its input is already cleared before it runs. Its failure mode
is **drift**: prose that reads well but no longer says exactly what its
source claim said. That's the thing a human checks first on the first real
run, not tone or readability.

## Benchmark

Five dimensions shared by both modes (fidelity), plus two synthesis-mode-only
dimensions (the reply gate and inherited framing balance). All thresholds
are today's starting judgment, adjustable the same way every other
protocol doc's are — by editing the threshold, with reasoning logged in
the changelog, never by asking Renderer to grade itself more leniently.

| # | Dimension | Mode | Threshold | How to measure |
|---|-----------|------|-----------|-----------------|
| 1 | **No unsourced claims** | both | 100% | Every sentence traces to a named `test_id` (plain-language) or `test_id`(s) (synthesis) present in the input |
| 2 | **No dropped caveats** | both | 100% | Every caveat in a rendered claim's `verdict`/`base_rate` that changes its meaning (small-n, DIRECTIONAL-ONLY, era restriction, "may include...") survives in the rendered sentence, not pushed to an unread footnote |
| 3 | **Denominator/uncertainty preservation** | both | 100% | Every stated rate keeps what it's a rate *of*; every uncertainty qualifier survives |
| 4 | **Strength-ladder fidelity** | both | 100% | Rendered wording strength matches the claim's declared `strength` (`Investigator_prompt.txt` §4.6) — not stronger, not weaker |
| 5 | **NEUTRAL register** | both | 100% | No claim reads more or less severe than its own `valence`/`grade` supports |
| 6 | **Reply-completeness gate** | synthesis only | 0 violations — hard gate | Zero rendered `individual`-unit claims with `reply: None`; `claims_skipped` in the stage-contract block accounts for every one excluded |
| 7 | **Framing balance** | synthesis only | 100% | Every cross-cutting insight carrying criticism has both the hostile-reader and promoter sentence, in NEUTRAL register (inherited from `Explorer_prompt.txt` Principle 1, checked the same way Editor checks it on individual claims) |

**Dimension 6 is a hard gate, never adjustable without an explicit, logged
decision** — same principle as every other hard gate in this project
(Editor's BLOCKING rule, Refiner's dimensions 1/2/7). A synthesis draft
that renders even one incomplete-reply `individual` claim is not done,
regardless of how well everything else scores.

## Improvement loop

1. Run a mode for real against one draft
2. Score against the dimensions above (5 for plain-language, all 7 for synthesis)
3. If all pass → the mode is calibrated for that version; keep running it
4. If any fail → identify the failing dimension, update the mode file (or
   the shared layer, if the gap is common to both modes), increment the
   version, repeat from step 1

## What "done" looks like for this protocol

Same discipline as every other protocol doc: run each mode for real at
least once, then check whether a human independently agrees the rendered
prose says exactly what the source claims said — no more, no less.
Specific things to watch for on the first runs:
- Did fidelity hold, or did good prose quietly drift from its source? This
  is the priority failure mode to catch, more than tone.
- Did synthesis mode ever render an incomplete-reply claim? That's an
  immediate priority fix regardless of how rare — dimension 6 exists
  precisely because this is the one failure mode with real legal exposure.
- Did plain-language mode ever introduce a claim not in its (person-free)
  input? Shouldn't be possible given the tier gate upstream, but confirm
  it on the first run rather than assuming.

## Changelog

- v1.0 (2026-08-23) — first draft, alongside `Renderer_prompt.txt` and
  both mode files (`docs/AGENT_DESIGN.md` §6 Step 6). No calibration data.
