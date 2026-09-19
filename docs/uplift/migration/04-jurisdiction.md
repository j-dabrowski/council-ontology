# Jurisdiction: WA Legal Framework — Migration Plan

Traces the target WA statutory framework in `docs/uplift/04-jurisdiction.md`
against current code. Depends on `02-claim-layer.md` (`framework_refs` must
be config-resolvable — that file's G-07/Step 1 define the field this
category populates).

**A more nuanced starting point than "WA law is absent."** Two findings
from this session change the shape of this problem. First, the data model
already correctly distinguishes must-leave from stay-and-vote-lawful
interests at the schema level: `InterestDeclaration.interest_type`
(`src/models/ontology.py:398`) is a real enum column, and
`queries.py:1873`'s `must_leave = row.interest_type in {"financial",
"proximity"}` already implements the exact legal distinction s5.65/reg 34C
draws. Second, a working detector for the *sibling* provision to s5.68
already exists — `_ministerial_approved()` (`queries.py:3429-3438`) catches
s5.69 Ministerial-approval citations via substring match, built after this
exact failure class (lawful conduct mislabelled as non-compliance, on named
individuals) was caught once in production. So this isn't a green field:
the legal *awareness* exists in the computation layer in two places
already; what's missing is (a) the citation/label layer pointing at UK
frameworks instead, (b) the s5.68 detector s5.69's sibling doesn't have,
and (c) any structured corpus for a jurisdiction critic to retrieve
against.

---

## Current state inventory

| Target capability | Current equivalent | Path | Status | Notes |
|---|---|---|---|---|
| Jurisdiction config: `framework_refs` as structured `{instrument, section}` data | Three independent hardcoded string-literal copies of Nolan/CIPFA labels | `config/test_registry.json` (`principles` array), `src/analysis/tests.py` (`principle=` field, dozens of call sites), `frontend/src/components/OverviewPanel.tsx:38-80` | WRONG | Already fully traced in `01-known-defects.md` G-28; restated here as the field this config would replace |
| Primary WA instruments table (LGA_1995, ADMIN_REGS, FG_REGS, CONDUCT_REGS, MODEL_CODE_2021, DLGSC, SAT) | No structured instrument registry anywhere; WA statutory awareness exists only as prose inside two places: `system_prompt.txt:233` (cites LGA 1995 s5.65 for `interest_type` classification) and a code comment at `queries.py:3429-3438` (cites s5.69) | `src/extraction/system_prompt.txt`, `src/analysis/queries.py` | MISSING (as structured config); PARTIAL (as uncited prose awareness) | Two of seven instruments have any representation at all, and both are uncited comments, not resolvable config |
| Nolan/CIPFA demoted to optional secondary mapping, not deleted | Currently primary and exclusive — no secondary/subordinate rendering concept exists | — | WRONG | Demotion, not deletion, is the target — a simpler change than a full removal |
| Statute corpus for C-03 (chunked, versioned, point-in-time, provenance-shaped) | No legal or guidance text corpus exists anywhere in the repo — confirmed by exhaustive grep for "statute", "legislation.org.au", "austlii", "Model Code of Conduct 2021", "Conduct Regulations 2007"; only near-hit is a passing unrelated phrase in `docs/pipeline/DATA_ENRICHMENT.md:146` | — | MISSING | Net-new corpus-building work; nothing to migrate from |
| s5.68 detection (any current extraction captures permitted-participation resolutions) | Zero hits anywhere for "5.68" across `src/extraction/schemas.py`, both system prompts, `src/analysis/queries.py` | — | MISSING | Confirmed by exhaustive grep, restated from `01-known-defects.md` G-29 |
| `declaration_fact.s5_68_permission_granted` / `s5_68_resolution_span` | No `declaration_fact` gold table exists yet (`02-claim-layer.md` G-10); `interest_declarations` (the closest raw table) has no such columns | `src/models/ontology.py` | MISSING | Blocked on `02-claim-layer.md`'s gold-table work existing first, or addable directly to `interest_declarations` as an interim, additive column |
| Census sweep over every must-leave declaration asking about a s5.68 resolution | The sibling mechanism (`_ministerial_approved()`, substring match on quote text for "5.69") is real and already runs over the full corpus, not a sample — a working template for exactly this sweep, one provision over | `src/analysis/queries.py:3429-3438` | PARTIAL (as a template); MISSING (for s5.68 itself) | Mechanically the smallest lift in this whole file: the pattern is proven, just needs a second string and its own field |
| Named-recusal claims blocked by the linter until the sweep completes | No linter exists yet (`02-claim-layer.md`); today's closest control is the S7 gate's blanket MIN_N/entity-resolution check, which doesn't know about s5.68 specifically | `src/invariant_gate.py` | MISSING (specific check); PARTIAL (a general named-claim gate exists to attach the specific rule to) | — |
| Interest-type-aware must-leave/impartiality distinction | **Already correctly modelled**: `InterestDeclaration.interest_type` is a real enum with financial/impartiality/proximity/other categories (`system_prompt.txt:233`'s extraction instruction, `ontology.py:398`'s column); `queries.py:1873`'s `must_leave = interest_type in {"financial","proximity"}` already implements the legal line | `src/models/ontology.py`, `src/analysis/queries.py` | ALIGNED (data model); WRONG (presentation — see below) | The schema already has what `04-jurisdiction.md`'s "Impartiality interests" section asks for; the defect (D-23, `01-known-defects.md` G-23) is that a correctly-computed impartiality figure is still rendered inside the same panel as a must-leave-driven grade with no separation |
| "Must-leave and impartiality never share a denominator in a graded claim" as a linter rule | No linter exists; today nothing prevents (and nothing currently does) blend the two into one denominator — the schema-level separation exists but isn't *enforced* as a rule anything could check | — | PARTIAL | Once `interest_type` is part of a declared grain (already true today, informally), this is a cheap linter rule to write |
| Delegate declarations (reg 34C basis for "correctly") | `_t_delegate_body_conflict`'s "correctly" claim has no citation anywhere (`01-known-defects.md` G-30) | `src/analysis/tests.py` | MISSING | — |
| Officer recommendations graded by SAT precedent, not a fixed default | `officer_divergence()`'s valence is one hardcoded direction (near-total ratification is always CRITICAL) applied to every item category uniformly, planning included, with no jurisdiction-critic input at all (`01-known-defects.md` G-25) | `src/analysis/divergence.py`, `src/analysis/tests.py` | WRONG | The target explicitly says this should be "derived from the jurisdiction critic's finding, not assumed" — that critic doesn't exist (`03-critic-agents.md` G-03) |
| Unminuted briefing forums as a corpus-level method-section limitation | Zero mentions anywhere in `Investigator_prompt.txt`/`pipeline/PIPELINE.md`, despite the pipeline already recognising "Briefing Forum" as a document type (`01-known-defects.md` G-26) | `docs/investigator/Investigator_prompt.txt` | MISSING | — |
| Era boundaries (2007 Conduct Regs, 2021 Model Code, 2020 COVID, 2018–2021 Inquiry) each defined once, not repeated | `config/council_eras.json` defines exactly one window (the Inquiry, 2018–2021, per-council) — confirmed by reading the file directly; the other three era boundaries (2007, 2021 Model Code, 2020 COVID) have **zero** representation anywhere in `src/` or `config/` | `config/council_eras.json`, `src/council_eras.py` | PARTIAL | One of four boundaries is config-driven at all; the mechanism (a config file + loader) already exists and is a direct template for adding the other three |
| Comparator councils (difference-in-differences against the Inquiry) | Architecturally single-council: every `council_id`-typed query function in `queries.py` (35 of them) takes exactly one council id; Perth is registered but not yet extracted (`01-known-defects.md` G-21) | `src/analysis/queries.py`, pipeline track | MISSING | Explicitly scoped by the target itself as a corpus-expansion workstream sequenced against `06` (pipeline), not started ad hoc here |

---

## Gaps

### G-01: Framework identity is prose in three places, not resolvable config
Target: `framework_refs` resolves against a jurisdiction config naming the seven WA instruments; Nolan/CIPFA rendered as a subordinate secondary mapping.
Current: three independent hardcoded Nolan/CIPFA copies (`01-known-defects.md` G-28); zero structured representation of any WA instrument.
Delta: this is both a data-migration task (extract the three hardcoded copies into one source) and a net-new-content task (write the WA instrument table, since nothing to migrate from exists for it).
Risk if unfixed: every `principle=` field continues to assert a framework this council isn't assessed against, and `02-claim-layer.md`'s `framework_refs` field (once built) has nothing real to resolve against.

### G-02: No statute corpus exists for retrieval
Target: full text of the seven instruments, chunked by section, point-in-time versioned across the 1995–2026 corpus window, plus DLGSC guidance and SAT precedent, tagged by role (binding/interpretive/precedent).
Current: confirmed absent in its entirety.
Delta: net-new content-acquisition work — this is the single largest lift in this file, comparable in scope to standing up a small internal legal-research database.
Risk if unfixed: `03-critic-agents.md`'s C-03 jurisdiction critic cannot be built at all — the target is explicit that this critic "cannot work from general knowledge" and must be retrieval, not a prompt with legal instructions.

### G-03: s5.68 has no detector; its sibling s5.69 proves the pattern works
Target: every must-leave declaration is swept for a s5.68 permitted-participation resolution; named recusal claims blocked until the sweep completes.
Current: `_ministerial_approved()` does exactly this mechanism for s5.69 today, corpus-wide, not sampled — restated from `01-known-defects.md` G-29, emphasised here as the concrete template to copy.
Delta: mechanically small (a second substring pattern, a second field) but with one open design question the source doc itself flags: confirming an actual *council resolution* occurred (a formal act) versus a citation merely appearing in someone's free-text remarks may need more than substring matching on quote text — s5.69's Ministerial-approval citations are presumably less ambiguous in how they're minuted than a council's own procedural resolution would be. This needs a human decision on evidentiary standard before the mechanism is copied blindly.
Risk if unfixed: per the source doc, the single highest-priority item in the whole plan — proven to be a live failure mode for the sibling provision, unaddressed for this one.

### G-04: Impartiality/must-leave distinction is correctly modelled but not enforced as a presentation rule
Target: must-leave and impartiality never share a denominator in a graded claim, enforceable once `interest_type` is part of the declared grain.
Current: the data model already gets this right (`must_leave = interest_type in {"financial","proximity"}`); the defect is presentational — a correctly-separated impartiality figure (0% recusal on 225 post-2022 impartiality declarations) still renders inside the same panel as a CRITICAL grade driven by must-leave data alone (`01-known-defects.md` G-23).
Delta: this is the cheapest gap in the file to close — the hard part (correct data modelling) is already done; only a linter rule and a rendering fix remain.
Risk if unfixed: a reasonable reader continues to infer that lawful stay-and-vote conduct contributed to an adjacent Critical grade.

### G-05: Delegate-declaration and officer-recommendation grading directions asserted, not derived
Target: both directions come from a jurisdiction critic's finding (reg 34C basis; SAT precedent on planning overrides), not a hardcoded default.
Current: `_t_delegate_body_conflict`'s "correctly" has no citation; `officer_divergence()`'s CRITICAL-on-high-ratification direction is one fixed rule for every item category.
Delta: both are unresolved normative questions dressed as settled code today — restated from `01-known-defects.md` G-25/G-30, flagged here as specifically requiring the jurisdiction critic's judgment once G-02's corpus exists, not a code fix in isolation.
Risk if unfixed: two claims continue to assert legal conclusions with no basis, one of them (officer-recommendation) on the panel the source doc calls one of its most attackable.

### G-06: Unminuted briefing forums uncaveated despite the pipeline already modelling them
Target: a standing method-section and per-claim caveat that substantial deliberation may occur off-record.
Current: MISSING, restated from `01-known-defects.md` G-26 — the pipeline recognises "Briefing Forum" as a document type but the caveat about the ones with *no* record at all was never written.
Delta: pure prose addition to `Investigator_prompt.txt`; no code change.
Risk if unfixed: per the source doc, the single largest structural gap in the report.

### G-07: Only one of four relevant era boundaries is config-driven
Target: the Inquiry window, the 2007 Conduct Regs, the 2021 Model Code, and the 2020 COVID/remote-meeting period are each defined once, in config, and available to any analysis that needs them.
Current: `config/council_eras.json` + `src/council_eras.py` already do exactly this for the Inquiry window alone — a real, working, per-council config mechanism with a loader, confirmed to have already replaced a formerly-hardcoded version of itself once (per that module's own docstring).
Delta: the mechanism doesn't need inventing, only extending — add three more keys to the same config shape.
Risk if unfixed: any future analysis touching the 2007/2021/2020 boundaries will hardcode them independently, exactly as the Inquiry window itself used to be hardcoded before `council_eras.json` existed — a recurrence of a problem already solved once for a different boundary.

### G-08: Inquiry-window analyses have no comparator, architecturally
Target: at least two neighbouring councils, converting DIRECTIONAL findings into defensible difference-in-differences results.
Current: architecturally single-council (`01-known-defects.md` G-21); explicitly out of scope for ad hoc work per the source doc's own sequencing instruction (belongs with the pipeline track's corpus-expansion work).
Delta: none proposed here — tracked as blocked, consistent with the source doc's own framing.
Risk if unfixed: unchanged from `01-known-defects.md` G-21's own risk statement.

---

## Implementation steps

### Step 1: Extract the three hardcoded Nolan/CIPFA copies into one config source
Files touched: new `config/frameworks.json` (or extend `config/test_registry.json`), `src/analysis/tests.py` (`principle=` literals replaced with a lookup), `frontend/src/components/OverviewPanel.tsx` (its own hardcoded list replaced with the same lookup, fetched from the published config rather than duplicated)
Depends on: none — this step is pure de-duplication and can run before any WA content is written
Done when: exactly one file defines the Nolan/CIPFA mapping; the other two locations read from it.

### Step 2: Build the WA primary-instruments config
Files touched: `config/frameworks.json` (add the seven-instrument table: `LGA_1995`, `ADMIN_REGS`, `FG_REGS`, `CONDUCT_REGS`, `MODEL_CODE_2021`, `DLGSC`, `SAT`, each with key/instrument-name/relevance), demote Nolan/CIPFA to a `secondary_mapping` field on the same config rather than deleting it
Depends on: Step 1 (same config file)
Done when: `02-claim-layer.md`'s `framework_refs` field has a real config to resolve `{instrument, section}` pairs against.

### Step 3: Add the remaining three era boundaries to the existing config mechanism
Files touched: `config/council_eras.json` (add `model_code_2021`, `conduct_regs_2007`, `covid_2020` keys alongside the existing Inquiry window, per council), `src/council_eras.py` (extend `EraWindow`/`load_council_eras()` to handle multiple named windows per council rather than the current single-window-per-council shape)
Depends on: none
Done when: any `_t_*` function needing the 2020, 2007, or 2021 boundary reads it from `council_eras.json`, not a literal.

### Step 4: Copy the s5.69 detection pattern to build a s5.68 detector
Files touched: `src/analysis/queries.py` (`_council_resolution_permitted()` or similar, alongside `_ministerial_approved()`), a new field on `interest_declarations` (additive column, e.g. `s5_68_permission_granted`, `s5_68_resolution_quote`) or on the future `declaration_fact` gold table if `02-claim-layer.md`'s Step 2 has landed by the time this runs
Depends on: a human decision (flagged in G-03) on the evidentiary bar for "a resolution was passed" vs. "the text merely cites the section" — resolve before implementing, don't default to the looser substring-match standard without deciding this explicitly first
Done when: a corpus-wide sweep (not a sample) has run, and the count of s5.68-permitted must-leave declarations is known.

### Step 5: Block named recusal claims pending the sweep; exclude s5.68-permitted instances once complete
Files touched: `src/invariant_gate.py` (an interim rule blocking any `names_individuals==true` recusal-metric claim until Step 4's sweep is marked complete in `config/agent_switches.json` or similar), `src/analysis/queries.py` (`conflict_recusal_stats()` and related functions exclude s5.68-permitted rows from the must-leave denominator once the sweep exists)
Depends on: Step 4
Done when: no recusal panel can name an individual while the s5.68 sweep is incomplete; once complete, the panel states the exclusion and its count explicitly (per the source doc's own requirement).

### Step 6: Enforce the must-leave/impartiality separation as a rule
Files touched: `src/analysis/queries.py` (`ConflictRecusalStats`/`RecusalTrendStats` — ensure `interest_type` is carried through to whatever the claim object's declared grain becomes, per `02-claim-layer.md`), a linter rule once `03-critic-agents.md`'s linter exists (or an interim check in `src/invariant_gate.py` if built before the full linter lands)
Depends on: `02-claim-layer.md`'s claim object existing with a `population.grain` field that can include `interest_type`
Done when: no claim can blend must-leave and impartiality declarations into one denominator; `01-known-defects.md` G-22/G-23/G-24's recusal-panel contradictions are structurally prevented, not just individually patched.

### Step 7: Add the unminuted-briefing-forums caveat
Files touched: `docs/investigator/Investigator_prompt.txt` (Part 0 or the relevant criteria section)
Depends on: none
Done when: the caveat text exists and is cross-referenced from officer-ratification, contestation-rate, and low-visible-contest test descriptions.

### Step 8: Resolve the delegate-declaration and officer-recommendation grading directions
Files touched: `src/analysis/tests.py` (`_t_delegate_body_conflict`, `_t_officer_divergence`), pending a human/jurisdiction-critic decision on the reg 34C and SAT-precedent questions
Depends on: Step 2 (the config needs to exist to cite against) and, ideally, `03-critic-agents.md`'s C-03 jurisdiction critic (Step 1 there) for the actual legal judgment — this step should not be resolved by an engineer's own reading of the law; it needs the retrieval-backed critic's finding
Done when: both claims either carry a cited basis for their current grading or are re-graded to neutral pending one.

### Step 9: Build the statute corpus for C-03
Files touched: new `data/legal_corpus/` (or similar), a chunking/ingestion script, provenance fields matching the project's existing shape (instrument, version, in-force dates, section, chunk id — deliberately mirroring `ExtractionEvidence`'s provenance shape per the source doc's own instruction)
Depends on: none technically, but sequence after Steps 1–2 so the corpus's instrument keys match the config's exactly
Done when: `03-critic-agents.md`'s C-03 (currently a stub, per that file's Step 1) can retrieve real chunked text for any of the seven instruments and cite a specific section.

### Cross-category dependency notes
- Step 6 depends on `02-claim-layer.md`'s claim object and grain concept; do not build an interim version that would need to be re-architected once that lands — an interim `src/invariant_gate.py` rule is acceptable as a stopgap (noted in Step 5) but should be written knowing it's temporary.
- Step 8 depends on `03-critic-agents.md`'s jurisdiction critic (which itself depends on this file's Step 9) — this creates a real two-step chain: 04 Step 2 → 04 Step 9 → 03's C-03 → 04 Step 8. Sequence accordingly; don't resolve the grading-direction question by engineering judgment alone in the meantime.
- Comparator councils (G-08) are explicitly out of this file's implementation steps per the source doc's own sequencing instruction — tracked, not planned here.
