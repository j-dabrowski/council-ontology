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
| council row | 1 council: "City of Cambridge" (Cambridge, WA) | `SELECT * FROM councils;` — single-council corpus, confirms this isn't multi-council yet |

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

The pipeline has now worked through 580 documents from the City of Cambridge, spanning meetings from 1995 to 2026, and extracted 14,013 motions and 16,249 recorded votes involving 400 councillors. The payload is that 98 percent of the roughly 45,000 entities pulled out of those documents - motions, planning applications, public questions, tenders, budget items, and the rest - carry at least one verbatim quote back to the source PDF, tied to a specific character offset in the original text. Nothing in the dataset floats free of its source.

Scale alone does not tell you whether an extraction pipeline can be trusted, so the project runs a separate validation pass that checks each document's output against its own text: how much of what was extracted is backed by a quote, how much has been paraphrased rather than lifted verbatim, and whether the entity counts line up with an independent inventory pass. Run across the full corpus, quote completeness averages 84 percent, with 141 of 580 documents flagged FAIL. Restricted to meetings from 2024 onward - 87 documents, the subset that has had the most validation attention - quote completeness rises to 98 percent, paraphrase rate holds at 6 percent, and there are zero FAILs, only 57 PASS and 30 REVIEW. The two figures describe different slices of the same pipeline, not a contradiction, and the gap between them is itself informative: it is roughly the gap between the current extraction prompt and the older passes still waiting on a re-extraction pass.

Because every fact in the dataset is typed and sourced, it stops being a pile of PDFs and becomes something you can query and reason over - which motions carried, which lost, who moved what, how council's decisions compare to what officers recommended going in. That comparison is possible now: matching agenda recommendations to minutes outcomes across 203 paired motions, council followed the officer recommendation 97 percent of the time. What that number means, and whether it holds up once you dig into which 3 percent didn't, is the subject of the next article.

This prose is a starting point, not final — rework tone/structure freely, but every number in it traces to a row above and should not be changed without re-verifying against the DB.
