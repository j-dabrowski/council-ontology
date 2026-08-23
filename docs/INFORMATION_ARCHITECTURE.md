# Information Architecture — the instrument, redesigned top-down

**What this is.** The second design artefact of the 2026-08-23 redesign
effort (the first: `investigator/COVERAGE_AUDIT_2026-08-23.md`). It designs
the flow of information from raw source documents to each output audience —
the stages, the representation at each stage, and where individual-level and
institution-level claims structurally diverge. It deliberately says nothing
about which stages are LLM agents: that is the third document (agent design),
which must be derived from this one, not the reverse. Nothing here is built.

**Status:** accepted 2026-08-23; referenced from `docs/MAP.md`. Design
only — implementation follows `AGENT_DESIGN.md` §6's build order.

---

## 1. Design constraints (each traceable to evidence)

| # | Constraint | Source |
|---|-----------|--------|
| C1 | Every claim carries its **unit of analysis** from birth; the individual/institutional split is enforced by which data product a claim can enter, never by per-component rendering discipline | Editor pass 1 flags 4, 5, 6 — all failures of hand-enforced UI gating; the 2026-08-06 hardcoded-names incident is the same class |
| C2 | Deterministic invariants (small-n, entity-resolution status, name-free schemas) are checked by a **scripted gate before any LLM review**; the semantic reviewer only sees drafts that already pass them | 5 of 7 Editor pass-1 blocking flags were mechanically checkable (small-n: 1, 3, 6; gating: 4, 5, 6; identity: 7) |
| C3 | A corpus is a **set of document classes** per institution, not one class | Coverage audit F3 — financial-sustainability rows are empty because minutes structurally lack them; annual statements / external audit results are different classes of the same institution |
| C4 | **Discovery and confirmation are separated by corpus role**: hypotheses are discovered on training corpora; the frozen, pre-registered battery is confirmed on corpora it never trained on | Multiple-comparisons exposure of explore-then-codify-then-run on one corpus; coverage audit R5 |
| C5 | Named individuals get **right of reply before publication** of any claim about them | Standard journalism verification practice; flag 2 (the mis-singled-out stay-and-vote superlative) would have died at this stage in one email |
| C6 | The **general engine / domain pack** boundary is explicit: every stage below is domain-agnostic; everything council-specific lives in a named pack | The redesign's founding principle; second-council prep rule |
| C7 | Cumulative coverage is a **standing register** consulted at hypothesis-generation time and updated at codification time | Coverage audit F1/R1 — survivorship lives in the taxonomy→battery gap, invisible to per-session breadth checks |
| C8 | Every claim in every tier retains **drill-down to source evidence**; declared blind spots are published as scope boundaries | Existing project hard rule (nothing unsourced); coverage audit R2 |

---

## 2. The two layers: engine and pack

```
┌───────────────────────────── DOMAIN PACK ("council") ─────────────────────────────┐
│ entity schema (councillor, motion, vote, tender, DA…)     document-class list     │
│ extraction prompts per class          criteria frameworks (Nolan, CIPFA, WA Act)  │
│ failure/strength taxonomy (Part 3)    hypothesis seeds     legal thresholds       │
│ domain vocabulary for rendering       precedent bank       reply-recipient rules  │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │ configures every stage; owns no stage
┌───────────────────────────────────────▼───────────────────────────────────────────┐
│ GENERAL ENGINE — the stages in §3, all schema-parameterised:                      │
│ acquisition · extraction · profiling · discovery · codification · confirmation    │
│ · claim assembly · invariant gate · semantic review · right of reply · rendering  │
│ plus the cross-stage stores: evidence ledger, claim store, coverage register      │
└───────────────────────────────────────────────────────────────────────────────────┘
```

The test of the boundary: onboarding a hospital board or a planning tribunal
should mean writing a new pack (schema, classes, taxonomy, seeds, criteria)
and **zero engine changes**. The pack is data + prompts, never flow logic.
(Design-review lens only for now — per the redesign discussion, the
abstraction is validated by paper-porting, not built speculatively before
institution #2 exists.)

---

## 3. The flow

```
            DOCUMENT CLASSES (C3)                      ┌──────────────────┐
   minutes ── agendas ── annual statements ── external │  Coverage        │
      │          │        audits (OAG) ── registers    │  Register (C7)   │
      ▼          ▼            ▼               ▼        │  16 dimensions × │
 ┌─────────────────────────────────────────────────┐   │  status; scope   │
 │ S1 EXTRACTION  (per class, pack prompts)        │   │  boundaries      │
 │   → typed records + EVIDENCE LEDGER (quotes)    │   └───▲──────────┬───┘
 └───────────────────────┬─────────────────────────┘       │ update   │ seed
 ┌───────────────────────▼─────────────────────────┐       │          ▼
 │ S2 CORPUS PROFILE                               │   ┌──────────────────┐
 │   NULL rates, spans, identity-resolution state, │   │ S3 DISCOVERY     │
 │   record-quality metrics (a publishable claim   │──►│  hypothesis gen  │
 │   input, not just an internal caveat)           │   │  + testing on    │
 └─────────────────────────────────────────────────┘   │  TRAINING corpora│
                                                       │  only (C4)       │
        ┌───────────────────────────────────┐          └────────┬─────────┘
        │ S5 CONFIRMATION (C4)              │                   │ validated
        │  frozen battery, pre-registered,  │          ┌────────▼─────────┐
        │  runs on corpora it never trained │◄─────────│ S4 CODIFICATION  │
        │  on → confirmation_status upgrade │  freeze  │  finding → claim │
        └───────────────┬───────────────────┘          │  GENERATOR (test)│
                        │                              │  declares unit,  │
 ┌──────────────────────▼──────────────────────────┐   │  n-rules, ladder │
 │ S6 CLAIM ASSEMBLY (battery run = `draft`)       │   └──────────────────┘
 │   generators × corpus → CLAIM OBJECTS (§4)      │
 │   every claim: unit, n, evidence refs, ladder   │
 └──────────────────────┬──────────────────────────┘
 ┌──────────────────────▼──────────────────────────┐
 │ S7 INVARIANT GATE (C2 — scripted, no LLM)       │──✗ blocks draft; fix
 │   MIN_N · name-free institutional schema ·      │    upstream, re-draft
 │   identity-resolution clean bill · superlative  │
 │   tie/denominator checks · tier derivation      │
 └──────────────────────┬──────────────────────────┘
 ┌──────────────────────▼──────────────────────────┐
 │ S8 SEMANTIC REVIEW (LLM — narrowed scope)       │──✗ flags → fix loop
 │   overclaim language · innocent explanations ·  │    (Conductor cap
 │   singling-out fairness · blended statistics    │     unchanged)
 └──────────────────────┬──────────────────────────┘
                        │ PASS splits by tier (C1):
        ┌───────────────┴───────────────────┐
        ▼                                   ▼
 INSTITUTIONAL PRODUCT               DEEP PRODUCT
 (unit=institutional only,           (all claims incl. individual,
  schema provably name-free)          full evidence + methodology)
        │                                   │
        │                     ┌─────────────▼──────────────┐
        │                     │ S9 RIGHT OF REPLY (C5)     │
        │                     │  per named person: packet  │
        │                     │  of claims-about-them →    │
        │                     │  sent; window; responses   │
        │                     │  attach to the claims      │
        │                     └─────────────┬──────────────┘
        ▼                                   ▼
 ┌────────────────────── S10 RENDERINGS (per audience) ─────────────────────┐
 │ institutional product → public site + plain-language summary (residents) │
 │ deep product          → deep report / deep dashboard (auditors, media)   │
 │ reply packets + scorecard → the council itself                           │
 └──────────────────────────────────────────────────────────────────────────┘
```

(S0, acquisition/scraping, precedes S1 and is unchanged; omitted for space.)

**Representation at each boundary:**

| Stage | Output representation |
|-------|----------------------|
| S1 | typed records (pack schema) + evidence ledger rows (verbatim quotes, doc/page refs) |
| S2 | corpus profile: one machine-readable document (NULL rates, spans, identity state, quality metrics) |
| S3 | hypothesis entries (INVESTIGATIONS-style: question, method, result, disposition) |
| S4 | claim **generators** — registered, parameterised test code + a declaration block (unit, MIN_N, strength ceiling, valence logic, principle tags) |
| S5 | pre-registration file (frozen generator list + decision rules, committed **before** first run on a confirmation corpus) + confirmation results |
| S6 | claim objects (§4), one store per draft run |
| S7/S8 | the same claims, annotated: gate results, review flags, resolutions |
| S9 | reply packets (per person) + attached responses |
| S10 | tier products (JSON snapshots, split by tier) + rendered surfaces |

---

## 4. The claim object

The single representation that flows from S6 to every output. Extends the
existing `TestResult` dataclass (`src/analysis/tests.py`) — fields marked ●
already exist there in some form.

```
claim:
  claim_id                                # stable: generator id + corpus + period
  generator: test_id ●                    # which registered generator produced it
  institution / corpus_run                # which corpus, which draft run
  document_classes: [minutes, ...]        # what it drew on (C3)

  unit_of_analysis:                       # C1 — the field everything gates on
    institutional                         #   no person recoverable
    | individual_implicating              #   aggregate by construction, but persons
                                          #   enumerable/inferable (per-person charts,
                                          #   small-N cells) — flag-6 class
    | individual                          #   claims about named persons
  named_entities: []                      # empty iff institutional
  entity_resolution: clean | open-splits  # flag-7 class; individual claims require clean

  statistic: value, n ●, denominator,     # n mandatory for any rate; flag-1/3 class
             baseline, period, era ●
  strength: descriptive | comparative |   # the language ladder; caps the words any
    superlative | associative |           # rendering may use — "bloc/coordinated" needs
    causal-implying                       # ≥ associative + explicit support (flag-4 class)
  superlative_check:                      # required iff strength=superlative:
    ties, shared_cause, lawful_exception  # flag-2 class (the singling-out guard)

  valence ● · grade ● · principle ● · genre ●
  confirmation_status:                    # C4
    discovered | confirmed_out_of_sample
  evidence: [ledger refs + quotes] ●      # C8 — drill-down source
  caveats: []
  review: gate results, editor flags, resolutions
  reply: sent_at | response | declined    # individual claims only (C5)
```

**Tier derivation is a pure function of the claim, never an authorial
choice:** institutional product ⇐ `unit=institutional` only;
deep product ⇐ all units, `individual` requiring `entity_resolution=clean`
and a completed reply step; `individual_implicating` claims enter the deep
product whole but may enter the institutional product only in a reduced form
that provably drops the person-level payload (e.g. the distribution without
the per-person bars). This lands on the existing `public`/`full` snapshot
tier mechanism in `src/cli.py` — same rail, but the tag becomes derived
from claim fields instead of hand-assigned per snapshot file.

---

## 5. Audiences

| Audience | Product | Form | Verification standard |
|----------|---------|------|----------------------|
| Residents (laymen) | institutional | plain-language summary + public site | inherits the institutional product's — simplification is safe because the input contains no persons (C1); a simplifier cannot create a claim about a person from person-free input |
| Media / journalists | deep | deep report + deep dashboard, full evidence, methodology, reply responses shown | Briginshaw-graded, per existing Part 4 |
| Professional auditors / watchdogs | deep | same product + reproducibility (generator code, pre-registration file, corpus profile) | full chain of custody: claim → generator → records → evidence ledger → source page |
| The council itself | reply packets (pre-publication) + its scorecard | per-person claim packets; institution-level scorecard | reply window before deep-product publication; responses attach to claims and ship with them |

Build order matches the redesign discussion: deep product is assembled
first (it is the superset); institutional product is a filtered projection
of it; the layman rendering is a transformation of the institutional
product only. Complexity flows downhill; risk cannot, because the person
data is absent from the input by then.

---

## 6. Corpus roles (discovery vs confirmation, C4)

```
corpus manifest:  institution · document classes · role
                                                    │
        role: TRAINING ──────────► S3 may mine it; findings feed S4
        role: CONFIRMATION ──────► S3 forbidden; only the frozen,
                                   pre-registered battery (S5) runs
```

Cambridge is the founding training corpus. Council #2 onboards as
CONFIRMATION first: the frozen battery runs, `confirmation_status` upgrades
(or refutes) each generator, and only *after* that pre-registered run may
the corpus be re-roled TRAINING for new discovery. Refutations are published
with the same honesty as nulls. A claim's confirmation status is visible in
every rendering — "observed in 1 institution" vs "confirmed in N" — which
also becomes the honest cross-council comparison the battery was always
meant to enable.

---

## 7. What maps where (delta from the current system)

| Current | In this architecture |
|---------|---------------------|
| `council draft` (queries + battery → mixed snapshots) | S6 claim assembly; output becomes claim objects grouped into tier products, not mixed-tier JSON |
| snapshot `public`/`full` tags in `cli.py` (all defaulting full, hand-assigned) | kept as the serving rail; tag derived from claim `unit_of_analysis` (§4), so "nothing tagged public yet" resolves structurally |
| `Reveal`/drill-down gates as the individual/institutional boundary in JSX | demoted to UX affordance inside the deep surfaces; the boundary itself moves to S7 + product schemas (C1) |
| Editor (defamation review, catching small-n, gating, identity, language, singling-out) | split: S7 takes the mechanical checks (small-n, gating schema, identity, name-free institutional product); S8 keeps only the semantic ones (language ladder, innocent explanations, singling-out, blended stats) |
| Fixer (frontend/pipeline/doc modes) + Conductor loop | unchanged in shape; operates on S8 flags only — S7 failures block the draft mechanically and route straight to the owning track without a review chain |
| component-source name grep before deploys | retained as defence-in-depth for the public surface (S7 proves the data name-free; the grep proves the code adds none back) |
| `Investigator_prompt.txt` Part 0 caveats / §0.4 identity splits | S2 corpus profile — machine-readable, consumed by S3 (feasibility), S7 (clean-bill checks), and publishable as the records-quality finding (coverage audit F4) |
| Dimension 1 per-session domain breadth | replaced by the coverage register (C7): sessions are scored on reducing the register's worst gap |
| `DATA_ENRICHMENT.md` pattern/instance layers | unchanged; gains the document-class pattern entries from coverage audit R3 |
| Cambridge-specific prompt content | the first domain pack's content (§2), extracted rather than rewritten |

## 8. Open questions carried to the agent-design document

1. Which stages need an LLM at all? Candidate answer to argue there: S1
   (extraction — already LLM), S3 (discovery), S8 (semantic review), the
   layman simplifier and reply-packet drafting in S9/S10 — with S2, S5, S6,
   S7, and tier derivation fully scripted. S4 is the interesting boundary
   case (code generation with declaration blocks — LLM-drafted,
   benchmark-gated as now).
2. Does Explorer/Refiner/Runner survive as named modes, or become S3 / S4 /
   (S5+S6)? What of their protocols transfers to stage contracts?
3. Where does the Conductor's authority end once S7 exists — does it own the
   whole S6→S9 chain, or only the S8 flag loop?
4. Right-of-reply operational design: send mechanism, window length,
   non-response handling, and how a response that *refutes* a claim
   re-enters the flow (re-draft? annotation?).
5. Whether the coverage register is a doc, a table in the DB, or generated
   from generator declarations — and which stage owns updating it.
