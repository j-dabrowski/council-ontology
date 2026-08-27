# Renderer Protocol

Governs `Renderer_prompt.txt` and its three modes: what "done" means per
mode, the fidelity benchmark each is scored against, and how this role is
calibrated. The sixth instance of the established protocol pattern this
project uses for every LLM role (`EXPLORATION_PROTOCOL.md`,
`REFINEMENT_PROTOCOL.md`, `EDITOR_PROTOCOL.md`, `FIXER_PROTOCOL.md`,
`RESEARCH_PROTOCOL.md`) — deliberately nothing novel in shape, per
`docs/AGENT_DESIGN.md` §2.

Related: `Renderer_prompt.txt` (shared layer), `plain_language_mode.txt` /
`synthesis_mode.txt` / `digest_mode.txt` (the three modes),
`docs/INFORMATION_ARCHITECTURE.md` §5 (the audience/verification-standard
table this role serves), `src/reply_packets.py` (the reply-completeness
gate synthesis mode enforces), `src/analysis/digest.py` (the scripted
salience/tier pipeline digest mode's input is built from).

---

## Status: v1.1, untested

No mode has run yet. There is no calibration data — treat every
threshold below as a starting point to be revised after the first real
run, not a settled benchmark. Unlike every risk-editorial role in this
pipeline (Editor, Fixer), Renderer's failure mode is never a defamation
exposure — its input is already cleared before it runs (digest mode is
the partial exception — see dimension 11). Its failure mode is
**drift**: prose that reads well but no longer says exactly what its
source claim said. That's the thing a human checks first on the first real
run, not tone or readability.

## Benchmark

Five dimensions shared by all three modes (fidelity), plus two
synthesis-mode-only dimensions (the reply gate and inherited framing
balance) and four digest-mode-only dimensions (selection discipline over a
ranked pool, rather than the render-everything default the other two
modes use). All thresholds are today's starting judgment, adjustable the
same way every other protocol doc's are — by editing the threshold, with
reasoning logged in the changelog, never by asking Renderer to grade
itself more leniently.

| # | Dimension | Mode | Threshold | How to measure |
|---|-----------|------|-----------|-----------------|
| 1 | **No unsourced claims** | all | 100% | Every sentence traces to a named `test_id` (plain-language), `test_id`(s) (synthesis), or `claim_id`/`item_id` (digest) present in the input |
| 2 | **No dropped caveats** | all | 100% | Every caveat in a rendered claim's `verdict`/`base_rate` that changes its meaning (small-n, DIRECTIONAL-ONLY, era restriction, "may include...") survives in the rendered sentence, not pushed to an unread footnote |
| 3 | **Denominator/uncertainty preservation** | all | 100% | Every stated rate keeps what it's a rate *of*; every uncertainty qualifier survives |
| 4 | **Strength-ladder fidelity** | all | 100% | Rendered wording strength matches the claim's declared `strength` (`Investigator_prompt.txt` §4.6) — not stronger, not weaker |
| 5 | **NEUTRAL register** | all | 100% | No claim reads more or less severe than its own `valence`/`grade` supports |
| 6 | **Reply-completeness gate** | synthesis only | 0 violations — hard gate | Zero rendered `individual`-unit claims with `reply: None`; `claims_skipped` in the stage-contract block accounts for every one excluded |
| 7 | **Framing balance** | synthesis only | 100% | Every cross-cutting insight carrying criticism has both the hostile-reader and promoter sentence, in NEUTRAL register (inherited from `Explorer_prompt.txt` Principle 1, checked the same way Editor checks it on individual claims) |
| 8 | **Selection traceability** | digest only | 100%, **hard gate** | Every highlight and inventory detail cites a real `claim_id` / `item_id` from the input pool — no fact appears that doesn't trace to one |
| 9 | **Routine suppression** | digest only | 100% | No candidate with `salience` below the period digest's own `min_salience` is rendered as a highlight |
| 10 | **Body-appropriate baselines** | digest only | 100% | No sentence compares one candidate's figure against a candidate from a different `body_class` |
| 11 | **No individual-unit claim in the public band** | digest only | 0 violations, **hard gate** | Nothing rendered comes from a candidate's `deep` field, or from any candidate whose `tier` isn't `"public"` |

**Dimensions 6, 8, and 11 are hard gates, never adjustable without an
explicit, logged decision** — same principle as every other hard gate in
this project (Editor's BLOCKING rule, Refiner's dimensions 1/2/7). A
synthesis draft that renders even one incomplete-reply `individual` claim,
or a digest draft that renders even one uncited fact or one `deep`/
non-public candidate, is not done, regardless of how well everything else
scores. Dimension 11 is digest mode's version of dimension 6 — both exist
because rendering a named individual to residents with no reply/reduction
safeguard is the one failure mode with real legal exposure; digest mode
gets there structurally (its input is pre-filtered to `tier=="public"`)
rather than via a per-claim reply check, but the check still has to run
against the *output*, not just trust the input was built correctly.

## Digest-mode benchmark corpus

Six real meetings, chosen to exercise every digest-specific dimension —
not a random sample. Verified live against the Cambridge corpus,
2026-08-27:

| Meeting | Date | Why it's in the set |
|---|---|---|
| 271 | 2026-03-24 | Dissent spike + a genuine unexplained absence (`governance.attendance`, `UNIT_INDIVIDUAL` in the deep view) — the case for dimension 11: the name must never reach the rendered digest, only its institutional projection's count. |
| 245 | 2026-04-28 | 6 tenders / $3.35M, a deputation, four councillors' conflict declarations, **and** the C2a case (an `institutional`-declared claim whose own text still names someone) that `run_invariant_gate`'s text scan exists to catch — confirms dimension 11 holds even when the upstream tier is technically already `"public"`-eligible before the text-scan demotes it. |
| 258 | 2026-05-12 | The committee case (Policy and Legislation Committee, 4 members): dimension 10 — nothing here may be compared against a full-council baseline. Also exercises the inventory (17 parking-review submissions filed as `other_items`, invisible to `engagement.participation`'s own query) and confirms the "Nil items" false-positive fix holds through to rendered prose. |
| 272 | 2026-02-24 | An ordinary full-council meeting with a mix of salient and routine claims — the standard case for dimensions 8/9 (citation discipline, routine suppression) without any of the edge cases above. |
| 275 | 2025-12-16 | A second ordinary meeting, far enough from 271/245/272 in time that a `week`/`fortnight` digest covering it never overlaps the others — exercises `compose_period_digest`'s window logic and multi-meeting attribution (`digest_mode.txt`'s "When a period covers multiple meetings"). |
| 184 | 2025-02-03 | Public Art Committee — genuinely quiet: every claim's `digest_floor` is 0.0, none names anyone. The `min_salience` floor should suppress everything here; if a digest built around this meeting alone produces a highlight, dimension 9 has failed. |

## Improvement loop

1. Run a mode for real against one draft
2. Score against the dimensions above (5 for plain-language, all 7 for
   synthesis, 5 + 4 = 9 for digest)
3. If all pass → the mode is calibrated for that version; keep running it
4. If any fail → identify the failing dimension, update the mode file (or
   the shared layer, if the gap is common to more than one mode), increment
   the version, repeat from step 1

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
- Did digest mode ever render a `deep` field, a non-`"public"`-tier
  candidate, or an uncited fact? Run it against meeting 271 and 245 first
  (above) — those two are specifically chosen to make this failure mode
  easy to trigger if the discipline isn't holding.
- Did digest mode's quiet-period fallback ever fabricate content instead
  of just naming the most recent meeting? Worth a dedicated check since
  the benchmark corpus above doesn't include an empty-window case (every
  meeting in it is real and content-bearing) — construct one manually the
  first time this runs.

## Changelog

- v1.1 (2026-08-27) — digest mode: dimensions 8–11 (two hard gates), the
  six-meeting benchmark corpus, alongside `Renderer_prompt.txt` v1.1 and
  `digest_mode.txt` (new). No calibration data for any mode yet.
- v1.0 (2026-08-23) — first draft, alongside `Renderer_prompt.txt` and
  both mode files (`docs/AGENT_DESIGN.md` §6 Step 6). No calibration data.
