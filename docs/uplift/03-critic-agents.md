# 03 — Critic Agents and the Review Loop

Depends on `02-claim-layer.md`. Critics operate on claim objects plus rendered
panels, not on prose reports.

## Division of labour

The linter handles everything expressible as a rule. Critics handle only what a
rule cannot express: is this the right framing, does the headline match the
evidence, would a resident understand it, is this defamatory, what does publishing
it incentivise.

Do not build critics that duplicate linter rules. If a critic finding recurs and
is mechanisable, promote it to a linter rule and retire that part of the critic's
brief.

---

## Roster

Each critic gets: a brief, an input contract, and an output contract. All emit
typed findings (see "Findings" below).

### C-01 Auditor
**Brief:** Would a WA local-government auditor accept this finding?
**Inputs:** claim object, rendered panel, jurisdiction config.
**Watches for:** grade/evidence mismatch, missing statutory basis, populations that
don't match the regulatory unit of analysis.

### C-02 Statistician
**Brief:** Is the inference sound?
**Inputs:** claim object **plus read access to gold** — must be able to re-run the
filter chain, not just reason about it.
**Watches for:** power, clustering, CI construction, multiple comparisons,
denominator validity, selection bias, causal language.
**Would have caught:** D-10, D-11, D-12, D-13, D-15, D-17.

### C-03 Jurisdiction expert
**Brief:** Is the legal framing correct for Western Australia?
**Inputs:** claim object + **retrieval over a curated statute corpus** (see 04).
**Critical:** this critic cannot work from general knowledge. s5.68 and the June
financial year are exactly the things a general-purpose critic pattern-matches
straight past. Build it as retrieval, not as a prompt with legal instructions.
**Would have caught:** D-01, D-28, D-29, D-30.

### C-04 Council's defence counsel
**Brief:** You act for the Town of Cambridge. Demolish this panel.
**Inputs:** claim object, rendered panel, gold read access.
**Why it matters most:** the only critic whose incentive matches the real reader
you are most exposed to. The existing Objection/Response blocks are a manual
version of this — formalise it and generate the Response block from its output.
**Would have caught:** D-22, D-23, D-24, D-25.

### C-05 Extraction sceptic
**Brief:** Is this a finding or a parser artefact?
**Inputs:** claim provenance, silver quality report, per-field/per-era error rates
from `05-verification.md`, the contradictions table.
**Watches for:** implausible base rates, suspiciously round nulls, findings whose
effect size is within the extraction error band, era-boundary discontinuities that
track document format changes rather than events.
**Would have caught:** D-08, D-09.

### C-06 Cross-panel editor
**Brief:** Do all panels in this build cohere?
**Inputs:** **every** claim in the build, simultaneously. Runs once per full build,
not per panel.
**Watches for:** denominator reconciliation, entity-naming consistency,
contradictory headlines across panels, duplicated individuals, grade-scale drift,
confound handled in one panel and not another.
**Structurally the only critic that can catch:** D-04, D-05, D-07, D-20.

### C-07 Subject / fairness
**Brief:** Argue as the named individual.
**Inputs:** claim object, per-person n and CI, source spans.
**Watches for:** attributability, sample adequacy for one person, whether the
lawful explanation gets equal prominence to the adverse reading, whether the
person could locate and contest the underlying evidence.
**Triggered by:** `names_individuals == true`.

### C-08 Visual QA
**Brief:** Render the panel and look at it.
**Inputs:** **rendered image**, not markup. This is the point.
**Watches for:** label collisions, overlapping ticks, colour-blind safety,
contrast, mobile reflow, whether the chart actually supports the headline,
misleading styling (arrows implying sequence between unrelated figures).
**Would have caught:** D-02, D-35, D-38. Nothing currently in the loop has eyes.

### C-09 Goodhart critic
**Brief:** If this metric becomes known, what behaviour does it incentivise?
**Watches for:** metrics gameable by reducing transparency, metrics that penalise
disclosure, metrics that reward moving business off the record.
**Would have caught:** D-27, and would have surfaced D-26.

### C-10 Layman
**Brief:** You are a Wembley resident with no governance background.
**Inputs:** rendered panel only — no claim object, no glossary.
**Watches for:** undefined jargon, competing denominators on one screen, absence
of a plain-English answer to "is my council OK?".
**Would have caught:** D-36, D-37, D-39.

### C-11 Editor-in-chief
**Brief:** Does the headline match the evidence, is the lede the actual finding,
is anything important buried?
**Runs last.** Has all other critics' findings and the claim.
**Would have caught:** D-22 — a headline quoting a rate its own footnote disowns.

---

## Routing

Do not run eleven critics on every panel. Route on claim properties:

| Trigger | Critics |
|---|---|
| always | C-08 visual, C-10 layman, C-11 editor |
| `grade in (critical, concern)` | + C-02 statistician, C-04 defence counsel |
| `names_individuals == true` | + C-07 subject, C-01 auditor |
| `framework_refs` non-empty | + C-03 jurisdiction |
| claim touches a field with era-stratum precision below threshold | + C-05 extraction sceptic |
| metric is behavioural / could be gamed | + C-09 Goodhart |
| once per full build | C-06 cross-panel |

---

## Findings

Typed, to prevent caveat mush (critics always find something → builder always
hedges → panels become unreadable):

```yaml
finding:
  id: str                    # stable across rounds, keyed on content
  critic: str
  claim_id: str
  severity: blocking | should_fix | note
  statement: str
  proposed_remedy: str | null
  state: open | closed | wontfix
  wontfix_reason: str | null
  rounds_seen: [int]
```

- Only `blocking` gates publication.
- Unresolved `note` findings **publish as a visible limitations section** rather
  than triggering another round. A panel that survives three rounds with open
  notes ships with them on its face.
- `wontfix` requires a reason and is itself published.

---

## Loop mechanics

Four failure modes to engineer against explicitly:

**1. Caveat mush.** Handled by typed findings above.

**2. Critic capture.** By round three a critic that has seen its own prior findings
addressed starts approving out of momentum.
→ **Critics see the panel cold.** No negotiation history, no "you previously said",
no prior findings in context. Pay the re-derivation cost.

**3. Regression.** Round 3's fix reopens round 1's finding.
→ **Persistent findings ledger** keyed by finding id. Every closed finding is
re-checked each round — by the linter where mechanisable, by a cheap targeted
re-run otherwise.

**4. Non-convergence.** Infinite loop on a claim that cannot be rescued.
→ **Hard cap at three rounds.** On failure the claim is written to a `dropped`
registry with its findings and is not published. Dropped claims are counted and
the count is published. "We tested 47 hypotheses, 12 reached the reporting
threshold, 3 were dropped after review" is a credibility asset.

### Flow

```
gold ──► analyst ──► claim object ──► LINTER (deterministic, blocking)
                          │                  │ fail
                          │                  └──► regenerate claim (round++)
                          ▼ pass
                      builder ──► rendered panel
                          │
                          ▼
                    CRITIC FAN-OUT (routed, cold)
                          │
                    findings ledger
                          │
              ┌───────────┴───────────┐
       blocking open              none blocking
              │                       │
       round < 3 ──► regenerate       ▼
       round = 3 ──► dropped[]     publish with open notes as limitations
```

The builder and analyst are both regeneration targets. Route by finding type:
statistical and framing findings go back to the analyst (claim regeneration);
visual and layman findings go to the builder (render only). A visual finding must
never trigger a claim regeneration — that is how a rendering bug becomes a
different statistic.

---

## Investigation prompts for the receiving agent

- What review or validation exists today between generation and publish? Is it a
  single prompt, a human step, or nothing?
- Is there any rendered-image capture in the pipeline? If not, what is the
  cheapest path to one (headless browser? existing SSR?).
- Are agent invocations currently stateful across rounds? If so, that is the
  critic-capture failure mode and needs breaking.
- Is there a place findings could persist today, or does that table need creating?
- Are there any existing prompts that mix statistical judgement with prose
  authorship? Those are the ones to split.
