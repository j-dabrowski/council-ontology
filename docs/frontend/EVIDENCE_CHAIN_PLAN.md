# The evidence chain — figure → rows → verbatim quote → source document

Status: **plan only, nothing built.** Written 2026-09-07.
Sixth in the sequence, after `TEST_REGISTRY_PLAN.md`, `PANEL_FRAMING_PLAN.md`,
`SURFACE_PROJECTION_PLAN.md`, `WATCH_FEED_PLAN.md` (all built) and
`METHOD_PAGE_PLAN.md`.
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

Phase 1 (Steps 1–5) does **one test end to end** —
`governance.officer_ratification` — and stops. Phase 2 generalises, and only
after a human has looked at Phase 1.

---

## Part A — What is actually there

### A.1 The asset is real: 71,486 evidence rows across 13 entity tables

| entity_table | rows | | entity_table | rows |
|---|---|---|---|---|
| motions | 29,283 | | delegated_decisions | 1,342 |
| other_items | 16,332 | | tenders | 1,326 |
| planning_applications | 5,861 | | committee_reports | 1,116 |
| public_questions | 5,787 | | appointments | 980 |
| budget_items | 4,604 | | building_permits | 755 |
| interest_declarations | 2,097 | | petitions | 450 |
| deputations | 1,553 | | **total** | **71,486** |

Covering **439 meetings** — exactly the set with `minutes_text` populated. The
`votes` table has no evidence rows at all (a vote's receipt is its motion or
declaration), which is already noted in `docs/frontend/INTERACTIVITY.md`.

### A.2 `char_offset IS NULL` is NOT the paraphrase flag. Using it would be a disaster.

**80.5% of evidence rows (57,551 of 71,486) have a null `char_offset`.** Taken
at face value that says four fifths of the corpus's receipts are paraphrase —
on the feature built to demonstrate rigour.

It is not what the field means, and the extractor says so itself
(`src/extraction/extractor.py:650`):

> Stored as a best-effort convenience for UI/lookup (e.g. highlighting a span).
> **Do NOT use `char_offset IS NULL` as a hallucination signal** — validation
> code should normalise both source text and quote at query time before
> matching.

`_resolve_offset` is a bare `text.find(quote)`: any whitespace difference, any
PDF word-split artefact, and it returns null.

Classifying a 400-row random sample of the null-offset rows with the validation
layer's own three tiers, against `minutes_text`:

| | share of null-offset rows | share of all evidence |
|---|---|---|
| matches after whitespace normalisation | 68% | ~55% |
| matches after stripped normalisation (letters+digits, ≥15 chars) | 22% | ~18% |
| **genuine paraphrase** | **11%** | **~8.7%** |

So roughly **91% of the corpus's quotes are recoverable as verbatim**, and
reading `char_offset` as the flag would mislabel about 72% of all evidence.
See B.2.

### A.3 There are two source texts, and they disagree

- `meetings.minutes_text` — what the extractor saw and what `char_offset`
  indexes into. Present for 439 of 580 meetings.
- A fresh PyMuPDF extraction of the PDF — what `src/validation/core.py`'s
  `extract_pdf_text()` uses.

`validation/summary.json` reports a **3.9%** corpus paraphrase rate against the
PDF text; the same three-tier rule against `minutes_text` gives **8.7%** (A.2).
The PDF is the better reference. Which text the chain resolves against changes
the number a reader sees, so it has to be stated, not left implicit — B.3.

### A.4 The API is not deployed, and the database is not deployable

The brief says "add API endpoints under `api/`". `api/main.py` exists and works
locally (FastAPI, 8 endpoints, `uvicorn ... --port 8000`, proxied by Vite in
dev). But:

- `docs/CICD_DECISIONS.md` logs **"API → Cloud Run deploy. No Dockerfile exists
  yet, no deploy workflow for `api/`"** under undecided infrastructure.
- `.gitignore:29` excludes `data/council.db`; `.gitignore:28` excludes
  `data/raw/cambridge/*.pdf`. The database is uploaded to GCS by hand.
- The published frontend reads static snapshots from `frontend/public/data/`.
  `VITE_API_URL` defaults to `http://localhost:8000`.

So endpoints alone would give the live site nothing. This is not a reason to
skip them — it is a reason to build the query once and serve it two ways. B.1.

### A.5 The evidence join already exists, four times, in a lossy form

`src/cli.py` inlines an `ExtractionEvidence` join at four points (lines ~1962,
2169, 2293, 2350). The divergence one is representative:

```python
div_quote.setdefault(mid, qt)      # first quote per entity, nothing else
```

One quote per entity, no offset, no match tier, no document reference, no
handling of entities with no evidence at all. That is what the panels render
today through `<SourceQuote>`. Phase 1 replaces it with a resolver that returns
all of it; the other three call sites are Phase 2.

### A.6 Page numbers are derivable, but only where the PDF is

`pymupdf` is a **core** dependency (`pyproject.toml`), and it reads text
per-page — so a quote's page can be found by searching page by page. But the
PDFs are gitignored and absent from any deployed environment.

Therefore: **page is computed at export time**, locally, where the PDFs are, and
shipped in the snapshot. The API path returns `page: null` when the PDF is
absent rather than guessing. B.4.

### A.7 `governance.officer_ratification` is the right starting point

`officer_divergence()` returns 203 matched agenda/minutes pairs, 6 of them
departures. `divergence.json` already carries one quote per exception, and
`DivergencePanel` already renders an expandable table with officer
recommendation, motion text and `<SourceQuote>`. The chain is half-built for the
6 exceptions and absent for the other 197 matched pairs — which is exactly the
gap worth closing first, because "we checked 203 and here are all 203" is a
stronger claim than "here are the 6 we found".

Each pair has **two** sides — an agenda motion and a minutes motion — so the
chain resolves evidence for both, not just the minutes side the snapshot
carries today.

---

## Part B — Decisions

### B.1 One resolver, two callers: an API endpoint and a static snapshot.

The brief asks for endpoints; the live site needs static files (A.4). Both, from
one function — which is the architecture the project already uses, where
`src/analysis/queries.py` feeds `api/main.py` and `cmd_draft`'s snapshot export
alike.

- `src/analysis/evidence.py` holds the resolver. It is the only place an
  `ExtractionEvidence` join is written.
- `api/main.py` gets `/api/evidence/{test_id}` over it — real, tested, useful
  locally and ready for the day the API deploys.
- `cmd_draft` exports the same output to `evidence/<test_id>.json`, which
  publishes and which the frontend reads.

**Do not make the frontend depend on the API.** A panel that only reveals its
sources on a developer's machine is not an evidence chain. Standing up Cloud Run
is not in this plan.

### B.2 Three match tiers, computed at request time, never read from `char_offset`.

Reuse `src/validation/core.py`'s `_norm`, `_norm_stripped` and
`_MIN_STRIPPED_LEN` — do not write a fourth matcher. Every quote carries:

| tier | meaning | how it renders |
|---|---|---|
| `exact` | found verbatim in the source text | quoted plainly |
| `normalised` | found after whitespace normalisation | quoted plainly; PDF line-wrapping is not a paraphrase |
| `stripped` | found after letters-and-digits normalisation | quoted, labelled "matched allowing for PDF text artefacts" |
| `paraphrase` | not found by any of the above | **labelled paraphrase, not presented as verbatim** |
| `no_evidence` | no evidence row for this entity | "no source quote recorded" |

The brief's requirement 3 is satisfied by the `paraphrase` tier alone —
about 8.7% of rows (A.2). Collapsing `normalised` and `stripped` into
"paraphrase" would be false, and collapsing them into "exact" would overstate.
Four tiers plus the empty case, because that is what the data actually contains.

`char_offset` may still be used as a fast path when it is non-null, but a null
never implies a tier.

### B.3 Resolve against the PDF, fall back to `minutes_text`, say which was used.

Per A.3 the PDF gives the better match rate and is what the published 3.9%
figure is measured against. So: resolve against the PyMuPDF text where the PDF
is available (export time), else `minutes_text`, and record which on every
quote as `resolved_against: "pdf" | "minutes_text"`. A reader comparing the
chain's paraphrase share against `/method`'s 3.9% deserves to know they were
measured against the same text — or that they were not.

### B.4 Page is computed at export, null in the API, never guessed.

`page` is the 1-based PDF page whose text contains the match, found with
pymupdf at export time. Where the PDF is absent it is `null` and the UI says
"page not recorded". Never derive a page from a character offset by assuming a
fixed page length.

### B.5 A row with no evidence is rendered, not dropped.

The brief's constraint, and it inverts the current behaviour: today
`div_quote.get(...)` yields `None` and the row simply shows nothing. Every row
in the chain appears, and a row with no evidence carries the `no_evidence` tier
and the words **"no source quote recorded"**. A chain that hides its gaps is
worth less than one that shows them — the same argument the scorecard's
not-computable rows already make.

Step 1 must report how many of the 203 pairs have no evidence on one or both
sides. Nobody knows that number yet.

### B.6 Never synthesise or tidy a quote.

The brief's other constraint, and it needs a mechanism, not just an intention:
the resolver returns `quote_text` from the database **unmodified** — no
trimming, no ellipsis, no case folding, no whitespace collapsing in the
returned value. Normalisation exists only inside the matcher, to decide the
tier; it never touches what is displayed. `<SourceQuote>` already renders
`quote.trim()` — even that should go, or be justified.

---

## Part C — The record shape

One entry per row behind a figure:

```json
{
  "entity_table": "motions",
  "entity_id": 8412,
  "role": "minutes_motion",
  "meeting_id": 258,
  "meeting_date": "2026-05-12",
  "document": {"filename": "0cb7f9ed.pdf", "url": "https://…", "page": 47},
  "quotes": [
    {"text": "…verbatim, unmodified…",
     "tier": "normalised",
     "char_offset": null,
     "resolved_offset": 128244,
     "resolved_against": "pdf"}
  ]
}
```

- `quotes` is a **list** — an entity may have several evidence rows, and A.5's
  `setdefault` currently throws all but the first away.
- `quotes: []` with `"tier": "no_evidence"` on the entry is B.5's case.
- `resolved_offset` is what the matcher found now; `char_offset` is what the
  extractor stored. Keeping both makes the A.2 discrepancy inspectable rather
  than papered over.

For `governance.officer_ratification` the payload is one entry per side of each
of the 203 pairs, grouped by pair, with the pair carrying `diverged: true|false`
so the 6 exceptions are a filter over the 203 rather than a separate list.

---

## Part D — The steps

**Phase 1 is Steps 1–5, one test, end to end. Stop there and show the user.**
Phase 2 (Step 6) generalises and needs an explicit go-ahead.

Every step ends with `pytest -q` where it touches Python, and `npm run lint &&
npm run build` where it touches the frontend.

**Standing context.** Read `docs/MAP.md`, `docs/frontend/INTERACTIVITY.md`
(the drill-down recipe and the hard rule), and `docs/frontend/METHOD_PAGE_PLAN.md`
B.1 if it has been built — the paraphrase share this feature exposes and the
one `/method` publishes must not contradict each other.

**Two constraints govern every step:**
- *Never synthesise or tidy a quote.* Verbatim from the database, or flagged
  (B.6).
- *Never hide a row.* Missing evidence is rendered as "no source quote
  recorded" (B.5).

**One commit per step**, committed once its acceptance checks pass; if they
fail, do not commit — report. `docs/TESTING.md` "Commit conventions" applies:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — `src/analysis/evidence.py`, the resolver

`resolve_evidence(session, entity_refs, council_id)` → Part C's entries, for a
list of `(entity_table, entity_id, role)`. It:

- joins `ExtractionEvidence` once, returning **all** quotes per entity;
- classifies each with the four tiers of B.2, reusing
  `src/validation/core.py`'s normalisers — do not write a new matcher;
- resolves against the PDF where present, else `minutes_text`, recording which
  (B.3);
- computes `page` where the PDF is present, else null (B.4);
- returns an entry for every requested ref, including those with no evidence
  (B.5);
- returns `quote_text` unmodified (B.6).

Then a thin `evidence_for_officer_ratification(session, council_id)` building
the refs from `officer_divergence()`'s 203 pairs, both sides.

**Report, for those 203 pairs:** the tier split across all their quotes, how
many sides have no evidence at all, and how the paraphrase share compares with
`validation/summary.json`'s 3.9%. If the paraphrase share is far above that,
say so — it is a finding about the corpus, not a bug to tune away.

Acceptance: unit tests for each tier including a genuine paraphrase and an
entity with no evidence; the report above with real numbers.

---

### Step 2 — `/api/evidence/{test_id}`

In `api/main.py`, over Step 1's resolver, with optional `year`, `councillor`
and `contractor` filters — implemented only where the test's underlying query
supports them (for `officer_ratification`, `year`). A filter the test cannot
support returns 400 with a message naming what it does support, rather than
being silently ignored.

Unknown `test_id` → 404 naming the registry as the source of valid ids.

Note in the module docstring that this endpoint is not reachable from the
published site (A.4) and that the frontend reads the snapshot instead — so the
next reader does not wire the frontend to it.

Acceptance: `uvicorn api.main:app` locally; the endpoint returns the 203 pairs;
filter and error paths exercised.

---

### Step 3 — Export `evidence/governance.officer_ratification.json`

`cmd_draft` writes it under an `evidence/` subdirectory of the draft; it joins
`manifest.snapshots` and publishes (B.1), same path `watch.json` uses.

**Measure and report the file size.** One test's 203 pairs should be small, but
the number decides whether Phase 2 can ship every test as static files or needs
per-test lazy loading — record it for that decision.

The payload carries verbatim minute text, so it goes through the draft → review
→ publish path like everything else. It names councillors wherever a motion's
quote does, which is inherent to a source quote and is why it is a receipt; note
that in the export's comment and confirm the Editor's scope covers it.

Acceptance: the file exists in a draft run, publishes, and its pair count is
203.

---

### Step 4 — The evidence drawer

Extend `frontend/src/components/DrillDown.tsx` — do not start a new drawer.
`<SourceQuote>` gains the tier vocabulary:

- `exact` / `normalised` — the quote, plainly.
- `stripped` — the quote, with "matched allowing for PDF text artefacts".
- `paraphrase` — the quote, clearly labelled **paraphrase — not found verbatim
  in the source**; never styled to look like a verbatim receipt.
- `no_evidence` — **"no source quote recorded"**, in the row's normal position.

Each quote shows its document filename, meeting date and page (or "page not
recorded"), and links to `minutes_pdf_url` where present.

Remove the `.trim()` currently applied to the quote, or justify keeping it in a
comment (B.6).

Acceptance: build + lint; all five states rendered from real data, screenshotted
or described row by row.

---

### Step 5 — Wire it into `DivergencePanel`, then stop

The existing expandable exceptions table becomes the chain: all **203** pairs
reachable (not just the 6 departures), each expanding to both sides' quotes
through Step 4's drawer. Keep the departures filtered to the front — they are
the finding; the other 197 are the evidence that the finding was tested.

The panel keeps reading its own snapshot for the figures and loads the evidence
payload separately, so a missing evidence file degrades to today's behaviour
rather than blanking the panel.

**Stop here.** Report: the tier split a reader actually sees, how many of the
203 show "no source quote recorded", and the file size from Step 3. Phase 2
needs a human's go-ahead.

Acceptance: build + lint; the chain demonstrated end to end on one figure —
name the figure, the rows, a quote, and its document and page.

---

### Step 6 — PHASE 2, on a go-ahead only: generalise

Do not start without one.

The registry already has the fields this needs: `evidence_query` (the
`queries.py` function behind each test) and `evidence_snapshot`. Generalising
means a per-test `entity_refs` builder for each test that has an
`evidence_query`, then reusing everything above.

Order the work by what the panels already support: the three other inline joins
in `src/cli.py` (A.5) are the obvious next ones, since their panels already have
click-through. Tests whose `evidence_query` is `tests.<generator>` — computed
inline, with no query function — have no entity list to resolve and are the last
group, not the first.

Decide static-per-test versus lazy-loaded from Step 3's measured size before
building, not after.

---

### Deliberately not in this plan

Deploying the API (A.4 — `docs/CICD_DECISIONS.md`'s open item) · changing
`_resolve_offset` or backfilling `char_offset` · re-running extraction or
validation · a full-text PDF viewer in the browser · highlighting the quote
inside a rendered page · evidence for the `votes` table, which has none by
design · Phase 2 without a go-ahead.
