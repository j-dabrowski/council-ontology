# /record — a browsable, non-argued page for residents

Status: **plan only, nothing built.** Written 2026-09-11.
Seventh in the sequence. Assumes the registry, the framing components, the
surface projections, /watch, /method and the evidence chain are all built.
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

Phase 1 is features 1 and 2, as the brief orders it. Phases 2 and 3 follow on a
go-ahead.

---

## Part A — What the data holds, and what it does not

### A.1 The privacy problem: planning records name private residents

**This is the finding that shapes feature 1.**

`planning_applications.applicant_name` is populated for **2,975 of 3,116**
applications. These are not councillors — they are ordinary residents. A live
example already sitting in `dose.json`'s drill-down payload:

> Application: 100DA - 2012
> Owner: Mr Peter Northcott & Ms Gillian Northcott
> Applicant: Mr Peter Northcott & Ms Gillian Northcott

attached to "Lot 197 (No. 27) Ruislip Street, West Leederville".

Across 3,000 sampled planning evidence quotes: **12% carry an
"Owner:"/"Applicant:" label**, 3% carry a personal title (Mr/Mrs/Ms/Dr).

Feature 1 as briefed — type a street, get every application on it, with a link
to the source quote — would therefore publish **private individuals' names
attached to their home addresses**, searchable by street. That is a different
and worse exposure than the councillor question this project's gates were built
for, and the existing guardrail cannot see it: `usable_roster_names()` and
`frontend/src/guardrail.ts` both match the **councillor** roster only. A
homeowner's name passes every check the project currently runs.

Nothing is exposed today, because `dose.json` and `planning.json` are full-tier
and ship to `data/published_full/`. /record is the change that would flip that
switch. See B.1 — it is the one decision that must be settled before Step 1.

### A.2 `public_interest` is `false` for all 29 registry rows

The page "shows only rows flagged `public_interest`". Nothing is flagged — the
field was seeded `false` in `TEST_REGISTRY_PLAN.md` Step 2 and appears on the
"deliberately not in this plan" list of every plan since. As written, the page
renders nothing.

Two things follow. Someone has to decide which tests are public-interest (B.2,
with a proposed set in C.1). And separately: **four of the five features are not
registry tests at all** — an address browser, a councillor card, a topic chart
and a curated moment have no `test_id`. Only the objector calculator maps to one
(`planning.objection_responsiveness`). So `title_public` and `public_interest`
govern the page's *framing and its registry-derived content*, not its feature
set. /record is not a projection of the registry the way the scorecard is, and
the plan should not pretend otherwise.

### A.3 Site data is good, and street lookup is tractable

2,454 sites, **3,105 of 3,116** applications linked to one. Addresses are
consistently structured:

```
Lot 82 (No. 25) Brighton Street, West Leederville
111 Harborne Street, Wembley
Lot 1 (No. 30) Branksome Gardens, City Beach
```

A crude street-type regex extracts a street name from **2,417 of 2,454 (98%)**.
Busiest streets: Cambridge Street (191 sites), Salvado Road (82), Branksome
Gardens (63), St Leonards Avenue (56), The Boulevard (38).

The `sites.suburb` column is **100% NULL** — the suburb is present as the
trailing comma-separated token of `address` and must be parsed from there.
`latitude`/`longitude` are populated (the geocoder ran), so a map is possible
later; it is not in this plan.

### A.4 Every objector-calculator figure checks out exactly

`objection_dose_response()` on the live corpus:

| objectors | applications | refused | refusal rate |
|---|---|---|---|
| 0 | 1,674 | 314 | **18.8%** |
| 1 | 818 | 179 | **21.9%** |
| 2–4 | 147 | 36 | **24.5%** |
| 5+ | **10** | 5 | **50.0%** |

`total_decided` 2,649, `max_objections` 22, and `headline_examples[0]` is the
betting agency — "Additional land use of 'Use Not Listed' (Betting Agency)…",
22 objectors. Feature 2 needs no new computation, only a new presentation.

### A.5 Councillor cards: three fields exist, two do not

`councillors.json` carries `tenure_years`, `first_vote`/`last_vote`, `n_votes`,
`roles`, `n_contested`, and the declarations list. **Motions moved** and **most
frequent seconder** are absent but derivable — `Motion.moved_by_id` /
`seconded_by_id`, and `co_mover_pairs()` already computes the pairs for
`co-movers.json`.

The same file also carries `win_rate`, `dissent_rate`, `dissent_effectiveness`,
`recusal_rate`, and declaration quotes with verbatim text. Those are exactly the
fields the brief's "factual fields only, no characterisation, no ranking
language" rules out. See B.3 — the answer is a reduced projection, not
publishing this file.

### A.6 Topic drift is a pure render of existing data

`trends.json`'s `topics` is 32 years × 6 categories (governance, procedural,
other, infrastructure, community, planning). 1995 reads: other 458, governance
155, planning 146, procedural 121, community 90, infrastructure 82. Feature 4
computes nothing new. Note "other" is the largest bucket in the sample year —
the chart must not hide that behind a tidier five-category story.

### A.7 The notable moments check out

- **Gary Mack, 30.8 years** — longest tenure in `tenure.json` (next: 23.0, 22.2).
- **2020 confidentiality spike** — `transparency.json` `peak_year` 2020,
  `peak_pct` 17.2%, against 8.3% in 2019 and 15.9% in 2021.
- **The 22-objector betting agency** — A.4.

Two of the three name or centre on an individual, on a page for general readers.
That is defensible for a tenure record (a public, neutral, verifiable fact) and
needs no argument; it is still a named-individual claim and belongs in the
Editor's scope, not outside it.

### A.8 Every snapshot this page needs is full-tier

`SNAPSHOT_TIER = {"watch": "public", "method": "public"}`. Everything else
defaults to `full` and ships to `data/published_full/`.

/record needs `planning`, `dose`, `councillors`, `tenure`, `trends` and
`transparency` — **none of which publish**. Built as briefed against today's
tiers, the page renders empty in production, exactly as /method did before
`49baefe`. See B.4.

---

## Part B — Decisions

### B.1 DECIDE FIRST: no private individual's name appears on /record.

**Recommendation, and the plan assumes it:** the page's payloads carry no
`applicant_name`, no owner name, and no quote text that contains one.

Concretely:

- `applicant_name` is never projected into a /record snapshot. It stays in the
  database and in full-tier artifacts.
- The evidence chain's "one click from a source quote" holds for everything on
  this page **except** planning-application quotes, which are shown with
  owner/applicant lines removed. A quote that cannot be shown that way shows its
  document reference — filename, meeting date, page — and the words "source
  quote withheld: names a private individual". A withheld quote is visible as
  withheld, per the project's standing convention that gaps are shown.
- The guardrail learns a second class. `frontend/src/guardrail.ts` and
  `usable_roster_names()` both match councillors only; neither can see "Mr Peter
  Northcott". Step 2 adds a **pattern-based** redactor for the
  `Owner:`/`Applicant:`/personal-title shapes A.1 measured, and a test that the
  /record payload contains none of them.

Pattern matching will not be perfect — a bare name with no label and no title
will pass. Say so in the docs rather than implying the redaction is complete,
and keep `applicant_name` out of the payload so the structured field, at least,
is certain.

This is a privacy decision, not a defamation one, and the existing gates do not
cover it. If the answer is instead "publish the names, they are in a public
minute", that is a legitimate position but it must be an explicit decision with
the Editor's view on it — not a side effect of shipping a street lookup.

### B.2 `public_interest` has to be populated before the page has content.

Proposed set in C.1 — nine tests whose questions a resident would actually ask.
The field governs framing and any registry-derived content on /record; it is not
what generates the five features (A.2).

Decide the set before Step 1. It is a content judgement, and the plan should not
make it silently.

### B.3 Councillor cards publish a reduced projection, not `councillors.json`.

A new `record_councillors` payload with the brief's five fields only: years
served, motions moved, votes cast, most frequent seconder, contested-vote
record — the last as **counts** (contested votes, on the winning side, on the
losing side), not as a `win_rate`. No `dissent_rate`, no
`dissent_effectiveness`, no `recusal_rate`, no declarations.

Order the cards **alphabetically or by first year served**, never by any
performance field. Sorting a list of people by win rate is ranking language
expressed as a UI affordance, and the brief rules it out.

"Most frequent seconder" names a second councillor on the first one's card — an
association claim, mild but real. Keep it (it is factual and symmetric) and
confirm the Editor sees it.

### B.4 Tier decisions, one per snapshot, not one blanket flip.

/record needs six snapshots (A.8). They are not equivalent:

| snapshot | contains | recommendation |
|---|---|---|
| `trends` | year × topic counts, no names | public |
| `transparency` | year × confidential share, category totals | public |
| `dose` | buckets, plus `apps[]` with address, description **and quote** | public **only after** B.1's redaction; drop `apps[].quote` names |
| `planning` | year trend + objection groups | public |
| `tenure` | per-councillor years, names | public — tenure is neutral and verifiable |
| `councillors` | rates, effectiveness, declaration quotes | **stay full-tier**; publish `record_councillors` instead (B.3) |

Each flip is a publish-boundary change. Do them in the step that needs them, not
in one sweep, so each gets its own review.

### B.5 The street index is a new derived artifact.

Feature 1 needs street → sites → applications. Build `record_streets.json` at
draft time: one entry per extracted street name, carrying its sites and each
site's applications (date, description, objection count, outcome, document
reference). Parse the suburb from the address trailing token (A.3).

Two honest limits to carry in the payload and render on the page:
- **37 of 2,454 sites (2%)** yield no street name from the address and are
  reachable only by full-address search.
- **11 applications** have no linked site and appear under no street at all.

Measure both at build time rather than trusting these figures — the corpus moves.

### B.6 Plain language is enforced, not intended.

The brief bans "valence", "CIPFA-B" and bare sample sizes from primary copy. Add
a test over the /record payload and page source for a small banned list —
`valence`, `CIPFA`, `Nolan`, `severity`, `n =`, `p <`, `institutional`,
`not computable` — with sample sizes allowed only inside a field named
`caveat`. A rule nobody checks will not survive three commits.

`title_public` copy is already written for all 29 rows and is the vocabulary
this page speaks.

### B.7 Build 1 and 2, then stop.

The brief's own priority. Phase 1 is features 1–2 plus the page shell. Phase 2
is feature 3 (councillor cards, and the heaviest tier decision after B.1).
Phase 3 is 4–5. Each phase ends with a look before the next starts.

---

## Part C — Tables

### C.1 Proposed `public_interest` set

Nine of 29, chosen as the questions a resident would ask unprompted. Each shown
with its existing `title_public`.

| id | title_public |
|---|---|
| `planning.objection_responsiveness` | Whether objecting changes the outcome |
| `planning.big_dollar_leniency` | Whether expensive developments get approved more easily |
| `planning.repeat_applicant` | Whether regular applicants do better |
| `conflict.recusal_management` | When councillors declare a conflict, do they leave? |
| `transparency.confidential_share` | What gets decided behind closed doors |
| `engagement.question_responsiveness` | Are residents' questions actually answered? |
| `engagement.participation` | How much residents take part in meetings |
| `procurement.concentration` | Who gets the council's contract money |
| `governance.incumbency` | How long councillors stay |

Deliberately excluded: the procurement-integrity internals
(`threshold_gaming`, `decider_supplier_conflict`, `single_source`), the
chamber-culture measures (`power_spread`, `durable_faction`, `freshman_effect`,
`election_cycle`, `chair_capture`, `oversight_body_capture`), and everything
whose title only makes sense next to a severity ladder. Adjust freely — this is
a proposal, not a finding.

### C.2 `record_streets.json` shape

```
{ generated_at, source: "data/council.db",
  coverage: { sites: 2454, sites_with_street: 2417, applications: 3116,
              applications_with_site: 3105, note: "…" },
  streets: [
    { name: "Cambridge Street", suburbs: ["Wembley", "West Leederville"],
      n_sites: 191, n_applications: …,
      sites: [ { address, lot_number,
                 applications: [ { date, description, n_objectors, outcome,
                                   reference, evidence: { filename, meeting_date, page } } ] } ] } ] }
```

No `applicant_name` anywhere in it (B.1). `evidence` is the document reference;
the quote itself is fetched through the existing evidence chain at click time,
redacted per B.1.

---

## Part D — The steps

Phase 1 is Steps 1–5. Phases 2 and 3 (Steps 6–8) need a go-ahead.

Every step ends with `pytest -q` where it touches Python, and `npm run lint &&
npm run build` where it touches the frontend.

**Standing context.** Read `docs/MAP.md` (per `CLAUDE.md`, every session),
`docs/frontend/TEST_REGISTRY_PLAN.md` Parts B–C,
`docs/frontend/EVIDENCE_CHAIN_PLAN.md` Part B, and
`docs/frontend/INTERACTIVITY.md`'s hard rule.

**Three constraints govern every step:**
- *No private individual's name reaches a /record payload or page* (B.1) —
  enforced by a test, not by care.
- *Plain language* (B.6) — enforced by the banned-vocabulary test.
- *Aggregate by default.* Individual detail is reachable on request, never on a
  landing view.

**One commit per step**, committed once its acceptance checks pass; if they
fail, do not commit — report. `docs/TESTING.md` "Commit conventions" applies:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — `public_interest`, and the page shell

Settle B.1 and B.2 first.

Set `public_interest: true` on the agreed rows in `config/test_registry.json`.
Extend `tests/test_test_registry.py`: at least one row is flagged, and every
flagged row has a non-empty `title_public`.

Then a `/record` route rendering only its own heading and the plain-language
intro — no severity chips, no principles, no Objection/Response. Add it to
`SiteNav`.

Acceptance: build + lint; `pytest -q`; the route renders; the flagged count
matches the decision.

---

### Step 2 — The private-name redactor

Before any planning data reaches the page. Per B.1:

- A pattern redactor for the `Owner:` / `Applicant:` / personal-title shapes,
  in `src/` so the export uses it and in `frontend/src/guardrail.ts` so the
  render path does too — or in one place both can reach, which is better.
- A test over a 3,000-quote sample asserting the redactor removes every
  `Owner:`/`Applicant:` line A.1 found, and a test that a name with no label and
  no title is **not** caught — so the limit is recorded in the suite rather than
  assumed away.

Report the real percentages you measure; A.1's 12% and 3% are from 2026-09-11.

Acceptance: both tests pass, including the one that documents the limit.

---

### Step 3 — `record_streets.json`

Part C.2's shape, built from `sites` + `planning_applications` + the evidence
document reference. Parse the street name and suburb from `address` (A.3).

Report at build time: how many sites yield no street name, how many
applications have no site, and the busiest ten streets. Carry the first two into
the payload's `coverage` block (B.5) — they render on the page as the lookup's
stated limits.

Assert in tests: no `applicant_name` field, and no `Owner:`/`Applicant:` string,
anywhere in the serialised payload.

Acceptance: the file builds; the coverage numbers reported; the name tests pass.

---

### Step 4 — Address lookup

Type-ahead over street names, then the applications on that street: date,
description, objection count, outcome, and a link to the source document.

Plain language throughout. The two coverage limits from Step 3 render as a
caveat line beneath the results, not as a footnote elsewhere.

Publish `record_streets` and `planning` at public tier (B.4) — each flip in this
step, each noted.

Acceptance: build + lint; look up three streets including Cambridge Street (191
sites) and one with a single site; confirm no applicant or owner name appears
anywhere on screen, including inside an expanded source quote.

---

### Step 5 — Objector calculator, then stop

Interactive: as the objector count moves 0 → 1 → 2–4 → 5+, the refusal rate
moves 18.8% → 21.9% → 24.5% → 50%. All four figures come from `dose.json`
(A.4), never from JSX.

Two things must be on screen, not buried: the 5+ bucket rests on **10
applications** and is directional; and the most-opposed application on record —
the betting agency, 22 objectors — **was refused**. Sample sizes go in the
caveat line, per B.6, not the headline.

Publish `dose` at public tier, after confirming B.1's redaction covers
`apps[].quote` (A.1's example lives in that exact field).

**Stop here.** Report: the four rates as rendered, the caveat copy, and the
result of the private-name check against the dose payload. Phases 2 and 3 need a
go-ahead.

---

### Step 6 — PHASE 2, on a go-ahead: councillor cards

B.3's reduced projection: years served, motions moved, votes cast, most frequent
seconder, contested-vote counts. Derive motions moved and the seconder from
`Motion.moved_by_id` / `co_mover_pairs()` (A.5). `councillors.json` stays
full-tier.

Cards ordered alphabetically or by first year served. No rate, no ranking, no
sorting by performance. Aggregate framing on the landing view; a card opens on
request.

---

### Step 7 — PHASE 3, on a go-ahead: topic drift

A render of `trends.json`'s 32 × 6 grid (A.6). Publish `trends` at public tier.
Do not collapse or rename the "other" bucket to make the chart tidier — it is
the largest category in some years and hiding it would misstate what the council
spent its time on.

---

### Step 8 — PHASE 3, on a go-ahead: notable moments

The three in A.7, each with its source quote through the evidence chain, each
sourced from a snapshot rather than typed. Publish `tenure` and `transparency`
at public tier.

Two of the three centre on a named individual or a single year's spike; both
belong in the Editor's scope for a pass before they ship.

---

### Deliberately not in this plan

Publishing `councillors.json` (B.3) · a map view of the street lookup, though
the geocoding exists (A.3) · full-text search across minutes · resolving the 37
street-less sites or the 11 site-less applications by hand · any new analysis —
every figure on this page already exists · Phases 2 and 3 without a go-ahead.
