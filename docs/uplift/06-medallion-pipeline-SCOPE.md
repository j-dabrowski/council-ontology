# 06 — Medallion Pipeline — SCOPING BRIEF ONLY

> **Do not produce an implementation plan from this file in the current pass.**
> This work requires its own dedicated session. What follows is the brief for that
> session, plus the investigation that must precede it.

## Why this is separated

The database restructure is the only workstream in this folder that can
**destroy data**. Re-running extraction over a 31-year corpus against the Claude
API is a several-hundred-dollar operation and, depending on what has been
retained, may not be fully reproducible at all.

Every other file in this folder is additive or refactoring. This one is not, and
it must not be planned casually alongside them.

---

## Hard constraints

1. **No re-extraction.** Do not call the Claude API to rebuild anything that
   already exists locally in any form.
2. **No destructive migration.** New tables alongside old. Cut over. Delete only
   after verification passes against both.
3. **Inventory before design.** The pipeline design is downstream of what can
   actually be reconstructed from local artefacts. Design first and you may
   specify a bronze layer that cannot be populated.

---

## Mandatory first step of the dedicated session: artefact inventory

Before any schema is designed, produce a complete inventory of what exists
locally:

| Question | Why it matters |
|---|---|
| Are **raw Claude API JSON responses** persisted? Where, in what format, for what proportion of the corpus? | These are the true bronze. If they exist, bronze is a replay, not a re-extraction. |
| Do raw responses cover the **whole corpus** or only recent runs? | Partial coverage means a hybrid bronze with mixed provenance quality. |
| What **model version and date** produced each response? | Needed for `extraction_error` stratification and for the published method text. |
| Are the **prompts** that produced each response retained and versioned? | Without these, responses cannot be interpreted or reproduced. |
| Are **source PDFs** retained, and are they page-addressable? | Required for V-4 rasterisation and for all source-span provenance. |
| What is currently in the **database** that exists *nowhere else*? | This is the irreplaceable set. Identify it explicitly before touching anything. |
| Has any **manual correction** been applied post-extraction, and is it recorded? | Manual fixes not present in raw JSON would be silently lost on a replay. |
| Are there intermediate files — normalised JSON, Pydantic dumps, CSV exports? | Possible partial bronze substitutes. |

**Deliverable of that step:** a reconstruction feasibility statement — for each
gold-layer concept, whether it can be rebuilt from local artefacts, and if not,
what the irreplaceable source is and where it is backed up.

Nothing else in that session begins until this exists.

---

## Target architecture (for that session to refine, not accept blindly)

### Bronze
Raw model output, immutable, replayable.
- Persisted Claude API responses, one record per call, with prompt id, model
  version, timestamp, source document, page range.
- **Per-field provenance is the key requirement:** every extracted value carries
  `(source_pdf, page, char_span_or_bbox, extraction_model, extraction_date,
  confidence)`.
- Without this you can never answer "is this panel wrong or is the parser wrong",
  cannot build per-bar source links, cannot offer right of reply on a specific
  claim, and critics can never verify anything — only reason about plausibility.
- **Retrofitting provenance later is far worse than building it now.** If existing
  raw responses do not carry it, determine whether spans can be recovered by
  re-matching extracted strings against source text. That recovery job is itself a
  scoped task for the dedicated session.
- Pydantic validation at the bronze boundary is the right place for shape
  enforcement; SQLAlchemy models below it.

### Silver
Cleaned, deduplicated, entity-resolved.
- **Single canonical entity resolution for contractors and councillors** — this is
  where D-05, D-06, D-07 are fixed. Two normalisation schemes exist today; silver
  is where exactly one must live.
- Canonical id tables with alias mappings, so "Leo Heaney" and "Leoheaney" resolve
  to one id and the alias set is inspectable.
- Bucket records like `Various contractors: ...` must be typed as buckets, not
  entities, and excluded from entity rankings.
- **Silver emits a quality report**, not just tables: dedup merge decisions,
  unresolved entity candidates, per-field null rates, records dropped and why,
  plus the contradictions table from V-2.
- That quality report is an input to the extraction sceptic critic. Findings like
  "n=10 for 5+ objectors" (D-08) are only flaggable if someone can see that
  submissions have a high null rate.

### Gold
Semantic facts with **declared grain**. See `02-claim-layer.md` for the table list
and the grain declarations.

**Gold is not agent-designed.** Agents may propose tables; proposals are gated and
must declare grain. Agent-designed gold is the garden of forking paths with a
build step — the agent shapes the schema around findings it already wants and
every downstream statistic inherits that bias.

---

## Known issues this layer must fix

From `01-known-defects.md`:

| Defect | Layer |
|---|---|
| D-04 denominators don't reconcile | gold — declared grain |
| D-05 two normalisation schemes | silver — single canonical resolution |
| D-06 bucket ranked among named firms | silver — bucket typing |
| D-07 duplicate Carr | silver — entity resolution against terms table |
| D-09 suspect ABSENT baseline | gold — ABSENT sub-typing (recusal / non-attendance / unknown) |
| D-29 s5.68 undetected | bronze schema extension + gold field |
| D-33 no accuracy statement | bronze per-field provenance |

---

## Dependencies both ways

- `05-verification.md` V-1/V-2/V-3 can run against the **current** database and
  should not wait for the pipeline. Their output informs the pipeline design.
- `02-claim-layer.md` linter rules L-06 and L-08 (denominator reconciliation,
  filter-chain replay) cannot pass until gold grain is declared.
- `04-jurisdiction.md` s5.68 work requires a bronze schema extension and should be
  sequenced into the pipeline session rather than bolted on.

---

## What the dedicated session should produce

1. Artefact inventory and reconstruction feasibility statement (gate — everything
   else waits on this).
2. Backup plan for the irreplaceable set, executed before any migration step.
3. Bronze schema, including the provenance retrofit strategy.
4. Silver entity-resolution design and quality-report spec.
5. Gold table definitions with declared grain, human-reviewed.
6. Migration sequence, additive, with a verification step comparing old and new
   outputs before any deletion.
7. A replay harness: rebuild the database from local artefacts end to end, with no
   API calls, as a repeatable operation.

Item 7 is the real success criterion. If the database can be rebuilt from local
artefacts on demand, every other change in this folder becomes low-risk.
