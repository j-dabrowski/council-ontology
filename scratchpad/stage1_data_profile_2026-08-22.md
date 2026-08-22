# Stage 1 Data Profile — Explorer session, 2026-08-22

Corpus reconfirmed byte-for-byte unchanged from the 2026-08-14 profile —
every table row count checked matches exactly:

councillors 400 · motions 14,013 · votes 16,249 · tenders 840 ·
interest_declarations 2,015 · planning_applications 3,116 · deputations
1,492 · petitions 383 · public_questions 3,478 · budget_items 3,978 ·
delegated_decisions 1,242 · committee_reports 881 · other_items 11,880 ·
appointments 944 · building_permits 667 · meetings 580 ·
community_submissions 2,114.

`config/agent_switches.json`: `data_enrichment_status: OPEN`,
`researcher_gate_mode: file-review`, `conductor_max_passes: 3`.

## Why this session leads with domain F (Effectiveness)

`EXPLORATION_PROTOCOL.md`'s 2026-08-20 note: domain F was added after all
Cambridge calibration was scored, and "the next investigation session is
the first one scored against the 6-domain version of Dimension 1." Session
10 covered A/B/C/D/E only. This is that next session.

## Checked against DATA_ENRICHMENT.md before generating hypotheses (Phase 3 step 1)

The four Researcher genres merged today (3.6–3.9, `Investigator_prompt.txt`)
each already have a matching Pattern entry (`pipeline/DATA_ENRICHMENT.md`
#11–#14) stating the corpus lacks the structural linkage the genre needs.
Confirmed with two quick queries rather than assumed:
- `motions.title` LIKE resignation/retirement/severance (29 hits): every
  hit is either Ocean Gardens Retirement Village governance business or a
  councillor's own resignation — zero senior-officer exit-payment events.
- `other_items.description` LIKE severance/redundancy/"exit payment": 0
  hits.
These confirm (don't just assume) that 3.8 in particular is a genuine
structural absence, not a query miss. **Decision: do not spend a Stage 4
slot re-testing 3.6–3.9 this session** — that would be a pre-flagged
structural kill, exactly what checking DATA_ENRICHMENT.md first is meant
to avoid.

## New probes this session (tables/angles not previously exercised this way)

- `motions` title LIKE '%trial%'/'%pilot%': 38 minutes-only hits,
  1996–2025, good era spread. Never previously aggregated as a set —
  each prior mention (e.g. Freeplay Zone in engagement-panel work) was
  incidental, not surveyed as a genre-F population. See [46].
- `budget_items` monthly count/dollar distribution (minutes only, joined
  to `meetings`): raw June count (472) initially looks anomalous vs
  neighbours (April 232, May 204, July 236) — but collapses to a single
  dominant meeting (2012-06-18, 264 rows) on inspection. March 2026 dollar
  total (~$3.46bn) traced to balance-sheet/asset-revaluation STATEMENT
  rows mixed into `amount`. See [47] — two new standing-checklist entries
  written to `Explorer_prompt.txt`.
- `appointments` × [18]'s win-rate metric, restricted to Audit-type/CEO
  Performance Review body_name matches: 33 distinct councillor appointees
  across 30 years, `body_name` values found via
  `LIKE '%Audit%' OR LIKE '%CEO Performance%'` (7 distinct exact strings,
  all genuine variants of the same two committee types, no false
  positives on manual read). See [48].
- `other_items.item_type` × `is_confidential` cross-tab: 5 rows
  type='confidential_item' AND is_confidential=0 (all "Nil" placeholder
  rows — correct); 55 rows is_confidential=1 with a different item_type
  (all genuinely sensitive matters under a different agenda-section
  label — correct). Full population read (n=60), not sampled. See [49].

## Method note carried forward (not a data caveat — a technique note)

An automated title-word-overlap + evaluation-keyword proxy was tried for
the [46] trial/pilot matching problem before falling back to manual
verification. It produced 35/38 spurious "followup" hits on single common
words (e.g. "power", "time", "options") — the exact false-positive trap
[13] already named for deputation-theme keyword bucketing. Kept as a
documented dead end at `scratchpad/h46_trial_evaluation.py`; a future
Refiner pass on this genre needs LLM-assisted matching, not regex/
word-overlap, to scale past the 15/38 hand-checked this session.

## Standing confound checklist — reconfirmed, two new entries added

All prior STANDING CONFOUND CHECKLIST items in `Explorer_prompt.txt`
reconfirmed applicable. Two new entries added this session (bulk-meeting
dumps distorting `budget_items` monthly counts; `budget_items.amount`
mixing spend with balance-sheet statement totals) — see
`Explorer_prompt.txt` and `INVESTIGATIONS.md` Session 11 `[STAGE 9]` entry
for full detail.
