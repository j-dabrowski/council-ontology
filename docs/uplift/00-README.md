# Council Ontology — Uplift Plan (Handover Brief)

## What this folder is

A specification of a **target state** for the Council Ontology / Intelcrier project,
derived from a critique session against the live Town of Cambridge report
(`council-ontology.vercel.app`).

It is **not** a migration plan. It describes where the project should end up and
what defects were found. The migration plan is the output you are being asked to
produce.

## Your task

You have read access to the full project and database. For each numbered file in
this folder:

1. **Locate the current equivalent.** Find the code, table, prompt, config, or
   component in the project that today performs the function described — or the
   thing that performs it badly, or the thing that was supposed to and is now
   dead.
2. **Classify it.** One of:
   - `ALIGNED` — already matches the target, no work
   - `PARTIAL` — exists, needs extension or correction
   - `WRONG` — exists, actively produces the defect described, needs replacement
   - `REDUNDANT` — superseded by the target design, needs deletion
   - `MISSING` — no equivalent exists, needs building
3. **Write the gap.** What specifically differs, with file paths and symbol names.
4. **Write sequential implementation steps** to close it.

## Output format

Produce one markdown file per category, mirroring this folder's numbering, in a
sibling folder. Each file:

```
# <Category> — Migration Plan

## Current state inventory
| Target capability | Current equivalent | Path | Status | Notes |

## Gaps
### G-<n>: <short name>
Target: ...
Current: ...
Delta: ...
Risk if unfixed: ...

## Implementation steps
### Step <n>: <imperative title>
Files touched: ...
Depends on: <step ids, possibly in other categories>
Done when: <observable condition>
```

Steps must be **sequential within a category** and must declare cross-category
dependencies explicitly. Do not interleave categories.

## Conventions

- **No Claude Code attribution in git commits.** No `Co-Authored-By`, no
  `Generated with`, no tool names in commit messages or bodies. Commit messages
  describe the change only.
- Do not re-query the Claude API for extraction during this work. See
  `06-medallion-pipeline-SCOPE.md` — this is a hard constraint and re-extraction
  is a four-figure cost.
- Prefer additive migration: new tables alongside old, cut over, then delete.
  Nothing in this plan requires a destructive first step.

## Reading order

| File | Category | Blocking? |
|---|---|---|
| `01-known-defects.md` | Concrete defects found in the live report | Reference for all others |
| `02-claim-layer.md` | Claim object + machine linter | Blocks 03, 04, 05 |
| `03-critic-agents.md` | Critic roster, routing, loop harness | Depends on 02 |
| `04-jurisdiction.md` | WA legal framework swap, s5.68 | Depends on 02 |
| `05-verification.md` | Autonomous accuracy measurement | Feeds error terms into 02 |
| `06-medallion-pipeline-SCOPE.md` | **Scoping brief only — separate session** | Do not plan in this pass |

## The one-line summary of the critique

The extraction layer was not the problem. The **claim layer** — the step between
"we have tables" and "here is a graded panel" — does not exist as a distinct
artefact, so framing errors, wrong denominators, wrong jurisdiction, and
unsupportable grades all ship together with no seam at which to inspect them.
Almost everything in this folder is about creating and defending that seam.
