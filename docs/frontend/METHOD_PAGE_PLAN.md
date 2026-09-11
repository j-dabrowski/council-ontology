# /method — replacing the Evidence page with the extraction-quality record

Status: **built** (Steps 1–7, 2026-09-07). Written 2026-09-07.
Fifth in the sequence, after `TEST_REGISTRY_PLAN.md`, `PANEL_FRAMING_PLAN.md`,
`SURFACE_PROJECTION_PLAN.md` and `WATCH_FEED_PLAN.md` (all built).
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

**Extended 2026-09-10** (`docs/frontend/ENTITY_RESOLUTION_SECTION_PLAN.md`,
built) with a fifth section, "Entity resolution" — placed on the page
between §2 (validation) and §3 (pipeline), since it's a validation story in
its own right. Unlike the four sections in Part C below, its source is
`data/council.db` itself at build time, not one of the five files this
plan's Part A surveys. It also moved `method.json` to `"public"` in
`SNAPSHOT_TIER` (B.6 below assumed `"full"`; that assumption no longer
holds — see that plan's B.5).

This is the page the project's credibility rests on, so its own rule is
stricter than the others': **every number traces to a file in `data/`, and
carries the date that file was generated.**

---

## Part A — What is actually in the five files

All five exist and all five have real content. What they do not have is a
common date, or a common population — which is the finding that shapes the
whole page.

### A.1 `data/census.json` — 537 documents, generated **2026-05-28**

Per-document: `filename`, `meeting_date`, `meeting_type`, `char_count`,
`size_bucket`, `decade`, `extraction_status`, `keyword_counts` (by category),
`section_count`, `estimated_motions` / `estimated_planning_items` /
`estimated_interest_declarations`, `flags`.

- `extraction_status`: 536 `ok`, 1 `empty` — this is **PDF→text** extraction,
  not the LLM extraction. Do not label it as extraction success.
- `flags` across the corpus: `large_document` 319, `tiny_document` 90,
  `high_da_count` 43, `no_motion_keywords` 18, `zero_keyword_hits` 1,
  `extraction_empty` 1.
- Decades: 1990s 97, 2000s 149, 2010s 163, 2020s 128. Every document has a
  `meeting_date`.

### A.2 `data/inventories/summary.json` — 537 inventoried, generated **2026-05-28**

`total_inventoried` 537, `total_ok` 535, `total_errors` 2. Carries a
`meeting_type_distribution` (8 types, Ordinary Council Meeting 331), an
`average_counts` block (motions 7.5, planning 8.3, interests 0.9, petitions 0.4,
budget items 2.4), and one `flagged_documents` entry (`d2af2d23.pdf`,
`l1_mismatch_full_doc`).

### A.3 `data/sample_validation/report.txt` — 18 documents, generated **2026-08-23**

The richest file of the five, and the only one that already contains **the
"what failure would mean" text the brief asks for.** Its METRICS block defines
each metric and states its target verbatim:

| Metric | Definition (from the file) | Target |
|---|---|---|
| Quote completeness | fraction of extracted entities with ≥1 source quote | >80%, FAIL if <50% |
| Paraphrase rate | quotes not found in whitespace-normalised source text | <30% |
| Coverage ratio | fraction of the extraction window covered by matched quotes | >5% |
| Inventory agreement | mean (extracted count / L1 count) across entity types | flagged if <0.4 or >2.5 |
| Keyword gap rate | MOVED/CARRIED/DA/DECLARATION hits not covered by a matched quote | <25% |

Aggregates (n=18): completeness 98.2%, paraphrase 2.0%, coverage 25.18%,
keyword gap 11.1%, **16 PASS / 2 REVIEW / 0 FAIL**. Plus a per-file table (18
rows, date/para/cov/gap/status) and an inventory-agreement flag list by entity
type. `summary.json` beside it carries the same aggregates as JSON, plus
`converged: true`.

### A.4 `data/validation/summary.json` — 580 documents, generated **2026-06-29**

`total_validated` 580, `errors` 0, **`pass` 256 / `review` 183 / `fail` 141**,
`avg_quote_completeness` 0.8366, `avg_paraphrase_rate` 0.0387,
`avg_coverage_ratio` 0.2569, `avg_keyword_gap_rate` 0.112,
`schema_flags_count` 206 plus the flagged filenames. 594 per-document records
sit beside it as `data/validation/<pdf-hash>.json`.

**This is the number that matters most and it is not the flattering one:
24% of documents are FAIL.** See B.3.

The rule that produces it is `determine_status()` in `src/validation/core.py`:
FAIL if zero quotes, or completeness <0.50, or (paraphrase ≥0.80 and coverage
<0.02); REVIEW if coverage <0.03, or paraphrase ≥0.50, or gap ≥0.40, or
completeness <0.80; PASS otherwise. Agendas are exempt from the coverage-based
FAIL and REVIEW triggers.

### A.5 `data/extraction_errors.json` — **one batch**, generated **2026-06-22**

`batch_id` `msgbatch_01WL9pZ5NG97qNmvQeuk4QaE`, `attempted` 341, `succeeded`
336, `failed` 5, and `errors_by_class` with the full Pydantic message per
failure (e.g. a `community_submissions.position` of `'conditional'` against a
`support|object|neutral` literal).

It is **not** a corpus-wide error record — 341 attempted, against 580 documents
in the database. Presenting 5/341 as the project's extraction error rate would
be wrong. See B.4.

### A.6 The coverage picture the files actually support

Computed 2026-09-07 from `census.json` and `data/council.db`:

```
census documents: 537 (2026-05-28)   raw PDFs on disk: 613   DB meetings: 580 (506 minutes)
```

Per year, census against database:

- **1995–2021: they agree**, to within one document in five separate years
  (1999, 2013, 2014, 2019, 2021 each -1) — consistent with dedup merges.
- **2022–2026: the database has 48 more documents than the census** (+6, +3,
  +12, +12, +15). Those PDFs were scraped after the census ran on 2026-05-28.
- **Recent years are agenda-heavy.** 2024 holds 23 documents but only 9
  minutes; 2026 holds 21 but 8. The battery reads `document_type='minutes'`
  only, so a reader shown "23 documents in 2024" would over-credit the corpus
  by more than half.

Three consequences for section 1, all in B.2: the census is a stale snapshot
rather than a manifest; there is **no file anywhere recording what the council
published but was never downloaded**; and minutes must be shown distinctly from
all documents.

### A.7 The README pipeline table has cost and status for all seven levels

`README.md` "Multi-level extraction pipeline" — Level 0 Census (Free, Done),
1 Inventory ($4.83 actual, Done), 2 Schema (Free, Done), 3a Sample selection
(Free, Done), 3b Sample extraction (~$0.50, Done), 3c Sample validation (Free,
Done), 4 Full-corpus validation (Free, Done), 5 Full extraction (~$70 actual,
Done — 580 docs, complete 2026-06-22), 6 Audit (Free, tooling done, human
review pending).

Note the level numbers are **plan order, not run order**: Level 4 (validate) is
numbered before Level 5 (extract), but extraction completed 2026-06-22 and
full-corpus validation ran 2026-06-29. The brief's sequence — extract, then
validate — is what actually happened. See B.5.

---

## Part B — Decisions

### B.1 Every number on this page is stale, by a different amount. Say so per section.

| Source | Generated | Age at 2026-09-07 |
|---|---|---|
| `census.json` | 2026-05-28 | 14 weeks |
| `inventories/summary.json` | 2026-05-28 | 14 weeks |
| `extraction_errors.json` | 2026-06-22 | 11 weeks |
| `validation/summary.json` | 2026-06-29 | 10 weeks |
| `sample_validation/report.txt` | 2026-08-23 | 2 weeks |
| `data/council.db` | dedup pass 6, 2026-09-04 | current |

The brief's "if a metric is stale, show the run date next to it" is therefore
not an edge case — it is the page's normal condition. Two rules follow:

1. **Every metric carries its source file and that file's `generated_at`**,
   rendered next to the number, not in a footnote. The page opens with the
   freshness table above so a reader sees the spread before any figure.
2. **What can be recomputed live, is.** Per-year document and minutes counts
   come from the database at generation time, so the matrix's "in the database"
   column is current even while its "censused" column is fourteen weeks old.
   That contrast *is* the coverage finding, not a defect to hide.

Do not regenerate the stale files to make the page tidy. Re-running the census
or full validation is a pipeline decision with a cost, and it is not in this
plan.

### B.2 Section 1 is minutes-vs-documents-vs-census, not manifest-vs-extracted.

The brief asks for "manifest count vs extracted count". There is **no manifest**
(A.6): `census.json` is a snapshot of PDFs already downloaded, so it cannot
reveal a meeting the council published and the scraper never fetched, and the
database now holds 48 documents the census predates. A matrix built as
manifest-minus-extracted would show negative gaps for 2022–2026 and read as a
defect where the truth is that the census is old.

Build the matrix with three columns per year — **censused** (dated),
**documents in the database** (live), **minutes in the database** (live) — and
state the limitation in one sentence beneath it: the outer boundary of this
corpus is what was downloaded, and no file records what was published but never
fetched. That sentence is the most important on the page. Honest gaps read as
rigour; an unstated boundary does not.

### B.3 Both validation results are shown, side by side, with why they differ.

Full corpus (n=580, 2026-06-29): **256 PASS / 183 REVIEW / 141 FAIL**.
Stratified sample (n=18, 2026-08-23): **16 PASS / 2 REVIEW / 0 FAIL**.

Showing only the sample would be choosing the flattering number on the page
whose whole purpose is not doing that. Show both, adjacent, each with its n and
date, and state plainly what separates them: different populations (18
stratified documents against all 580, agendas included), different dates, and a
`determine_status()` rule where a FAIL is dominated by *missing quotes*
(zero quotes, or fewer than half the entities carrying one) rather than by wrong
quotes — the paraphrase rate is 3.9% corpus-wide.

Each metric gets the brief's "what failure of this would mean" line. A.3's file
supplies the definitions and targets verbatim; the consequence sentence is
written once, per metric, and belongs in `method.json` beside the number, not in
JSX (same discipline as the registry).

### B.4 `extraction_errors.json` is labelled as one batch, or left off.

341 attempted against 580 documents in the database (A.5). Render it as "the
last recorded extraction batch — `msgbatch_01WL9pZ5…`, 2026-06-22: 336 of 341
succeeded, 5 schema-validation failures", with the error classes. Never as a
corpus-wide rate. If that framing cannot be made clear in the space available,
leave the section out rather than let 5/341 read as 5/580.

### B.5 The diagram follows run order, and says the level numbers do not.

Draw the brief's sequence — census → inventory → typology → sample →
validate-sample → extract → validate — because that is what happened, with cost
and status per stage from A.7's table. Add one line noting the README's level
numbers are plan order, which is why full-corpus validation is Level 4 but ran
after Level 5. Do not renumber the README to match; the plan order is a record
of how the pipeline was designed and is worth keeping.

### B.6 A `method.json` snapshot, generated and published like the others.

The frontend reads static snapshots from `frontend/public/data/`; these five
files live in `data/` and are not published. So a generator reads them (plus the
database for the live columns) and writes `method.json`, which joins
`manifest.json` and ships via `council publish` — the same path
`WATCH_FEED_PLAN.md` B.3 established for `watch.json`.

Every metric in it is an object, never a bare number:

```json
{"value": 0.8366, "source": "data/validation/summary.json",
 "generated_at": "2026-06-29T18:21:55Z", "n": 580,
 "target": ">80%", "means_if_failed": "…"}
```

so provenance travels with the figure and the page cannot render one without
its date. That shape is what makes the brief's "no hardcoded illustrative
figures" checkable rather than a promise: **no number is written in JSX at
all** — the page renders only what the snapshot carries.

`method.json` carries no claim about any person and no battery result, so S7
does not apply to it. It still passes through draft → review → publish like
every other snapshot.

*(As of `ENTITY_RESOLUTION_SECTION_PLAN.md`, the "no claim about any person"
half of that sentence no longer holds unconditionally — the entity-resolution
section pairs a firm with a "sitting councillor's surname" fact. It still
carries no *name*, by construction, which is what keeps it out of S7's
scope; see that plan's B.1/B.2.)*

### B.7 `/evidence` redirects to `/method`.

Same pattern as `/digest` → `/watch`, already built. `EvidencePage.tsx` is
deleted once nothing imports it. The four "planned" cards are not migrated —
`docs/frontend/PRODUCT_ROADMAP.md` is where planned surfaces belong, and Step 7
moves anything still wanted there.

---

## Part C — What each section can actually show

| § | Section | Sourced from | Live or dated |
|---|---|---|---|
| 1 | Coverage matrix | `census.json` (censused, dated) + `council.db` (documents, minutes — live) | mixed, by column |
| 1 | Type mix | `inventories/summary.json` `meeting_type_distribution` | 2026-05-28 |
| 1 | Document flags | `census.json` `flags` tallies | 2026-05-28 |
| 2 | Five metrics + targets + consequence | `sample_validation/report.txt` METRICS block; values from both summaries | 2026-08-23 / 2026-06-29 |
| 2 | Full-corpus split | `validation/summary.json` `pass`/`review`/`fail` | 2026-06-29 |
| 2 | Sample split + per-file table | `sample_validation/summary.json` + `report.txt` | 2026-08-23 |
| 2 | Status rule | `determine_status()`, `src/validation/core.py` | code, not data |
| 2 | Schema flags | `validation/summary.json` `schema_flags_count` (206) | 2026-06-29 |
| 3 | Pipeline diagram | README "Multi-level extraction pipeline" table | statuses as at that table |
| 3 | Last batch | `extraction_errors.json` (B.4) | 2026-06-22 |
| 4 | Nulls statement | `scorecard.json` — `n_not_computable`, `n_supportive` | current draft |
| 5 | Entity resolution — supplier spelling variants, surname collisions | `data/council.db`, live (`ENTITY_RESOLUTION_SECTION_PLAN.md`) | live |

Section 4's counts are the point of it: the battery ships **2 not-computable**
tests and **10 supportive** results in the current draft. A page arguing that
nulls are reported rather than hidden should cite the nulls it reports, not
assert the principle.

Nothing in the five files supports a per-document browser, a raw-data export or
an audit trail — the four things the current Evidence page promises. Those stay
promises, in the roadmap, out of this page.

---

## Part D — The steps

Seven steps. 1–2 are pipeline; 3–6 are the page, one section at a time; 7 is
docs.

Every step ends with `pytest -q` from the repo root where it touches Python, and
`npm run lint && npm run build` from `frontend/` where it touches the frontend.

**Standing context for every step.** Read `docs/MAP.md`,
`docs/frontend/WATCH_FEED_PLAN.md` B.3 (the publish path this reuses), and
`docs/frontend/INTERACTIVITY.md`'s hard rule.

**Two constraints govern every step:**
- *Every number traces to a file in `data/`.* No figure is written in JSX,
  including as a default, a placeholder or an example. If a number cannot be
  sourced, the page does not show it — say so rather than approximating.
- *A stale metric shows its date.* Every rendered figure carries the
  `generated_at` of the file it came from, next to it.

**One commit per step**, committed once its acceptance checks pass; if they
fail, do not commit — report. `docs/TESTING.md` "Commit conventions" applies:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — `method.json`

New `src/analysis/method.py`: `build_method_record(session, council_id)`
returning the B.6 shape, reading `census.json`, `inventories/summary.json`,
`sample_validation/summary.json` + `report.txt`, `validation/summary.json`,
`extraction_errors.json`, and the database for the live per-year columns.

- Every metric is `{value, source, generated_at, n, …}` — never a bare number.
- Parse `report.txt`'s METRICS block for each metric's definition and target
  rather than retyping them; they are the file's own words and should stay that
  way. The per-metric `means_if_failed` sentence is new prose — write it once,
  here, in the record.
- A missing or unparseable source file is `null` with a `"source_missing"`
  reason, never a zero. Step 3's page renders that as an explicit gap.

Report the freshness table (B.1) from the real files, and flag any file whose
`generated_at` differs from A.1–A.5 — the corpus may have moved since this plan
was written.

Acceptance: unit tests over a fixture directory including one missing file and
one malformed one; the record printed for the real corpus with every
`generated_at` visible.

---

### Step 2 — Publish `method.json`

`cmd_draft` writes it; it joins `manifest.snapshots` and `file_hashes`; `council
publish` copies it. It is not claim-derived, so it does not join
`CLAIM_DERIVED_SNAPSHOTS` and S7 does not run on it (B.6) — state that in the
code comment so the omission reads as a decision.

Add a placeholder `frontend/public/data/method.json` in the shape of the other
placeholders, so a build before the first publish renders an empty page rather
than an error.

Acceptance: a `council draft` run emits it; `pytest -q` green including the
publish-gate tests.

---

### Step 3 — Section 1, the coverage matrix

New `frontend/src/pages/MethodPage.tsx`, routed at `/method`, with `/evidence`
as `<Navigate to="/method" replace />` (B.7). Add `/method` to `SiteNav`.

The matrix per B.2: one row per year, three columns — censused (dated),
documents in the database, minutes in the database — with the divergence drawn
rather than smoothed. Years where the database exceeds the census are the
normal, explainable case, not an error state, and must not be styled as one.

Beneath it, in one sentence: the corpus's outer boundary is what was
downloaded, and no file records what was published but never fetched.

Then the type mix and document-flag tallies from `inventories/summary.json` and
`census.json`, each with its date.

Acceptance: build + lint; the rendered per-year numbers match a direct query of
`council.db` and `census.json` — check three years by hand, including one from
2022–2026, and show the comparison.

---

### Step 4 — Section 2, the validation metrics

Both splits side by side (B.3), each with n and date; the five metrics with
value, target, and the `means_if_failed` sentence; the `determine_status()` rule
stated plainly; the schema-flag count; and the 18-row per-file sample table from
`report.txt`.

Do not average the two splits, do not lead with the sample, and do not soften
141 FAIL. The page's credibility comes from that number being on it.

Acceptance: build + lint; every figure on screen traceable — pick five at random
and name the file and field each came from.

---

### Step 5 — Section 3, the pipeline diagram

The seven stages in run order (B.5), each with cost and status from A.7's
table, plus the last-batch record framed per B.4. Inline SVG or CSS, no new
dependency, legible in light and dark.

The stage costs are real dollars from the README ($4.83 inventory, ~$0.50
sample, ~$70 full extraction) — treat them as figures under the standing
constraint: sourced, and dated to the table they come from.

Acceptance: build + lint; the diagram readable at a narrow width without
horizontal scroll.

---

### Step 6 — Section 4, why nulls are reported

Short — a paragraph, not an essay. It makes one argument: a system that only
reports findings is a system that manufactures them. It cites the current
battery's own counts from `scorecard.json` (C.1) so the claim is demonstrated
rather than asserted, and it links to the scorecard's not-computable rows.

Then delete `EvidencePage.tsx` once nothing imports it.

Acceptance: build + lint; `/evidence` redirects; the cited counts match the
scorecard page exactly.

---

### Step 7 — Documentation

- `docs/frontend/PRODUCT_ROADMAP.md` — the four surfaces the Evidence page
  promised (source browser, raw export, methodology notes, audit trail) move
  here as roadmap items; note that /method now covers the methodology one.
- `docs/TESTING.md` — `method.json` in the snapshot list and the publish flow.
- `docs/MAP.md` — a "Where do I add X?" row: *a new extraction-quality metric on
  the public record* → `src/analysis/method.py`, sourced from a file in `data/`.
- `docs/pipeline/PIPELINE.md` — record the staleness spread B.1 measured, and
  that the page surfaces it rather than hiding it. If a re-run of census or
  full-corpus validation is wanted, that is a pipeline decision to log here, not
  a frontend change.
- Mark this file's status **built**.

---

### Deliberately not in this plan

Re-running the census, the inventory or full-corpus validation to freshen the
numbers (B.1) · building the source-document browser, raw-data export or audit
trail (C) · renumbering the README's pipeline levels (B.5) · changing
`determine_status()`'s thresholds · the Level 6 human audit, whose tooling is
done and whose review is still pending.
