# 04 — Jurisdiction: WA Legal Framework

Depends on `02-claim-layer.md` (`framework_refs` must be config-resolvable).

## The problem

The report grades a Western Australian local government against the **Nolan
principles** and **CIPFA** codes — UK frameworks. Every reader in the Australian
local-government sector gets a free reason to dismiss the entire report regardless
of the quality of the underlying data.

Worse, the wrong framework hides a real mechanism: WA has statutory provisions the
pipeline does not appear to model, and at least one of them means the report may
be grading **lawful conduct as non-compliance, on named individuals**.

---

## Target state

### Jurisdiction config

Framework references become data, resolvable against a config, not prose in a
prompt. A claim declares `framework_refs`; the renderer displays whichever
framework family is configured; the jurisdiction critic validates that every
reference binds the entity being assessed.

Primary instruments for WA local government:

| Key | Instrument | Relevance |
|---|---|---|
| `LGA_1995` | Local Government Act 1995 (WA) | ss 5.60–5.70 (interests), s5.68 (permission to participate), s3.57 (tenders), Part 5 Div 2 (meetings) |
| `ADMIN_REGS` | Local Government (Administration) Regulations 1996 | r34B (disclosure), r34C (impartiality interests), public question time provisions |
| `FG_REGS` | Local Government (Functions and General) Regulations 1996 | rr11–18 (tenders, thresholds, exemptions, panels of pre-qualified suppliers) |
| `CONDUCT_REGS` | Local Government (Rules of Conduct) Regulations 2007 | conduct rules, historical — superseded in part |
| `MODEL_CODE_2021` | Model Code of Conduct 2021 | current behavioural standard; **note the commencement date as an era boundary** |
| `DLGSC` | DLGSC operational guidelines | interpretive, not binding — flag as such |
| `SAT` | State Administrative Tribunal decisions | precedent on planning override, officer recommendations |

Keep Nolan/CIPFA as an **optional secondary mapping** for cross-jurisdiction
comparability, rendered subordinate to the primary instrument. Do not delete —
demote.

### Statute corpus for the jurisdiction critic

The jurisdiction critic (C-03) must retrieve, not recall. Build a corpus once:

- Full text of the instruments above, chunked by section/regulation.
- Point-in-time versions where the instrument changed inside the corpus window
  (1995–2026). The Model Code 2021 and the 2007 Conduct Regs both create era
  boundaries that any pre/post analysis must respect.
- DLGSC guidance documents, tagged as interpretive.
- Relevant SAT decisions on planning-authority override, tagged as precedent.

Store with the same provenance shape as everything else: instrument, version,
in-force dates, section, chunk id.

---

## s5.68 — highest-priority single check in this plan

**The mechanism:** under LGA 1995 s5.68, a council may resolve to permit a member
who has disclosed a financial interest to remain in the room, participate in
discussion, and vote. Where that resolution is passed, **staying is lawful**.

**The exposure:** the recusal chart colours "declared a must-leave interest and
stayed" as amber/red compliance failure, on **named individuals**. If the pipeline
does not detect s5.68 resolutions in the minutes, an unknown share of those red
bars are lawful conduct published as critical non-compliance.

**Required work:**

1. Determine whether any current extraction captures s5.68 resolutions at all.
   Search prompts, schemas, and gold for any concept of permitted participation.
2. Add `s5_68_permission_granted` (and `s5_68_resolution_span`) to
   `declaration_fact`.
3. Run a **census** sweep — not a sample — over every must-leave declaration in
   the corpus, asking a closed question of the surrounding minute text: *does this
   item contain a resolution permitting the member to participate?* Closed
   verification of this kind is well suited to the vision path in
   `05-verification.md`.
4. Until the sweep completes, any claim with `names_individuals == true` on a
   recusal metric must be blocked by the linter.
5. Once complete, must-leave denominators exclude s5.68-permitted instances, and
   the panel states the exclusion and its count.

---

## Other jurisdiction corrections

### Fiscal year (D-01)
Australian local government FY ends **30 June**. Put the boundary in jurisdiction
config and have linter rule L-16 forbid literal month anchors. The
"use-it-or-lose-it" hypothesis tests May/June against the rest of the year; the
July peak currently in the data is consistent with start-of-year contract and
panel renewals, which is a different (and unremarkable) phenomenon.

### Impartiality interests (D-23)
Admin Reg 34C impartiality interests are **stay-and-vote lawful**. A 0% recusal
rate on them is the expected outcome, not an adverse finding. Must-leave and
impartiality must never share a denominator in a graded claim. This is enforceable
as a linter rule if `interest_type` is part of the declared grain.

### Delegate declarations (D-30)
The claim that institutional delegates declaring ~0% is "correct" needs a cited
basis. Under r34C an association-based impartiality interest arguably arises from
a Council-appointed delegate role, and many WA councillors do declare one. Either
cite the basis for the current grading or regrade to neutral.

### Officer recommendations (D-25)
Check SAT precedent before grading. Frequent departure from officer
recommendations on planning matters is generally treated as the risk signal, since
officer recommendations encode statutory requirements and overrides are
appealable. A 97% adoption rate may be close to what a well-functioning planning
authority looks like. The panel's grade direction should be derived from the
jurisdiction critic's finding, not assumed.

### Unminuted briefing forums (D-26)
WA councils hold unminuted briefing/concept forums where substantial deliberation
occurs. This is a **corpus-level limitation**, not a panel-level caveat: it bounds
what the minutes can show about contest, deliberation, and officer influence.
It belongs in the method section and as a standing caveat on every claim about
visible contest, officer adoption, and contestation rate.

### Era boundaries
The corpus spans 1995–2026. Any pre/post analysis must be aware of:
- 2007 Rules of Conduct Regulations
- 2021 Model Code of Conduct
- 2020 remote-meeting and emergency-procurement arrangements (D-20)
- the Authorised Inquiry window (2018–2021)
These overlap. The Inquiry-window analyses currently attribute changes to the
Inquiry that could be any of the above (D-21).

---

## Comparator councils (D-21)

The single highest-value analytical upgrade. The Inquiry is used as a natural
experiment in at least four panels with no control, so any WA-wide shift is
indistinguishable from a Cambridge effect.

Adding two neighbouring councils of similar size converts several DIRECTIONAL
findings into defensible difference-in-differences results. Scope this as a
corpus-expansion workstream: it has extraction cost implications and should be
sequenced against the pipeline work in `06`, not started ad hoc.

---

## Investigation prompts for the receiving agent

- Where do "Nolan" and "CIPFA" strings live? Prompt text, a config, a database
  column, or hardcoded in components? This determines whether the swap is a
  config change or a regeneration.
- Does any extraction prompt or schema mention s5.68, "permitted to participate",
  or similar? If not, this is MISSING and blocks named publication.
- Is `interest_type` a first-class field in the declaration tables, and does it
  distinguish financial / proximity / impartiality?
- Where is the fiscal or calendar year boundary defined?
- Are era boundaries (Inquiry window, Model Code, COVID) defined once or repeated
  per analysis?
- Is there any existing corpus of legal or guidance text in the project?
