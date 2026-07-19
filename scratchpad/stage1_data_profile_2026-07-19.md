# Stage 1 — Data Survey / Profile — City of Cambridge corpus

**Date:** 2026-07-19
**Trigger:** Routine Stage 1 re-survey per `EXPLORATION_PROTOCOL.md` ("Proposed
stages" → Stage 1), ahead of a new exploration session. The corpus was last
profiled/investigated in **session 8 (2026-06-25/26)**; ~3 weeks have passed, and
live `-wal`/`-shm` files were present, so "has anything changed since session 8"
was treated as an open question to verify, not assume.
**DB:** `data/council.db` (SQLite, ~184MB). Backup (pre-dedup): `data/council.db.bak-predupe-20260624`.
**Scope:** Profile only. No hypotheses generated or tested (that is Stage 2+).

---

## 0. WAL / freshness check (done first)

- `PRAGMA journal_mode` = `wal`; a live `council.db-wal` (9.4MB, mtime 2026-06-24
  00:55) and `-shm` (mtime 2026-06-24 13:42) were present at survey start.
- `PRAGMA wal_checkpoint` returned `0|521|521` — 521 pages checkpointed cleanly,
  fully merged into the main DB. All queries below reflect the post-checkpoint state.
- **Interpretation:** the WAL was dated **2026-06-24** — the same day as the
  councillor dedup and the session-8 build work. Post-checkpoint row counts match
  the session-8 documented figures exactly (deduped 400 councillors, etc.). So the
  WAL held **uncommitted session-8-era writes, not new post-session-8 data.**
  Nothing landed in the corpus after session 8.

---

## 1. Table row counts — vs documented (Investigator_prompt.txt 0.2 / INVESTIGATIONS.md)

| Table | Count (2026-07-19) | Documented | Delta |
|---|---|---|---|
| councils | 1 | 1 | — |
| councillors | **400** | ~400 (405→400 dedup) | — (dedup intact) |
| councillor_terms | 58 | "sparse" | — (sparse, as noted) |
| sites | 2,454 | — | (not previously pinned) |
| meetings | 580 | 580 | — |
| motions | 14,013 | ~14,000 / 14,013 | — |
| votes | 16,249 | ~16,250 | — |
| planning_applications | 3,116 | ~3,100 / 3,116 | — |
| community_submissions | 2,114 | — | (not previously pinned) |
| interest_declarations | 2,015 | ~2,000 | — |
| tenders | 840 | ~840 | — |
| budget_items | 3,978 | ~4,000 | — |
| deputations | 1,492 | — | — |
| petitions | 383 | — | — |
| public_questions | 3,478 | — | — |
| appointments | 944 | — | — |
| committee_reports | 881 | — | — |
| delegated_decisions | 1,242 | — | — |
| building_permits | 667 | — | — |
| other_items | 11,880 | — | — |
| extraction_evidence | 71,486 | ~71,000 | — |
| relationships | 158 | ~158 | — |

**Backup delta confirmed:** `council.db.bak-predupe-20260624` = **405** councillors
vs working **400** → the −5 dedup (applied 2026-06-24) is present and has not
regressed.

**Verdict: every table count matches the documented figures. No table moved. No
new data landed since session 8.**

---

## 2. Date-span coverage

| Table (date via meeting join) | Min | Max |
|---|---|---|
| meetings | 1995-04-18 | 2026-06-09 |
| motions | 1995-04-18 | 2026-05-26 |
| votes | 1995-06-13 | 2026-05-26 |
| tenders | 1995-06-13 | 2026-04-28 |
| budget_items | 1995-05-23 | 2026-05-26 |
| interest_declarations | 1995-06-13 | 2026-05-26 |

- Most recent **minutes** doc: 2026-05-26 (Ordinary Council Meeting). The
  2026-06-09 max on `meetings` is a **Special Council Meeting agenda**, not minutes.
- **Meetings per year (minutes only)** confirm the known gaps still hold:
  sparse-then-dense pattern intact; the 2022–2023 corpus gap is visible —
  2022 = 13, **2023 = 8**, 2024 = 9 (vs ~14–26 in healthy years). No January
  ordinary meetings. 2026 = 8 (part-year). Nothing shifted.

**Verdict: date spans and per-year coverage unchanged; documented gaps
(2022 Jan–Apr+Jun, 2023 Jan–Apr+Jun–Jul; no January ordinaries) still hold.**

---

## 3. document_type breakdown (meetings)

| document_type | Count | Documented |
|---|---|---|
| minutes | 506 | 506 |
| agenda | 66 | 66 |
| unknown | 4 | 4 |
| addendum | 4 | 4 |

**Verdict: exact match (506/66/4/4). No drift.** Agenda contamination discipline
(filter `document_type='minutes'` on trend/voting queries) still required.

---

## 4. NULL-rate check on investigation-critical columns

### Confirmed still-bad (the known kill list — all unchanged)
| Column | Finding | Status |
|---|---|---|
| `planning_applications.application_date` | **3,116 / 3,116 = 100% NULL** | [latency] **still INFEASIBLE** |
| `planning_applications.decision_date` | **3,116 / 3,116 = 100% NULL** | processing-latency impossible |
| `community_submissions.submitter_name` | **1,034 / 2,114 = 48.9% blank**; remainder dominated by placeholders ("Adjoining neighbour" ×9, "Adjoining landowners" ×8, "Northern neighbour", "Neighbours"…) | [6] repeat-submitter identity **still unsupportable** |
| `tenders` confidential × amount | 111 `is_confidential=1`; only **22 (~20%) carry an amount** | [25] dollar-weighted confidential trend **still not computable** |

### Newly-characterised NULL rates (columns a fresh hypothesis might lean on)
| Column | Populated / total | NULL rate | Implication for Stage 2 |
|---|---|---|---|
| `planning_applications.estimated_value` | 286 / 3,116 | **90.8% NULL** | Any DA-value hypothesis caps at n≈286; only **241** decided (APPROVED/REFUSED) with a value → **directional only** ([14]/[20] territory). |
| `planning_applications.applicant_name` | 2,975 / 3,116 | 4.5% NULL/blank | Usable (real names; [20] used it) — but confers no approval edge (already null [20]). |
| `tenders.awarded_to` | 457 / 840 | **45.6% NULL/blank** | ~1/3–1/2 of awards have no named winner; conflating NULL with "redacted" over-counts confidentiality (the [25] trap). |
| `tenders.amount` | 351 / 840 | 58.2% NULL | Only 351 awards have a dollar figure (drives the [2] $147.9M figure). |
| `budget_items.amount` | 2,927 / 3,978 | 26.4% NULL | — |
| `budget_items` schema | columns: `item_number, description, amount, is_confidential` only | — | **No typed fund/reserve/investment fields.** [24] financial-resilience **still blocked** — needs the finance-aware re-extraction (DATA_ENRICHMENT #1); the raw table cannot support a clean reserve-trajectory series. |
| `budget_items.is_confidential` | 24 rows = 1 | — | Confirms [25]: budget_items carries only 24 heterogeneous confidential statement rows, not closed-door spend. |
| `motions.officer_recommendation` | 391 / 14,013 | **97.2% empty** | Officer-divergence work must use `src/analysis/divergence.py`, not this column directly (as noted session 5). |

---

## 5. Enum sanity check

| Enum | Values (all as stored) | Documented | OK? |
|---|---|---|---|
| `votes.choice` | FOR 11,941 / AGAINST 4,111 / ABSENT 197 | UPPERCASE; no ABSTAIN; ~11,900/4,100/197 | ✅ exact |
| `motions.outcome` | CARRIED 12,287 / **NULL 827** / LOST 514 / DEFERRED 253 / WITHDRAWN 76 / LAPSED 56 | ~12,300 CARRIED, ~827 blank, long tail | ✅ (note: the ~827 "blank" are stored as **NULL**, not `''`) |
| `planning_applications.status` | APPROVED 2,122 / REFUSED 535 / DEFERRED 224 / PENDING 176 / WITHDRAWN 31 / NULL 23 / APPEALED 5 | UPPERCASE | ✅ |
| `interest_declarations.interest_type` | IMPARTIALITY 1,369 / FINANCIAL 333 / PROXIMITY 203 / OTHER 86 / blank 24 | UPPERCASE; impartiality-dominant | ✅ (matches [19] narrative) |
| ⚠️ `community_submissions.position` | **object 1,521 / support 453 / neutral 122 / NULL 18** | (not previously pinned) | **LOWERCASE — exception to the "enums UPPERCASE" rule** |

**Verdict: enums consistent with documentation, one important exception surfaced —
`community_submissions.position` is stored LOWERCASE (`object`/`support`/`neutral`).**
A naive `position='OBJECT'` returns nothing. Existing [7]/[12] queries already use
`position='object'`, so built panels are correct; this is a trap for *new* queries.

---

## 6. Councillor identity state

- **Dedup intact:** working DB = 400, backup = 405. The 2026-06-24 dedup (−5) is
  present and stable.
- **No new split-identity candidates** (the direct consequence of no new data
  landing). The same-surname / one-side-zero-votes heuristic still surfaces the
  **same pre-documented residuals** flagged in caveat 0.4:
  - **Barlow: Kate (872) vs Catherine (12)** — the known Kate/Catherine case, still unmerged.
  - **Everett Ian (394)**, **McKerracher Kate (398)**, **Steele Ian (63)** — the
    family-only stub cases; their siblings are distinct low-vote or zero-vote records.
  All were known before session 8; none are new.
- **197 councillor records have zero votes.** 0 of them hold a `councillor_terms`
  row; **91 appear as a motion mover/seconder.** The bulk are **extraction
  placeholders parsed into `given_name`** — e.g. "Not specified", "Given name not
  stated", "Moved", "Seconded", "Mr", "CEO", "Mayes; Mayor", "Delmenico; Cr". These
  are pre-existing artifacts, not new. They do not affect the deduped 400-real-person
  analysis (zero votes; the analysis layer filters), **but a naive new mover/seconder
  query would pick them up** (see confound note in §8).

**Verdict: identity state unchanged and stable; dedup holds; no new merge candidates.**

---

## 7. WHAT'S NEW SINCE SESSION 8

**Nothing. The corpus is stable and unchanged.**

Every diagnostic re-checked — table row counts, date spans, per-year coverage,
document_type split, the known-bad NULL columns, enum value sets, and the
councillor dedup — matches the session-8 documented state exactly. The live
`-wal` was session-8-era uncommitted writes (2026-06-24), now checkpointed; it
introduced no post-session-8 data. **No new documents were extracted, no corpus
gap was filled, no row count moved, no schema changed.**

Two things this survey *characterised more fully* than prior docs (not "new data",
but newly pinned facts):
1. `community_submissions.position` is **lowercase** — an exception to the blanket
   "enums UPPERCASE" caveat.
2. Exact NULL rates on `estimated_value` (90.8%), `tenders.awarded_to` (45.6%),
   `tenders.amount` (58.2%), and confirmation that `budget_items` has **no typed
   fund/reserve schema** (only description/amount/is_confidential).

---

## 8. What this means for Stage 2 hypothesis generation

### Previously killed/parked hypotheses — are any newly unblocked?
**None.** Because no new data landed, every hypothesis killed or parked for a
*structural data* reason remains blocked for the identical reason:

| Hyp | Prior status | Re-check verdict |
|---|---|---|
| **[24] Financial-resilience arc** (reserves/investment) | ⏸ Parked pending finance-aware re-extraction | **STILL PARKED.** `budget_items` still has no typed fund/reserve fields; the unblock (DATA_ENRICHMENT #1 re-extraction) has not happened. Do not resurrect on the raw table. |
| **[17] "Deferred" = soft no** (DA reference linkage) | ✗ Killed — sparse linkage | **STILL SPARSE.** No new planning records; linkage density unchanged. |
| **[6] Repeat submitter identity** | ✗ Killed — placeholder names | **STILL UNSUPPORTABLE.** 48.9% blank + placeholder-dominated. |
| **[latency] Planning decision latency** | ✗ Pre-killed — 100% NULL dates | **STILL INFEASIBLE.** application_date/decision_date 100% NULL. |
| **[25] Confidential $ share over time** | ✗ Null — confidentiality = missingness | **STILL NULL.** 111 confidential tenders, only 22 with amount. |

**Single most important implication:** Stage 2 must generate hypotheses that live
**within the existing supported data envelope.** Do **not** re-queue the
data-blocked threads hoping fresh coverage arrived — this survey confirms it did
not. The only route to unblock [24] (the highest-value parked thread) is the
finance-aware re-extraction of the minutes' Investment Schedule / reserve reports
(DATA_ENRICHMENT #1 / PIPELINE Phase E) — a pipeline task, not a query task.

### New confound/coverage traps to add to the standing checklist (Explorer_prompt.txt)
1. **`community_submissions.position` is LOWERCASE** (`object`/`support`/`neutral`).
   A new query using `position='OBJECT'` silently returns nothing — an exception
   to the "enums UPPERCASE" caveat. Add explicitly.
2. **197 zero-vote placeholder councillor records** (junk `given_name` values;
   91 appear as motion mover/seconder). Any *new* mover/seconder-based hypothesis
   must filter to real, voting councillors (or join on votes), or these artifacts
   contaminate sponsorship/agenda-setting stats. ([27/28] used lift + real names,
   so was safe; a naive count-of-motions-moved query is not.)
3. **`estimated_value` is 90.8% NULL** — any planning-value hypothesis is capped at
   n≈241 decided applications → **directional only**, flag on any panel.
4. **`tenders.awarded_to` 45.6% NULL/blank** — never treat NULL winner as "redacted";
   it conflates genuine confidentiality with plain extraction gaps (the [25] trap,
   which inflated 2020 to 100% vs the defensible 62% on the `is_confidential` flag).

### Data that IS well-supported (green light for Stage 2)
Votes/choice (16,249, clean enums), motions/outcome (14,013), interest_declarations
with legal-type split (2,015), tenders concentration on the 351 amounts, planning
approval/objection linkage (community_submissions 2,114 with clean lowercase
position), extraction_evidence provenance (71,486 rows, healthy coverage across all
entity tables) — all intact and unchanged. Sponsorship edges (`moved_by_id`/
`seconded_by_id`, 93% populated) remain the richest untapped relational layer.
