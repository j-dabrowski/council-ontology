# Research Protocol

The staged, benchmark-gated plan for running and **iteratively improving**
`Researcher_prompt.txt` — the council-agnostic role that grows
`Investigator_prompt.txt` Part 3 (the failure/effectiveness taxonomy) from
real-world AU/UK local-government precedent. Governs the same way
`EXPLORATION_PROTOCOL.md` governs `Explorer_prompt.txt`: a benchmark is
declared up front, sessions are scored against it, the prompt is improved
until it clears the benchmark, then frozen and reused.

Related: `Researcher_prompt.txt` (the prompt this protocol improves),
`PRECEDENT_BANK.md` (the record every session appends to),
`Investigator_prompt.txt` Part 3 (the merge target for approved candidates),
`DISCOVERY_LOOP_DESIGN.md` (Component D/E — the design this protocol
implements).

---

## Why this exists, and why it's a separate role

Investigator (`Investigator_prompt.txt` + its three modes) is deliberately
DB-only — Part 0 scopes it to `data/council.db` — because that constraint is
what keeps findings sourced and verifiable. Nothing about that should
change. But the failure taxonomy Investigator hunts against (Part 3) can
only ever contain genres someone already thought to add. Left alone, it
only grows from what this project's own corpus investigations happen to
stumble into — a much slower and narrower source than the real world's
supply of council failures, audits, and effectiveness reviews.

The Researcher role fills that gap with a genuinely different capability
(web search/fetch) that Investigator should not gain, and its output is
genre-level precedent, not corpus-specific findings. Two constraints follow
directly and are non-negotiable, not just style preferences:

- **Researcher output is never a claim about a specific council currently
  in this project's scope.** It documents "councils have been found to do
  X" as a genre, grounded in a named, checkable precedent — never "this
  council did X." Any candidate that reads as a claim about Cambridge (or
  any council actually being investigated) fails Dimension 4 outright,
  full stop, no exception. **This constraint is absolute** — it doesn't
  loosen in either mode of the merge flow below, gated or auto.

## The benchmark

Four dimensions. A candidate genre entry clears the benchmark only when it
passes all four. A session (which may propose multiple candidates) is
scored dimension-by-dimension per candidate, not as a session average —
one bad candidate should not hide behind three good ones.

| # | Dimension | Threshold | How to check |
|---|---|---|---|
| 1 | **Non-duplication** | Candidate does not restate an existing Part 3.x genre (`Investigator_prompt.txt`) or an existing pattern in `DATA_ENRICHMENT.md` | Read both files; a candidate whose failure-mode row would be near-identical to an existing one fails, even if the cited precedent is different |
| 2 | **Grounded precedent** | Cites a real, checkable case — a named inquiry, audit report, or news investigation with outlet + date — not a generic "this could happen" | The citation must be specific enough that a human can independently verify it exists before the candidate is approved |
| 3 | **Data-signature translatability** | The precedent translates into a concrete signature expressible against this project's schema vocabulary (tables/fields/free-text patterns a minutes-derived corpus could plausibly hold) | Write the signature row the way Part 3.1–3.5 write theirs; if it can't be written without inventing data no minutes corpus would have, it fails |
| 4 | **Defamation safety** | Genre-level only; no claim, named or implied, about any specific council currently in this project's scope | Re-read the candidate as if it were about Cambridge — if it reads as an assertion rather than a lens, it fails |

## Merge flow — gated by default (v1.3, 2026-08-22)

**Two modes.** `Researcher_prompt.txt` v1.1 (2026-08-20) removed the human
gate entirely, on the reasoning that every stage needs to be chainable by a
future harness/cloud runner without a human deciding whether each one may
proceed. That reasoning is sound for a role with a track record — but v1.1
shipped before Researcher had ever been run once, so it removed the one
check that would have caught a bad self-check with zero real evidence that
the self-check was trustworthy. v1.2 restored a gate as the **default**,
kept as an explicit, human-declared per-session opt-in for the fully
autonomous path — the same shape every other role in this project uses (see
`Explorer_prompt.txt`'s Stage 9, `CONDUCTOR.md`'s escalation flow): gated
by default, autonomous only when a human deliberately says so when starting
the run, never as something the role decides for itself mid-session. v1.3
moved the *default* itself into `researcher_gate_mode` in
`config/agent_switches.json`, so a headless/scheduled invocation with no
one present to "declare" anything at session start still has a real value
to read; an explicit per-session instruction still overrides it either way.

**File-review mode (the config's default value):**
1. Researcher session runs, drafts candidate(s), self-scores each against
   the four dimensions below.
2. **All four pass** → Researcher writes a self-contained, ready-to-apply
   pending-merge file to `docs/research/pending_merges/` (see
   `Researcher_prompt.txt` Phase 4 for the exact contents) containing the
   text to paste into both `Investigator_prompt.txt` Part 3 and
   `pipeline/DATA_ENRICHMENT.md`. Logs the entry in `PRECEDENT_BANK.md` as
   `status: candidate — pending human review`. Neither target file is
   touched this session.
3. **Any dimension fails** → identical to auto mode, below.
4. A human later opens the pending-merge file, applies it by hand (or
   rejects it) exactly as instructed in the file, and updates the
   `PRECEDENT_BANK.md` entry to `status: merged` or `status: rejected`
   accordingly.

**Auto-merge mode (when the config's value is `auto-merge`, or explicitly declared at session start):**
1. Researcher session runs, drafts candidate(s), self-scores each against
   the four dimensions below.
2. **All four pass** → Researcher itself merges the candidate into
   `Investigator_prompt.txt` Part 3 as the next numbered sub-section, and
   adds the matching Pattern entry to `pipeline/DATA_ENRICHMENT.md` (tagged
   `source: Researcher`) — same session, no separate approval step. Logs
   the entry in `PRECEDENT_BANK.md` as `status: merged`.
3. **Any dimension fails** → Researcher logs the candidate in
   `PRECEDENT_BANK.md` as `status: rejected`, with the specific failing
   dimension(s) and a one-line reason. Never deleted — that's what stops a
   future session re-proposing it (mirrors the "honest null, logged not
   deleted" discipline `INVESTIGATIONS.md` already uses for Investigator).

Either way, the session ends with the stage-contract block defined in
`Researcher_prompt.txt` (`status: DONE`, `gate_mode`, pending/merged/rejected
counts, `next`) — what a future harness reads to decide what runs next; a
human reading it today gets the same information without re-reading the
session.

**What auto-merge mode trades away, honestly, when a human deliberately
chooses it:** a bad self-check is live in `Investigator_prompt.txt`
immediately, with no second pair of eyes first. Defensible once there's real
calibration data showing the self-check is trustworthy (see "Cadence" and
"Calibration log" below) — the blast radius is bounded even then, since a
bad genre steers future Explorer effort (wasted, cheaply visible at the next
benchmark score) but, per the firewall above, can never itself become a
claim about a real council. If a merged candidate turns out to be a mistake,
the fix is the same as any other prompt regression: edit
`Investigator_prompt.txt` to remove it, log why in the calibration log
below — this file isn't precious. File-review mode (the default) exists
specifically so this trade isn't made silently, by default, before anyone
has evidence it's a good trade.

## Cadence — open question, first-pass recommendation

Unlike Investigator, Researcher isn't gated by a corpus event, so it has no
natural "run per council" trigger. Recommendation, pending real calibration
data: run once before onboarding any new council (so the taxonomy is as
broad as possible before that corpus's typology stage reads
`DATA_ENRICHMENT.md`), plus on-demand whenever a candidate feels overdue.
Revisit once a few sessions exist to see whether a fixed periodic cadence
would actually have caught something the on-demand trigger missed.

## Calibration log

**First session run against this version of the prompt (v1.3)** — 2026-08-22.
Both candidates passed all four dimensions on first draft; no rejections this
session, so no "why did it fail" data yet — that's still open for a future
session.

Proposed prompt/protocol edit for human review (not applied — see
`Researcher_prompt.txt`'s "self-edit gate" note): the four dimensions
themselves felt well-calibrated and not ambiguous to self-check in practice.
The one friction point worth recording: `Researcher_prompt.txt`'s ROLE
section frames this as "broad web research," but nothing in the prompt or
protocol tells a session whether it has web-search tooling available, or
requires it before Dimension 2 can be honestly scored as "pass." This
session used live web search to verify both candidates' citations
(specific report names, dates, and figures came back exactly as drafted from
prior knowledge, so no drafts needed correction this time) — but a session
without search tooling would have no way to know its Dimension-2 self-score
was resting on unverified memory rather than a checked citation. Suggested
edit for a human to consider: add a line to Phase 1 or Phase 3 making live
verification of each citation (not just recall) an explicit part of the
Dimension 2 check, so the gate doesn't silently degrade to "sounds
plausible" in an environment without search access.

| Date | Session | Gate mode | Candidates proposed | Pending review | Merged | Rejected (dimension, reason) |
|---|---|---|---|---|---|---|
| 2026-08-22 | first-ever Researcher run (v1.3) | file-review | 2 (P2, P3) | 2 | 0 | 0 |
| 2026-08-22 | second Researcher run (v1.3) | file-review | 2 (P4, P5) | 2 | 0 | 0 |

**Second-session note:** again no rejections, so still no failure-mode data.
Both candidates this pass (P4 special severance payments, P5 audit-opinion
backlog) sit closer to existing genres than P2/P3 did — worth a human
double-checking Dimension 1 specifically on these two once reviewing the
pending-merge files, since a same-session self-check has an obvious blind
spot (the session that drafts a candidate is also the one scoring its own
non-duplication). If a future session starts seeing candidates rejected on
Dimension 1 at review time despite a self-scored "pass," that's the signal
this risk was real and Phase 1's non-duplication notes need to be written
more adversarially, not just descriptively.
