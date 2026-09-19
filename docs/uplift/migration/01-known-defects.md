# Known Defects — Migration Plan

Traces each of the 39 defects in `docs/uplift/01-known-defects.md` to its
root cause in the current codebase, classifies it, and sequences the fixes.
Per `00-README.md`: this file is reference material for `02-claim-layer.md`,
`03-critic-agents.md`, `04-jurisdiction.md`, `05-verification.md` — several
of the gaps below are only fully closeable once the claim-object work in
`02-claim-layer.md` exists, and are flagged as such rather than given a
standalone fix.

**A note on source-material drift.** Two defects (D-20, D-31) don't fully
match current code as described. D-20 is written as an *inconsistency*
between two panels' COVID treatment; current code shows *neither* panel
caveats it — a shared absence, not an inconsistency. D-31 describes a
corpus-level drill-down that names individuals on an unconfirmed match;
the code paths that actually ship today (the scorecard test, its evidence
chain, and `/method`'s entity-resolution section) all withhold the name by
explicit, dated, commented design (2026-08-06 through 2026-09-16 show
iterative redaction hardening after real incidents). Most likely
explanation: the critique was run against an earlier deployed snapshot, or
against a surface this pass didn't check (`/record`'s raw-lookup page,
which is *designed* to show real names as a public-record tool, not a
drill-down attached to an accusation). Flagged per-defect below, not
resolved further here.

---

## Current state inventory

| D-id | Target capability | Current equivalent | Status | Notes |
|---|---|---|---|---|
| D-01 | Fiscal-year-anchored spend analysis (WA year: 1 Jul–30 Jun) | `_t_eoy_spending`, `src/analysis/tests.py:1441-1481` — buckets by raw calendar month, hardcodes `highlight_label="Dec"` | WRONG | No fiscal-year config exists anywhere; `src/council_eras.py` handles scrutiny eras, not fiscal years |
| D-02 | Exactly 12 month-bars rendered | `_t_eoy_spending` (`tests.py:1454-1462`) + `BatteryTestPanel.tsx:55` | RESOLVED (2026-09-19 verification) | Confirmed by direct code reading, not a live draft: `by_month` is a fixed `[0.0]*12` array populated for `range(12)` unconditionally; `_bars()` (`tests.py:148-158`) is a straight passthrough with no drop/merge; `BatteryTestPanel.tsx`'s `ChartView` renders exactly `chart.bars.length` items with no filter. All 12 bars always render — see G-02 |
| D-03 | One reconciled tender-total population across panels | `_tender_rows()` (`tests.py:182-190`, undeduped) vs `tender_concentration()` (`queries.py:2103-2246`, deduped) | WRONG | Two real, different populations; neither panel declares which |
| D-04 | Every panel's n traceable to one declared population + filter chain | No such mechanism anywhere in `src/analysis/` | MISSING | Confirmed: every `_t_*` function writes its own ad hoc filter chain independently |
| D-05 | One canonical display label per contractor, shared by every chart | `_normalise_contractor()` (`queries.py:2052`) + `display_name` dict (`:2188-2189`) used by `tender_concentration()`; `_t_procurement_incumbency` (`tests.py:1165,1186`) re-derives its own via `.title()` on the normalised key | WRONG | Second, inferior implementation of the same problem `tender_concentration()` already solved |
| D-06 | Multi-recipient tender awards attributed without double-counting | `Tender.awarded_to` (`ontology.py:412`) / `ExtractedTender.awarded_to` (`schemas.py:276`) — single free-text string, no multi-recipient concept | MISSING | Confirmed live in DB: "Various contractors: Total Eden..., Elliotts..., Malua..., Hugall and Hoile" as one row, alongside 8 other rows where those same names appear alone or in different composites |
| D-07 | One entity per real person in contested-vote ranking | `voting_power()` (`queries.py:1517-1557`) keys by `councillor_id`, labels with full given+family name — not the reproducing path; the actual bug was `DissentProfilesChart.tsx`'s Y-axis, fixed 2026-09-19 | PARTIAL → FIXED | `voting_power()`/`PowerPanel.tsx` confirmed clean, as suspected. The actual reproducing path: `dissent_profiles()` (`queries.py:1170-1243`) already computes `councillor_id` correctly, but `src/cli.py`'s dissent snapshot serialization dropped it, and the unwired `DissentProfilesChart.tsx` then labelled its Y-axis with `surname(p.name)` alone — a real, confirmed collision (2 distinct Cambridge councillors named Carr both qualify for the chart). Component is dead code (zero imports anywhere in `frontend/src/registry`/`pages`), so not a *live* defect, but fixed anyway per Step 4's own instruction to fix the reproducing path once found, not just confirm the suspected one is clean |
| D-08 | One row per real objector | `ExtractedCommunitySubmission` now carries a `count` field (schema + `community_submissions.count` column, 2026-09-19) | FIXED (schema, future extractions only) | Join/normalisation logic (`queries.py:2905-2929`) was already sound; the schema now distinguishes a named submitter (`count=None`, read as 1) from an aggregate-reported group (`submitter_name=None`, `count=N`). No re-extraction of the existing corpus — existing rows keep an implicit count of 1, per the no-re-query constraint |
| D-09 | Non-attendance measurable independent of vote-tally rows | New `MeetingAttendance` table (`src/models/ontology.py`), populated in `save_extraction()` going forward and backfilled for the existing corpus via `scripts/backfill_attendance.py` (2026-09-19) | FIXED | 3,327 attendance rows recovered from `data/llm_archive/` with zero new API calls; covers 373/686 minutes meetings (54%) — the rest have no archived chunk-0 to recover from, an honest gap, not fabricated |
| D-10 | No grade issued below a validity floor (CI or minimum n) | `_t_recusal_trend` (`tests.py:307-367`): `declined = post_pct < pre_pct - 5` → CRITICAL, no n-gate on the primary grade | WRONG | A `thin_financial` check exists (`:325`) but only softens a *secondary* comparison's wording, never gates the primary grade |
| D-11 | Small-n institutional claims not graded SUPPORTIVE/CRITICAL outright | `_t_threshold_gaming` (`tests.py:1115-1156`, n unchecked); `_t_delegate_body_conflict` (`tests.py:370-445`, thin-n disclosed in prose only) | WRONG / PARTIAL | MIN_N (`src/invariant_gate.py`) only applies to individual-unit claims — architecturally exempt for all 29 (institutional-unit) battery tests |
| D-12 | No ratio between structurally different event populations | `_t_recusal_overall` (`tests.py:205-240`), `factor = declared_recusal_pct / baseline_recusal_pct` (`:215`); re-derived independently in `ConflictRecusalPanel.tsx:213-221` | WRONG | Numerator = mandatory-after-disclosure act; denominator = ordinary (and per D-09, undercounted) non-attendance. Computed twice, Python + TSX |
| D-13 | Rates clustered by councillor/meeting before comparison | `_t_oversight_body_capture` (`tests.py:678-751`), `_t_freshman` (`:1484-1533`), `_t_deputation_dissent` (`:1579-1607`) — all pool vote/motion rows flat | WRONG / PARTIAL | Freshman's pooled result is corroborated by an unshipped clustered check per its own comment; the shipped statistic is still unclustered |
| D-14 | Displayed precision capped by what n/CI supports | `_capped_pct()` helper (`tests.py`, 2026-09-19), applied to every fresh numerator/denominator percentage site | PARTIAL (interim heuristic) | An n-based stopgap (0dp below n=30), not a real CI-based cap — that needs `02-claim-layer.md`'s confidence interval (Step 24). Ratios/lifts/dollar-value roundings and percentages derived from an already-divided fraction (no denominator in scope at the call site) are out of scope for this pass |
| D-15 | Ranked sponsorship pairs backed by the computed statistic + correction | `_t_sponsorship` (`tests.py:785-815`) — own comment states headline/verdict are "static prose... not derived from `s` at all"; only `base_rate` is genuinely computed | WRONG | Worse than framed: no ranking-vs-correction problem exists yet because no data-driven ranking ships at all; the prose is simply disconnected |
| D-16 | Win-rate panel states its own baseline-interpretation | `voting_power()` docstring (`queries.py:1477-1478`) already documents "baseline is the carry rate (~76%)" — but `_t_voting_power`'s headline/verdict (`tests.py:664-669`) never restates it | PARTIAL | Caveat exists only in a Python docstring, never reaches the reader; `base_rate` field carries the number but not the interpretation |
| D-17 | Selection mechanism for missing dollar-values investigated | `_t_big_dollar_leniency` (`tests.py:1211-1262`) — filters to non-null value, n≥20 floor, `era` field self-declares the filtered population | PARTIAL | Denominator is honestly labelled (real mitigation); the selection-bias question itself is uninvestigated |
| D-18 | "Flat" requires a monotonicity check, not just min-max spread | `_t_repeat_applicant` (`tests.py`) now requires spread<=5pp outright, or spread<=14pp AND no consistent step-by-step direction across >=3 populated buckets | FIXED | A monotonic trend (a real, consistent pattern) is no longer called "flat" just because its total spread is small; a 2-bucket case (no shape to assess) falls back to the plain spread check |
| D-19 | No causal language on observational comparisons | Fixed 2026-09-19: `_t_objection_dose` verdict (`tests.py`), `ObjectionDosePanel.tsx` (the exact quoted phrase, "It isn't the act of objecting that moves council — it's the numbers"), `ConflictRecusalPanel.tsx`'s "leans toward letting the matter through" | FIXED | The two frontend phrases were claim-authoring entirely outside `tests.py` — the S7 gate's text scan still never inspects component source, a real gate-coverage gap noted for `02-claim-layer.md`/`04-jurisdiction.md`, not closed by this fix |
| D-20 | Same confound treatment across panels touching the same year | `COVID_CONFOUND_CAVEAT` (`tests.py`) now appended to `_t_transparency`, `_t_confidential_topics`, and `_t_question_responsiveness` (every branch, incl. the era-neutral one) — 2026-09-19 | FIXED | See source-drift note above — was a shared absence, not an inconsistency; now a shared, single source-of-truth caveat text |
| D-21 | Inquiry-attributed shifts checked against a comparator council | `_council_era_window()` (`queries.py:3401-3413`), used by 3+ tests; every one of 35 `council_id`-typed query functions takes exactly one council | MISSING | Architecturally single-council; Perth corpus not yet extracted (pipeline track) |
| D-22 | Headline leads with must-leave-only rate | `_t_recusal_overall` now uses `ConflictRecusalStats.must_leave_recusal_pct`, a new corpus-wide aggregate field — 2026-09-19 | FIXED | The *per-councillor* frontend colour-coding already fixed this exact defect (`ConflictRecusalPanel.tsx:39-44`, 2026-08-11); the *corpus-wide* headline/grade now matches. Live-corpus effect was substantial: blended stay rate showed 25.0% recusal (CRITICAL-leaning); must-leave-only shows 90.2% (119/132) — the blended figure was masking genuinely strong compliance on legally-mandatory conflicts |
| D-23 | Impartiality-type figures visually separated from the grade they don't affect | `RecusalTrendPanel.tsx`'s impartiality stat now carries an explicit badge + label — 2026-09-19 | FIXED | `RecusalTrendStats.impartiality_post_*` (`queries.py`) was already computed correctly and correctly excluded from the grade; the fix is presentation-only, a "Context only — does not affect the grade above" badge plus clarifying label text |
| D-24 | Headline and inline callout compare the same two eras | `_t_recusal_trend` (`tests.py`) and `RecusalTrendPanel.tsx`'s confound callout both switched to pre→post — 2026-09-19 | FIXED | New `RecusalTrendStats.financial_pre_pct`/`financial_pre_n` field closes the gap in both the battery test's verdict and the frontend panel's own separate confound callout (a second, independent live occurrence found while fixing this) |
| D-25 | Officer-divergence panel discloses detection limits; deferrals split from departures; direction reviewed per category | `_t_officer_divergence` (`tests.py`) now discloses both — 2026-09-19; directionality unresolved | FIXED (×2 of 3) | Amendment-blindness is now in the `TestResult.verdict`, not just a code comment; LOST/DEFERRED now reported separately (`DivergencePair.council_outcome` already carried the distinction — no `divergence.py` change needed, just no longer collapsed at the `tests.py` aggregation step). Directionality (is high ratification adverse or expected for planning) is a normative question deferred to `04-jurisdiction.md`'s jurisdiction critic, per this step's own scope — not attempted here |
| D-26 | Unminuted deliberative-forum caveat in methodology | Added to `Investigator_prompt.txt` Part 0.4, cross-referenced from the Part 3 officer-capture row — 2026-09-19 | FIXED | The team already modelled briefing forums institutionally; the caveat about the *unminuted* ones was simply never written |
| D-27 | Goodhart caveat on recusal metric | Added to `Investigator_prompt.txt` Part 0.4, cross-referenced from the Part 3 declared-but-not-recused row — 2026-09-19 | FIXED | — |
| D-28 | Framework citations match WA law, not UK | Nolan/CIPFA hardcoded independently in 3 places (`config/test_registry.json`'s `principles`, `tests.py`'s `principle=` literals, `OverviewPanel.tsx:38-80`) | WRONG (citation layer) / PARTIAL (computation layer) | WA statutory awareness already exists uncited in computation: `system_prompt.txt:233` uses s5.65; `queries.py:3429-3438` has a working s5.69 detector |
| D-29 | s5.68 (council-resolution exception) detected | `_ministerial_approved()` (`queries.py:3429-3438`) detects the *sibling* provision s5.69 via substring match; zero hits for "5.68" anywhere | PARTIAL | Structurally analogous working mechanism exists for s5.69, built after this exact failure mode (lawful conduct mislabelled) was caught once in production |
| D-30 | Legal citation backing "correctly" claims | `_t_delegate_body_conflict` headline (`tests.py:~427-430`) — "correctly" is a bare adjective, no citation anywhere | MISSING | — |
| D-31 | No unconfirmed name-match names anyone; collision count has a chance baseline | `_t_decider_supplier_conflict` (`tests.py:993-1052`) + `evidence_for_decider_supplier_conflict` (`evidence.py:1416-1477`) + `_build_surname_collision` (`method.py:619-683`) | PARTIAL | The two live/public surfaces already withhold names by construction; no null model (expected-collisions-under-chance) exists anywhere. See source-drift note |
| D-32 | Site byline checked against corpus roster for name collisions | No personal name/byline found anywhere in `frontend/src/` (footer, contact, about, package metadata) | NOT DETERMINABLE FROM SOURCE | Likely originates outside this repo (hosting-dashboard metadata) — needs the original critique session's screenshot/URL, not derivable from code |
| D-33 | Accuracy statement with precision/recall, model version, extraction date, audited sample | `build_method_record()` (`src/analysis/method.py`) already ships quote-completeness, paraphrase-rate, coverage-ratio, PASS/REVIEW/FAIL split, each with its own `generated_at` — **and is public tier** (`SNAPSHOT_TIER["method"]="public"`, `src/cli.py:1981`) | PARTIAL | Narrower gap than framed: model version and Level-6 human-audit results are the two specific things absent; the rest is live today |
| D-34 | "Sent to the Town on [date]; response here" disclosure | `TestResult.reply` field (`tests.py:129`) + full `src/reply_packets.py` assembly/ledger machinery exist; zero frontend component reads `reply` | PARTIAL | Two independent gaps: no frontend rendering even if populated, and the process has never actually been run |
| D-35 | Non-overlapping axis tick labels | `BatteryTestPanel.tsx:62` — bare `unit` prop, no `tickFormatter`/`interval`/rotation | WRONG | Confirmed root cause; affects all 14 generic-fallback battery tests, not a one-off |
| D-36 | One-line plain-English "is my council OK?" verdict | `OverviewPanel.tsx:6-17` — a hand-written synthesis **used to exist**, deliberately removed (`SECOND_COUNCIL_PLAN.md` Phase 3.5) because it hardcoded Cambridge-specific conclusions | MISSING (deliberate) | Named, designed replacement (Renderer's synthesis mode) exists but has never run — blocked on a separate track, not an oversight |
| D-37 | Jargon terms defined at point of use | No glossary/tooltip component exists anywhere in `frontend/src/`; `/method`'s `metric.definition` is a separate, narrower per-metric field | MISSING | — |
| D-38 | No arrow/flow styling between non-flowing denominators | `ConflictRecusalPanel.tsx:195-210` — literal arrow glyph between two of three differently-denominated stats | WRONG | Confirmed root cause, compounds D-12 |
| D-39 | WA/Australia jurisdiction visible wherever Nolan/CIPFA appear | `AboutPage.tsx:149,158` is the only "Western Australia" text anywhere in the frontend; zero hits in `SiteNav`/`SiteFooter`/`CouncilHeader` | PARTIAL | Disambiguator exists exactly once, on a page most readers won't visit first |

---

## Gaps

### G-01: Fiscal-year anchor hardcoded to calendar December
Target: EOY-spending analysis anchors on the WA local-government year (1 Jul–30 Jun).
Current: `_t_eoy_spending` (`tests.py:1441-1481`) buckets by calendar month and hardcodes `highlight_label="Dec"`.
Delta: no fiscal-year config exists anywhere in `src/`; the function asserts a false fiscal fact in its own headline text.
Risk if unfixed: a genuine July use-it-or-lose-it pattern is invisible; the panel tests, and fails, the wrong month.

### G-02: 12-month chart may render fewer than 12 bars — RESOLVED, does not reproduce
Target: every month has a bar, or a documented reason why not.
Current: backend unconditionally emits 12 bars (`by_month = [0.0]*12`, populated over `range(12)` with no conditional skip, `tests.py:1454-1462`); `_bars()` (`tests.py:148-158`) does a bare list comprehension over whatever pairs it's given, no length check; `BatteryTestPanel.tsx`'s `ChartView` renders `bars.map(...)` over `chart.bars` verbatim, no filter/threshold.
Delta: none — verified 2026-09-19 by reading the full path from data assembly to render, not a live draft (Step 1's own "Files touched: none" already anticipated this). No drop/merge path exists anywhere in the current pipeline, so there is nothing that could produce fewer than 12 bars.
Risk if unfixed: none — not a live defect. No code change made.

### G-03: Two tender-total populations presented as comparable
Target: one reconciled, deduplicated tender-dollar population feeds every panel that states a total.
Current: `_tender_rows()` (undeduped) feeds the month panel; `tender_concentration()` (deduped, with a documented real triplicate-extraction case) feeds the contractor panel.
Delta: same underlying `tenders` table, two different population definitions, no declaration of which on either panel face.
Risk if unfixed: the two headline totals can never agree, by construction — not noise, a guaranteed reconciliation failure.

### G-04: No declared population/grain object anywhere in the analysis layer
Target: every statistic's n traces to one declared, filterable population definition.
Current: confirmed absent architecturally — every `_t_*` function in `tests.py` writes its own ad hoc SQLAlchemy filter chain independently, with nothing to catch two "about the same thing" tests silently diverging.
Delta: this is the single most consequential structural gap in the whole defect list — it is the reason D-01, D-03, D-04, D-08, D-13, D-17 all exist as distinct symptoms of one missing piece of architecture.
Risk if unfixed: exactly D-04's own framing — the single most attackable element of the report, and the current architecture guarantees such pairs exist, not by accident.

### G-05: Contractor display-label re-derived independently per chart
Target: one canonical display label per contractor, shared by every chart that names one.
Current: `tender_concentration()` preserves an original-spelling `display_name`; `_t_procurement_incumbency` instead applies `.title()` directly to the destructively-normalised key, producing "Totaleden"/"Leoheaney"/"Cjdequipment".
Delta: a second, inferior implementation of a problem already solved once in the same file's neighbour function.
Risk if unfixed: the two panels can never be cross-read to audit whether entity resolution is behaving consistently — precisely the check an adversarial reader would attempt first.

### G-06: Multi-recipient tender awards have no data model
Target: a tender awarded jointly to several firms attributes (or splits) dollars without double-counting any one firm.
Current: `Tender.awarded_to`/`ExtractedTender.awarded_to` is a single free-text string; confirmed live in the DB that "Various contractors: Total Eden..., Elliotts..., Malua..., Hugall and Hoile" exists as one row alongside 8 other rows where those same names recur alone or in different composites.
Delta: schema has no multi-recipient concept at all — this is an extraction-schema gap, not just an analysis-layer aggregation bug.
Risk if unfixed: real double-counting/fragmentation of dollars; a "Various contractors: ..." bucket ranking as a peer of named firms reads as deliberate obscuring to a lay reader.

### G-07: Contested-vote ranking display path — found and fixed (2026-09-19)
Target: one entity per real person in any contested-vote ranking.
Current: `voting_power()`'s query/render path (`queries.py:1517-1557`, `PowerPanel.tsx:214`) confirmed clean — labels with full given+family name, would not produce a bare "Carr". The actual reproducing path was the unwired `DissentProfilesChart.tsx` (zero imports anywhere in `frontend/src/registry`/`pages`, confirmed by grep): its Y-axis used `surname(p.name)` alone, and 2 distinct real Cambridge councillors named Carr both qualify for the chart (`total_votes_on_carried >= 50`) — a genuine collision, verified by running `dissent_profiles()` against the live corpus (councillor_ids 240 and 5, both "Carr").
Delta: `dissent_profiles()` (`queries.py:1170-1243`) already computed `councillor_id` correctly; `src/cli.py`'s `dissent` snapshot serialization dropped it before it ever reached the frontend, and the frontend `DissenterProfile`/`DissentPair` types had no id field to carry it even if present. Three-layer fix: `councillor_id`/`id_a`/`id_b` now flow through serialization and the frontend types; `DissentProfilesChart.tsx` appends a given-name initial to the surname label only when a collision exists among the currently-charted profiles, keyed by `councillor_id` (not display label) for the chart's `Cell` identity.
Risk if unfixed: none live today (dead code, not rendered on any page) — fixed anyway since the reproducing path was found, so it can't resurface if the component is ever wired into a page later.

### G-08: Objection extraction has no per-submission count field — FIXED (schema only)
Target: a dose-response bucket reflects true objector volume, one row per real person.
Current: `ExtractedCommunitySubmission.count` (schema), `CommunitySubmission.count` (additive column) now let an aggregate-reported group ("14 objections received") be its own row with `submitter_name=None, count=14`, distinct from a named individual's row (`count=None`, read as 1) — updated `system_prompt.txt` instructs the extractor never to fold the two into one entry.
Delta: join/normalisation logic itself was already sound and confirmed against the live DB; the schema was the limiting factor, now closed. Future extractions only, per the no-re-query constraint — the existing corpus's rows are untouched and keep an implicit count of 1, same as before this fix.
Risk if unfixed: n/a for future extractions. The existing corpus still measures "how many objectors happened to be individually named," not true volume, until re-extracted — an accepted, honestly-stated gap, not silently fixed retroactively.

### G-09: Attendance/apology data extracted but discarded before persistence — FIXED
Target: non-attendance measurable independently of vote-tally rows.
Current: a new `meeting_attendance` table (`src/models/ontology.py`'s `MeetingAttendance`/`AttendanceStatus`) is now written on every extraction (`save_extraction()`, `src/extraction/extractor.py`), keyed by `(meeting_id, councillor_id)`, resolved through the same `_get_or_create_councillor()` matching every other entity type uses. `scripts/backfill_attendance.py` recovered 3,327 rows for the existing corpus from `data/llm_archive/`'s chunk-0 raw responses, with zero new API calls — deliberately narrow (only ever inserts `MeetingAttendance`, never touches votes/motions/any other table, unlike a full `archive_import.py --force` re-run).
Delta: none remaining in the persistence mechanism itself. Coverage is honestly partial: 373/686 minutes meetings (54%) now have at least one attendance row; the rest have no archived chunk-0 response to recover from (predates archiving, or was archived without a `pdf_path`/chunk-0 match) — reported as a real gap, not backfilled with an invented value.
Risk if unfixed: n/a — closed. The remaining 46% coverage gap is a data-availability limit, not a code defect; any panel reading this table should state its own denominator (how many meetings have attendance data) rather than assume full coverage.

### G-10: No validity floor gates a grade
Target: no CRITICAL/SUPPORTIVE grade issued below a stated minimum-n or CI-overlap check.
Current: `_t_recusal_trend`'s primary grade (`declined = post_pct < pre_pct - 5` → CRITICAL) has no n-gate at all; a `thin_financial` check exists but only softens a *secondary* comparison's prose.
Delta: the report's single most severe grade (n=12) is statistically indistinguishable from noise and nothing in the code would prevent it from shipping that way again on any future corpus.
Risk if unfixed: the report's most severe grade continues to rest on noise.

### G-11: MIN_N architecturally exempts every battery test
Target: no institutional-unit claim graded SUPPORTIVE/CRITICAL below a stated minimum n either.
Current: `src/invariant_gate.py`'s MIN_N check only runs on individual/individual_implicating-unit claims; all 29 battery tests default to `UNIT_INSTITUTIONAL` and are exempt by construction, confirmed by reading `run_invariant_gate()`'s control flow.
Delta: this is a scope gap in the invariant gate itself, not a bug in the two example functions (`_t_threshold_gaming` n=69 unchecked; `_t_delegate_body_conflict` already self-aware and caveated in prose, but valence is still unconditionally SUPPORTIVE regardless of n).
Risk if unfixed: absence of evidence renders as evidence of absence, at both ▲ and ✓ severity, on any future thin-n institutional test.

### G-12: Invalid ratio between structurally different event populations
Target: no ratio computed between two events that aren't the same kind of observation.
Current: `_t_recusal_overall`'s `factor = declared_recusal_pct / baseline_recusal_pct` divides a mandatory-after-disclosure act by an (undercounted, per G-09) ordinary-non-attendance rate; independently re-derived in `ConflictRecusalPanel.tsx:213-221`.
Delta: the ratio is invalid by construction, independent of any statistical-power concern, and computed twice from the same fields in two languages.
Risk if unfixed: the report's headline comparison is structurally unsound regardless of sample size.

### G-13: Vote/motion rows pooled as independent observations
Target: rates compared across councillors/meetings are clustered by the actual unit of analysis.
Current: `_t_oversight_body_capture`, `_t_freshman`, `_t_deputation_dissent` all pool vote/motion rows flat; effective n (e.g. 31 councillors) is far smaller than the reported vote-row n (e.g. 10,867).
Delta: freshman's pooled result happens to be corroborated by an unshipped clustered check per its own code comment — a lucky consistency, not a structural safeguard.
Risk if unfixed: reported precision vastly overstates effective sample size (e.g. 73.28% vs 73.13% on an effective n of 31).

### G-14: No precision cap relative to n or CI — interim heuristic shipped (2026-09-19)
Target: displayed decimal precision never exceeds what the sample supports.
Current: `_capped_pct(numerator, denominator, decimals=1)` (`tests.py`) rounds to 0 decimal places whenever the denominator is below 30, 1 (or an explicit override) otherwise — applied at every site computing a fresh percentage from a numerator/denominator pair (16 sites across `_t_transparency`, `_t_officer_divergence`, `_t_unanimity_trend`, `_t_freshman`, `_t_election_cycle`, `_t_deputation_dissent`, `_t_attendance`-style ABSENT split, `_t_confidential_topics`, `_t_question_responsiveness_meeting`).
Delta: this is Step 7's own named stopgap, not the real fix — a genuine CI-based cap needs `02-claim-layer.md`'s confidence interval (tracked as Step 24 here). Left untouched, deliberately: ratios/lifts (`below/above`, `rate/base`, `conf_med/opn_med`), differences of two already-rounded rates, dollar-value chart bars, and percentages computed from an already-divided fraction with no denominator in scope at the display site (`_t_power_spread`'s `base_carry_rate`) — none of these are a fresh "X of Y as a %" the heuristic applies to cleanly.
Risk if unfixed: reduced, not eliminated — the 16 fixed sites can no longer show false precision on a thin sample; the untouched ratio/fraction sites still can, tracked above as the residual scope for Step 24's real fix.

### G-15: Sponsorship-network prose disconnected from its own statistic
Target: the rendered claim is derived from the same computation the panel's number comes from.
Current: `_t_sponsorship`'s headline/verdict are static, hand-written, Cambridge-2000s-specific prose per its own code comment — not derived from the computed `s` object at all; only `base_rate` is genuine.
Delta: worse than D-15's original framing (a ranking lacking a permutation-null) — there is no data-driven ranking shipping yet, so there's no correction to add until the prose is reconnected to real computation first.
Risk if unfixed: a Cambridge-specific historical narrative ships unconditionally to every future council (a second-council-generalisation defect, not just a statistical one).

### G-16: Win-rate baseline interpretation stays in a docstring
Target: the panel states, in its own rendered text, that win rate approximates agreement-with-the-majority, not power.
Current: `voting_power()`'s docstring already documents "baseline is the carry rate (~76%)"; `_t_voting_power`'s headline/verdict never restates it.
Delta: the correct framing exists in code, one field away from the reader, and simply isn't surfaced.
Risk if unfixed: frequent dissenters are visually flagged as "losers" in a hierarchy chart with no adjacent explanation.

### G-17: Dollar-value recording's selection mechanism uninvestigated
Target: whether recording a dollar value correlates with application size/formality is checked, not assumed away.
Current: `_t_big_dollar_leniency` already self-declares its filtered population (`era="applications with a recorded value"`) and has an n≥20 floor — real, if minimal, mitigation.
Delta: the selection-bias question itself (does recording correlate with size/formality) has no missingness analysis anywhere.
Risk if unfixed: ~9% of the true population drives a graded claim about the other 91%, with no evidence the recorded subset is representative.

### G-18: "Flat" determined by min-max spread, not monotonicity — FIXED
Target: "no trend" and "a real non-monotonic pattern" are described differently.
Current: below a ±5pp band (the same no-clear-trend threshold `conflict.recusal_trend` already uses), shape doesn't matter — genuinely negligible either way. Between 5 and 14pp, a consistent step-by-step direction across the (frequency-ordered) buckets is now treated as a real pattern and no longer called "flat," while a non-monotonic zigzag of the same magnitude still is. A 2-populated-bucket case (this corpus's middle frequency bands are sometimes empty) has no shape to assess and falls back to the plain spread check, same as before.
Delta: closed — verified against the live corpus (82%/72%/84%/83%, a non-monotonic dip-then-recover, correctly still "flat") and the Testville/baseline synthetic fixture (2-point case, correctly still diverges by spread alone).
Risk if unfixed: n/a — closed.

### G-19: Causal-sounding language on observational comparisons — FIXED
Target: no panel text implies a mechanism where only a correlation was tested.
Current: three sites rewritten to state an association plus the alternative confounding explanation (a non-compliant application can independently attract both more objectors/scrutiny and a worse outcome), instead of asserting a mechanism: `_t_objection_dose`'s verdict (`tests.py`), `ObjectionDosePanel.tsx`'s "It isn't the act of objecting that moves council — it's the numbers", and `ConflictRecusalPanel.tsx`'s "a declared-interest vote leans toward letting the matter through".
Delta: the two frontend instances were claim-authoring entirely outside `tests.py`, on a surface the S7 invariant gate's text scan never inspects (it only scans `TestResult` fields, never component source) — that gate-coverage gap itself is *not* closed by this fix, only the two live instances of it are. Noted for `02-claim-layer.md`/`04-jurisdiction.md` as a real gap: nothing currently stops a future frontend edit from reintroducing causal language undetected.
Risk if unfixed: n/a for the three fixed sites. The underlying gate gap remains — see Delta.

### G-20: COVID/remote-meeting confound uncaveated on any era-split panel — FIXED
Target: any panel whose value could be confounded by 2020 remote-meeting rules, emergency procurement, or hardship policy says so.
Current: `COVID_CONFOUND_CAVEAT` (`tests.py`), one shared string, appended to `_t_transparency`, `_t_confidential_topics`, and every branch of `_t_question_responsiveness` (including the era-neutral one, which still spans 2020). Also added to `docs/investigator/Investigator_prompt.txt` Part 0.4 as a standing caveat for any future test touching a year-trend or era split, with cross-references from the Part 3 officer-capture/recusal criteria rows.
Delta: was a shared absence across every affected panel, not the described inconsistency between two of them (see source-drift note) — now a single source-of-truth caveat text, not three independently hand-written ones.
Risk if unfixed: n/a — closed for the three named panels and documented as a standing methodology rule for future ones.

### G-21: Inquiry treated as a natural experiment with no comparator
Target: an Inquiry-attributed shift is checked against a comparator council over the same window before being graded as a Cambridge effect.
Current: `_council_era_window()` is used by 3+ battery tests; every `council_id`-typed query function in `queries.py` (35 of them) takes exactly one council id — architecturally single-council.
Delta: Perth's corpus (per `00-codebase-map.md`) is registered but not yet extracted — this is blocked on the pipeline track, not just an analysis-layer gap.
Risk if unfixed: any WA-wide regulatory shift (2021 Model Code of Conduct, remote-meeting rules) is indistinguishable from a Cambridge-specific effect in every one of these tests.

### G-22: Corpus-wide recusal headline/grade use the blended rate, contra the frontend's own fix — FIXED
Target: headline and grade lead with the must-leave-only rate everywhere, not just in per-councillor colour-coding.
Current: `ConflictRecusalStats` gained `must_leave_total`/`must_leave_recused`/`must_leave_recusal_pct` — computed via the same fan-out-safe `_linked_declared_votes()` link and quote-aware `_actually_stepped_out()` check every per-councillor figure already used, corpus-wide and unfiltered by `min_declared` (matching `declared_total`'s scope). `_t_recusal_overall` now keys `stay`/`managed`/headline/`n` off it, falling back to the blended rate only if a corpus has zero must-leave declarations at all.
Delta: closed. `tests/test_council_agnostic.py`'s `DIRECTION_ALLOW` had `conflict.recusal_management` allow-listed specifically because the blended metric wasn't sensitive to either synthetic profile's real must-leave trend — removed now that the fix makes it correctly diverge (verified: `test_direction_tracking` now fails if the entry is left in, confirming the divergence is real, not accidental).
Risk if unfixed: n/a — closed. The Scorecard, digest, and S7 gate all consume this `TestResult` directly and now get the corrected figure.

### G-23: Impartiality figures juxtaposed with a grade they don't affect — FIXED
Target: a reader cannot mistake the 0%-impartiality-recusal figure as contributing to the panel's Critical grade.
Current: `RecusalTrendPanel.tsx`'s impartiality stat carries a `badge-neutral` "Context only — does not affect the grade above" tag, and its label now states outright that staying/voting on these is lawful and the figure is excluded from the must-leave grade.
Delta: correctness of computation vs. clarity of presentation — was a rendering gap, not a statistical one; `RecusalTrendStats.impartiality_post_*` itself is unchanged.
Risk if unfixed: n/a — closed.

### G-24: Headline and inline callout compare different era pairs — FIXED
Target: every stated comparison in one panel uses the same two reference points, or explicitly labels when it doesn't.
Current: `RecusalTrendStats` gained `financial_pre_pct`/`financial_pre_n` (`queries.py`, via the existing `_era_pct` helper — no new query pattern). `_t_recusal_trend`'s confound-check sentence (`tests.py`) and `RecusalTrendPanel.tsx`'s separate frontend confound callout — a second, independent occurrence of the same inconsistency, found while fixing this — both now compare pre→post, matching their respective headlines. `financial_pre_pct`/`financial_pre_n` also added to the public "recusal" snapshot (`src/cli.py`) and the frontend `RecusalData` type.
Delta: was `RecusalTrendStats` having no pre-side financial field to align to — now added.
Risk if unfixed: n/a — closed on both the battery test and the frontend panel.

### G-25: Officer-divergence panel's three compounding overstatement risks — 2 of 3 fixed
Target: amendment-detection limits disclosed in the claim itself; deferrals reported separately from genuine departures; directionality reviewed per item category rather than one hardcoded default.
Current: `_t_officer_divergence`'s verdict (`tests.py`) now states both the amendment-detection limit and a LOST-vs-DEFERRED breakdown, e.g. live corpus: of 6 "departures," 1 LOST outright and 5 DEFERRED (a procedural pause, not necessarily a rejection). `valence=CRITICAL if near_total else SUPPORTIVE` is still one fixed rule applied to every item category — that's the one gap explicitly not attempted this pass.
Delta: the first two were disclosure gaps (data/limitation existed, wasn't surfaced) — both closed without any `divergence.py` change, since `DivergencePair.council_outcome` already carried the LOST/DEFERRED distinction; the aggregation in `tests.py` was just collapsing it. The third is an unresolved normative question, not a code defect — flagged for `04-jurisdiction.md`'s jurisdiction critic, not assumed.
Risk if unfixed: reduced from three compounding risks to one (directionality) on what the source doc calls its own most attackable panel category.

### G-26: Unminuted deliberative-forum caveat missing from methodology — FIXED
Target: the methodology prompt states that Cambridge (like every WA council) holds unminuted briefing/concept forums where deliberation may occur off-record, reframing officer-ratification/contestation/low-visible-contest findings.
Current: added to `Investigator_prompt.txt` Part 0.4, with the Part 3 "officer capture" row now pointing back at it explicitly.
Delta: was a pure caveat-writing gap — the team already modelled these forums institutionally. Doc-only fix, no code change (Step 11's own scope) — the live battery panels (officer_divergence, oversight_body_capture) don't yet carry this caveat in their own `TestResult.verdict` text, unlike G-20's fix; that would be a `tests.py` change beyond this step's stated file list.
Risk if unfixed: n/a in the methodology doc; the live-panel gap just noted remains open (not this step's scope).

### G-27: No Goodhart caveat on the recusal metric — FIXED
Target: the methodology states the metric can only see councillors honest enough to declare.
Current: added to `Investigator_prompt.txt` Part 0.4, with the Part 3 "declared-but-not-recused voting" row now pointing back at it explicitly.
Delta: was a net-new caveat, doc-only per this step's scope — same live-panel caveat gap as G-26 above (`_t_recusal_trend`/`_t_recusal_overall` don't carry it in their own verdict text yet).
Risk if unfixed: n/a in the methodology doc; the live-panel gap remains open.

### G-28: UK frameworks cited where WA statutory language already exists uncited
Target: every `principle=` field cites an instrument this council is actually assessed against.
Current: Nolan/CIPFA hardcoded independently in `config/test_registry.json`, `tests.py`, and `OverviewPanel.tsx` (three unsynced copies); meanwhile `system_prompt.txt:233` already cites LGA 1995 s5.65 and `queries.py:3429-3438` already has a working s5.69 detector, both uncited in any output-facing label.
Delta: the WA legal-framework redesign itself belongs to `04-jurisdiction.md`; this gap is scoped to *tracing* the three-way duplication and confirming that some WA statutory awareness already exists in computation, just not in citation.
Risk if unfixed: every `principle=` field asserts a legal basis this council isn't assessed against — see `04-jurisdiction.md` for the replacement design.

### G-29: s5.68 council-resolution exception has no detector
Target: a council resolution under s5.68 permitting a member to remain and vote is distinguished from an undeclared conflict.
Current: `_ministerial_approved()` detects the sibling s5.69 provision via a substring match on quote text, built specifically after this exact failure class was caught in production (2026-08-22, four councillors' s5.69-approved stay-and-vote wrongly ranked as an individual compliance-lapse pattern); zero equivalent exists for s5.68.
Delta: structurally analogous mechanism exists and works for the sibling provision — extending it is mechanically smaller than building recognition from nothing, though confirming an actual *council resolution* occurred (vs. a citation merely appearing in free text) may need a real extracted field, a design question for `04-jurisdiction.md`.
Risk if unfixed: per the source doc, the single highest-priority item in the whole plan — lawful, council-authorised conduct labelled a compliance lapse, on named individuals, and the codebase has already proven this exact error occurs in production for the sibling provision.

### G-30: Unsupported legal conclusion in delegate-panel headline
Target: "correctly" claims cite a specific legal basis or are softened to an observation.
Current: `_t_delegate_body_conflict`'s "public role, correctly" is a bare adjective in an f-string, no citation anywhere in the function, its docstring, or `queries.py`.
Delta: net-new citation needed, or the claim is softened — a `04-jurisdiction.md` question once a WA legal-reference layer exists.
Risk if unfixed: a specific, checkable legal claim ships with no basis, beside a live counter-argument (reg 34C) the report doesn't address.

### G-31: No chance-baseline for the surname-collision count
Target: a raw collision count is reported against an expected-count-under-chance, and no code path names anyone from an unconfirmed match.
Current: the two live/public surfaces (`_t_decider_supplier_conflict` + its evidence chain; `/method`'s `_build_surname_collision`) already withhold councillor names by explicit, commented, dated design; no null model (birthday-problem-style expected collision count given N awards and K surnames) exists in any of the three related code paths.
Delta: the naming-safety half of D-31 already appears solved on the surfaces that ship; the statistical half (is 2-of-412 even above chance) is unaddressed everywhere.
Risk if unfixed: a result that may be *below* chance continues to be reported as a finding rather than a null result.

### G-32: Site byline/subject collision — no code equivalent found
Target: confirmed given the original critique session's source (screenshot/URL), then checked against the corpus roster.
Current: not derivable from this repository — no personal name, byline, or author string exists anywhere in git-tracked frontend/config source.
Delta: this is either outside the codebase (hosting-dashboard metadata) or was already removed; needs the human who ran the original critique to say where they saw it.
Risk if unfixed: cannot be assessed without that input — carried as open, not assumed resolved.

### G-33: Accuracy statement missing model version and audit results
Target: `/method` states model version, extraction date, and Level-6 human-audited-sample results alongside its existing metrics.
Current: `build_method_record()` already ships quote-completeness, paraphrase-rate, coverage-ratio, and PASS/REVIEW/FAIL split, each timestamped, and is already public-tier — a narrower gap than framed.
Delta: `Meeting.extracted_at` is never read by `method.py`; `data/audit_report.md` (Level 6, "tooling done, human review pending" per README) is not among the five files `build_method_record()` reads.
Risk if unfixed: the report's one already-public accuracy surface still omits the two facts (which model, human-verified sample) that would let a skeptical reader actually calibrate trust.

### G-34: Right-of-reply data has no frontend surface
Target: a "sent to the Town on [date]; response here" line on every named-individual claim.
Current: `TestResult.reply` field and the full `src/reply_packets.py` assembly/ledger machinery exist end-to-end on the backend; zero frontend component reads `reply`; the process has never been run for real.
Delta: two independent gaps — a rendering gap (build once `reply` is populated) and a process gap (someone has to actually run `council reply-packets` and record real responses).
Risk if unfixed: per the source doc, this single line is worth more than any statistical fix in the whole document, and it's the only P0 in this file where the backend groundwork is essentially done.

### G-35: Axis tick labels overlap on 14 generic-panel tests
Target: numeric axis ticks render as visually distinct labels regardless of value range.
Current: `BatteryTestPanel.tsx:62`'s bare `unit` prop with no `tickFormatter`/`interval`/rotation — the shared axis for every one of the 14 generic-fallback battery tests.
Delta: confirmed root cause, not a one-off — will recur on the next council with different value ranges unless fixed at the shared component.
Risk if unfixed: reproducible garbling on 14 of 29 tests, and will resurface identically for council #2.

### G-36: No plain-English "is my council OK?" verdict
Target: one sentence, somewhere, answers the question every resident actually has.
Current: a hand-written synthesis existed once and was deliberately removed because it hardcoded Cambridge-specific conclusions that would be "unchanged and wrong for any other council"; the designed replacement (Renderer's synthesis mode) has never been run.
Delta: not an oversight — a known, named gap blocked on a separate track's calibration.
Risk if unfixed: unchanged from the source doc's framing; blocked, not forgotten.

### G-37: No glossary or hover-definitions for jargon
Target: CIPFA-A..G, Nolan principles, lift, ×N, DIRECTIONAL, base rate, matched votes, must-leave, impartiality interest, recusal, and blended rate are each defined at the point they appear.
Current: no glossary/tooltip component exists anywhere in `frontend/src/`; the one static explanatory paragraph in `ScorecardPanel.tsx:120-126` covers the valence ladder only, once, not attached to individual jargon occurrences; `/method`'s `metric.definition` is a separate, narrower field scoped to that page only.
Delta: net-new component.
Risk if unfixed: every governance-framework label and every derived-statistic term on every panel is unexplained at its point of use.

### G-38: Funnel arrow implies flow between non-flowing denominators
Target: three differently-denominated statistics are not visually chained.
Current: `ConflictRecusalPanel.tsx:195-210` renders an explicit arrow glyph between two of the three stats (baseline rate → declared rate), with the third (a raw count) merely adjacent.
Delta: confirmed root cause; directly compounds G-12's substantive validity problem with a layout that visually asserts the false relationship even for a reader who wouldn't otherwise infer it from text.
Risk if unfixed: — as stated in the source doc.

### G-39: WA jurisdiction cue absent from site-wide chrome
Target: a reader landing directly on any analysis panel sees a WA/Australia cue, not just on a separately-navigated About page.
Current: the only "Western Australia" text anywhere in the frontend is on `AboutPage.tsx:149,158`; zero hits in `SiteNav`/`SiteFooter`/`CouncilHeader`, the persistent chrome shown on every panel where Nolan/CIPFA terms actually appear.
Delta: the disambiguating fact exists exactly once, off the most likely entry point (a shared panel link).
Risk if unfixed: a reader arriving via a shared link sees "cambridge" + Nolan + CIPFA with zero jurisdiction cue on that page.

---

## Implementation steps

Ordered: independent mechanical fixes first (no shared infrastructure needed),
then fixes that share a dependency on the claim-object work in
`02-claim-layer.md`, then fixes blocked on other tracks. Steps within each
group are sequential; groups may be worked in parallel by different people
since they touch disjoint files, but the dependency notes below must still
be honoured.

### Step 1: Verify the 12-month chart bar count against a live draft
Files touched: none (verification only) — `data/draft/cambridge/<run_id>/finance.eoy_spending... json` (inspect, don't edit)
Depends on: none
Done when: G-02 is reclassified from UNVERIFIED to a definite status with a citation, before any fix is attempted.

### Step 2: Fix the fiscal-year anchor
Files touched: `src/analysis/tests.py` (`_t_eoy_spending`), `src/council_eras.py` or a new `config/fiscal_year.json` if a per-council fiscal-year boundary is needed for a second council
Depends on: none
Done when: `_t_eoy_spending` buckets by WA fiscal year (Jul–Jun) and `highlight_label` reflects the actual use-it-or-lose-it month(s); a re-run against Cambridge shows July, not December, as the flagged month.

### Step 3: Unify contractor display-label derivation
Files touched: `src/analysis/queries.py` (extract `display_name`-preservation logic from `tender_concentration()` into a shared helper), `src/analysis/tests.py` (`_t_procurement_incumbency` calls the shared helper instead of `.title()`-ing the normalised key)
Depends on: none
Done when: the Top-15 and repeat-winners charts show identical spelling for the same contractor.

### Step 4: Investigate and, if needed, fix the contested-vote display path
Files touched: TBD pending investigation — likely a retired chart component or `voting_power()`'s caller
Depends on: none
Done when: either the current live path is confirmed not to reproduce the "Carr" duplicate (G-07 closed as not-a-current-defect), or the actual reproducing path is found and fixed to key by `councillor_id`, not display name.

### Step 5: Persist attendance/apology extraction output
Files touched: `src/models/ontology.py` (new table or columns for per-meeting presence/apology), `src/extraction/extractor.py` (`save_extraction()` — write `councillors_present`/`councillors_apology`), a one-off backfill script reading `data/llm_archive/` for already-extracted meetings (no re-querying the API, per the hard constraint in `00-README.md`)
Depends on: none
Done when: a `meeting_attendance`-shaped table exists and is populated for the full corpus without any new Claude API calls; `_t_attendance` can compute genuine non-attendance independent of vote-tally ABSENT rows.

### Step 6: Add a `count` field to community-submission extraction
Files touched: `src/extraction/schemas.py` (`ExtractedCommunitySubmission`), `src/extraction/system_prompt.txt`, `src/models/ontology.py` (`CommunitySubmission`)
Depends on: none (this is a schema change for *future* extractions only — no re-extraction of the existing corpus is required or proposed here, consistent with the no-re-query constraint; existing rows keep an implicit count of 1)
Done when: new extractions distinguish a named individual submission from an aggregate-reported group.

### Step 7: Cap displayed precision to what n/CI supports
Files touched: `src/analysis/tests.py` (a shared formatting helper used by all 29 `_t_*` functions)
Depends on: Step 10 (a CI/interval needs to exist before precision can be capped to it) — sequence after the claim-object group below, or ship an interim n-based heuristic (e.g. no more than 0 decimal places below n=30) as a stopgap now.
Done when: no percentage in any panel shows more significant figures than its n supports.

### Step 8: Fix the "flat" classification rule
Files touched: `src/analysis/tests.py` (`_t_repeat_applicant`)
Depends on: none
Done when: the function distinguishes "no monotonic trend" from "flat" and only claims the latter when the data actually has no meaningful spread in either direction.

### Step 9: Remove causal language from `_t_objection_dose` and the frontend recusal panel
Files touched: `src/analysis/tests.py` (`_t_objection_dose` verdict text), `frontend/src/components/ConflictRecusalPanel.tsx` (remove the hardcoded causal phrase; either delete the callout or replace with the raw comparison stated non-causally)
Depends on: none
Done when: neither surface asserts a mechanism beyond what the observational data supports; the S7 gate's text-scan scope question (frontend never inspected) is noted to `04-jurisdiction.md`/`02-claim-layer.md` as a gate-coverage gap, not fixed here.

### Step 10: Add a COVID/remote-meeting caveat to every era-split test
Files touched: `src/analysis/tests.py` (`_t_question_responsiveness`, `_t_transparency`, `_t_confidential_topics`), `docs/investigator/Investigator_prompt.txt` Part 0
Depends on: none
Done when: all three (not just the one D-20 originally named) carry the same 2020 confound caveat.

### Step 11: Add missing methodology caveats (briefing forums, Goodhart)
Files touched: `docs/investigator/Investigator_prompt.txt`
Depends on: none
Done when: Part 0 or the relevant criteria section states both caveats; downstream panels referencing officer-ratification/contestation/recusal cite them.

### Step 12: Align corpus-wide recusal headline/grade to the already-fixed must-leave-only logic
Files touched: `src/analysis/queries.py` (`ConflictRecusalStats` — add a must-leave-only aggregate field), `src/analysis/tests.py` (`_t_recusal_overall` — switch `stay`/`managed`/headline to the new field)
Depends on: none
Done when: the corpus-wide headline and the per-councillor colour-coding agree on which rate drives the grade.

### Step 13: Visually separate the impartiality figure from the recusal grade
Files touched: `frontend/src/components/RecusalTrendPanel.tsx`
Depends on: none
Done when: the 0%-impartiality figure carries an explicit "does not affect the grade above" marker or is moved out of the graded panel entirely.

### Step 14: Align the recusal-trend confound-check to the same era pair as the headline
Files touched: `src/analysis/queries.py` (`RecusalTrendStats` — add `financial_pre_pct`/`financial_pre_n`), `src/analysis/tests.py` (`_t_recusal_trend`)
Depends on: none
Done when: headline and confound-check either use the same two eras, or the text explicitly labels the difference.

### Step 15: Disclose officer-divergence detection limits and split deferrals from departures
Files touched: `src/analysis/divergence.py` (`officer_divergence()` — return LOST/DEFERRED as separate counts, not one boolean), `src/analysis/tests.py` (`_t_officer_divergence` — surface the amendment-blindness caveat in the `TestResult`, report LOST/DEFERRED separately in the verdict)
Depends on: none for the disclosure/split; the directionality question (is high ratification adverse or expected for planning matters) is flagged to `02-claim-layer.md`/human review, not resolved here.
Done when: the `TestResult` states its own detection limit and reports genuine departures separately from deferrals.

### Step 16: Add a name-frequency null model to the surname-collision test
Files touched: `src/analysis/queries.py` (`decider_supplier_conflict()` or a new helper computing expected collisions given N awards and K distinct surnames), `src/analysis/tests.py` (`_t_decider_supplier_conflict`), `src/analysis/method.py` (`_build_surname_collision()`)
Depends on: none
Done when: the reported collision count is accompanied by an expected-count-under-chance, and a below-chance result is reported as a null, not a finding.

### Step 17: Add model version and Level-6 audit results to `/method`
Files touched: `src/analysis/method.py` (`build_method_record()` — read `Meeting.extracted_at`/model from `data/llm_archive/` or `data/batch_jobs/`, read `data/audit_report.md` once Level-6 review exists)
Depends on: Level-6 human audit actually being performed (README: "tooling done, human review pending") for the audited-sample half; the model-version half has no dependency and can ship immediately.
Done when: `/method` states which model extracted the corpus and, once available, cites a human-audited sample size and result.

### Step 18: Build a frontend right-of-reply display
Files touched: `frontend/src/components/` (new component reading `TestResult.reply`), wherever named-individual claims render
Depends on: `council reply-packets` actually being run for real at least once, and at least one real response recorded — an operational step, not a code dependency, but the display should be built and tested against synthetic `reply` data now rather than waiting.
Done when: any claim carrying a non-null `reply` renders its sent-date/response inline.

### Step 19: Fix axis tick formatting on the generic battery panel
Files touched: `frontend/src/components/BatteryTestPanel.tsx`
Depends on: none
Done when: no tick label collides with another across all 14 generic-fallback tests at standard panel widths — verified by rendering each and inspecting, not just by code review (see `03-critic-agents.md`/`05-verification.md` for whether rendered-image inspection becomes a standing check).

### Step 20: Remove the funnel-arrow styling
Files touched: `frontend/src/components/ConflictRecusalPanel.tsx`
Depends on: Step 12/Step 14 (the underlying denominators these three stats represent should be settled first, so the layout fix reflects the final set of numbers, not an intermediate one)
Done when: no arrow or equivalent flow-implying element connects stats with different denominators.

### Step 21: Add a WA jurisdiction cue to site-wide chrome
Files touched: `frontend/src/components/SiteNav.tsx`, `SiteFooter.tsx`, `CouncilHeader.tsx`
Depends on: none
Done when: every page, not just About, carries a visible WA/Australia cue alongside the council name.

### Step 22: Build a glossary/tooltip component
Files touched: new `frontend/src/components/Glossary.tsx` or a tooltip wrapper, wired into every panel that prints a `principle`/jargon term
Depends on: Step 24/25 (the framework-citation redesign in `04-jurisdiction.md` may change which terms need defining — sequence the glossary's term list after that lands, or accept it will need a follow-up pass)
Done when: every jargon term listed in D-37 has a definition reachable at its point of use.

### Step 23: Design and add a declared population/grain field to the claim object
Files touched: cross-references `02-claim-layer.md`'s claim-object schema
Depends on: **`02-claim-layer.md`** — this step is a restatement of that category's core deliverable as it applies to G-04/G-08(part)/G-13/G-17; do not build a parallel mechanism here.
Done when: `02-claim-layer.md`'s steps close this; `01`'s role is limited to having identified G-03, G-04, G-06, G-08, G-13, G-17 as the concrete defects this closes.

### Step 24: Add a validity/CI gate applicable to institutional-unit claims
Files touched: cross-references `02-claim-layer.md` and `src/invariant_gate.py`
Depends on: **`02-claim-layer.md`** (the claim object needs a confidence-interval or minimum-n field to gate on) — closes G-10, G-11, G-14 once built.
Done when: `02-claim-layer.md`'s steps close this.

### Step 25: Reconnect sponsorship-network prose to its computed statistic
Files touched: `src/analysis/queries.py` (`sponsorship_network()`), `src/analysis/tests.py` (`_t_sponsorship`)
Depends on: **`02-claim-layer.md`** for the multiple-comparison-correction machinery once a real ranking exists; the prose/statistic reconnection itself has no cross-category dependency and can be done first as its own sub-step.
Done when: headline/verdict describe what `sponsorship_network()` actually returns, with no hand-written Cambridge-specific narrative; a permutation-null correction is added once a real top-N ranking ships.

### Step 26: WA legal-framework replacement
Files touched: cross-references `04-jurisdiction.md` in full
Depends on: **`04-jurisdiction.md`**, which itself depends on `02-claim-layer.md` per the reading order in `00-README.md`. Closes G-28, G-29, G-30 (and the citation half of D-28).
Done when: `04-jurisdiction.md`'s steps close this.

### Step 27: Cross-council comparator for Inquiry-attributed claims
Files touched: cross-references the pipeline track's Perth-onboarding work (`pipeline/PIPELINE.md`, `docs/SECOND_COUNCIL_PLAN.md`) — outside this plan's category set entirely
Depends on: Perth's corpus being extracted and validated (pipeline track, not started per project memory as of 2026-09-18).
Done when: at least one comparator council's data exists and a query path accepting two council ids is built — tracked here as blocked, not designed.

### Step 28: Plain-English synthesis verdict
Files touched: cross-references the Renderer role (`docs/render/Renderer_prompt.txt`, synthesis mode)
Depends on: Renderer calibration (a separate, already-identified blocker per `00-codebase-map.md` §6 — "no calibration data").
Done when: Renderer's synthesis mode has run for real at least once and produced a plain-English verdict `OverviewPanel.tsx` can render — tracked here as blocked, not designed.
