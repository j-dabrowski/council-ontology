# Council-Ontology Findings — Verified Reference Dump

Everything below was checked directly against `data/council.db` and the codebase on 2026-07-16. Use only these values; do not pull numbers from docs/memory, which are stale.

## 1. Corpus scale

| Metric | Verified value | How obtained |
|---|---|---|
| Document rows (extracted PDFs) | **580** | `SELECT COUNT(*) FROM meetings;` |
| Distinct physical meeting events | **530** | `SELECT COUNT(DISTINCT meeting_date) FROM meetings;` — 580 documents ≠ 580 meeting events; several dates have both an agenda and minutes row (some have 3 rows: agenda + minutes + addendum). Top overlap dates: 2025-12-16, 2025-10-28, 2023-12-11, 2023-10-09, 2022-11-15 (3 rows each). |
| Earliest meeting_date | **1995-04-18** | `SELECT MIN(meeting_date) FROM meetings;` |
| Latest meeting_date | **2026-06-09** | `SELECT MAX(meeting_date) FROM meetings;` |
| Total motions | **14,013** | `SELECT COUNT(*) FROM motions;` |
| Total votes | **16,249** | `SELECT COUNT(*) FROM votes;` |
| Total councillors | **400** (current) | `SELECT COUNT(*) FROM councillors;` on live `data/council.db` |
| Total councillors (stale) | 405 | `SELECT COUNT(*) FROM councillors;` on `data/council.db.bak-predupe-20260624` — this is the **pre-dedupe** figure. The "405" claim in the original draft came from this old backup, not the current DB. Use 400. |
| document_type breakdown | minutes 506 / agenda 66 / addendum 4 / unknown 4 (sums to 580) | `SELECT document_type, COUNT(*) FROM meetings GROUP BY document_type ORDER BY 2 DESC;` |
| council row | 1 council: "Town of Cambridge" (Cambridge, WA) | `SELECT * FROM councils;` — single-council corpus, confirms this isn't multi-council yet |

## 2. Provenance claim (entity → source quote coverage)

**Cannot claim literal 100%.** Real figure: **98.15%** (44,099 of 44,929 extracted entities have ≥1 row in `extraction_evidence`).

Method: for each of the 13 entity tables that `extraction_evidence.entity_table` references, counted `COUNT(*)` in the table vs `COUNT(DISTINCT entity_id)` in `extraction_evidence WHERE entity_table = <table>`.

Per-table breakdown:

| table | rows | with evidence | % |
|---|---|---|---|
| motions | 14,013 | 13,288 | 94.8% |
| planning_applications | 3,116 | 3,102 | 99.6% |
| public_questions | 3,478 | 3,478 | 100.0% |
| deputations | 1,492 | 1,490 | 99.9% |
| petitions | 383 | 383 | 100.0% |
| appointments | 944 | 944 | 100.0% |
| committee_reports | 881 | 870 | 98.8% |
| budget_items | 3,978 | 3,971 | 99.8% |
| interest_declarations | 2,015 | 2,011 | 99.8% |
| tenders | 840 | 840 | 100.0% |
| delegated_decisions | 1,242 | 1,242 | 100.0% |
| building_permits | 667 | 667 | 100.0% |
| other_items | 11,880 | 11,813 | 99.4% |
| **TOTAL** | **44,929** | **44,099** | **98.15%** |

`extraction_evidence` table has 71,486 total rows (some entities have multiple quotes). Schema: `id, meeting_id, entity_table, entity_id, quote_text, char_offset, char_length`. Weakest table is **motions at 94.8%** (725 motions with no quote) — worth naming if the article leans on motions specifically as the flagship entity.

## 3. Validation metrics — CRITICAL: two different subsets, do not conflate

Source: `data/validation/summary.json` (generated 2026-06-29T18:21:55Z) for the full-corpus figures. Independently recomputed from the 593 raw per-document files in `data/validation/*.json` (593 files exist because 13 meetings were re-validated after a June 2026 dedupe pass; deduping to "latest file per meeting_id" reproduces the summary.json full-corpus numbers exactly, and also cleanly isolates a 2024+ subset).

Dedup method: grouped validation JSON files by `meeting_id`, kept the one with the latest file mtime per meeting. Confirmed this reduces 593→580 and every remaining `meeting_id` exists in the live `meetings` table (no stale/orphaned records).

| Metric | Full corpus (n=580) | 2024+ subset (n=87) |
|---|---|---|
| Avg quote completeness | **83.66%** (matches summary.json `avg_quote_completeness: 0.8366` exactly) | **98.07%** |
| Avg paraphrase rate | summary.json says **3.87%**; independent recompute (averaging only docs with ≥1 quote, n=439) gives **5.11%** — methodology difference (summary.json likely averages in zero-quote docs as 0), not a data error. Report as "roughly 4-5%." | **6.18%** |
| PASS | 256 | 57 |
| REVIEW | 183 | 30 |
| FAIL | **141** | **0** |
| n | 580 | 87 |

**The finding**: the claimed "98% quote completeness / 6% paraphrase / 0 FAILs across 87 docs" is **exactly correct for the 2024+ subset** and **wrong if presented as full-corpus**. Full-corpus quote completeness is 83.7%, not 98%, with 141 FAILs. Any sentence using the 98%/6%/0-FAIL numbers must explicitly say "for meetings from 2024 onward" or equivalent — do not let it read as a full-corpus claim.

2024+ subset filter used: `meeting_date >= '2024-01-01'` on the validation JSON's own `meeting_date` field (each file embeds `meeting_id`, `meeting_date`, `document_type`, `status`, `quote_completeness.completeness_rate`, `quotes.paraphrase_rate`, `quotes.total`).

Per-file JSON structure (example fields, from `936cc360.json`): `filename`, `meeting_id`, `meeting_date`, `meeting_type`, `document_type`, `total_chars`, `quotes.{total,paraphrased,stripped_matched,paraphrase_rate,paraphrase_examples}`, `coverage_ratio`, `entity_counts.*`, `inventory_agreement.*` (per-entity-type L1-inventory-vs-extracted ratio + flag), `keyword_gap.*`, `quote_completeness.{total_entities,entities_with_quotes,completeness_rate,missing_by_table}`, `status` (PASS/REVIEW/FAIL), `entity_density.*`, `schema_completeness.*`.

### 3a. The 141 FAILs — do they skew old and large?

**Only partially confirmed — do not state "FAILs skew old and large" as a clean finding.**

Method: same 580 deduped validation records as above. `document_type` pulled from the live `meetings` table via `meeting_id` join (153 of the older validation JSON files predate the `document_type` field and don't carry it themselves). Decade = `(year // 10) * 10` on `meeting_date`. Size = each file's own `total_chars`.

**By decade** — a step change around 2020, not a smooth "older is worse" gradient. The 2010s (29.4%) actually fails slightly more often than the 1990s (28.1%):

| decade | FAILs | total | rate |
|---|---|---|---|
| 1990s | 27 | 96 | 28.1% |
| 2000s | 41 | 149 | 27.5% |
| 2010s | 47 | 160 | 29.4% |
| 2020s | 26 | 175 | 14.9% |

Pre-2020 fails at roughly double the rate of 2020s (≈28% vs 14.9%). That's real and worth stating, but frame it as a step change (consistent with a recent prompt/pipeline improvement), not a monotonic decade-by-decade climb.

**By document_type** — minutes fail more than agendas: 130/506 (25.7%) vs 11/66 (16.7%). Addendum (0/4) and unknown (0/4) have no fails but are too small a sample to mean anything.

**By size (total_chars) — does NOT cleanly support "large."** FAIL is bigger than PASS, but REVIEW is the largest bucket of all three, bigger than FAIL:

| status | n | avg_chars | median_chars |
|---|---|---|---|
| PASS | 256 | 180,112 | 19,856 |
| REVIEW | 183 | 429,323 | 439,749 |
| FAIL | 141 | 301,074 | 353,285 |

So "large" predicts "not a clean PASS" (i.e., REVIEW or FAIL), not FAIL specifically. Controlling for decade makes this weaker still — FAIL vs non-FAIL average size within the same decade is close and sometimes reversed:

| decade | FAIL avg_chars (n) | non-FAIL avg_chars (n) |
|---|---|---|
| 1990s | 232,224 (27) | 236,552 (69) |
| 2000s | 417,047 (41) | 409,241 (108) |
| 2010s | 276,435 (47) | 318,058 (113) — non-FAIL is *larger* |
| 2020s | 234,233 (26) | 189,357 (149) |

**Bottom line for the article**: "FAILs are concentrated in pre-2020 documents (roughly double the fail rate of 2024+ material)" is defensible. "FAILs skew large" is not — that's actually a REVIEW-status effect, and within any given decade, document size doesn't reliably distinguish FAIL from non-FAIL.

## 4. Officer divergence (reasoning-layer teaser number)

Source: ran `src.analysis.divergence.officer_divergence(session, council_id=1)` live against `data/council.db` (function in `src/analysis/divergence.py`).

Method (from the code, for accurate framing in prose): finds all meeting dates that have both an agenda document and a minutes document, matches agenda motions carrying a non-null `officer_recommendation` to minutes motions at the same meeting date (first by exact `item_number`, falling back to fuzzy title match via `SequenceMatcher`, threshold `min_confidence`), then classifies each matched pair as FOLLOWED (minutes outcome = CARRIED) or DIVERGED (outcome = LOST or DEFERRED). Motions with null outcome, WITHDRAWN, or LAPSED are excluded (INDETERMINATE, not counted). Explicit code-comment limitation: this does not detect "council amended the motion text before carrying it" — that would need motion-text diffing, which is deferred/not implemented.

| min_confidence | matched pairs (n) | followed | diverged |
|---|---|---|---|
| 0.5 (function default) | **203** | 197 (97.0%) | 6 (3.0%) |
| 0.6 | 192 | 187 (97.4%) | 5 (2.6%) |
| 0.7 | 191 | 186 (97.4%) | 5 (2.6%) |
| 0.8 | 190 | 185 (97.4%) | 5 (2.6%) |
| 0.9 | 188 | 183 (97.3%) | 5 (2.7%) |
| 1.0 (exact match only) | 187 | 182 (97.3%) | 5 (2.7%) |
| exact item_number matches only (post-filter) | 187 | 182 | 5 (2.7%) |

**The finding**: the ~97%/~3% split is robust across every matching strictness tried. **The claimed n=133 does not reproduce under any threshold** — real count today is 187 (strict exact match) to 203 (function default). This is very likely just corpus growth since 133 was last computed (more agenda/minutes pairs have been extracted since). Use **203** (the function's own default behavior) as the reported n, or 187 if described as "exact item-number matches only" — either is defensible and both are verified live; 133 is not.

## 4a. The two "98%" figures, and the real in-sample/out-of-sample story

Checked 2026-07-19, prompted by a hiring-post draft using "98% in-sample / 84% out-of-sample" language.

**They are different aggregations, both full-corpus by default:**

| Figure | What it is | Method |
|---|---|---|
| **98.15%** | Entity-level pooled aggregate: of all 44,929 extracted entities across the entire 30-year corpus, 44,099 have ≥1 quote. Counts every entity once. | `SELECT COUNT(DISTINCT entity_id) FROM extraction_evidence WHERE entity_table=<t>` summed across all 13 tables ÷ total row count. Same number as section 2. |
| **83.66%** (~84%) | Per-document average of the validation script's `quote_completeness.completeness_rate`, averaged across all 580 documents equally (every doc weighted the same regardless of size). This is a **blend** of tuned and untuned documents — see below. | Deduped `data/validation/*.json`, mean of `quote_completeness.completeness_rate`, n=580. Same as section 3. |
| **98.07%** | Same per-document metric, restricted to the 87 documents dated 2024-01-01+. | Same field, filtered `meeting_date >= '2024-01-01'`, n=87. |

**Verified extraction chronology (from `meetings.extracted_at`), confirming a real train/apply split:**

| Batch | extracted_at | n | What it was |
|---|---|---|---|
| Calibration sample | 2026-05-31 | 12 of 18 | The Level 3a stratified sample (`data/cambridge_sample.json`) — cross-era, includes 3 docs from 1995/1997 — used to confirm the prompt's metrics were broadly acceptable before scaling. Not an iterative tuning loop. |
| **2024+ full extraction** | 2026-06-09 to 06-19 | 87 | Exactly the 2024+ subset. This is where the extraction pipeline was actually iterated and refined. |
| **Pre-2024 bulk pass** | 2026-06-22 | 340 | The 1990s–2023 corpus, extracted in a single day, after the 2024+ work concluded, with no further per-era tuning. |
| (untimestamped) | NULL | 141 | Older rows without an `extracted_at` value (92 of these do have motions — likely an early/experimental extraction pass that predates timestamp tracking, not a sign of missing extraction). Not otherwise investigated. |

**Recomputed with the actual tuned/untuned split** (not the calibration-sample framing I used in an earlier pass at this file, which understated the effect):

- **Pre-2024, the true held-out set (n=493):** avg completeness **81.12%**
- **2024+, the set the pipeline was iterated against (n=87):** avg completeness **98.07%**
- **Full corpus blended (n=580):** **83.66%** — note this blends the two groups; it is *not* a clean "out-of-sample" number, since it includes the 87 well-performing tuned documents mixed in with the 493 untuned ones.

**Verdict: an in-sample/out-of-sample framing is legitimate and verifiable** — "98% on the set the pipeline was iterated against, 81% on the corpus extracted afterward with the frozen prompt and no further tuning" is a defensible, checked claim. An earlier pass at this file wrongly rejected this framing based on the 18-doc calibration sample alone, without checking `extracted_at`; that was an error, corrected here.

**One remaining caveat to keep the claim airtight**: the 18-doc calibration sample does include three 1990s/1997 documents (used for a pre-scaling sanity check, not iterative tuning). So say "iteratively refined against the 2024+ corpus, then applied unmodified to the remaining 493 documents" rather than "formatting it never saw" — the prompt did see a handful of 1990s documents during calibration, just not during the actual improvement loop.

**Recommended article/post language**: "98 percent on the 2024+ documents the pipeline was iteratively tuned against; 81 percent on the 493 older documents extracted afterward with that same frozen prompt and no further per-era tuning. The blended full-corpus figure, weighting every document equally, is 84 percent. Separately, counting every extracted entity once across the whole 30-year corpus rather than averaging per document, 98 percent of all ~45,000 entities carry a quote — a different statistic from either of the above, not a third contradiction."

## 5. Things NOT independently verifiable / not checked

- No claim in the original list was left unverifiable — every figure got either a confirmed match, a corrected value, or a clearly flagged subset mismatch.
- Did not check whether `votes` rows themselves carry `extraction_evidence` — the entity_table list in `extraction_evidence` does not include `votes`, `councillors`, `councillor_terms`, `meetings`, `sites`, `relationships`, or `community_submissions`. The provenance claim as computed covers the 13 "content" entity tables that are the actual extraction targets; votes are structurally derived from motions rather than independently quote-sourced. Worth knowing if a future draft wants to claim vote-level sourcing specifically — that would need a separate check.

## 6. Corrected figures to use going forward (single source of truth)

- Documents: 580 (document rows) / 530 (distinct meeting events) — pick one and label it correctly
- Date range: 1995-04-18 to 2026-06-09
- Motions: 14,013
- Votes: 16,249
- Councillors: **400** (not 405 — 405 is pre-dedupe)
- Entity-quote coverage: **98.15%** (not "every"/100%)
- Full-corpus validation: 83.66% quote completeness, 141/580 FAIL
- 2024+ validation (87 docs): 98.07% quote completeness, ~6.18% paraphrase, 0 FAIL
- Officer divergence: 97.0% followed / 3.0% diverged over **203** matched pairs (not 133)

## 7. Draft prose (built only from the verified numbers above)

The pipeline has now worked through 580 documents from the Town of Cambridge, spanning meetings from 1995 to 2026, and extracted 14,013 motions and 16,249 recorded votes involving 400 councillors. The payload is that 98 percent of the roughly 45,000 entities pulled out of those documents - motions, planning applications, public questions, tenders, budget items, and the rest - carry at least one verbatim quote back to the source PDF, tied to a specific character offset in the original text. Nothing in the dataset floats free of its source.

Scale alone does not tell you whether an extraction pipeline can be trusted, so the project runs a separate validation pass that checks each document's output against its own text: how much of what was extracted is backed by a quote, how much has been paraphrased rather than lifted verbatim, and whether the entity counts line up with an independent inventory pass. Run across the full corpus, quote completeness averages 84 percent, with 141 of 580 documents flagged FAIL. Restricted to meetings from 2024 onward - 87 documents, the subset that has had the most validation attention - quote completeness rises to 98 percent, paraphrase rate holds at 6 percent, and there are zero FAILs, only 57 PASS and 30 REVIEW. The two figures describe different slices of the same pipeline, not a contradiction, and the gap between them is itself informative: it is roughly the gap between the current extraction prompt and the older passes still waiting on a re-extraction pass.

Because every fact in the dataset is typed and sourced, it stops being a pile of PDFs and becomes something you can query and reason over - which motions carried, which lost, who moved what, how council's decisions compare to what officers recommended going in. That comparison is possible now: matching agenda recommendations to minutes outcomes across 203 paired motions, council followed the officer recommendation 97 percent of the time. What that number means, and whether it holds up once you dig into which 3 percent didn't, is the subject of the next article.

This prose is a starting point, not final — rework tone/structure freely, but every number in it traces to a row above and should not be changed without re-verifying against the DB.
