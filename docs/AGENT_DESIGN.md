# Agent Design — roles derived from the flow

**What this is.** The third design artefact of the 2026-08-23 redesign
(after `investigator/COVERAGE_AUDIT_2026-08-23.md` and
`INFORMATION_ARCHITECTURE.md`). It assigns an owner to every stage of the
flow in `INFORMATION_ARCHITECTURE.md` §3, answers that document's §8 open
questions, and specifies what each existing prompt/protocol file becomes.
Accepted 2026-08-23; referenced from `docs/MAP.md`. Nothing here is built
yet — §6 is the build order for the implementation sessions.

**The assignment rule.** Owner follows task, in this order:

1. **Script** — wherever the check or transformation is decidable from
   structured data. Scripts are free, deterministic, run every time, and
   never hallucinate. The Editor pass-1 evidence stands: 5 of 7 blocking
   flags were script-detectable.
2. **LLM role** — only where the task is judgment over open-ended text:
   generating hypotheses, drafting code, weighing language, translating
   register. Every LLM role stays benchmark-gated by a protocol doc, with a
   machine-readable stage contract — the pattern the project has already
   proven five times over.
3. **Human** — wherever accountability is the point: publish authorization,
   sending words to real people, accepting a protocol version bump. Same
   gates as today; the redesign adds no new agent autonomy anywhere.

---

## 1. Stage → owner

| Stage | Task | Owner | Today |
|-------|------|-------|-------|
| S0 Acquisition | fetch documents per class | **script** (existing scrapers, extended per document class) | script ✓ |
| S1 Extraction | documents → typed records + evidence ledger | **LLM-in-a-loop, non-agentic** (existing tiered extractor, pack prompts) | same ✓ |
| S2 Corpus profile | NULL rates, spans, identity state, record-quality metrics | **script** — new `council profile` command | Explorer's Stage 1 (agent-authored) |
| S3 Discovery | hypothesis generation + testing on training corpora | **Explorer** (narrowed — §2) | Explorer Stages 2–4 |
| S4 Codification | finding → registered claim generator + declaration block | **Refiner** (extended — §2) | Refiner ✓ |
| S5 Confirmation | frozen battery on confirmation corpus, pre-registration check | **script** (`council draft --role confirmation`) | no equivalent |
| S6 Claim assembly | generators × corpus → claim objects | **script** (`council draft`, as now) | script ✓ |
| S7 Invariant gate | MIN_N, name-free schema, identity clean bill, superlative checks, tier derivation | **script** — new, runs inside `council draft`; failure blocks the draft | Editor (LLM) catches these late |
| S8 Semantic review | language ladder, innocent explanations, singling-out, blended stats | **Editor** (narrowed — §2) | Editor ✓ (over-broad) |
| S8 fix loop | act on Editor flags | **Fixer** (unchanged) + **Conductor** (unchanged shape) | ✓ |
| S9 Right of reply | packet assembly · sending · response ingestion | **script** assembles (claims are structured; filter by `named_entities`, render template) · **human** sends and receives · responses re-enter as S8-class fix items | no equivalent |
| S10 plain-language rendering | institutional product → layman summary | **Renderer** (new role — §2) | no equivalent |
| S10 deep-report prose | cross-claim synthesis (FINDINGS_SUMMARY successor) | **Renderer**, synthesis mode | Explorer Stage 7 |
| S10 surfaces | panels/pages render tier products | **frontend track** (human + coding sessions, INTERACTIVITY recipe) | ✓ |
| Coverage register | dimensions × status; scope boundaries | **script verifies** (CI cross-check: every shipped generator maps to a register row) · **Refiner updates** on codification · **Researcher proposes** new rows | Dimension 1 (per-session count) |
| Taxonomy growth | precedent → Part 3 + register rows | **Researcher** (unchanged, gated) | ✓ |
| Publish | tier products → public | **human**, via the existing authorization-record gate | ✓ |

Net: two new scripts carry most of the redesign's weight (S2 profile, S7
gate); one LLM role is added (Renderer), one is retired (Runner), none
gains autonomy.

---

## 2. The role roster

### Survives, narrowed — **Explorer** (S3)
Sheds three duties: authoring the data survey (consumes the S2 profile
instead — which retires the root cause of its two failed benchmark
dimensions rather than re-prompting around it), building panels/snapshots
(Stages 5–6 leave the prompt; rendering belongs to S10 owners — this also
resolves the known "nothing to act on when Stage 4 yields only nulls"
wrinkle), and per-session domain-breadth bookkeeping (replaced by
register-gap seeding: Stage 2 hypothesis lists open against the coverage
register's worst gaps, per the audit's R4). Keeps: hypothesis generation,
testing, INVESTIGATIONS.md discipline, kill/null honesty, enrichment-backlog
writes, Stage 9 self-scoring. Runs only on `role: TRAINING` corpora — the
corpus manifest is now a hard input.

### Survives, extended — **Refiner** (S4)
Keeps both entry points and the six-dimension benchmark. Gains: emitting the
**generator declaration block** (unit of analysis, MIN_N, strength ceiling,
valence logic, principle tags — the fields S7 enforces) as a required output,
and updating the coverage register row for every codified test. Its
benchmark gains one dimension: declaration completeness (hard gate — an
undeclared generator is unshippable because S7 cannot gate what isn't
declared).

### Retired — **Runner**
Its duties reassigned, none dropped: battery execution and snapshot export
were always `council draft` (script); regression spot-checks become S7
assertions plus the existing CI; frontend verification stays the
build-check script; "clean run as input to the human publish decision"
becomes the draft manifest + gate results, which the existing authorization
record already consumes. What made Runner a *role* was standing between a
script and a human gate; with S7 in place there is no judgment left in that
gap. `Runner_prompt.txt` is archived, not deleted (its checklist seeds the
S7 assertion list).

### Survives, narrowed — **Editor** (S8)
Scope shrinks to the four semantic classes: overclaim language (the
strength-ladder check), innocent-explanation search, singling-out fairness,
misleading blended statistics. Everything mechanical is S7's, and an S7
failure never reaches the Editor. `EDITOR_PROTOCOL.md` is recalibrated
accordingly: the pass-1 flags that were mechanical leave its benchmark
corpus, and it gains a false-positive dimension (flag rate on drafts that
S7 already passed — the Editor re-litigating the gate is a defect, not
diligence). Prediction to verify at first run: pass volume drops enough
that the 3-pass cap-outs seen in both real chains stop being the norm.

### Unchanged — **Fixer** (frontend / pipeline / doc modes) and **Conductor**
Fixer's three modes, BLOCKED status, and sidecar survive as-is; it now only
ever receives S8-class flags. The Conductor keeps its loop, pass cap, gate
profiles, and the publish invariant verbatim — see §3 Q3 for its boundary.

### Unchanged — **Researcher**
Same gated flow, same pending-merges mechanism. One addition to its output
format: a candidate genre may propose a coverage-register row (dimension +
what would close it), so top-down coverage growth lands in the register the
same way it lands in Part 3.

### New — **Renderer** (S10), two modes, one shared layer
The same role-with-modes shape as Investigator and Fixer:
- **plain-language mode**: institutional product → resident-facing summary.
  Input is structurally person-free (C1), so the defamation surface is
  closed by construction; the mode's risk is *fidelity*, so its protocol
  benchmark is fidelity-shaped: no claim not present in the input, no
  dropped caveat that changes a claim's meaning, denominators and
  uncertainty survive translation, register plain without editorialising
  (NEUTRAL, per the framing rules).
- **synthesis mode**: deep product → cross-claim prose (the
  FINDINGS_SUMMARY / Overview successor), inheriting the existing framing
  discipline (hostile-reader + promoter sentence pairs, NEUTRAL register).
A new `RENDERER_PROTOCOL.md` governs both modes — the sixth instance of the
established protocol pattern, deliberately nothing novel.

---

## 3. The five open questions, answered

**Q1 — which stages need an LLM?** As the table shows: S1 (extraction,
non-agentic), S3 (Explorer), S4 (Refiner, code-drafting under benchmark),
S8 (Editor), S10 (Renderer). Five. Everything else — profile, confirmation
run, claim assembly, invariant gate, tier derivation, reply-packet assembly,
register verification — is scripted. S9's letter itself is a template;
judgment about *sending* it is human by design, not for lack of capability.

**Q2 — does Explorer/Refiner/Runner survive?** Explorer and Refiner survive
as the two modes of the Investigator role, mapped 1:1 onto S3 and S4;
Runner is retired (§2). The protocols transfer almost whole: benchmark
dimensions change where a duty moved (Explorer loses the survey/build
dimensions, gains register-gap reduction; Refiner gains declaration
completeness), and every role's completion output converges on the stage
contract + JSON sidecar shape that Editor v0.3, Fixer, and Researcher
already share — one uniform contract format across all five LLM roles.

**Q3 — where does the Conductor's authority end?** At the S8 flag loop,
exactly: it spawns Editor and Fixer, enforces the pass cap, and stops. It
does not own S7 — a gate failure is not a review finding, it's a blocked
draft routed straight to the owning track as ordinary work, with no chain,
no pass count, no Editor call (same logic as the existing rule that a FAIL
never triggers an idle track's Fixer). It does not own S9 — right of reply
is human-paced and can't sit inside an agent loop with a pass cap. And the
publish invariant is untouched: both S7 and S9 add *more* prerequisites to
the authorization record, never an alternative path around it.

**Q4 — right-of-reply operations.** Packet assembly is scripted (claims
filtered by `named_entities`, rendered into a fixed template: the claims,
their evidence, the response window, how responses are published).
Sending requires a human act — words addressed to a real person leave the
building only on a human's authorization. In interactive operation that
means the human sends; in scheduled operation (§5) the human act is
merging the reply-packet PR, and a workflow performs the mechanical send
after merge — same accountability, unattended mechanics. Window: fixed per pack config (council pack:
14 days is the conventional journalistic floor for non-urgent findings —
confirm against WA practice before first use). Non-response: publish with
"was offered the opportunity to respond and declined / did not respond" —
the standard formula, recorded on the claim's `reply` field. A response
that *disputes* a claim re-enters as an S8-class fix item (the Editor
weighs it exactly like an innocent-explanation finding: amend, annotate, or
withdraw); a response that merely *comments* attaches verbatim to the claim
and ships with it in the deep product. Responses are never editable by any
role — verbatim or absent.

**Q5 — the coverage register's form.** A source file plus a verifier: the
register itself is a small structured file (dimensions, status, scope-
boundary notes — the audit's grid as living data), because empty and
blocked rows cannot be generated from code that doesn't exist. A CI script
cross-checks it against the shipped generators' declaration blocks — every
generator maps to a row, every DENSE/MODERATE row's listed tests actually
exist — so the file can drift only in the directions code can't verify,
which are exactly the rows humans and Researcher curate. Refiner updates it
on codification (verified by the script); Researcher proposes rows through
pending-merges; Explorer reads it at Stage 2.

---

## 4. File-by-file deltas

| File | Becomes |
|------|---------|
| `Investigator_prompt.txt` (shared layer) | survives; Part 0's caveats section points at the S2 profile artefact instead of hand-maintained prose; Part 4 gains the strength ladder + superlative-check definitions (they are claim-object law, so they live in the shared layer all roles read) |
| `Explorer_prompt.txt` v2.6 | v3.0 — drop Stage 1 (consume profile), drop Stages 5–6 (build), reseed Stage 2 from the register; renumber; Stage 9 dimensions per §3 Q2 |
| `Refiner_prompt.txt` v1.1 | v1.2 — declaration block emission + register update step |
| `Runner_prompt.txt` v1.0 | archived; checklist seeds the S7 assertion list |
| `Editor_prompt.txt` v0.3 | v0.4 — scope narrowed to the four semantic classes; explicit instruction that S7-covered classes are out of scope |
| `Fixer_prompt.txt` + 3 modes | unchanged |
| `CONDUCTOR.md` | one addition: the S7/S9 boundary statements from §3 Q3; loop unchanged |
| `EXPLORATION_PROTOCOL.md` / `REFINEMENT_PROTOCOL.md` / `EDITOR_PROTOCOL.md` | dimension edits per §2; calibration histories kept, new columns dated |
| `RESEARCH_PROTOCOL.md` / `Researcher_prompt.txt` | one addition: optional register-row proposal in candidate output |
| new: `RENDERER_PROTOCOL.md` + `Renderer_prompt.txt` + 2 mode files | per §2 |
| new: `council profile`, S7 gate in `council draft`, register verifier, packet assembler | scripts; land under the existing CLI + CI conventions, PR-per-run rule from `AUTOMATION_ARCHITECTURE.md` applies unchanged |
| `AGENT_PROMPTS.md` | roster updated: Runner row removed, Renderer rows added; invocation pattern unchanged |
| `AUTOMATION_ARCHITECTURE.md` | updated on acceptance: stage rows re-mapped to §1 (Runner row removed, S2/S7 scripts and Renderer added); Part 5's schedule-vs-dispatch question closed by §5's run types; the one-PR-per-run rule, GCS-vs-git rule, and Part 4 chaining survive unchanged |

## 5. Autonomous operation

The whole pipeline must be runnable start-to-end with no human in the
loop except PR review — `AUTOMATION_ARCHITECTURE.md`'s model (GitHub
Actions run on its own branch; every git-tracked effect in one PR per
run; results publishable to the frontend on merge). This section maps the
redesigned stages onto that model. Its rules all survive unchanged: the
GCS-vs-git split, one PR per triggered run (not per role), later stages
checking out the run's own branch, the PR as the single review surface,
and the publish authorization invariant.

### Two run types (closing `AUTOMATION_ARCHITECTURE.md` Part 5's open question)

The corpus-role model (C4) answers "schedule or dispatch" structurally —
they are different runs:

```
 MAINTENANCE RUN — scheduled (fortnightly/monthly), fully autonomous-capable
 ───────────────────────────────────────────────────────────────────────────
 cron → Flow 0 (S0–S2: scrape → extract → validate → dedup → S2 profile)
      │    · candidate DB → staged GCS; the S2 PROFILE is the PR's
      │      git-trackable summary (one artefact, both duties)
      │    · GATE: PR merge promotes staged DB → canonical
      ▼
 promotion → S5/S6 battery run (frozen generators only — no discovery)
      → S7 invariant gate (script; failure = blocked draft, PR carries the
        gate report, run stops there)
      → S8 Editor (auto gate profile once calibrated — see ladder below)
      → Renderer refresh (plain-language + synthesis, only for claims that
        changed) → tier products
      → publish per autonomy ladder; Vercel deploys on merge
 The run's PR carries a CLAIM DIFF: new / changed / retired claims, tier
 moves, valence or grade flips — the redesign's version of "a summary
 standing in for the DB." LLM roles in the whole loop: Editor and
 Renderer only.

 DISCOVERY RUN — workflow_dispatch, deliberate, never scheduled
 ───────────────────────────────────────────────────────────────
 Explorer (TRAINING corpora only) → optionally Refiner chained in the
 same run (Part 4's one-PR-per-run chaining applies verbatim) → PR:
 scratchpad scripts + findings summary + generator diff + declaration
 blocks + coverage-register update. Produces instrument changes, never
 publications — a merged discovery PR changes what the NEXT maintenance
 run computes.
```

Discovery is dispatch-triggered because it changes the instrument, and
the register — not the calendar — says when that's worth doing; a new
fortnight of minutes changes the *data*, which is exactly what the
maintenance run handles with the frozen battery.

### The autonomy ladder (per tier, matched to the risk gradient)

| Level | What runs unattended | Human acts remaining |
|-------|---------------------|----------------------|
| 0 — today | nothing end-to-end | every gate |
| 1 — institutional autonomy | maintenance run through to **public-tier publish and deploy**: S7 proves the institutional product name-free, Editor runs in auto profile, publish uses `--gate-profile auto` re-validating the on-disk PASS + gate records | Flow 0 PR merge; deep product still held |
| 2 — deep-product autonomy with claim-level holdback | deep product publishes too, except claims whose `reply` field is incomplete — **held back per claim, not per draft** (the claim store makes partial publication well-defined); reply-packet PR merge authorizes the send workflow | Flow 0 PR merge; reply-packet PR merge |
| 3 — full post-hoc | everything, PRs auto-merged, human reviews after the fact | none in-loop |

Recommended ceiling: run at level 2. Level 1 is reachable as soon as S7 +
tier derivation exist and Editor's narrowed scope has calibration data
(the condition `AUTOMATION_ARCHITECTURE.md` Flow D already sets, met
faster because S7 shrinks what Editor must be reliable *at*). Level 3 is
listed for completeness, and deliberately not recommended for the deep
tier: publishing new claims about named people with no prior human
glance, and sending them letters nobody merged, is the one autonomy the
risk assessment never gets cheaper. The publish invariant holds at every
level — autonomy substitutes *which* verifiable authorization record
gates publish (PR merge + PASS sidecars + gate report instead of
`--confirm`), never whether one exists.

This also resolves Flow E's flagged open question: the public tier keeps
the existing hash-verified mechanism and becomes auto-eligible at level 1;
the deep tier's addition is the reply-completeness check at level 2 —
both are additions to the authorization record, not a switch to a generic
PR gate.

## 6. Suggested build order (for the implementation sessions)

Risk-reduction first, roles last — each step ships value alone:

1. **S7 invariant gate** + claim-object fields it needs (`unit_of_analysis`,
   `n` enforcement, `named_entities`, `entity_resolution`) — closes the
   largest live exposure (the flag-1/3/5/6/7 classes) before anything else
   moves. **Done 2026-08-23** — `TestResult` (`src/analysis/tests.py`) gained
   the three fields plus their vocabulary constants (`UNIT_INSTITUTIONAL` /
   `UNIT_INDIVIDUAL_IMPLICATING` / `UNIT_INDIVIDUAL`,
   `ENTITY_RESOLUTION_CLEAN` / `_OPEN_SPLITS`); `src/invariant_gate.py`
   implements the three checks (name-free institutional schema, MIN_N,
   entity-resolution clean bill), reading `MIN_N` from `config/invariants.json`
   (calibrated to Editor's own n ≤ 3 BLOCKING line); `council draft` runs it
   between battery computation and `manifest.json`, writing `gate_report.json`
   either way and exiting non-zero with no manifest on failure — see
   `docs/TESTING.md`'s "Draft & publish workflow". `tests/test_invariant_gate.py`
   covers a clean battery, each of the three violation classes individually,
   and a mixed battery that fails on one bad claim among clean ones. Verified
   against the real Cambridge corpus: `council draft cambridge` (29 claims,
   all `institutional`) clears the gate; splicing one synthetic `individual`
   claim (n=2, `entity_resolution="open-splits"`) into that same real battery
   trips both the MIN_N and entity-resolution checks. No deviation from spec.
2. **Tier derivation** onto the existing `public`/`full` rail — makes the
   institutional product real; first `public`-tagged snapshots. **Done
   2026-08-23** — `derive_claim_tier` (`src/invariant_gate.py`) is a pure
   function of a claim batch: `"public"` iff every claim is
   `institutional`-unit, `"full"` if any is `individual`/
   `individual_implicating`. `_tier_of` (`src/cli.py`) now calls it for the
   `scorecard` snapshot (the only one built from `TestResult` claims today —
   `CLAIM_DERIVED_SNAPSHOTS`) instead of reading a static `SNAPSHOT_TIER`
   entry; every other snapshot (per-councillor profile data, not yet claim
   objects) is unaffected. `tests/test_invariant_gate.py` covers all-clean,
   one bad claim of each unit, a not-computable claim not counting against
   the tier, and the empty-battery edge case. Verified against the real
   Cambridge corpus: `council draft cambridge` now derives `scorecard` as
   `"public"` (29/29 claims institutional) — the first snapshot ever tagged
   public; splicing one well-formed (gate-passing, n=25, entity_resolution
   clean) `individual` claim into that same real battery drops it back to
   `"full"`, confirming tier derivation is a real, independent check and not
   just a restatement of the S7 gate. Did not run `council publish` for
   real — that copies bytes into the git-tracked, Vercel-served
   `frontend/public/data/`, a separate publish-authorization decision this
   step doesn't make on its own.
   **Deviation (scoping, not a spec conflict):** `derive_claim_tier` is
   whole-batch, not per-claim — one non-institutional claim drops the
   entire `scorecard` snapshot to `"full"` rather than shipping a filtered
   institutional subset. §4's "reduced form" per-claim redaction for
   `individual_implicating` claims (e.g. a distribution without its
   per-person bars) is real future work, not built here: no claim in the
   current battery needs it, and designing the redaction mechanism against
   zero real examples would be speculative. Revisit once a generator
   actually produces a non-institutional claim.
3. **S2 `council profile`** — unblocks the Explorer/Refiner prompt edits.
   **Done 2026-08-23** — `compute_corpus_profile` (`src/analysis/profile.py`)
   computes one machine-readable document, council-agnostic (keyed off the
   ontology's own tables/columns, no Cambridge-specific content): span
   (document counts by type, date range, and a zero-meeting-month gap
   detector computed from the data, not a hand-maintained gap list),
   entity_counts (council-scoped row counts across every entity table),
   record_quality (NULL/coverage rates on the fields Part 0 already flags as
   structurally sparse, vote-choice distribution, tender confidentiality),
   and identity_resolution (with-votes/with-terms/with-neither, and a
   duplicate-family-name heuristic explicitly labeled "worth checking, not
   confirmed"). `council profile <council>` (`src/cli.py`, between
   `validate` and `analyse`) writes `data/<council>_profile.json`
   (gitignored, refreshed each run — added to `.gitignore`) and prints a
   summary. `tests/test_profile.py` (13 tests, in-memory SQLite) covers span
   gap detection, council-scoped counts, each null-rate/coverage
   calculation, the no-rows-gives-None (not division-by-zero) case, and
   that two councils sharing one DB never leak into each other's profile.
   Did not wire this into S3/S4/S7/S8 consumption or rewrite
   `Investigator_prompt.txt` Part 0 to point at it — both are explicitly
   Step 5's job ("Prompt/protocol revisions"), not this step's.
   Verified against the real Cambridge corpus: `council profile cambridge`
   reproduces, from data alone, several caveats Part 0 currently states by
   hand — `planning_application_date_null_rate` / `_decision_date_null_rate`
   both 1.0 (matches "100% NULL"), `councillor_term_coverage_rate` 0.167
   (matches "sparsely populated"), and `zero_meeting_months_in_span`
   surfacing the documented 2022/2023 CMS-migration gap months plus the
   recurring no-January-meeting pattern, without either being hardcoded
   anywhere in the script. No deviation from spec.
4. **Coverage register file + verifier** — the audit grid becomes data.
5. **Prompt/protocol revisions** (Explorer v3, Refiner v1.2, Editor v0.4,
   Conductor addition) — now they describe a world that exists.
6. **Renderer + reply pipeline** — the new audience surfaces, last, on top
   of stable products.
7. **Workflow wiring (§5)** — the maintenance-run workflow at autonomy
   level 1 (institutional tier end-to-end), then level 2 once the reply
   pipeline exists; the discovery-run workflow is just
   `AUTOMATION_ARCHITECTURE.md`'s Flow A/B on the new prompts and needs no
   new machinery.
