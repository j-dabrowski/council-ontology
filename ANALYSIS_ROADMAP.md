# Council-Ontology Analysis Roadmap

## Purpose

Defines the analysis features to build on top of the extracted corpus, the query functions
that power them, and the data contracts each visualisation needs. Scoped to the 2024+ corpus
first (244 docs already extracted); notes what changes when the pre-2024 batch lands.

**The division of labour:**
- This doc covers the data and query layer: new functions in `src/analysis/queries.py`,
  new CLI subcommands under `council analyse`, and one data-enrichment script.
- Frontend layout and component choices are a separate decision; this doc defines what
  data each chart needs and in what shape.

**Corpus note used throughout this doc:**
- **2024+ corpus**: 244 extracted docs (2024–2026). This is what's in the DB now.
  All query functions default to `from_year=2024` until the full corpus lands.
- **Full corpus**: 590 docs (1995–2026). Pre-2024 extraction is deferred until the demo
  frontend is built. When it lands, re-run all queries with `--all-years` to widen scope.
  No code changes needed — just remove the year filter.

---

## Status table

### Already complete

| # | Feature | CLI command | Notes |
|---|---------|-------------|-------|
| ✅ A1 | All councillors by vote count | `council analyse cambridge councillors` | No year filter; includes name stubs |
| ✅ A2 | Pairwise voting alignment matrix | `council analyse cambridge alignment [--min-shared N] [--limit N]` | No `--from-year` at CLI level yet (fix pending) |
| ✅ A3 | Contested motions list | `council analyse cambridge contested [--min-against N] [--limit N]` | All years, no filter |
| ✅ A4 | Top planning sites by application count | `council analyse cambridge planning [--limit N]` | Raw addresses, not geocoded |
| ✅ A5 | Single councillor vote summary | `council analyse cambridge councillor --name NAME` | Family name partial match; no year filter |
| ✅ A6 | Motions filtered by tag | `council analyse cambridge motions --tag TAG [--limit N]` | Tag is substring match on `motions.tags` |
| ✅ A7 | ALLY/OPPONENT relationship edges | `council build-relationships cambridge [--from-year YYYY]` | 62 ALLY edges written (2024+); 0 OPPONENT pairs |

### Pending

| # | Feature | Depends on | Status | 2024+ useful? |
|---|---------|------------|--------|--------------|
| Q1 | Councillor activity ranges | DB | ✅ **Done** | 13 councillors, 9 active |
| Q2 | Contestation rate by year | DB | ✅ **Done** | 2024: 15%, 2025: 9%, 2026: 5% |
| Q3 | Topic distribution by year | DB | ✅ **Done** | 8 tags tracked |
| Q4 | Co-mover pairs | DB | ✅ **Done** | Cutler→Le Page leads (30) |
| Q5 | Interest declarations by councillor + type | DB | ✅ **Done** | Le Page 72, Barlow 69 |
| Q6 | Public engagement by year | DB | ✅ **Done** | 610 questions, 134 deputations |
| Q7 | Budget aggregate by year | DB | ✅ **Done** | 1,330 items with amounts |
| Q8 | Planning approval rate + refusal reasons | DB | ✅ **Done** | 50% approval (8/16 decided, 2024+) |
| E1 | Geocode planning sites | `sites.latitude/longitude` already exist | ✅ **Done** | `scripts/geocode_sites.py` built |
| E2 | Officer divergence matching | agenda+minutes extractions | ✅ **Done** | 133 matched pairs; 4 diverged (3%) |
| C1 | `council analyse cambridge activity` CLI | Q1 | ✅ **Done** | — |
| C2 | `council analyse cambridge trends` CLI | Q2 + Q3 | ✅ **Done** | — |
| C3 | `council analyse cambridge co-movers` CLI | Q4 | ✅ **Done** | — |
| C4 | `council analyse cambridge interests` CLI | Q5 | ✅ **Done** | — |
| C5 | `council analyse cambridge engagement` CLI | Q6 | ✅ **Done** | — |
| C6 | `council analyse cambridge budget` CLI | Q7 | ✅ **Done** | — |
| C7 | `council analyse cambridge divergence` CLI | E2 | ✅ **Done** | — |
| Fix | `--from-year` / `--to-year` on all `analyse` subcommands | — | ✅ **Done** | All existing + new subcommands support year filters |

---

## Completed analysis features

### A1 — All councillors by vote count

`council analyse cambridge councillors`

Prints every councillor seen in the DB for this council, sorted by total vote count. Sourced
from a direct `COUNT(votes)` join — no year filtering. Includes name-stub councillors (AGM proxy
voters with 1–7 votes) and dedup artifacts. Useful as a raw roster; use Q1 for a cleaned,
date-bounded version.

**Limitations:** No `--from-year` filter. No active/inactive label. No dissent rate.

### A2 — Pairwise voting alignment matrix

`council analyse cambridge alignment [--min-shared N] [--limit N]`

Calls `voting_alignment_matrix()` in `src/analysis/queries.py`. Computes agreement rate
for every councillor pair who share ≥N votes (default 5). Colour-coded output: green ≥85%,
yellow 50–85%, red <50%.

**Current results (all years, min-shared=5):** All pairs with enough shared votes are in
the green band. Cambridge votes near-unanimously — the matrix alone doesn't reveal structure.
**Limitation:** `voting_alignment_matrix()` accepts `from_year`/`to_year` but the CLI does not
expose them. The "Fix" item in the pending table adds these flags.

### A3 — Contested motions list

`council analyse cambridge contested [--min-against N] [--limit N]`

Lists carried motions with at least N dissenting votes (default 2). Sorted by `votes_against`
descending. Shows date, item number, truncated title, for/against counts.

**Current results:** 68 motions carried with ≥1 against; 17 with ≥2; 15 with ≥3; 4 with all
possible votes against. No year filter — the list is dominated by 2024–2026 data because
pre-2024 extraction is sparse.

### A4 — Top planning sites by application count

`council analyse cambridge planning [--limit N]`

Calls `top_planning_sites()`. Groups `planning_applications` by `site_id`, counts applications
per site, returns top N addresses ordered by count. Addresses are raw extracted strings —
not geocoded. 107 applications total in the 2024+ corpus.

### A5 — Single councillor vote summary

`council analyse cambridge councillor --name NAME`

Partial family-name match. Returns total votes, for/against/abstain counts, declared interests
count, and dissent rate (% of votes cast against the carried majority). No date filter — covers
the full history for that councillor in the DB.

### A6 — Motions by tag

`council analyse cambridge motions --tag TAG [--limit N]`

Substring match on `motions.tags`. Returns date, item number, title, outcome for all matching
motions. Useful for pulling all planning, budget, or governance motions. Top tags in the 2024+
corpus: governance (881), planning (425), procedural (418), infrastructure (323), budget (240).

### A7 — ALLY/OPPONENT relationship edges

`council build-relationships cambridge [--from-year YYYY] [--all-years] [--dry-run]`

Computes pairwise voting alignment and writes typed edges to the `relationships` table.
Thresholds: ALLY ≥85% agreement, OPPONENT ≤40%, minimum 10 shared votes. Clears and rewrites
on each run. Default `--from-year 2024`.

**Current results (2024+):** 62 ALLY edges. 0 OPPONENT pairs — Cambridge council votes
near-unanimously, so no pair falls below the 40% threshold. The ALLY edges reflect micro-blocs
within that consensus.

---

## Part 1: Query functions

All new functions go in `src/analysis/queries.py`. All accept `from_year: int | None = None`
and `to_year: int | None = None`. Default callers pass `from_year=2024` for now; when the
full corpus lands, callers pass nothing (no filter).

Every function documented below includes the data shape returned and the visualisation it feeds.

---

### Q1 — Councillor activity ranges

**Function:** `councillor_activity_ranges(session, council_id, from_year, to_year)`

**Returns:**
```python
list[CouncillorActivity]

@dataclass
class CouncillorActivity:
    councillor_id: int
    given_name: str
    family_name: str
    first_vote_date: date
    last_vote_date: date
    total_votes: int
    is_active: bool        # last_vote_date within 18 months of today
    dissent_rate: float    # fraction of votes cast against the carried majority
```

**SQL sketch:**
```sql
SELECT c.id, c.given_name, c.family_name,
       MIN(m.meeting_date), MAX(m.meeting_date), COUNT(v.id)
FROM councillors c
JOIN votes v ON v.councillor_id = c.id
JOIN motions mt ON v.motion_id = mt.id
JOIN meetings m ON mt.meeting_id = m.id
WHERE m.council_id = :council_id
  AND (:from_year IS NULL OR strftime('%Y', m.meeting_date) >= :from_year)
GROUP BY c.id
```

`is_active`: `last_vote_date >= today - 18 months`. This is a heuristic — council elections
are ~4 years apart; an 18-month gap almost always means the person left.

`dissent_rate`: a second query counts votes where `v.choice = 'AGAINST'` and the motion's
`outcome = 'CARRIED'` — i.e. the councillor voted against something that passed.

**Known dedup artifact:** Some councillors with 1–7 votes and a single meeting date are family
members recorded as proxy voters at AGMs of Electors (e.g. "Catherine Barlow", "Georgina
Randklev", entries from 2025-10-28 and 2026-02-24). Filter these from the activity list with
`total_votes >= 10` by default, or expose a `--min-votes N` flag. Do not delete these records
— they are real attendees at specific meeting types.

**Visualisation powered:**
- Councillor cards (name, active badge, vote count, dissent rate, date span)
- Gantt timeline (Y-axis: councillors sorted by first vote; X-axis: years; bar = active period)
- "Current vs. former" label on all other councillor charts

**Full corpus gain:** Extends bars back to 1995. Gary Mack's record (1995–2026, 452 votes)
becomes the visual anchor of 30 years of continuous service.

---

### Q2 — Contestation rate by year

**Function:** `contestation_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[YearContestationStats]

@dataclass
class YearContestationStats:
    year: int
    total_carried: int
    contested: int           # carried with votes_against >= 1
    contestation_rate: float # contested / total_carried
    most_contested: list[tuple[str, int]]  # [(motion_title, votes_against), ...] top 3
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
       COUNT(mt.id) as total,
       SUM(CASE WHEN mt.votes_against >= 1 THEN 1 ELSE 0 END) as contested
FROM motions mt
JOIN meetings m ON mt.meeting_id = m.id
WHERE mt.outcome = 'CARRIED'
  AND m.document_type = 'minutes'
  AND m.council_id = :council_id
GROUP BY yr ORDER BY yr
```

**2024+ corpus baseline:** 2024: 103 carried / 15 contested (14.6%),
2025: 186 / 16 (8.6%), 2026: 189 / 10 (5.3%). Three data points — interpretable but thin.

**Visualisation powered:**
- Line chart: contestation rate (%) over time
- Bar chart: total carried vs. contested per year (stacked)
- Annotation layer: hover on a year to see the 3 most-contested motions

**Full corpus gain:** 30-year trend. The early extracted years (1995–2023, sparse) show near-zero
contestation, which may be genuine or may reflect incomplete extraction. Treat pre-2024 values
as illustrative until the full batch runs. Add a visual note: "2024–2026: full coverage;
earlier years: partial."

---

### Q3 — Topic distribution by year

**Function:** `topic_distribution_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
dict[int, dict[str, int]]
# {year: {tag: motion_count}}
# e.g. {2024: {"governance": 120, "planning": 45, "budget": 30, ...}}
```

**Implementation note:** `motions.tags` is a comma-separated string (e.g. `"planning,development"`).
Split on `,`, strip whitespace, count each tag independently. The top 8 tags in the current
corpus are: governance (881), planning (425), procedural (418), infrastructure (323),
community (241), budget (240), policy (124), development (107). Use these as the canonical
display tags; bin everything else as "other".

**Visualisation powered:**
- Stacked area chart: years on X, stacked bands per tag coloured by category
- Pie/donut for a selected year (filter by clicking a year on the area chart)
- "What Cambridge spends its time on" — governance and procedural always dominate;
  spikes in planning or infrastructure signal development periods

**Full corpus gain:** The area chart fills in. 2024+ shows what recent Cambridge looks like;
pre-2024 shows the historical baseline. The shape across 30 years is the interesting story.

---

### Q4 — Co-mover pairs

**Function:** `co_mover_pairs(session, council_id, from_year, to_year, min_count=5)`

**Returns:**
```python
list[CoMoverPair]

@dataclass
class CoMoverPair:
    mover_id: int
    mover_name: str
    seconder_id: int
    seconder_name: str
    count: int          # motions where this pair moved+seconded
```

**SQL sketch:**
```sql
SELECT mt.moved_by_id, mt.seconded_by_id, COUNT(*) as n
FROM motions mt
JOIN meetings m ON mt.meeting_id = m.id
WHERE m.council_id = :council_id
  AND mt.moved_by_id IS NOT NULL
  AND mt.seconded_by_id IS NOT NULL
GROUP BY mt.moved_by_id, mt.seconded_by_id
HAVING COUNT(*) >= :min_count
ORDER BY n DESC
```

**Known data quality issue:** The councillor named "Shannon Unknown" in co-mover results is a
dedup artifact — the family name was extracted without a given name, and the normaliser filled
`given_name = "Unknown"`. These pairs (e.g. `Shannon Unknown → Melanie Foley: 16`) are
pre-2024 data from a partially extracted doc. Filter by `is_active=True` for the 2024+ view
to avoid these stubs surfacing.

**Visualisation powered:**
- Chord diagram: councillors on a circle, arc thickness = co-mover count (most compact for this)
- Alternative: directed graph with labelled edges (mover → seconder)
- Supplements the voting alignment heatmap: two councillors who always vote together AND always
  propose together is the strongest signal of a working partnership

**Full corpus gain:** Pre-2024 co-mover pairs from earlier terms flesh out historical alliances
(e.g. Shannon/Foley pairing from pre-2015 data).

---

### Q5 — Interest declarations by councillor and type

**Function:** `interest_declarations_summary(session, council_id, from_year, to_year)`

**Returns:**
```python
list[InterestSummary]

@dataclass
class InterestSummary:
    councillor_id: int
    councillor_name: str
    total: int
    by_type: dict[str, int]   # {"IMPARTIALITY": 40, "FINANCIAL": 5, "PROXIMITY": 2, ...}
    top_topics: list[str]     # top 3 motion tags where this councillor declared
```

**SQL sketch (two queries):**
```sql
-- 1. Counts by councillor and type
SELECT id.councillor_id, id.interest_type, COUNT(*) as n
FROM interest_declarations id
JOIN meetings m ON id.meeting_id = m.id
WHERE m.council_id = :council_id
GROUP BY id.councillor_id, id.interest_type

-- 2. Motion topics where declarations occur (join via meeting_id)
SELECT id.councillor_id, mt.tags, COUNT(*) as n
FROM interest_declarations id
JOIN meetings m ON id.meeting_id = m.id
JOIN motions mt ON mt.meeting_id = m.id
WHERE m.council_id = :council_id AND mt.tags IS NOT NULL
GROUP BY id.councillor_id, mt.tags
```

**2024+ corpus data:** 521 total declarations. Le Page (73), Barlow (69), Carr (61), Mayes (56),
Mack (52). Predominantly IMPARTIALITY (456), then PROXIMITY (31), FINANCIAL (21). FINANCIAL
declarations (21) are worth surfacing distinctly — they indicate a pecuniary interest.

**Visualisation powered:**
- Horizontal bar chart per councillor, segmented by type (IMPARTIALITY/FINANCIAL/PROXIMITY),
  sorted by total. Le Page stands out at the top.
- Click a councillor's bar → expand to a list of specific declarations with meeting dates
  and the motion subject they related to.
- "Most declared topics" for a councillor — which tags appear most in motions near their
  declarations. (Note: approximate — this is per-meeting, not per-motion-item.)

**Full corpus gain:** Extends to all historical declarations. The pattern of who declares most
across 30 years may shift — some councillors with low 2024 counts may have had high earlier
periods.

---

### Q6 — Public engagement by year

**Function:** `public_engagement_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[EngagementStats]

@dataclass
class EngagementStats:
    year: int
    public_questions: int
    deputations: int
    petitions: int
    total: int
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
  COUNT(DISTINCT pq.id) as questions,
  COUNT(DISTINCT d.id)  as deputations,
  COUNT(DISTINCT p.id)  as petitions
FROM meetings m
LEFT JOIN public_questions pq ON pq.meeting_id = m.id
LEFT JOIN deputations d ON d.meeting_id = m.id
LEFT JOIN petitions p ON p.meeting_id = m.id
WHERE m.council_id = :council_id AND m.document_type = 'minutes'
GROUP BY yr ORDER BY yr
```

**2024+ corpus data:** 610 public questions, 134 deputations, 20 petitions — distributed
across 2024–2026. These numbers are only from minutes (not agendas, which also list questions
and deputations as proposals). Decide whether to include agenda counts too — they'll be higher
but represent planned slots, not actual attendees.

**Visualisation powered:**
- Stacked bar or grouped bar per year: questions / deputations / petitions in distinct colours
- Spike in deputations in a specific year signals a controversial decision period
- "How much does the public engage with Cambridge council?" — the baseline story

**Full corpus gain:** The most meaningful trend over 30 years. A rising line here is the real
civic signal. Not useful until pre-2024 extraction runs — 2024–2026 is only 3 data points.
Mark this chart as "preview — 30-year data pending" until then.

---

### Q7 — Budget aggregate by year

**Function:** `budget_by_year(session, council_id, from_year, to_year)`

**Returns:**
```python
list[BudgetYearStats]

@dataclass
class BudgetYearStats:
    year: int
    total_items: int
    items_with_amount: int
    total_amount: float | None    # sum of amounts in dollars
    largest_items: list[tuple[str, float]]  # [(description, amount)] top 5
```

**SQL sketch:**
```sql
SELECT strftime('%Y', m.meeting_date) as yr,
  COUNT(bi.id) as total,
  SUM(CASE WHEN bi.amount IS NOT NULL THEN 1 ELSE 0 END) as with_amount,
  SUM(bi.amount) as total_amount
FROM budget_items bi
JOIN meetings m ON bi.meeting_id = m.id
WHERE m.council_id = :council_id AND m.document_type = 'minutes'
GROUP BY yr ORDER BY yr
```

**Known data quality issue:** `budget_items.amount` was extracted as a raw number from motion
text. The LLM may have extracted sub-totals, line-item amounts, and annual totals for the same
budget cycle — double-counting is likely. Do not present the summed total as "total council
spend." Instead present it as "total dollar value of budget items discussed in council." Add
a caveat to the frontend.

**Visualisation powered:**
- Bar chart: total dollar value discussed in council per year (with caveat tooltip)
- Table: top 5 largest single items per year (clickable to see the motion)
- "Cambridge's biggest financial decisions" as a discovery feature

**Full corpus gain:** Extends to pre-2024 budget cycles.

---

### Q8 — Planning approval rate

**Function:** `planning_outcomes(session, council_id, from_year, to_year)`

**Returns:**
```python
@dataclass
class PlanningOutcomes:
    total: int
    approved: int
    refused: int
    deferred: int
    pending: int
    approval_rate: float        # approved / (approved + refused)
    top_sites: list[tuple[str, int]]  # [(address, n_applications)]
    top_applicants: list[tuple[str, int]]  # [(applicant, n_applications)]
```

**2024+ corpus note:** Only 107 planning applications extracted. The 2024+ corpus includes
agendas (which carry fuller planning detail) and minutes (which carry the voted outcome).
The 63 APPROVED / 19 REFUSED split gives a 77% approval rate — but this is from partial data.
Treat as directional until the full corpus lands.

**Visualisation powered:**
- Donut chart: APPROVED / REFUSED / DEFERRED / PENDING breakdown
- Table: top sites by application count (which addresses keep coming back to council)
- Table: top applicants (developers / agents with most applications)
- Map (requires E1 geocoding): dots coloured by outcome

**Full corpus gain:** ~5,700 estimated planning items across the full corpus. The historical
approval rate and top sites become meaningful with full data.

---

## Part 2: CLI additions

Extend `council analyse` with new subcommands. All follow the existing pattern in `src/cli.py`.

### C1 — `council analyse cambridge activity`

```
council analyse cambridge activity [--min-votes N] [--from-year YYYY] [--to-year YYYY]
```

Calls Q1. Prints a table: name / first vote / last vote / total votes / is_active / dissent_rate.
Default `--min-votes 10` to suppress AGM proxy voters.

### C2 — `council analyse cambridge trends`

```
council analyse cambridge trends [--from-year YYYY] [--to-year YYYY]
```

Calls Q2 (contestation) + Q3 (topic distribution). Prints two tables: year × contestation_rate,
and year × tag counts. The frontend reads the JSON export from this.

### C3 — `council analyse cambridge co-movers`

```
council analyse cambridge co-movers [--min-count N] [--from-year YYYY] [--to-year YYYY] [--active-only]
```

Calls Q4. Default `--min-count 5`, `--active-only` filters to councillors with `is_active=True`.

### C4 — `council analyse cambridge interests`

```
council analyse cambridge interests [--from-year YYYY] [--to-year YYYY]
```

Calls Q5. Prints per-councillor declaration counts by type. Flags any FINANCIAL declarations
explicitly (these are pecuniary interest — worth surfacing).

### C5 — `council analyse cambridge engagement`

```
council analyse cambridge engagement [--from-year YYYY] [--to-year YYYY]
```

Calls Q6. Prints per-year: questions / deputations / petitions / total.

### C6 — `council analyse cambridge budget`

```
council analyse cambridge budget [--from-year YYYY] [--to-year YYYY] [--top N]
```

Calls Q7. Prints year total + top N items by amount.

### C7 — `council analyse cambridge divergence`

```
council analyse cambridge divergence [--from-year YYYY] [--to-year YYYY] [--min-similarity F]
```

Calls E2 (officer divergence). Prints matched pairs: meeting date / item title / officer
recommendation summary / council outcome / diverged (Y/N).

### Fix — add `--from-year` / `--to-year` to existing `alignment` subcommand

`voting_alignment_matrix()` in `queries.py` already accepts `from_year`/`to_year`.
The CLI handler in `src/cli.py` doesn't expose them. Add these two args to the `alignment`
branch in `cmd_analyse`. One-line fix.

---

## Part 3: Data enrichment — site geocoding (E1)

**Script:** `scripts/geocode_sites.py`

**New columns on `sites` table:**
```sql
ALTER TABLE sites ADD COLUMN lat REAL;
ALTER TABLE sites ADD COLUMN lng REAL;
ALTER TABLE sites ADD COLUMN geocode_status VARCHAR(10);
-- values: 'ok', 'failed', 'skipped'
```

**Logic:**
1. Query all `sites` where `lat IS NULL` and `address IS NOT NULL`.
2. For each address: prepend ", City of Cambridge WA" to the raw string for context.
3. Call Nominatim geocoding API (free, no key required, rate-limit: 1 req/sec).
4. Write `lat`, `lng`, `geocode_status` back to the DB.
5. Incremental: skip sites with `geocode_status IS NOT NULL` unless `--force`.

**CLI:** `council geocode cambridge [--force] [--dry-run]`

**Expected results:** 107 planning applications → at most 107 unique sites. Many will share
addresses. Perth suburb geocoding via Nominatim is reliable for street-level addresses.

**Visualisation powered:**
- Map layer on the planning chart: dots at geocoded positions, coloured by outcome
- "Where are the most-discussed development sites in Cambridge?" — the geographic story

**Full corpus gain:** ~5,700 planning items → many more unique sites. The map becomes
meaningful at scale.

---

## Part 4: Officer divergence matching (E2)

This is the highest-novelty analysis the project can produce — comparing what officers
recommended (from agendas) to what councillors actually decided (from minutes).

**Prerequisite:** Both an agenda and its matching minutes must be extracted for the same
meeting. This is only guaranteed for 2024+ (where the scraper was fixed to download both).

**New module:** `src/analysis/divergence.py`

### Matching strategy

For each meeting date where both an agenda and a minutes document exist in the DB:

1. **Meeting-level match:** `agenda.meeting_date = minutes.meeting_date AND
   agenda.meeting_type ≈ minutes.meeting_type` (fuzzy, because type labels vary slightly —
   "Ordinary Council Meeting" vs "Council Meeting"). Match on date first; use type as
   a tiebreaker if multiple meetings on the same day.

2. **Motion-level match:** For each motion in the agenda (with `officer_recommendation`),
   find the best-matching motion in the minutes by:
   - Item number (exact, if present on both)
   - Title similarity (fuzzy string match — `difflib.SequenceMatcher`, threshold 0.6)
   - Recommendation text overlap (if item number and title both absent)

3. **Divergence classification** for each matched pair:
   - `FOLLOWED` — council voted CARRIED and officer recommended approval (or LOST and
     officer recommended refusal).
   - `DIVERGED` — council voted CARRIED where officer recommended refusal, or vice versa,
     or council voted DEFERRED/LOST on a recommended approval.
   - `UNMATCHED` — agenda item has no matching minutes motion (possible for items
     withdrawn or carried forward).
   - `NO_RECOMMENDATION` — the agenda motion has `officer_recommendation IS NULL`.

### Output schema

```python
@dataclass
class DivergencePair:
    meeting_date: date
    item_number: str | None
    title: str
    officer_recommendation: str    # text from agenda
    council_outcome: str           # from minutes: CARRIED/LOST/DEFERRED/etc.
    diverged: bool
    match_confidence: float        # 0.0–1.0 from fuzzy match score
```

**CLI:** `council analyse cambridge divergence [--from-year YYYY] [--min-confidence F]`

**Expected output (2024+ corpus):**
Currently: 61 agendas extracted, 103 minutes (Council Meeting/Ordinary) extracted in the
same period. Not all agenda+minutes pairs will match cleanly due to meeting type label
variation. Estimate: ~40–50 meeting pairs matchable; ~400–600 motion pairs.

**Visualisation powered:**
- "Council vs officers" panel: "Cambridge council followed officer recommendations in X% of
  cases." Below: a table of divergences sorted by meeting date, with motion text.
- Per-topic divergence rate: did council diverge more on planning than governance?
- Per-councillor: who moved the dissenting motions when council diverged from officers?

**Deferred until:** This analysis requires human spot-checking of the match quality before
publishing numbers. After the matching script is built, run it and review a sample of
`match_confidence < 0.8` pairs manually.

---

## Part 5: Frontend data contracts

What each visualisation needs from the backend. This section defines the JSON shape
each frontend component should expect. The CLI commands above can emit `--json` output
in these shapes; a Flask/FastAPI layer serves them to the frontend.

### Alignment heatmap

```json
{
  "councillors": ["Gary Mack", "Georgie Randklev", ...],
  "matrix": [[1.0, 0.92, ...], [0.92, 1.0, ...], ...],
  "total_shared": [[0, 452, ...], [452, 0, ...], ...]
}
```
Source: existing `voting_alignment_matrix()`. Emit as JSON with `--json` flag on the CLI.

### Voting network graph

```json
{
  "nodes": [{"id": 1, "name": "Gary Mack", "votes": 452, "is_active": true}, ...],
  "edges": [{"source": 1, "target": 3, "weight": 0.92, "shared": 380, "kind": "ALLY"}, ...]
}
```
Source: `relationships` table (ALLY edges) + Q1 for node metadata.

### Councillor activity timeline (Gantt)

```json
[
  {"name": "Gary Mack", "first": "1995-07-25", "last": "2026-05-26",
   "votes": 452, "is_active": true, "dissent_rate": 0.02},
  ...
]
```
Source: Q1.

### Contestation trend

```json
[
  {"year": 2024, "total_carried": 103, "contested": 15, "rate": 0.146},
  {"year": 2025, "total_carried": 186, "contested": 16, "rate": 0.086},
  ...
]
```
Source: Q2.

### Topic distribution stacked area

```json
[
  {"year": 2024, "governance": 120, "planning": 45, "budget": 30, "infrastructure": 28, ...},
  ...
]
```
Source: Q3.

### Interest declaration bar chart

```json
[
  {"name": "Michael Le Page", "total": 73,
   "by_type": {"IMPARTIALITY": 68, "FINANCIAL": 3, "PROXIMITY": 2}},
  ...
]
```
Source: Q5.

### Planning map

```json
[
  {"address": "123 Wembley Rd", "lat": -31.93, "lng": 115.83,
   "status": "APPROVED", "applications": 3, "site_id": 12},
  ...
]
```
Source: Q8 + E1.

### Officer divergence panel

```json
{
  "total_matched": 487,
  "diverged": 28,
  "divergence_rate": 0.057,
  "by_tag": {"planning": 0.09, "budget": 0.03, "governance": 0.02},
  "examples": [
    {"date": "2024-06-25", "title": "Development Application ...", "outcome": "REFUSED",
     "officer_recommendation": "RECOMMENDED APPROVAL", "diverged": true}
  ]
}
```
Source: E2.

---

## Corpus expansion checklist

When pre-2024 extraction is complete (329 minutes), run these in order:

```bash
# Re-run deduplication (new pre-2024 names may create new stubs)
python scripts/dedup_councillors.py          # preview
python scripts/dedup_councillors.py --apply  # write

# Refresh dynamic layer
council build-relationships cambridge --all-years  # needs --all-years flag added

# Widen all analysis queries (remove from_year default)
council analyse cambridge activity             # no --from-year → all years
council analyse cambridge trends               # 30-year contestation + topic charts
council analyse cambridge alignment --all-years
council analyse cambridge co-movers --all-years
council analyse cambridge interests --all-years
council analyse cambridge engagement --all-years
council analyse cambridge budget --all-years
council analyse cambridge divergence --all-years  # only adds minutes-side; agendas only 2024+

# Re-geocode (new planning sites from pre-2024 docs)
council geocode cambridge

# Re-validate for quality assurance
council validate cambridge --all-years
```

**What changes with the full corpus:**

| Chart | 2024+ (now) | Full corpus |
|-------|-------------|-------------|
| Contestation trend | 3 data points | 30-year line |
| Topic distribution | 3 years | 30-year stacked area |
| Councillor timeline | 2024–2026 activity only | Full career spans (e.g. Mack 1995–2026) |
| Co-mover pairs | Current-term pairs | Historical partnership record |
| Interest declarations | 521 records | ~5,700 estimated records |
| Planning map | 107 applications | ~5,700 estimated applications |
| Public engagement | 3-year preview | 30-year trend (the compelling civic story) |
| Officer divergence | 2024+ agendas only | Still 2024+ only (no historical agendas) |

---

## Build order

Implement in this sequence. Each step is independently shippable.

1. **Fix alignment CLI** — add `--from-year`/`--to-year` to `council analyse cambridge alignment`.
   One-line change in `src/cli.py`. Unblocks using the alignment data with a year filter.

2. **Q1 — councillor activity ranges** + **C1** CLI. This is the foundation for all
   "who is active" filtering in every other query. Build first.

3. **Q2 + Q3 — contestation and topic trends** + **C2** CLI. These two go together (same
   `--from-year` / `--to-year` args, same output table). Powers the two timeline charts.

4. **Q5 — interest declarations** + **C4** CLI. Self-contained. The political data journalists
   want. Build early.

5. **Q4 — co-mover pairs** + **C3** CLI. Depends on Q1 (`--active-only` filter). Can work
   without it if you accept the name-stub noise.

6. **Q6 + Q7 + Q8 — engagement, budget, planning** + **C5/C6** CLI. Three small queries,
   low effort, add them together.

7. **E1 — geocoding**. One-off enrichment script. Run once, done.

8. **E2 — officer divergence**. The most complex piece. Build last, after the simpler
   queries have been validated. Requires manual spot-checking of match quality.

---

## Future product features

### F1 — Council boundary map (per-council Overview + aggregate Map page)

The same GeoJSON + data pipeline serves two surfaces:

**Surface A — Per-council Overview page (static graphic)**
A programmatically generated SVG or Canvas image rendered from structured data — not
AI-generated. Lives on each council's Overview page as a geographic anchor for the report.

What it shows:
- Council boundary polygon (GeoJSON)
- Tender award locations as dots (from geocoded `sites` table — depends on E1)
- Meeting venue (council chambers) as a distinct marker
- Prominent suburb labels and recognisable landmarks within the boundary

Rendering approach: D3.js or equivalent — project GeoJSON boundary into a fixed viewport,
overlay DB-sourced points. Outputs a deterministic image from the current data; re-renders
when data changes.

**Surface B — Map page (interactive aggregate view)**
The existing Leaflet map on `/map` overlays all council boundary polygons simultaneously,
covering WA or the Perth metro area. Each polygon is coloured or annotated with summary
data (e.g. transparency score, number of tenders, recusal rate). Users can zoom and pan
freely; clicking a council boundary opens a summary card linking to that council's report.

This gives the Map page a clear purpose: "see how councils compare geographically." As more
councils are added, the map fills in and becomes the product's discovery surface — readers
find their council on the map and drill into its report.

**Data needed:**
- Council boundary GeoJSON for each council (publicly available from data.wa.gov.au)
- Geocoded tender/planning sites (E1)
- Meeting venue coordinates (manual entry — one-off per council)
- Per-council summary stats for the map overlay (from existing scorecard/analysis queries)
- Optional: suburb boundary GeoJSON for labelling within the per-council graphic

**Scope note:** This is a self-contained frontend sub-project. The render pipeline (data → SVG)
can be built independently of the rest of the analysis stack. The same GeoJSON and data
contracts generalise to any council — adding a council means sourcing its boundary file
and running the geocoding step.

---

### F2 — Monthly digest feed (Overview page, Latest Activity)

An automated pipeline that triggers when new meeting minutes are published, extracts 2–4
highlights, stores a structured digest record, and renders a fade-back timeline on the
Overview page.

**Pipeline:**
1. Scraper detects new minutes on the council website (poll or webhook)
2. Minutes extracted via existing pipeline
3. Digest generation step: prompt selects 2–4 notable items from the new minutes —
   a tender awarded, a contentious vote, a recusal, a new conflict, anything with
   unusual public engagement. Keyed off interestingness, not volume.
4. Digest record written to a new `digests` table: `(council_id, period_start, period_end,
   highlights JSON, generated_at)`

**Frontend — Latest Activity section (Overview page):**
- Most recent digest shown prominently
- Previous months accessible via scroll/click with fade transition
- Default display window: 6 months; all historical digests stored and queryable
- Granularity follows publication cadence (typically monthly, occasionally fortnightly)

**Key design challenge:** The highlight extraction prompt. It must select for
*interestingness to a general reader*, not just high-volume or high-dollar items.
Requires iteration and a test battery of known-notable past events.

**Monetisation alignment:**
- Latest month's digest: free (drives return visits and sharing)
- Historical digests beyond 6 months: paywalled or email-gated
- Email alerts ("new minutes published — here's what matters"): paid tier

---

## Investigation Protocol (draft — needs iterative refinement)

### Current approach

Investigations have been conducted by prompting Claude Code Opus with extended thinking
enabled. Opus autonomously spawns subagents, queries the database, forms hypotheses,
tests them, and writes findings to INVESTIGATIONS.md. The `Investigator_prompt.txt`
(currently v2.2) governs investigation stance, test bars, severity grading, and framing.

This produced the 30+ investigations in INVESTIGATIONS.md, but it is not reproducible in
a controlled way: two Opus runs on the same corpus may explore different hypotheses, apply
different rigor thresholds, or skip the same check. The goal is to formalise this into a
staged, ordered protocol that is auditable and improvable.

### Goal

A protocol that:
- Produces the same standard tests every run (tests.py battery already achieves this for
  the fixed 23 tests; the protocol extends discipline to bespoke investigations)
- Can be run by any sufficiently capable model given only the protocol document and the DB
- Maps explicitly onto the three output pages: Evidence / Analysis / Overview
- Is improved iteratively only until a declared benchmark is met, then frozen and reused

### Improvement model: benchmark-gated, not open-ended

The protocol should follow the same discipline as the Level 1 inventory loop in PIPELINE.md:
iterate to improve, stop when a benchmark is met, then use the frozen version repeatedly.

**Analogy:** The inventory prompt was iterated until `other_content_rate ≤ 20%`. Once that
threshold was reached the prompt was frozen and the same version ran across the full corpus.
The investigation protocol should work identically — improve until it clears a declared score,
then stop improving and start running.

This matters because open-ended iterative improvement has no stopping condition. Each run
always reveals something that could be done better. The result is a protocol that is
perpetually being refined rather than being used productively.

**The benchmark must be declared before iterative improvement begins.** Defining the target
after seeing results introduces post-hoc goalpost-moving. The benchmark should specify:
- What a "good" investigation run looks like (coverage, depth, efficiency)
- How to score a completed run against those criteria
- What score constitutes "good enough to freeze"

**Benchmark candidates (to be decided before the first improvement run):**

The benchmark needs to be agreed before iterative improvement starts. Some dimensions to
consider:

| Dimension | Example threshold | How to measure |
|-----------|------------------|----------------|
| Hypothesis coverage | ≥ N hypotheses generated per governance domain | Count hypothesis list entries by Nolan/CIPFA domain |
| Test efficiency | ≤ X% of tested hypotheses are structurally unsupportable | Count infeasible results that a data survey would have killed |
| Finding rate | ≥ Y% of tested hypotheses produce a publishable result (Finding or Banked) | INVESTIGATIONS.md entry classification |
| Evidence completeness | ≥ Z% of confirmed findings have drill-down data with source quotes | Check snapshot JSON for inlined evidence |
| Protocol adherence | All 8 stages produced their defined output | Audit checklist per session |
| Framing balance | Final output passes the CRITIC / PROMOTER / NEUTRAL review | Subjective pass/fail against v2.1 criteria |

The exact thresholds are TBD. They should be set by reviewing the existing Cambridge
investigation sessions (Phases A–K in INVESTIGATIONS.md) and asking: what would a
"perfect" session look like, and what score would the actual sessions have received?
Working backwards from known good output to define the benchmark is the right approach.

Once a benchmark is agreed and written into this document, the improvement loop is:
1. Run a full investigation session following the staged protocol
2. Score the session against the benchmark
3. If score ≥ threshold: freeze the protocol, record the version, begin production use
4. If score < threshold: identify the lowest-scoring dimension, update `Investigator_prompt.txt`,
   increment the version number, and repeat from step 1

**Do not begin iterative improvement until the benchmark is written here.**

### Proposed stages

**Stage 1 — Data survey**
Before forming hypotheses, profile the database: table sizes, date ranges, coverage quality,
known NULL fields, known extraction gaps. Answer "what can this data actually support?"
Output: a structured data profile written to the scratchpad.
Purpose: kills unsupportable hypotheses before they waste test budget (e.g. [latency] was
killed because application_date and decision_date are 100% NULL — a pre-survey would have
caught this immediately).

**Stage 2 — Hypothesis generation**
Generate a broad candidate list anchored to recognised governance criteria (Nolan / CIPFA /
Best-Value). Do not test yet — enumerate first. Each hypothesis should name the table(s) it
requires and the predicted direction.
Output: numbered hypothesis list (format: INVESTIGATIONS.md Phase headers).
Open question: should this happen before or after Stage 1? Surveying first is more efficient
(prunes impossible hypotheses), but cold hypothesis generation before seeing the data may
produce more imaginative candidates. Proposed resolution: a lightweight survey (table sizes
+ known NULL fields) before generation, but deep per-table profiling only on-demand during
Stage 4 testing.

**Stage 3 — Standard battery**
Run `run_test_battery()` from tests.py. Deterministic — no hypothesis needed, same 23 tests
every run. Produces the Scorecard. Should run before bespoke investigations so the baseline
picture is established first.
Output: scorecard.json.

**Stage 4 — Hypothesis testing**
For each non-standard hypothesis from Stage 2, write a query, run it, apply the two-tier
bar (standard test: include regardless; flagship: novel × resident-relevant × surprising),
and classify as Finding / Null / Banked / Infeasible.
Save findings immediately to INVESTIGATIONS.md with the standard entry format. Retain
scratchpad scripts under `scratchpad/`.
Output: classified investigation entries, scratchpad scripts.
Open question: should confirmed findings' evidence be exported here (to a staging file) or
deferred to Stage 5? Exporting immediately during testing means Stage 5 is just assembly,
but it adds overhead to each test loop. To be determined by experience.

**Stage 5 — Evidence export**
For each confirmed Finding, export granular evidence records with verbatim source quotes as
structured JSON. This feeds the Evidence page drill-downs. Run `council publish` to inline
the drill-down data into snapshot files.
Output: updated snapshot JSONs with inlined drill-down data and source quotes.

**Stage 6 — Panel and analysis generation**
For each Finding, produce: chart data, headline, verdict text, valence chip, backTo link.
Register the panel in the battery (BatteryTestPanel) or as a bespoke component. Confirm
every panel corresponds to a battery test (no orphan panels — per methodology v2.2).
Run `council publish cambridge` and verify the frontend renders.
Output: updated Analysis page. Frontend build clean.

**Stage 7 — Summary synthesis**
Once all panels are stable, run a synthesis pass: write the plain-English overview
(7–8 cross-cutting insights), assign the one-liner verdict, regenerate overview.json.
Apply the CRITIC / PROMOTER / NEUTRAL review sequence from Investigator_prompt.txt v2.1
to calibrate framing before publishing.
Output: updated overview.json, updated Overview page content.

**Stage 8 — Visual generation**
Generate the council boundary map graphic (F1) using geocoded data and boundary GeoJSON.
This runs last because it depends on the full tender/planning data being finalised.
Output: SVG/Canvas graphic for Overview page hero.

### Open questions about ordering

The staging above is a first draft. The following tensions need empirical resolution by
running a full investigation cycle under the protocol and noting where it breaks down:

1. **Browse depth vs efficiency.** Unguided browsing is expensive in tokens. The Stage 1
   survey should be driven by a fixed checklist (what tables, what counts, what NULL rates,
   what known gaps), not left to Opus to infer. The checklist itself should be versioned
   alongside `Investigator_prompt.txt`.

2. **Hypothesis generation before vs after data survey.** See Stage 2 note above. First
   full run should try survey-first and note any hypotheses that felt artificially constrained
   by seeing the data profile too early.

3. **When to export evidence.** The current pattern (export during publish, not during testing)
   means a Finding sits unexported for potentially multiple sessions. An alternative: during
   Stage 4, Opus writes a structured `evidence_staging/{hypothesis_id}.json` immediately on
   confirmation, and Stage 5 just assembles these into snapshot files. This keeps evidence
   closer to the investigation moment but adds schema discipline to Stage 4.

4. **How many hypotheses to generate vs how many to test.** Generating 30 and testing 10 is
   fine; generating 100 is waste. The right number is probably "all hypotheses that could
   plausibly clear the two-tier bar given the data profile." Opus should apply the data profile
   as a filter during generation, not after.

### Protocol document home

`Investigator_prompt.txt` is the canonical protocol document (now at v2.2). The staged
protocol above should be added to it as a numbered preamble that Opus follows in order.
Each stage should define:
- What inputs it reads
- What output it produces and where it saves it
- What the stopping condition is

The next step is to run a single new council (or a Cambridge refresh) end-to-end following
this staged order, note every deviation and inefficiency, and increment the protocol to v2.3.
The protocol version should be noted at the top of each INVESTIGATIONS.md session header.
