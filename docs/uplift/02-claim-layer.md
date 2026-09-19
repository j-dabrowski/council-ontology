# 02 — The Claim Layer

**This is the central architectural change. Most other files depend on it.**

## The problem it solves

Today the analyst emits a report and the builder interprets it into a panel. That
single step fuses four separable decisions: what population was measured, what
statistic was computed, how severe it is, and how to say it. When any one is wrong
the others ship with it and there is no seam at which to inspect.

Consequence: a wrong denominator (D-04), a wrong grade (D-10), a wrong jurisdiction
(D-28), and a headline contradicting its own footnote (D-22) all reached
production simultaneously.

## Target state

The analyst emits **structured claim objects**. The builder renders them with no
interpretive latitude. A deterministic linter runs between the two.

### Claim schema

```yaml
claim:
  id: str                          # stable, survives regeneration
  hypothesis: str                  # the question, phrased before the answer is known
  hypothesis_registry_id: str      # see "Hypothesis registry" below

  framework_refs:                  # config-driven, not prose
    - instrument: LGA_1995
      section: s5.65
    - instrument: ADMIN_REGS
      section: r34C

  population:
    grain: str                     # e.g. "(meeting, item, councillor)"
    definition: str                # human-readable, precise
    base_table: str
    filter_chain: [str]            # every filter applied, in order
    exclusions: [{rule: str, n_excluded: int, reason: str}]

  numerator: {definition: str, n: int}
  denominator: {definition: str, n: int}

  comparison:
    type: within_subject | between_subject | temporal | none
    reference_definition: str      # what the comparison group IS
    reference_is_same_event: bool  # false => must be flagged (see L-07)

  statistic:
    value: float
    ci_low: float
    ci_high: float
    method: str
    clustering_unit: str | null    # councillor | meeting | item | null
    multiple_comparison:
      family_size: int
      correction: none | bonferroni | bh | permutation
      survives_correction: bool | null

  power:
    mde: float                     # minimum detectable effect at this n
    achieved_power: float | null

  extraction_error:
    fields: [{field: str, era: str, precision: float, recall_floor: float}]
    source: str                    # verification run id

  confounds:
    addressed: [{name: str, how: str}]
    unaddressed: [str]

  provenance:
    source_spans: [span_ref]       # for drill-down and right of reply
    query_hash: str
    gold_table_versions: {table: version}

  names_individuals: bool
  individuals: [{name: str, n_for_this_person: int, ci_low: float, ci_high: float}]

  grade: critical | concern | neutral | supportive
  grade_justification: str

  narrative:
    headline: str
    body: str
    objection: str
    response: str
    caveats: [str]                 # rendered, not optional
```

### Design notes for the implementing agent

- `grain` is mandatory and free-text is not acceptable — validate it parses as a
  tuple of known dimension names.
- `filter_chain` must be sufficient to reproduce `denominator.n` by replay. Make
  the linter actually replay it.
- `narrative` fields are the **only** place the builder may write prose, and they
  must be generated from the structured fields, not alongside them.
- `caveats` render on the panel face. They are not a footnote the headline may
  contradict.

---

## The linter

Deterministic rules, no model. Runs on every claim before any critic sees it.
Failures are blocking. This is where most of `01-known-defects.md` becomes
mechanically impossible to reship.

| ID | Rule | Kills |
|---|---|---|
| L-01 | `grade == critical` requires CI excluding the null value | D-10 |
| L-02 | `grade == supportive` requires `achieved_power >= 0.8` | D-11 |
| L-03 | Reported significant figures ≤ what CI width supports | D-14 |
| L-04 | `clustering_unit` non-null wherever denominator grain is finer than the inference unit | D-13 |
| L-05 | `names_individuals` requires: per-person n ≥ threshold, per-person CI, source_spans non-empty, right-of-reply field present | D-31 |
| L-06 | All claims sharing a `population.definition` must share `denominator.n` | D-04 |
| L-07 | `comparison.reference_is_same_event == false` → blocking unless explicitly justified and surfaced as a caveat | D-12 |
| L-08 | `filter_chain` replayed against gold must reproduce `denominator.n` exactly | D-03, D-04 |
| L-09 | `framework_refs` must resolve against the jurisdiction config (see 04) | D-28 |
| L-10 | `multiple_comparison.family_size > 1` requires a correction and `survives_correction` non-null | D-15 |
| L-11 | Every figure appearing in `narrative.headline` must exist as a field in `statistic` or `numerator`/`denominator` — no headline-only numbers | D-22, D-24 |
| L-12 | `narrative.headline` and `narrative.body` must reference the same denominator definition | D-22, D-24 |
| L-13 | Words `flat`, `no difference`, `no effect` require CI containing zero *and* adequate power | D-18 |
| L-14 | Causal verbs (`causes`, `drives`, `moves`, `leans toward`, `makes ... more likely`) blocked unless `comparison.type == within_subject` or a design justification field is populated | D-19 |
| L-15 | Any claim whose era-stratum extraction precision is below threshold cannot be graded above `neutral` | D-33 |
| L-16 | Fiscal-period claims must reference the jurisdiction's FY boundary from config, never a literal month | D-01 |
| L-17 | Entity names in any claim must resolve to a canonical id in the silver entity tables | D-05, D-06, D-07 |
| L-18 | Rendered chart series count must equal declared category count | D-02 |

Run the linter in CI as well as in the pipeline. A claim that fails should produce
a readable diagnostic naming the rule and the offending field.

---

## Hypothesis registry

Every hypothesis the analyst tests is logged **before** the result is known, with
a stable id, including those that return null and never become panels.

Purposes:
1. Gives `multiple_comparison.family_size` a real value instead of 1.
2. Enables publishing "we tested N hypotheses; M reached the reporting threshold",
   which is the difference between an analysis and a highlight reel.
3. Prevents silent hypothesis-shopping across regeneration runs.

Schema: `id, question, pre_registered_at, gold_tables_used, outcome
(reported | null | dropped), claim_id | null, drop_reason | null`.

---

## Gold table grain declarations

**Gold tables must not be agent-designed.** "Tables designed by AI-agent
investigation of what data is most useful for analysis" is the garden of forking
paths with a build step: the agent shapes gold around findings it already wants,
and every downstream statistic inherits that.

Gold is a small, stable, reviewed set of semantic facts with **declared grain**:

| Table | Grain | Notes |
|---|---|---|
| `vote_fact` | (meeting, item, councillor) | `position` enumerated incl. ABSENT; ABSENT sub-typed recusal / non-attendance / unknown |
| `declaration_fact` | (meeting, item, councillor, interest_type) | includes `s5_68_permission_granted` flag — see 04 |
| `tender_fact` | (meeting, award) | canonical contractor id, confidential flag, value, value_recorded flag |
| `application_fact` | (application) | applicant canonical id, value, value_recorded flag, objector count, outcome |
| `question_fact` | (meeting, question) | answered / deferred / unknown |
| `membership_fact` | (councillor, body, term) | delegate and committee appointments |
| `motion_fact` | (meeting, item) | mover, seconder, officer recommendation, outcome, amendment flag |

Agents may **propose** new gold tables. Proposals are gated and must declare grain.
Half the denominator chaos in D-04 is almost certainly undeclared grain.

---

## Regeneration semantics

Because claims are data:
- Swapping Nolan/CIPFA for the LG Act is a config change, not a regeneration.
- Re-grading after new error terms arrive touches claims only, never bronze/silver.
- A failed critic round regenerates the claim, not the pipeline.

Make sure the implementation preserves this. If any of the above requires
re-running extraction, the layering is wrong.

---

## Investigation prompts for the receiving agent

- Is there currently any persisted intermediate between query results and panel
  props? If so, what is its shape and how close is it to the schema above?
- Where is `grade` currently decided — in a prompt, in code, or by hand?
- Where does panel headline text originate? Is it generated from the same object
  as the numbers, or written separately?
- Is there anywhere in the codebase that already declares a table's grain?
- How are contractor and councillor names canonicalised, and at what layer? (D-05
  suggests at least two code paths.)
- Is there any record of hypotheses that were tested and not published?
