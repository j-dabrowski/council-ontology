# Coverage Audit — 2026-08-23

**What this is.** A one-off audit of what the investigation instrument
currently measures, laid against external reference frameworks for
institutional oversight. It answers one question from the 2026-08-23 redesign
discussion: *is the current hypothesis/battery coverage a well-formed slice of
what an institutional-accountability instrument should measure, or
survivorship from what the Explorer happened to notice?* It is a design
artefact — nothing here changes any prompt, test, or panel by itself. Its
recommendations feed the redesign's other two documents,
`docs/INFORMATION_ARCHITECTURE.md` and `docs/AGENT_DESIGN.md`.

**Inputs audited:** the 27 registered battery tests in `src/analysis/tests.py`
(test_ids, genres, Nolan/CIPFA principle tags), all 49 numbered hypotheses in
`INVESTIGATIONS.md` (findings, banked, nulls, kills — Sessions 1–11), the
Part 3 failure taxonomy (3.1–3.9) in `Investigator_prompt.txt`, and the
6-domain Dimension 1 check in `EXPLORATION_PROTOCOL.md`.

**Reference frameworks used:**

- **Performance-audit tradition** — ISSAI 300's three Es (economy, efficiency,
  effectiveness) plus the WA Office of the Auditor-General's actual
  local-government audit program since the 2017 mandate: procurement, records
  management, gifts and benefits, information systems, fraud controls,
  financial management, asset management
  ([program overview](https://audit.wa.gov.au/resources/local-government/),
  [procurement audit](https://audit.wa.gov.au/reports-and-publications/reports/local-government-procurement/),
  [records management audit](https://audit.wa.gov.au/reports-and-publications/reports/records-management-in-local-government/audit-focus-and-scope/),
  [financial audit results](https://audit.wa.gov.au/reports-and-publications/reports/local-government-2023-24-financial-audit-results/)).
  This is the strongest external axis because it is what a WA council is
  *actually* audited against — alignment with it is external legitimacy.
- **Political-science oversight** — McCubbins & Schwartz's police-patrol vs
  fire-alarm oversight distinction (1984); principal–agent analysis of the
  elected-chamber/administration relationship; the capture literature
  (Carpenter & Moss, *Preventing Regulatory Capture*, 2014) for
  operationalising "capture" beyond vibes; distributive-politics work on
  whether benefits track power.
- **The project's own frameworks** — Nolan principles and CIPFA A–G (already
  tagged on every battery test), Part 3 genres, and Dimension 1's six domains.
  Auditing the battery against the project's *own* taxonomy is deliberate: the
  gap between what the taxonomy names and what the battery tests is exactly
  where survivorship would show.

---

## The grid

Verdicts: **DENSE** (multiple tests + multiple confirmed/banked hypotheses),
**MODERATE** (tested, but partial or structurally limited), **THIN** (touched
once, or only nulls), **EMPTY** (no test, no hypothesis), **DATA-BLOCKED**
(tested or parked, and the corpus cannot currently support it — an enrichment
question, not an Explorer failure).

| # | Dimension | Tradition | Battery tests | Hypotheses | Verdict |
|---|-----------|-----------|---------------|------------|---------|
| 1 | Conflict-of-interest management (declare → recuse → manage) | OAG · Nolan Integrity/Objectivity · Part 3.3 | `conflict.recusal_management`, `conflict.recusal_trend`, `conflict.delegate_body_conflict` | [1]✓ [19]✓ [23]◐ [31]◐ [41]✗clean · [34]✗linkage | **DENSE** |
| 2 | Procurement integrity (threshold-gaming, supplier capture, decider–supplier links) | OAG (its first LG performance audit) · ICAC/IBAC grammar · Part 3.3 | `procurement.concentration`, `procurement.threshold_gaming`, `procurement.incumbency`, `procurement.decider_supplier_conflict` | [2]✓ [15]✗ [26]✗clean [35]✗clean [42]✗clean | **DENSE** — and notably two-sided: four converging clean nulls are published as supportive credits |
| 3 | Transparency / confidentiality use | Part 3.4 · Nolan Openness · CIPFA G | `transparency.confidential_share`, `transparency.confidential_tender_size`, `transparency.confidential_topics` | [9]✓ [25]✗ [30]◐ [36]◐ [44]◐ [49]✗clean | **DENSE** |
| 4 | Power structure & factional capture | Perth Inquiry root-cause genre · Part 3.2 · Carpenter/Moss capture | `governance.power_spread`, `governance.chair_capture`, `governance.durable_faction`, `governance.oversight_body_capture`, `governance.unanimity_trend` | [5]✗ [11]✓ [18]✓ [21]✗dup [27]◐ [28]◐ [45]◐ [48]◐ | **DENSE** |
| 5 | Elected-vs-administrative locus (principal–agent, officer capture, delegation) | Principal–agent · Part 3.2 "visible contest is theatre" · Golden Triangle | `governance.officer_ratification` | [17]✗ [22]✗ [32]✗INFEASIBLE [33]✗ [43]✗confounded | **MODERATE / partly DATA-BLOCKED** — one shipped test; the deeper questions ([32] committee-vs-chamber, [43] CEO-era discontinuity) died structurally. The corpus sees the chamber, not the administration — a hard limit of minutes as a source |
| 6 | Chamber renewal & incumbency | Part 3.2 · descriptive | `governance.incumbency`, `governance.freshman_effect`, `governance.election_cycle`, `governance.attendance` | [8]✓ [10]✗ [16]✗ [45]◐ | **MODERATE** (mostly neutral/descriptive — appropriate) |
| 7 | Citizen-input responsiveness (questions, deputations, petitions, objections) | McCubbins/Schwartz **fire-alarm** · CIPFA B | `engagement.question_responsiveness`, `engagement.deputation_dissent`, `engagement.participation`, `planning.objection_responsiveness` | [3]✗ [6]✗ [7]✓ [12]✓ [13]✗ [37]✓ [38]✗linkage [40]✗ | **MODERATE** — the only fire-alarm channel in an otherwise pure police-patrol battery; petition outcomes ([38]) are data-blocked |
| 8 | Planning fairness (applicant favouritism, big-dollar leniency) | ICAC favouritism risk · Nolan Objectivity | `planning.big_dollar_leniency`, `planning.repeat_applicant` | [14]✗clean [20]✗clean | **MODERATE** (clean nulls, shipped as such) |
| 9 | Economy / value-for-money (spending discipline, timing, waste) | ISSAI 300 economy/efficiency · OAG financial audits · Part 3.1 | `finance.eoy_spending` | [4]✗ [29]✗clean [47]✗clean | **THIN** — one test, all nulls; the corpus records *decisions to spend*, not costs or unit prices |
| 10 | Financial sustainability (reserves, debt, structural balance, capitalisation dependency) | The core of the intervention literature (Caller report; s.114 wave) · Part 3.1/3.6/3.7/3.9 | — | [24] ⏸ PARKED (data) | **EMPTY + DATA-BLOCKED** — see headline finding below |
| 11 | Programme effectiveness (did declared interventions achieve their stated purpose?) | ISSAI 300 effectiveness · UK VFM arrangements duty · CIPFA C/D · Part 3.5 | — | [46] ◐ (first attempt, Session 11; methodology needs tightening) | **EMPTY in battery, in progress** — taxonomy (3.5) and Dimension 1 domain F already exist; no shipped test |
| 12 | Gifts, benefits & post-separation relationships | OAG audited exactly this, LG-wide · ICAC | — | — | **EMPTY** — likely partly data-blocked (gift registers are usually separate documents, but acceptances/hospitality do surface in minutes) |
| 13 | Records & recordkeeping quality | OAG (a full LG performance audit topic) · VAGO/IBAC "poor records are themselves an indicator" | — | [49]✗clean touches it | **THIN — reframe opportunity**: the pipeline's own extraction caveats (§0.4 splits, NULL rates, missing values) are currently *internal apologies*; under this dimension they are publishable *findings about the council's records* |
| 14 | Distributive equity (do benefits/attention track power or geography?) | Distributive-politics literature · Nolan Selflessness | — | [42]✗clean is the only adjacent test (timing, not geography) | **EMPTY** — plausibly feasible: planning applications and works tenders carry locations |
| 15 | Asset management | OAG LG audit topic | — | — | **EMPTY + DATA-BLOCKED** — valuations/renewals live in annual statements, not minutes |
| 16 | Service performance (are the services any good?) | Best Value · resident experience | — | — | **EMPTY — out of scope, and honestly so**: needs data external to any document corpus. Should be named as a scope boundary, not silently absent |

**Nolan cross-check** (the battery's own tags): Integrity, Objectivity,
Accountability, Openness are all well covered. **Selflessness** is touched
only by `governance.election_cycle`; **Leadership** (model the principles,
challenge breaches in others) and **Honesty** have no test — Honesty is
probably untestable from minutes, but Leadership has a data trail (who moves
the censure motion, who dissents when a peer's conflict is at issue) and is a
legitimate future hypothesis seed.

---

## Findings

### F1 — The taxonomy is well-formed; the battery is skewed. The skew has a name.

The external frameworks largely *validate* the project's internal taxonomy:
Part 3 (3.1–3.9) plus Dimension 1's six domains already name almost every row
in the grid — including the empty ones. Rows 10, 11, 15 are all *named in
Part 3* (3.1, 3.5, 3.6, 3.7, 3.9) and have **zero shipped tests**. So the
answer to the survivorship question is precise: **survivorship lives in the
gap between taxonomy and battery, not in the taxonomy itself.** The top-down
mechanism (Part 3, grown by the Research track) knows what should be
measured; the bottom-up mechanism (Explorer → Refiner → battery) has only
codified the subset that is legible in voting and meeting records. The
instrument's centre of gravity is conduct and chamber politics because that
is what minutes record — corpus gravity, not agent failure. But an audit that
only checks "did each session touch each domain" (Dimension 1's current form)
will never surface this, because it measures session inputs, not cumulative
instrument coverage.

### F2 — Headline: the instrument would catch a City of Perth, but not a Croydon.

The battery as shipped detects the Perth failure mode — cultural dysfunction,
factionalism, conflict mismanagement — with real depth. It is nearly blind to
the *other* canonical failure mode, financial collapse, even though the
project's own Part 2.3 records that "failure was years in the making and
visible in the financials long before the crisis" (Caller report: reserves
£57.7m → £8.8m; the speculative-investment precursor). Rows 9/10/15 are the
whole of that failure mode, and their combined shipped coverage is one
end-of-year-spending test that returned null. For Cambridge this happens to
be tolerable — its actual historical stress (the Inquiry era) *was* the
cultural mode. As a general instrument for any institution, it is half-blind,
and the blindness is invisible from inside the current benchmark.

### F3 — The financial blind spot is a *corpus-composition* problem, not a test-writing problem.

[24] parked because reserve/debt trajectories are not reliably in minutes;
they are in annual financial statements, budgets, and (since 2017-18) the
OAG's own published LG audit results — different document classes from the
same institution. Writing more minute-based financial tests will not close
rows 10/15. Two consequences for the redesign:

1. `DATA_ENRICHMENT.md` should carry the pattern ("financial-sustainability
   signals need the annual-statement document class, not more minute
   extraction") at its pattern layer.
2. The information-architecture design should treat **a corpus as a set of
   document classes per institution**, not one class — this is also what the
   general-engine principle needs anyway (a hospital board's "minutes"
   equivalent won't carry its finances either).

### F4 — Cheap wins exist where a reframe, not new data, closes the row.

- **Row 13 (records quality):** the pipeline already *measures* the council's
  recordkeeping (split identities, NULL rates, unlinkable petitions, reused
  item references) and currently spends that knowledge only as internal
  caveats. OAG publishes records management as a first-class audit finding.
  A battery test that scores corpus-record quality — with the extraction
  ledger as evidence — converts existing liabilities into a published,
  council-agnostic, valenced finding. ([38]'s and [34]'s data-linkage nulls
  are then partially *re-attributed to the council*, where they belong.)
- **Row 12 (gifts/benefits):** minutes do record hospitality acceptances and
  gift disclosures in some councils; a hypothesis seed costs one Explorer
  slot to establish whether Cambridge's do.
- **Row 14 (distributive equity):** locations already extracted for planning
  and works items make "does spending/attention track ward or faction"
  testable now. This is also the strongest *layman-relevant* empty row — it
  is the question residents actually ask ("does my end of the district get
  anything?").

### F5 — The fire-alarm channel exists but is thin, and it is the audience-relevant one.

Row 7 is the only place the instrument listens to signals *initiated by
residents* rather than patrolling records. McCubbins & Schwartz's point is
that real-world oversight leans mostly on fire alarms because patrols are
expensive and miss what constituents already know. For the planned audience
tiers (residents, media, the council, auditors) this channel is
disproportionately valuable — it is the natural front door for the layman
tier — and half its hypotheses died to linkage gaps ([38] petitions have no
outcome field). Those specific enrichment entries are higher-value than their
current backlog position suggests.

### F6 — Strengths the audit confirms (credit where due).

Three properties of the current instrument are genuinely ahead of standard
practice and must survive any redesign: **published honest nulls** (the four
converging procurement nulls shipped as supportive credits are exemplary —
most real oversight bodies bury these); **valence balance** enforced
per-test, with a PROMOTER pass in the record; and **principle-anchored
framing** (every test already cites Nolan/CIPFA), which is exactly the
"convert a pattern into an alleged failure against a named standard" practice
the audit tradition demands. The coverage problem is a gap problem, not a
quality problem.

---

## Recommendations (design inputs, nothing built)

1. **Make cumulative coverage a standing artefact.** This grid, kept as a
   register (a `COVERAGE.md` or a table in the redesigned methodology doc),
   updated whenever a test ships or a hypothesis resolves. Dimension 1 then
   changes meaning: from "did this session touch ≥5 domains" to "did this
   session reduce the register's worst gap" — cumulative-coverage-aware
   session planning instead of per-session breadth counting.
2. **Name the scope boundary.** Rows the instrument *chooses* not to cover
   (16, and 10/15 until the document-class decision) should be stated in the
   published methodology — an instrument that declares its blind spots is
   credible; one that silently lacks them is survivorship.
3. **Feed the pattern layer.** Three `DATA_ENRICHMENT.md` pattern-layer
   candidates fall out directly: financial-sustainability document class
   (F3), petition/outcome linkage (F5), gift/hospitality records (F4).
4. **Seed the next Explorer sessions from the grid, top-down.** Rows 11
   (continue [46]), 13 (records-quality test), 14 (distributive equity),
   plus the Leadership-principle seed — chosen to close register gaps rather
   than to follow corpus gravity.
5. **Carry F2/F3 into the information-architecture design** (next redesign
   document): multi-document-class corpora; and the discovery/confirmation
   split from the 2026-08-23 discussion (Cambridge as training corpus; the
   frozen battery pre-registered against council #2) — which this audit
   reinforces, since a battery shaped by one corpus's gravity is exactly the
   kind that needs out-of-sample confirmation.
