# Autonomous Discovery Loop — Design Proposal

**Status: built, 2026-08-20.** All five components (A–E) are implemented —
see the file list at the bottom of this note. `MAP.md` has been updated to
match §7 below. This doc is kept as the design record; `MAP.md` and the
individual track docs are now the source of truth for current state.

**What shipped:**
- **A** — `investigator/Investigator_prompt.txt` Part 3.5 (Policy/programme
  effectiveness genre), plus its Part 5 source citation.
- **B** — `pipeline/DATA_ENRICHMENT.md` restructured: every entry now has a
  Pattern (council-agnostic) layer above its Instance (Cambridge) layer.
- **C** — `scripts/inventory_typology.py` (`_load_data_enrichment_patterns`,
  `_section_known_patterns`, wired into `_generate_extraction_prompt`) reads
  `DATA_ENRICHMENT.md`'s pattern layer before generating the Level 2
  schema-update prompt. `pipeline/PIPELINE.md` documents the new step.
  Verified: parses all 12 current patterns correctly, `py_compile` clean.
- **E** — `research/RESEARCH_PROTOCOL.md` (four-dimension benchmark,
  approval flow, empty calibration log) and `research/PRECEDENT_BANK.md`
  (seeded with P1, the Part 3.5 entry, logged retroactively).
- **D** — `research/Researcher_prompt.txt`, now **v1.2** (still never run,
  no calibration data exists). Shipped as v1.0 (human-gated) in this
  session; revised same-day to v1.1 (fully self-governing — Researcher
  merged its own passing candidates directly, no checkpoint) after an
  explicit instruction that every stage should be chainable by a future
  harness without a human deciding whether each may proceed; revised again
  to v1.2 in a later session, restoring a human gate as the **default**
  (file-review mode: passing candidates get a ready-to-apply file in
  `research/pending_merges/`, not a direct edit) with auto-merge preserved
  as an explicit, human-declared opt-in — reasoning: v1.1 removed the one
  check that would have caught a bad self-check before any real session had
  ever tested whether the self-check was trustworthy. Full detail in
  `Researcher_prompt.txt`'s own changelog and `RESEARCH_PROTOCOL.md`'s
  "Merge flow" section — those two files are the current source of truth
  for gate behaviour, not this paragraph.
- **MAP.md** — updated: new 🔭 Research track section, Pipeline/Investigator
  track descriptions amended, diagram and both tables updated per §7 below;
  later updated again to match v1.2's gate reversal.
- **Also shipped same day, not originally scoped as A–E:**
  `Explorer_prompt.txt` bumped to v2.4 — every structural kill (INFEASIBLE)
  now requires a `DATA_ENRICHMENT.md` write in Phase 3 (check for a
  matching Pattern first, add an Instance or write both), closing a gap
  where the write side was described in `MAP.md`/this doc but never
  actually instructed anywhere in the runtime prompt.

**Not done / explicitly deferred:** `EXPLORATION_PROTOCOL.md` Dimension 1
was updated to 6 domains (A–D, F, with E=Strength) as part of shipping A,
resolving one of the original open questions below. The other open
questions (§8) are still open — none blocked shipping, all are about how
the *next* session/corpus should use what's now built, not about whether
it works.

## 1. The goal, stated precisely

Not: a human (me, or Claude in an ad-hoc brainstorm) comes up with good
investigation ideas and feeds them in. The goal is that **running the
pipeline and investigator on any corpus — including one nobody has looked at
yet — is itself capable of discovering things like "this council has thirty
years of before/after traffic-speed measurements sitting unextracted, and
that's a testable question"**, without a human supplying the idea first. And
it should do this while minimising wasted LLM spend, in particular avoiding
repeated full re-extraction passes over a corpus that's already been
processed.

That second constraint is what shapes the whole design: discovery has to
happen **as early as possible in the pipeline** — before Level 2 extraction
commits — because anything discovered *after* extraction can only be acted
on by going back and re-extracting, which is exactly the cost we're trying
to avoid paying repeatedly.

## 2. What already exists (verified against the current repo, 2026-08-19)

| Piece | Where | What it does |
|---|---|---|
| Failure taxonomy | `investigator/Investigator_prompt.txt` Part 3 (lines 449–488) | Four genres — 3.1 financial failure, 3.2 governance/cultural dysfunction, 3.3 integrity/corruption, 3.4 process/transparency abuse. Each row: failure mode → real precedent (Northamptonshire, City of Perth, IBAC Operation Royston...) → data signature to hunt for. Drives what hypotheses Explorer even considers. |
| General precedent bank | `investigator/Investigator_prompt.txt` Part 5 | Static list of methodology sources (Nolan Principles, CIPFA/SOLACE, Briginshaw). Not case-study material, not growing, not what §4 below is proposing. |
| Investigator → Pipeline backlog | `pipeline/DATA_ENRICHMENT.md`, edge documented in `MAP.md`'s connection table | When an investigation is scored against `EXPLORATION_PROTOCOL.md`'s benchmark, gaps it hit get written here as a re-extraction backlog. **This is the write side of a compounding-knowledge loop, and it already exists.** Entries are currently phrased as this-corpus-specific instances (e.g. "officer recommendation captured on MINUTES motions", tied to Cambridge's `[24]`), not abstracted patterns. |
| Corpus setup / typology stage | `pipeline/PIPELINE.md` §Level 1→2, `scripts/inventory_typology.py`, CLI `council typology <council>` | Cheap, deterministic aggregation (no LLM call) over Level 1 inventories. Looped until `other_content_rate ≤ 20%`. Once converged, generates a schema-update prompt for Level 2 — currently informed only by the typology report + current schema. **Has no read-side connection to `DATA_ENRICHMENT.md` today.** |
| Self-improving prompt governance | `investigator/EXPLORATION_PROTOCOL.md` | Precedent for the governance pattern used below: a prompt self-scores against a benchmark, proposes its own next edit, a human approves before the version bumps. |

## 3. Four gaps, and why each blocks the stated goal

**Gap A — the taxonomy only knows how to hunt for misconduct.**
All four Part 3 genres are about a council doing something *wrong*
(financial mismanagement, dysfunction, corruption, opacity). "Did the
council follow through on a stated commitment, and did it actually achieve
the goal" is a different kind of question — not wrongdoing-hunting,
effectiveness-hunting. Real-world precedent for this exists as its own
discipline (government "value for money" / VFM audits; CIPFA/SOLACE's good
governance framework has a core principle about outcomes for citizens, not
just process integrity) but nothing in Part 3 currently points Explorer at
it. Because hypothesis generation is taxonomy-driven, **no hypothesis in
this genre can ever be formed**, so it can never hit a "we don't have this
data" wall, so it can never get written to `DATA_ENRICHMENT.md`. The gap is
upstream of everything else.

**Gap B — `DATA_ENRICHMENT.md` entries don't generalise across corpora.**
Existing entries are phrased as *this corpus's* gap ("meeting-unique
interest-declaration ↔ motion linkage", tied to Cambridge investigation IDs).
For a second council's typology stage to usefully consume this file, each
entry needs an abstracted layer above the Cambridge instance — e.g. pattern
= *"before/after measurement pairs tied to a discrete, dated intervention,
reported inconsistently in free text over decades"* — with Cambridge's
traffic-calming-shaped instance as one example of it. Without that split,
the file is corpus trivia, not transferable knowledge.

**Gap C — typology has no read side.**
Even once Gap B is fixed, nothing currently makes the typology stage look
at `DATA_ENRICHMENT.md` before generating its Level 2 schema-update prompt.
The write side (investigator → backlog) exists; the read side (backlog →
next corpus's schema design) doesn't.

**Gap D — genre growth is bottlenecked on this project's own corpus
experience.** Even with A–C fixed, the taxonomy only grows from what
Explorer happens to stumble into on the corpora it's actually run against.
Real-world council failures/audits/effectiveness reviews are a much larger
and faster-growing source of genre precedent than one project's own
investigation history will ever produce alone.

## 4. Proposed architecture — four components

### Component A — broaden Part 3 with an effectiveness/follow-through genre

Add **Part 3.5 — Policy/programme effectiveness** to
`Investigator_prompt.txt`, in the same row-format as 3.1–3.4: failure mode →
precedent → data signature. Its data signature is three co-occurring
things, not one field:
1. a **stated commitment** (a motion approving X with a declared goal),
2. an **implementation record** (was it done, on what timeline/cost),
3. an **outcome measurement** (was it checked afterward, does it show the
   goal was met).

This is deliberately a new *genre*, not a one-off hypothesis — the traffic-
calming idea would be one possible instance Explorer might independently
arrive at once this genre exists in its checklist, on any corpus that has
the right shape of data, without anyone having told it to look for traffic
calming specifically.

### Component B — restructure `DATA_ENRICHMENT.md` entries: pattern + instance

Each entry gains two layers:
- **Pattern** (council-agnostic): the abstracted signal shape and why it
  matters, phrased so it doesn't name Cambridge specifics.
- **Instance** (this corpus): the concrete example that surfaced it, with
  the existing Unblocks/Now/Want/Payoff/Effort fields, INVESTIGATIONS.md id.

A single pattern can accumulate instances across corpora over time — this
is the actual "wealth of knowledge" mechanism: not a bigger list of
Cambridge gaps, but fewer, richer, increasingly-confirmed patterns.

### Component C — wire typology's read side

The typology loop (`council typology <council>`, looped until
`other_content_rate ≤ 20%`) gains a step, run each pass alongside its
existing inventory-aggregation review: cross-reference the current corpus's
typology report against `DATA_ENRICHMENT.md`'s pattern layer (not the
Cambridge-specific instances). Where a pattern's signal shape matches
something the current corpus's "other_content" / rare-heading data
plausibly contains, that becomes a candidate for the Level 2 schema-update
prompt — spent **before** extraction commits, not after.

Cost note: this reuses the aggregation that typology already computes for
free (no new LLM calls for the matching step beyond what generates the
existing schema-update prompt) and runs once per corpus at setup time, not
as a recurring loop.

### Component D — Researcher role: growing the taxonomy from external precedent

A new, council-agnostic role — not run per-corpus, not run per-investigation
— that periodically surveys real AU/UK local-government failures, audits,
and effectiveness reviews and proposes **taxonomy additions** (new Part 3.x
genres, or precedent to sharpen an existing one). Governed the same way
`EXPLORATION_PROTOCOL.md` already governs `Explorer_prompt.txt`: the
Researcher proposes its own edit, a human approves before Part 3 is bumped.
Part 3.5 (Component A) is this role's *first* output in concept, but going
forward the Researcher is what keeps the taxonomy growing without relying
on this project's own corpora to happen to surface new genres.

Two design constraints, resolved below:
- **Defamation/accuracy firewall.** This role researches *precedent
  patterns* (genres of council failure), not claims about any specific
  council in this project's corpus. It must never inject unverified claims
  about Cambridge (or any council actually being investigated) into a
  finding — its output is taxonomy-level ("councils have been found to do
  X"), consumed the same way Part 5's existing precedent is: as a lens to
  look through, re-verified against this project's own data before
  anything publishes, never as a fact about this corpus.
- **Tooling difference.** Investigator is deliberately DB-only (Part 0
  scopes it to `data/council.db`) — that constraint is what keeps findings
  sourced and verifiable, and should not be diluted. The Researcher needs
  web search/fetch, which Investigator doesn't have and shouldn't gain.
  This has to be a separate role/prompt, not a mode bolted onto Explorer.

### Component E — the governance loop that turns Researcher output into Part 3

This was previously just "governed the same way as `EXPLORATION_PROTOCOL.md`"
— that's an analogy, not a design. Spelling it out properly, in the same
shape as the existing exploration/refinement loops:

**Intermediate artifact, not a direct diff.** Researcher output never
touches `Investigator_prompt.txt` directly. It lands in a new file —
`research/PRECEDENT_BANK.md` — as a **candidate genre entry**, in the same
row-format Part 3 already uses (failure/effectiveness mode → real precedent
→ data signature), tagged `status: candidate`. This mirrors how
`DATA_ENRICHMENT.md` sits between Investigator and Pipeline as a reviewable
buffer rather than a live edit target — the same pattern, applied one level
up (Research → Investigator's own taxonomy, instead of Investigator →
Pipeline's schema).

**Benchmark, in a new `research/RESEARCH_PROTOCOL.md`** (mirroring
`EXPLORATION_PROTOCOL.md`'s dimension table). A candidate genre must clear:
1. **Non-duplication** — doesn't restate an existing Part 3.x genre or a
   pattern already in `DATA_ENRICHMENT.md`.
2. **Grounded precedent** — cites a real, checkable case (an inquiry
   report, an audit, a news investigation with a named outlet/date), not a
   generic "this could happen."
3. **Data-signature translatability** — the precedent must translate into
   a concrete signature expressible in terms this project's schema
   vocabulary could plausibly hold (tables/fields/free-text patterns) —
   otherwise it's a genre Explorer could never act on regardless of corpus.
4. **Defamation safety** — genre-level only, no claims about any
   specific council currently in this project's scope.

**Approval flow.** A human reviews candidates in `PRECEDENT_BANK.md`
periodically (not gated to any corpus event). Approved candidates get
merged into `Investigator_prompt.txt` Part 3 as the next numbered
sub-section, with a version bump (matching how Explorer's own version
bumps are human-approved). Rejected candidates stay in
`PRECEDENT_BANK.md` with `status: rejected` and a one-line reason — the
same "honest null, logged not deleted" discipline `INVESTIGATIONS.md`
already uses — so the Researcher doesn't keep re-proposing the same idea.

## 5. How the loop compounds across corpora

- **Corpus 1 (Cambridge, current state):** schema was built from typology +
  human judgement alone; `DATA_ENRICHMENT.md` populated reactively,
  post-extraction; re-extraction likely needed if new patterns are wanted.
- **Corpus 2:** typology stage (Component C) now reads Corpus 1's abstracted
  patterns (Component B) at setup time, before Level 2 locks in — some of
  what would have needed a Corpus-1-style re-extraction is caught upfront
  instead. Corpus 2's own investigation adds new pattern instances (and,
  if the Researcher role has landed, benefits from whatever taxonomy
  growth happened independently of either corpus).
- **Corpus 3+:** typology reads an even richer pattern set (more corpora
  behind it, more confirmed instances per pattern, more taxonomy genres
  from the Researcher), so a larger share of what would have been discovered
  reactively is instead caught at setup — the reactive
  `DATA_ENRICHMENT.md`-triggers-re-extraction path should see diminishing
  use as prior-corpus knowledge and external precedent both compound.

## 6. Suggested build order (not committed)

The three non-Researcher components are extensions of loops that already
exist; the Researcher (D) and its governance loop (E) are genuinely new
infrastructure (new role, new tooling, new protocol doc). Rough dependency
order:

1. **A** (Part 3.5 genre) — smallest, unblocks nothing else but is a
   direct prompt edit, easy to validate against the existing benchmark
   discipline in `EXPLORATION_PROTOCOL.md`.
2. **B** (pattern/instance split in `DATA_ENRICHMENT.md`) — restructuring
   an existing file, no new mechanism.
3. **C** (typology read side) — depends on B existing in the new shape.
4. **E** (`RESEARCH_PROTOCOL.md` + `PRECEDENT_BANK.md` scaffolding,
   benchmark defined) — can be designed before D exists, the same way
   `EXPLORATION_PROTOCOL.md` predates a compliant `Explorer_prompt.txt`
   session.
5. **D** (Researcher role / `Researcher_prompt.txt`) — last, since it's
   the piece E is built to gate, and the defamation-firewall behaviour
   needs E's benchmark to already exist so it can be scored against it
   from the first run.

## 7. Target-state system map — what `MAP.md` becomes

**Applied 2026-08-20.** This section was the plan; `MAP.md` now reflects it.
Kept here as the design record of what changed and why.

### 7.1 New track: 🔭 Research — *council-agnostic, not corpus-gated*

Grows the investigator's taxonomy from real-world precedent. Unlike the
other four tracks, it has no per-corpus state — it runs on its own cadence,
independent of which councils are in the pipeline.

- `research/Researcher_prompt.txt` — **runtime artifact** (like Explorer/
  Refiner/Runner): surveys real AU/UK local-government failures, audits,
  and effectiveness reviews; proposes candidate genres into
  `PRECEDENT_BANK.md`. Deliberately web-capable (search/fetch) — the one
  role in the system that isn't DB-only, which is exactly why its output
  never lands directly in a finding.
- `research/RESEARCH_PROTOCOL.md` — benchmark-gated governance for
  `Researcher_prompt.txt`, mirroring `EXPLORATION_PROTOCOL.md`'s shape:
  dimensions (non-duplication, grounded precedent, data-signature
  translatability, defamation safety), calibration log, freeze condition.
- `research/PRECEDENT_BANK.md` — the growing artifact itself: candidate
  genre entries (`status: candidate` / `approved` / `rejected`), each in
  Part-3 row format. Approved entries get merged into
  `Investigator_prompt.txt` Part 3 by a human, with a version bump;
  rejected ones stay logged so they aren't re-proposed.

**Loop:** run Researcher → append candidates to `PRECEDENT_BANK.md` →
score against `RESEARCH_PROTOCOL.md` → human approves or rejects → approved
candidates merged into `Investigator_prompt.txt` Part 3, version bumped.

### 7.2 Modified tracks

- **Pipeline** — `DATA_ENRICHMENT.md`'s description changes from "backlog,
  consumed *if/when* a re-extraction is decided" to "pattern/instance
  backlog: **written** by Investigator (unchanged), **read** by the
  typology stage on every new corpus, before Level 2 schema locks in."
  `PIPELINE.md`'s typology section gains the Component-C cross-reference
  step in its Level 1→2 description.
- **Investigator** — `Investigator_prompt.txt` Part 3 gains 3.5+ over time
  (starting with the effectiveness/follow-through genre), sourced from
  either this project's own corpus experience (as today) or, now, from
  the Research track's approved candidates.

### 7.3 Updated connection diagram

```
                         ┌─────────────────────────────────────────────┐
                         │  STRATEGY (PRIVATE_ASSESSMENT.md)            │
                         │  reads everything → sets priorities          │
                         └───────▲─────────────▲──────────────▲────────┘
                                 │             │              │
   ┌───────────────┐   DB + schema    ┌────────────────┐  findings   ┌──────────────┐
   │   PIPELINE    │ ───────────────► │  INVESTIGATOR  │ ──────────► │   FRONTEND   │
   │  PIPELINE.md  │  (substrate +    │ Investigator_  │  become     │INTERACTIVITY │
   │               │   caveats feed   │ prompt.txt +   │  panels     │PRODUCT_ROAD- │
   │  DATA_ENRICH- │   prompt Part 0) │ INVESTIGATIONS │             │MAP.md        │
   │  MENT.md  ◄───┼──────────────────┤ + PROTOCOL +   │             └──────┬───────┘
   │  (pattern/    │  write: enrichment│ FINDINGS_SUMM. │                    │
   │  instance,    │  backlog (as now) └───────┬────────┘   council publish  │
   │  read at      │                            │            (pipeline cmd)   │
   │  typology,    │  NEW: typology reads        │ protocol governs            │
   │  NEW)         │  pattern layer (§C)         │ prompt iteration            │
   └──────┬────────┘                             │                            │
          │                                      │                            │
          │  council publish exports             │                            │
          └────────── snapshots ─────────────────┴─────────────► snapshots ───┘

                         ┌─────────────────────────────────────────────┐
                         │  RESEARCH (NEW — council-agnostic)           │
                         │  Researcher_prompt.txt → PRECEDENT_BANK.md   │
                         │  → scored vs RESEARCH_PROTOCOL.md            │
                         │  → human-approved merge into Part 3   ───────┼──► Investigator_prompt.txt
                         └─────────────────────────────────────────────┘      Part 3 (taxonomy)
```

### 7.4 Updated edges table (new/changed rows only)

| Edge | Direction | What flows |
|---|---|---|
| **Investigator → Pipeline** (`DATA_ENRICHMENT.md`) — *changed* | backlog | Unchanged write side. Entries now carry a pattern layer (council-agnostic) above the existing instance layer. |
| **Pipeline (`DATA_ENRICHMENT.md`) → Pipeline (typology stage)** — *new* | self-loop, read | On every new corpus, the typology convergence loop cross-references its aggregation against `DATA_ENRICHMENT.md`'s pattern layer before generating the Level 2 schema-update prompt. No new LLM calls — reuses the existing aggregation. |
| **Research → Investigator** (`PRECEDENT_BANK.md` → Part 3) — *new* | taxonomy growth | Approved candidate genres are merged into `Investigator_prompt.txt` Part 3 by a human, version bumped. Council-agnostic — benefits every corpus's investigation, not just the one that triggered it (there usually isn't one). |
| **RESEARCH_PROTOCOL.md → Researcher_prompt.txt** — *new* | governance | Same shape as `EXPLORATION_PROTOCOL.md → Explorer_prompt.txt`: benchmark-gated, human-approved version bumps. |

### 7.5 Updated "Where do I add X" table (new rows only)

| If you're… | Go to |
|---|---|
| noting a reusable **cross-corpus** pattern (not just this corpus's gap) | `pipeline/DATA_ENRICHMENT.md` — pattern layer, above the instance |
| proposing a new failure/effectiveness genre from real-world precedent | `research/Researcher_prompt.txt` (run) → `research/PRECEDENT_BANK.md` (record) → human-approved merge into `Investigator_prompt.txt` Part 3 |
| improving the researcher prompt | `research/RESEARCH_PROTOCOL.md` (benchmark) → bump `Researcher_prompt.txt` |
| running/improving the typology stage's schema-gap cross-reference | `pipeline/PIPELINE.md` (Level 1→2 section) |

## 8. Open questions

- Does Component A's genre also need updating in `EXPLORATION_PROTOCOL.md`'s
  benchmark dimensions (e.g. does "domain breadth 5/5" become "6/6")?
- Per the existing second-council-prep note (generalise Cambridge-specific
  assumptions before a second council), does Component B's restructuring
  effort fold into that work, or precede it?
- How often should the Research track actually run in practice — before
  onboarding each new council (front-loaded), on its own periodic cadence,
  or purely on-demand? It doesn't need the "per new corpus" trigger the
  other components have, but it still needs *some* trigger.
- Does `PRECEDENT_BANK.md` need per-genre calibration data the way
  `EXPLORATION_PROTOCOL.md` tracks Cambridge scores, or is a simpler
  candidate/approved/rejected log sufficient since it's not scored against
  a specific corpus?
