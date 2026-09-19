# 05 — Verification and Accuracy Measurement

Fully autonomous. Feeds `extraction_error` into every claim object (see 02) and
supplies the extraction sceptic critic (C-05) with its inputs.

## The problem

The report's entire method claim is "Data extracted via Anthropic Claude". No
precision, no recall, no model version, no extraction date, no audited sample.
Every named adverse finding is downstream of extraction quality (D-33).

## The circularity trap

If verification uses the same model, same task shape, and same input
representation as extraction, it measures nothing. Correlated errors guarantee
agreement precisely on the cases where the extractor is confidently wrong, and
the output is "98% accurate, AI-verified" with no information content.

Three axes must differ. Use all three:

**Different task shape.** Extraction is open-ended generation ("find every
declaration in this minute"). Verification must be closed adjudication ("here is
a claim and a page — supported, contradicted, or not determinable"). Closed
verification is a far easier task with far lower error rates, which is what makes
this work. Never ask the verifier to re-extract and diff.

**Different input representation.** If bronze was extracted from the PDF text
layer, verify from **rendered page images** via vision. This is the
highest-value element of the design. Text-layer failures — two-column bleed,
table cells read out of order, ligature mangling, 1990s scans — do not propagate
to a vision pass. It is a second *path to the evidence*, not just a second
opinion.

**Different model.** Different family where possible, different generation
otherwise. Weakest axis, but free.

---

## The anchor: document-derived checks

These do not rest on any model's judgement. They are the calibration set and the
number that goes on the published page. Everything model-based sits on top of them
and is reported as secondary.

### V-1 Stated tally reconciliation
Wherever a minute writes a tally ("carried 5/2"), that is ground truth printed on
the page. Reconcile against extracted vote rows.
- **Census coverage**, zero models, unambiguous.
- Directly measures accuracy on the single most important field in the corpus.
- Output: reconciliation rate, per era, per document format.

### V-2 Internal contradiction sweep
A minute constrains itself. Detectable without any model:
- Same councillor recorded both ABSENT and casting a vote on one item.
- A declaration with no matching item.
- A vote row for a councillor outside their term dates.
- A mover or seconder not in attendance.
- Tally count exceeding chamber size.
Every contradiction is a **free labelled negative**. Count corpus-wide for a lower
bound on error rate across 100% of records. Persist as a `contradictions` table —
it is an input to C-05.

### V-3 Cross-document arithmetic
- Attendance lists vs vote rows.
- Agenda item numbering vs minute item numbering (also required for the
  agenda↔minutes matching the officer-recommendation panel depends on).
- Tender award values against any stated aggregate in the same document.
- Councillor names against the councillor-terms table.

**Run V-1 to V-3 before building anything model-based.** They are cheap, they may
supply most of what is needed, and they will show where to aim the sampling.

---

## Model-based layers

### V-4 Render pages to images
Prerequisite for everything below. Page-level rasterisation, stored addressable by
`(source_pdf, page)` so any claim's source span can be rendered on demand — this
also supplies the drill-down and right-of-reply surface required by L-05.

### V-5 Precision pass
Stratified sample (era × document format × field), n ≈ 500. Vision verifier,
different model family from the extractor, closed three-way adjudication against
the cited span: `supported | contradicted | not_determinable`.

### V-6 Three-way adjudication and the contested table
Extractor, verifier, arbiter. Disagreements route to the arbiter. **Unresolved
three-way splits are written to a `contested` table** with full provenance and
excluded from silver.

The contested table is the important structural element: it is where uncertainty
is *recorded* rather than resolved, and it means the pipeline never stalls on a
decision it cannot make. The count of contested records is itself a published
quality metric.

### V-7 Capture–recapture for recall
Recall requires finding what the extractor missed, which is open-ended generation
again with the same failure modes. Use capture–recapture over a page sample
(n ≈ 120 pages), second pass independent (vision path, different prompt lineage,
no sight of pass one):

- A = pass-one finds, B = pass-two finds, C = both
- estimated population ≈ A×B/C
- recall of pass one ≈ C/B

**Report as a floor, not an estimate.** Independence is violated by shared blind
spots, and violation always biases toward overstating recall. State this in the
method text — it is a strength, not a weakness.

### V-8 Adversarial injection
For classes the free checks cannot reach. Take real pages, inject synthetic
period-appropriate declarations, tender awards, and objections, re-run extraction,
measure detection. This is the only method here not hostage to shared blind spots,
and it measures recall directly.
- Keep injections in a **held-out set** that never reaches silver.
- Period-appropriate phrasing matters: a 1996-format injection tests whether the
  extractor handles 1996 formats, which is the actual question.

### V-9 Census verification of named claims
Legal exposure is not spread across the corpus. It sits on a handful of claims:
the named councillors in the recusal chart, the surname collisions, anything with
`names_individuals == true`.

For these, sampling is the wrong instrument. Verify **every** source span behind
every named adverse bar — order 300 spans, trivial for a vision pass. A 97% corpus
precision rate is no defence when the specific bar is one of the 3%.

### V-10 s5.68 census sweep
Detailed in `04-jurisdiction.md`. Runs on the same vision infrastructure: a closed
question over every must-leave declaration asking whether the surrounding minute
text contains a resolution permitting participation.

---

## Outputs

### Per-field, per-era error table
Precision varies enormously by era and format. 2020s structured minutes will
verify near-perfectly; 1996 scans will not. A single headline accuracy number is
not acceptable output.

Schema: `field, era, format, precision, precision_ci, recall_floor, n_sampled,
verification_run_id`.

This table:
- populates `claim.extraction_error`
- drives linter rule L-15 (claims from low-precision strata cannot be graded above
  neutral)
- supplies C-05
- is likely to explain D-08 (objector under-count) and D-09 (ABSENT baseline)

### Error term folded into claim CIs
Extraction error is a source of uncertainty and must widen intervals, not sit in a
footnote. A claim whose effect size is within the extraction error band for its
stratum is not a finding.

### Published method text

Write it out rather than gesturing at it. Target shape:

> Extraction: [model, version, date]. Verified on a stratified sample of 500
> records by an independent vision-based pass using [different model], adjudicated
> by a third model. Field-level precision 0.94–0.98 (95% CI), varying by era —
> see the per-era table. Recall floor 0.89 by capture–recapture on 120 pages; the
> independence assumption is violated by correlated model errors, so true recall
> may be lower. Vote-tally arithmetic reconciles on 99.2% of 3,411 stated tallies
> across the full corpus. 412 records are recorded as contested and excluded. All
> named findings are individually source-linked and 100% verified.

The document-derived reconciliation figure is the load-bearing sentence — it is
the only one that does not depend on a model assessing a model.

---

## Sequence

1. V-1, V-2, V-3 — census checks. Zero models. Likely surfaces real bugs
   immediately and may reshape priorities for the rest of this file.
2. V-4 — page rasterisation.
3. V-5, V-6 — precision pass, adjudication, contested table.
4. V-7 — capture–recapture recall floor.
5. V-9, V-10 — named-claim census and s5.68 sweep. **Blocks named publication.**
6. V-8 — injection tests for whatever the above leaves thin.
7. Fold error terms into claim CIs; wire era thresholds into the linter.

---

## Investigation prompts for the receiving agent

- What is persisted from the original Claude API extraction calls? Raw responses,
  parsed objects, or only the final rows? (Overlaps with `06` — do not duplicate
  that investigation, cross-reference it.)
- Is there per-field provenance today — source PDF, page, character span — or only
  per-document?
- Are source PDFs retained locally and page-addressable?
- Does any validation run today between extraction and database insert?
- Is the model version and extraction date recorded anywhere per record?
- Are stated tallies ("carried 5/2") extracted as a field? If not, that is the
  first thing to add — it is the anchor.
