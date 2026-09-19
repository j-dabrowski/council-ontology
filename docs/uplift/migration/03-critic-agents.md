# Critic Agents and the Review Loop — Migration Plan

Traces the target 11-critic roster, typed-findings ledger, and loop
mechanics in `docs/uplift/03-critic-agents.md` against the current
Editor/Fixer/Conductor review chain, established in full in
`00-codebase-map.md` §6 and referenced throughout `01-known-defects.md`.
Depends on `02-claim-layer.md` per that file's own header — critics
operate on claim objects, which don't exist yet; this file's steps
therefore all assume `02-claim-layer.md`'s Step 1 (the claim object) has
landed.

**Headline finding.** Today there is exactly **one** reviewer role
(Editor, `docs/review/editor/Editor_prompt.txt`) doing the job the target
splits across 11 critics. Reading its Procedure section in full shows it
already checks, in one undifferentiated pass: overclaim/framing (target
C-11's brief), innocent-explanation search (C-04's brief, near-verbatim —
"has a defensible innocent reading been considered"), singling-out
fairness (C-07's brief), misleading blended statistics (C-02's denominator
concern and D-23's impartiality-blending issue by name), proportionality
against stated n/base-rate/era (C-02 again), and caveat integration/balance
(a caveat-mush concern the target splits into typed findings). One prompt,
one pass, one severity axis (BLOCKING/ADVISORY, not the target's
blocking/should_fix/note three-tier) is doing roughly six of eleven
target briefs simultaneously — which is itself the root cause of why a
2026-08-22 real run could still miss things a narrower, routed critic
would have caught cold.

**A genuinely positive finding, not just a gap.** The target's
critic-capture mitigation ("critics see the panel cold... pay the
re-derivation cost") is already true of Editor today, structurally, by
accident rather than design: grepping `Editor_prompt.txt`,
`scripts/conductor_loop.py`, and `src/cli.py` for any read of a prior
round's `defamation_review_<n>.json` returns zero hits — each Editor pass
re-derives everything from scratch. This also means regression (a fix
reopening a prior finding) is mechanically hard to miss, since nothing is
assumed carried-forward. This property should be preserved, not rebuilt,
when the roster is split into 11 critics.

---

## Current state inventory

| Target capability | Current equivalent | Path | Status | Notes |
|---|---|---|---|---|
| Division of labour: linter handles rules, critics handle judgment | No linter exists yet (`02-claim-layer.md`); Editor's prompt does both rule-like checks (n≤3 blocking, per `src/invariant_gate.py`'s MIN_N doing the same job mechanically for scorecard claims) and judgment calls in one prompt | `docs/review/editor/Editor_prompt.txt`, `src/invariant_gate.py` | PARTIAL | The S7 gate already offloads *some* of Editor's mechanical work (Editor's own §5 explicitly defers to `gate_report.json` for scorecard claims' n-check) — the split the target wants is already half-built for exactly one rule |
| C-01 Auditor (WA auditor acceptance, statutory basis, regulatory unit match) | No dedicated role; closest is Editor's proportionality/Briginshaw check, which asks whether severity matches evidence but not whether the *population* matches the *regulatory* unit of analysis | `Editor_prompt.txt` §3 | MISSING | Nothing checks "is this the right regulatory population" specifically |
| C-02 Statistician (power, clustering, CI, multiple comparisons, denominator validity, causal language) | Editor checks "does the claim state n/base-rate/era" (a presence check) but never computes CI, power, or clustering — confirmed zero statistical-inference machinery anywhere (`01-known-defects.md`'s statistical-defects trace) | `Editor_prompt.txt` §3 | PARTIAL (presence-only) | Would have caught D-10–D-13, D-15, D-17 per the target's own claim — none of these were caught in the one real run to date |
| C-03 Jurisdiction expert (retrieval over statute corpus) | No jurisdiction-specific role and no statute corpus exists (`04-jurisdiction.md`) | — | MISSING | — |
| C-04 Council's defence counsel | Editor's "innocent-explanation search" bullet is this brief, word for word, but folded into a general checklist rather than run as an adversarial pass with its own incentive | `Editor_prompt.txt` §3 | PARTIAL | The Objection/Response blocks the target mentions as "a manual version of this" are confirmed to exist (`config/test_registry.json`'s `objection`/`response` fields, per `00-codebase-map.md` §8) — a real, if manual, precedent to formalise |
| C-05 Extraction sceptic (implausible base rates, error-band overlap) | No dedicated role; nothing today checks whether a finding's effect size falls inside the extraction error band, because no error-band data is computed at all (`05-verification.md`) | — | MISSING | Would have caught D-08, D-09 — neither was caught |
| C-06 Cross-panel editor (whole-build denominator reconciliation, entity consistency) | Editor's §1 procedure is per-claim ("enumerate every named-individual claim"), never a whole-build simultaneous pass; §4's `PRIVATE_ASSESSMENT.md` cross-check is manual and pre-declared, not automatic reconciliation | `Editor_prompt.txt` §1, §4 | MISSING | The target calls this "structurally the only critic that can catch" D-04/D-05/D-07/D-20 — consistent with those defects all shipping despite a real Editor pass having run |
| C-07 Subject/fairness (argue as the named individual) | Editor's "singling-out fairness" bullet covers pattern-vs-accusation but not a full adversarial argue-as-the-subject pass with per-person n/CI | `Editor_prompt.txt` §3 | PARTIAL | — |
| C-08 Visual QA (rendered image) | Confirmed absent: zero image-capture dependencies anywhere in the codebase (`00-codebase-map.md` §5, re-confirmed independently twice) | — | MISSING | The target's own note — "nothing currently in the loop has eyes" — is exactly right; D-02, D-35, D-38 all ship through this exact gap |
| C-09 Goodhart critic | No dedicated role or check anywhere | — | MISSING | Would have caught D-27, surfaced D-26 |
| C-10 Layman (rendered panel only, no claim object) | No dedicated role; Editor works from the claim/JSON side, never from a cold rendered-panel-only perspective | — | MISSING | Would have caught D-36, D-37, D-39 |
| C-11 Editor-in-chief (headline vs. evidence, runs last, sees all other findings) | Editor's overclaim/strength-ladder check is adjacent but Editor is the *only* reviewer, so there is no "runs last, sees all others' findings" position — it has nothing to run after | `Editor_prompt.txt` §3 | PARTIAL | Would have caught D-22 — did not, in the one real run |
| Typed findings (`id`/`critic`/`claim_id`/`severity`/`state`/`wontfix_reason`/`rounds_seen`) | Editor's output is a markdown-shaped list of BLOCKING/ADVISORY items (`Editor_prompt.txt` "## Output" section, `{"severity": "BLOCKING\|ADVISORY", ...}`) — two severities, not three, and no persistent `id`/`state`/`rounds_seen` tracking across passes | `Editor_prompt.txt` "## Output" | PARTIAL | The severity concept exists; the full typed-ledger shape (open/closed/wontfix lifecycle, cross-round identity) doesn't |
| Unresolved `note` findings publish as a visible limitations section | No `note`-equivalent tier exists (only BLOCKING/ADVISORY); nothing today publishes a standing limitations section assembled from unresolved advisory findings | — | MISSING | — |
| Critic capture mitigation (cold context, no negotiation history) | **Already true**, structurally, by accident — confirmed zero code paths feed a prior `defamation_review_<n>.json` back into a new Editor invocation | `src/cli.py`, `scripts/conductor_loop.py` | ALIGNED | Preserve this property explicitly when building the 11-critic roster; don't let a router or orchestrator introduce state that isn't there today |
| Regression protection (persistent findings ledger, re-checked each round) | No explicit ledger; regression protection is an *emergent* property of full statelessness (every pass re-derives everything), not a designed re-check mechanism | — | PARTIAL (emergent, not designed) | Works today by accident of the stateless design; will need to become explicit once findings persist with `state`/`rounds_seen`, since a genuinely persistent ledger reintroduces exactly the state the current design avoids by chance |
| Hard cap at three rounds; dropped-claims registry | `config/agent_switches.json`'s `conductor_max_passes` (currently 3) is a real, existing cap — but on *Editor/Fixer passes over a whole draft*, not per-claim, and there is no `dropped` registry — a capped-out draft escalates to a human, it doesn't publish with some claims dropped and others shipped | `config/agent_switches.json`, `scripts/conductor_loop.py` | PARTIAL | The cap-and-escalate mechanic exists at the wrong granularity (whole draft, not per-claim) for the target's "publish with dropped-count as a credibility asset" design |
| Routing (route critics by claim properties, not run all on everything) | No routing exists — Editor runs its full checklist against every claim in the draft, uniformly | `Editor_prompt.txt` | MISSING | — |
| "Builder and analyst are both regeneration targets; visual findings go to builder only" | No such distinction exists — Fixer has 3 modes (frontend/pipeline/doc) which is a *similar* shape (route by what needs fixing) but is track-scoped, not finding-type-scoped, and nothing prevents a visual finding from triggering a full claim regeneration today because there's no claim object to regenerate yet | `docs/review/fixer/*.txt` | PARTIAL | Fixer's 3-track split is real, reusable precedent for the target's builder/analyst regeneration-routing — same shape, different axis |

---

## Gaps

### G-01: One monolithic critic instead of eleven routed ones
Target: eleven critics, each with a narrow brief, routed by claim properties so not every critic runs on every claim.
Current: Editor's single prompt already performs the substance of roughly six of the eleven briefs (C-02, C-04, C-06(partial), C-07(partial), C-11(partial), and a presence-only C-01-adjacent check), undifferentiated, on every claim, every pass.
Delta: splitting is not "build six new capabilities from nothing" — it's disaggregating one prompt's existing checklist into separately-routable, separately-improvable roles, plus building the five capabilities that don't exist in any form (C-03, C-05, C-08, C-09, C-10).
Risk if unfixed: a single prompt covering six briefs has six chances per pass to under-attend to any one of them — consistent with the one real Editor run to date catching some issues (per its FAIL result) but missing D-04, D-22 and others the target attributes to specific, narrower critics.

### G-02: No statistician critic with real inference machinery
Target: C-02 re-runs the filter chain against gold and checks power/clustering/CI/multiple-comparisons/causal language.
Current: Editor checks only that n/base-rate/era are *stated*, never computes or verifies them; no CI/clustering/power machinery exists anywhere to check against (`02-claim-layer.md` G-02).
Delta: this critic cannot be built before `02-claim-layer.md`'s Step 4 (statistical inference module) exists — there is nothing for it to read.
Risk if unfixed: D-10–D-13, D-15, D-17-style defects continue to require a human or a lucky general check to catch, rather than a routed, reliable one.

### G-03: No jurisdiction critic or statute corpus
Target: C-03 retrieves against a curated, versioned WA statute corpus; explicitly must not work from general knowledge.
Current: no such corpus exists anywhere in the repo (confirmed by grep — the only near-hit is a passing phrase in `docs/pipeline/DATA_ENRICHMENT.md`, not an actual corpus); no jurisdiction-specific review role exists.
Delta: this is `04-jurisdiction.md`'s corpus-building work as a prerequisite, plus a new critic role once it exists.
Risk if unfixed: D-01, D-28, D-29, D-30 continue to require a human with WA local-government expertise to catch — exactly the gap that let UK frameworks and a missing s5.68 check ship in the first place.

### G-04: No cross-panel/whole-build critic
Target: C-06 runs once per build, sees every claim simultaneously, and is described as the *only* structurally capable check for denominator reconciliation, entity-naming consistency, and cross-panel confound inconsistency.
Current: Editor is per-claim; its one whole-build-adjacent check (§4, cross-checking `PRIVATE_ASSESSMENT.md`'s pre-declared risk items) is manual and requires the risk to already be known and written down, not discovered automatically.
Delta: this is a materially different kind of critic (batch, not per-item) and can't be retrofitted onto Editor's existing per-claim loop — it needs its own invocation, once per `council draft` run, after every other claim has passed.
Risk if unfixed: D-04, D-05, D-07, D-20 — all defects the target explicitly says nothing else can catch — continue to ship even after a full, real Editor pass, exactly as observed.

### G-05: No visual/rendered-image critic
Target: C-08 renders the panel and looks at it — the target's own words, "nothing currently in the loop has eyes."
Current: confirmed, independently, twice, across `00-codebase-map.md` and `01-known-defects.md` — zero image-capture tooling exists anywhere.
Delta: needs a rendering path (headless browser or existing SSR — see Step 3 below) before any visual critique is possible at all; this is infrastructure, not a prompt.
Risk if unfixed: D-02, D-35, D-38-style defects — anything only visible in the rendered output — have no mechanism to ever be caught before publish, no matter how good the other ten critics are.

### G-06: Findings are two-tier and ephemeral, not three-tier and persistent
Target: typed findings with `id`/`state`/`wontfix_reason`/`rounds_seen`, letting unresolved `note`-severity findings ship as a published limitations section instead of blocking forever.
Current: Editor's BLOCKING/ADVISORY output has no third tier and no persistent identity across rounds — an ADVISORY finding that's still open after round 3 has no defined fate; nothing structures it into a limitations section.
Delta: needs both a schema change (three tiers) and a new publish-time step (assemble unresolved notes into a rendered section) — currently nothing produces that section from anything.
Risk if unfixed: the caveat-mush failure mode the target explicitly names ("critics always find something → builder always hedges → panels become unreadable") has no structural prevention today beyond Editor's own discretion about what to flag.

### G-07: Regression protection is emergent, not designed
Target: a persistent findings ledger, re-checked each round, explicitly engineered against regression.
Current: regression protection exists today only as a side effect of Editor being fully stateless (it re-derives everything, so a regressed issue would be caught again by chance, not by design) — the same statelessness is also what makes the critic-capture mitigation "free" today (see the ALIGNED row above).
Delta: introducing a genuine persistent ledger (Step 4 below) must be done carefully — it's solving G-06/regression tracking but must not reintroduce the state-across-rounds problem that critic-capture mitigation currently avoids by having none. The ledger should record finding history for humans/reporting; it must never be read back into a critic's own context before that critic re-judges a claim.
Risk if unfixed either way: build the ledger wrong and you trade one failure mode (no regression tracking) for the other (critic capture) that the current accidental design avoids.

### G-08: No per-claim drop mechanism; only a whole-draft pass cap
Target: three-round cap *per claim*, failing claims written to a `dropped` registry and counted publicly ("47 tested, 12 published, 3 dropped").
Current: `conductor_max_passes` (`config/agent_switches.json`, currently 3) caps whole-draft Editor/Fixer passes, escalating the entire draft to a human on cap-out — a real, working mechanism, but at the wrong granularity for the target's per-claim design.
Delta: needs re-scoping from whole-draft to per-claim, plus a new `dropped` registry and a published count — neither exists today.
Risk if unfixed: today, one unresolvable claim in an otherwise-clean draft blocks the entire draft rather than being dropped and disclosed — a worse failure mode than the target's design for exactly the "we tried, this one didn't survive review" case.

### G-09: No routing; every check runs on every claim uniformly
Target: route critics by claim properties (grade, `names_individuals`, `framework_refs`, era-precision, gameability) so cheap checks always run and expensive/specialist ones run only when triggered.
Current: Editor's single prompt evaluates its full checklist against every claim regardless of grade or content.
Delta: routing requires the claim object's fields to route on (`02-claim-layer.md` Step 1) — this can't be built before that.
Risk if unfixed: as the roster grows to eleven critics, running all eleven on every claim is both expensive and — per the target's framing — actively counterproductive (irrelevant critics manufacture noise).

---

## Implementation steps

### Step 1: Split Editor's existing checklist into its constituent critic briefs
Files touched: new `docs/review/critics/` directory — `auditor.txt` (stub, blocked on 04), `statistician.txt` (stub, blocked on 02 Step 4), `defence_counsel.txt` (from Editor §3's innocent-explanation-search bullet), `subject_fairness.txt` (from Editor §3's singling-out bullet), `editor_in_chief.txt` (from Editor §3's overclaim/strength-ladder bullet, made to run last)
Depends on: `02-claim-layer.md` Step 1 (claim object as the input contract every critic reads)
Done when: every check currently inside `Editor_prompt.txt`'s §3 has an owning critic file, even where that critic can't run yet for lack of upstream data (statistician, auditor).

### Step 2: Build the typed-findings schema and ledger
Files touched: new `src/analysis/findings.py` (the `finding` dataclass per the target schema, three severities), a persistence layer (a JSON sidecar per draft, similar in spirit to today's `defamation_review_<n>.json` but structured per-finding rather than per-review-document)
Depends on: Step 1 (need critics that produce findings to have a schema for)
Done when: a critic's output is a list of typed `finding` objects, not free-form prose; `wontfix` findings require and store a reason; the ledger is queryable by `claim_id` and `state`.

### Step 3: Build the rendering path for C-08
Files touched: new `scripts/render_panel_image.py` or equivalent (headless-browser capture of one panel component, given a snapshot's JSON — investigate reusing the existing Vite dev server + a headless Chromium via Playwright, already a project dependency per `pyproject.toml`'s `[browser]` extra used by the Cambridge scraper)
Depends on: none technically, though it's most useful once claim objects exist to attach the rendered image's findings back to (Step 1)
Done when: given a snapshot JSON and a `test_id`, a PNG of the rendered panel can be produced headlessly, addressable the same way `05-verification.md`'s V-4 page-rasterisation is (by a stable key), and a C-08 critic prompt can be given that image as input.

### Step 4: Build C-06, the cross-panel critic, as a whole-build pass
Files touched: new `docs/review/critics/cross_panel.txt`, wired into `council draft` (or `council editor-loop`) as a step that runs once, after every individual claim has a claim object, before per-claim critics run — inputs are every claim in the build simultaneously
Depends on: Step 1; `02-claim-layer.md`'s gold-table layer (Step 2 there) for entity-consistency checks to have a canonical id to check against
Done when: a build with two claims sharing a `population.definition` but different `denominator.n` (G-04/D-04's exact shape) is flagged automatically, without a human having pre-declared the risk.

### Step 5: Build the routing table
Files touched: new `src/review/routing.py` (or extend `scripts/conductor_loop.py`), implementing the trigger table from `03-critic-agents.md` verbatim
Depends on: Step 1 (claim properties to route on), Steps 1–4 (critics to route to)
Done when: a NEUTRAL, non-named, non-gameable claim triggers only C-08/C-10/C-11 (the "always" row), not the full roster.

### Step 6: Re-scope the pass cap from whole-draft to per-claim; build the dropped registry
Files touched: `scripts/conductor_loop.py` (currently whole-draft `conductor_max_passes` logic), new `dropped_claims.json` registry written alongside a draft's manifest
Depends on: Steps 1–2 (need per-claim findings to know which specific claim is stuck, not just that the draft overall failed)
Done when: one unresolvable claim is dropped and counted, not escalating the entire draft; `council draft`'s manifest reports a dropped count the same way it reports snapshot tiers today.

### Step 7: Assemble unresolved `note` findings into a published limitations section
Files touched: `src/cli.py` (`_generate_snapshots()` or `cmd_publish`), a new `limitations` field on the relevant snapshot(s)
Depends on: Steps 2, 5, 6
Done when: a panel that survives three rounds with an open `note`-severity finding ships with that finding rendered on its face, not silently dropped or endlessly re-litigated.

### Step 8: Preserve the cold-critic property explicitly
Files touched: whichever orchestrator ends up dispatching the 11-critic roster (likely an extension of `scripts/conductor_loop.py`)
Depends on: Steps 1–5
Done when: a test exists asserting no critic invocation is ever given a prior round's findings for the same claim in its own context — the ALIGNED property identified above must survive the transition from "true by accident" to "true by design."

### Cross-category dependency notes
- Steps 1 (auditor, statistician) and the whole of G-03 are blocked on `04-jurisdiction.md`'s statute corpus and `02-claim-layer.md`'s statistical-inference module respectively — build the routing/ledger/visual infrastructure (Steps 2, 3, 5–8) first, since those have no such blocker.
- `05-verification.md`'s C-05 extraction-sceptic critic needs the per-field/per-era error table that file defines — this file's Step 1 stub for that critic should stay a stub until `05-verification.md` Step 1 (V-1/V-2/V-3 census checks) lands.
