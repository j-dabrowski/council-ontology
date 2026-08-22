# Automation Architecture — Stage-by-Stage Data Flow, and the GitHub Actions Design

Cross-cutting infra doc (see `MAP.md`) — not owned by one track, since it
maps the full path from a manually-updated database through every agent
role to the live Vercel site. **Design sketch, not built** (same status as
`pipeline/PIPELINE.md`'s "Production scale" section, which this doc extends
into the investigator/review tracks that section doesn't cover — read that
section first for the scrape/extract half of the automation story; this doc
picks up from `council.db` existing in GCS onward). Nothing described here
has been implemented; this is the plan, written down before building it, the
same discipline every other design-sketch section in this project follows.

**Companion docs, not duplicates:** `docs/TESTING.md` documents the two
workflows that already exist (`draft.yml`, `publish.yml`) and the GCP
one-time setup; `docs/AGENT_PROMPTS.md` holds the fixed prompt string for
each role; `docs/CICD_DECISIONS.md` logs *why* each infra choice was made,
chronologically. This doc is the *map* — what goes where, in what order,
gated how — that ties those three together and fills the gap none of them
individually cover.

---

## Part 1 — The one rule that decides where every file lives

**Working/private state lives in GCS. Reviewed/durable state lives in git.**
Everything else in this doc is a consequence of that one line, so it's worth
stating precisely why, not just asserting it:

`.gitignore` already encodes this as a deliberate design decision, not an
oversight — `docs/investigator/*.md` is gitignored by an **allow-list**
(everything ignored except two explicitly named protocol docs), with a
comment stating exactly why: investigator *output* docs (`INVESTIGATIONS.md`,
retroactive audits, session syntheses) "name real individuals with
risk-adjacent framing... matching the risk `PRIVATE_ASSESSMENT.md`
documents." The *prompt files* (`Investigator_prompt.txt`,
`Explorer_prompt.txt`, `Refiner_prompt.txt`, `Runner_prompt.txt`) are
untouched by that rule for a simpler reason — they're `.txt`, not `.md`, so
the glob never matches them. That's not an accident either: prompt files are
methodology (how to investigate), always safe to publish; `INVESTIGATIONS.md`
is findings (what was found about named people), not safe until Editor has
reviewed it. `data/council.db` follows the identical logic one level up —
the raw extraction, gitignored, kept in a private GCS bucket, for the same
reason `docs/CICD_DECISIONS.md`'s 2026-08-05 entry gives: it's *every*
entity and quote, not the curated, reviewed subset that clears into public
JSON.

**The practical consequence for automation:** every stage above ran on a
human's laptop until now, where "state not yet published" could simply mean
"a gitignored file sitting on disk." A GitHub Actions runner has no
persistent disk between runs — so any state that used to survive only
because it lived on one laptop now has nowhere to go unless it's explicitly
placed somewhere. The GCS bucket already holding `council.db` is that
place. The bucket gains three more prefixes alongside the existing
`drafts/` and `published/full/`:

```
gs://$BUCKET/
  council.db                    (existing — raw DB, human-uploaded)
  drafts/cambridge/<run_id>/    (existing — council draft output)
  published/full/cambridge/     (existing — paywall-pending full tier)
  investigations/
    INVESTIGATIONS.md           (NEW — the detective's notebook, agent read/write.
                                  scratchpad/*.py stays git-tracked, same as today —
                                  no separate GCS staging for it, see Part 3)
  backups/                      (NEW — see CICD_DECISIONS.md's 2026-08-22 entry;
                                  council.db snapshots for the diff-based
                                  out-of-band-fix detection discussed there)
```

Nothing else about the existing GCS setup changes — same bucket, same OIDC
trust relationship, same bucket-wide read access noted in
`CICD_DECISIONS.md`. `investigations/` and `backups/` need the same
prefix-scoped write extension already proposed there for `backups/`.

---

## Part 2 — Every stage, its inputs, its outputs, where they land

The literal answer to what files go where — every stage in the system, in
execution order. **Location** column: `git` (public repo, durable), `GCS`
(private bucket, durable), `local` (gitignored, one machine only — today's
default for anything not yet moved to GCS per Part 1), or `Vercel` (the
served site itself).

| Stage | Trigger (today → proposed) | Reads | Writes | Location |
|---|---|---|---|---|
| **Scrape/census/inventory/extract** (`README.md`'s pipeline table) | manual → scheduled cron (`PIPELINE.md` "Production scale") | council website, `data/council.db` | `data/council.db` (updated in place) | **today:** local, then uploaded to GCS by hand (`gcloud storage cp`). **proposed (Flow 0):** candidate DB uploaded to a *staged* GCS path + a git-trackable summary opens a PR — see Part 3 |
| **dedup / build-relationships / geocode** | manual (`council dedup`, etc.) → part of the same scheduled Flow 0 run | `data/council.db` | `data/council.db` (in place) | same as above — staged GCS path, promoted only once Flow 0's PR is merged |
| **Explorer** (generate/test hypotheses) | manual → `workflow_dispatch`/scheduled | `council.db` (GCS), `INVESTIGATIONS.md` (GCS), `Investigator_prompt.txt` + `Explorer_prompt.txt` (git) | appends to `INVESTIGATIONS.md`; new `scratchpad/*.py` scripts; calibration-log entries in `Explorer_prompt.txt` | `INVESTIGATIONS.md` → **GCS** (re-upload); `scratchpad/*.py` + `Explorer_prompt.txt` edits → **git** (already-tracked file types, see Part 1) |
| **Refiner** (codify a finding) | manual → `workflow_dispatch` | same as Explorer, plus `REFINEMENT_PROTOCOL.md` (git) | edits `src/analysis/queries.py` + `tests.py` (code); appends to `INVESTIGATIONS.md` | code → **git, via a PR** (see Part 3); `INVESTIGATIONS.md` → GCS |
| **Runner** (frozen battery, no hypotheses) | manual → `workflow_dispatch` | `council.db` (GCS), `tests.py` (git) | a verification report; no code changes | report → GCS or PR body (low-stakes, informational) |
| **`council draft`** | manual `workflow_dispatch` (existing `draft.yml`) → proposed: also auto on relevant merges/PRs (Part 3) | `council.db` (GCS), current `queries.py`/`tests.py` (git checkout) | `data/draft/<run_id>/*.json` | **GCS** (`drafts/`) — existing, unchanged |
| **Editor** (defamation review) | today: human-run locally, not yet in CI | a draft directory (GCS) + `Investigator_prompt.txt` Part 4 (git) + `PRIVATE_ASSESSMENT.md` (gitignored, local-only — see Part 3 note) | `defamation_review_<n>.md` + `.json` sidecar | **GCS**, written into the same draft directory |
| **Fixer** (3 modes, dispatched on FAIL) | today: human-run; chained by Conductor | Editor's flagged issues + the relevant track's files | edits to `frontend/src/`, `src/`, or doc files | **git**, same PR discipline as Refiner (it's still a code/content change) |
| **`council publish`** | always manual (`--confirm` or validated `--gate-profile auto`) | one specific draft dir (GCS), hash-verified | `frontend/public/data/*.json` | **git**, direct commit (existing behaviour, unchanged — see Part 3) |
| **Vercel deploy** | automatic on push to `main` touching `frontend/` | `frontend/public/data/` + `frontend/src/` (git) | the live site | **Vercel** — already fully automatic, no change |

---

## Part 3 — The automation design: one uniform rule, plus two stages that don't write git at all

**The governing rule, stated once, applied everywhere: any pipeline run
that writes a *git-tracked* file change lands on its own branch and opens
its own PR — never a direct commit to `main`, regardless of how low-risk
the content looks.** This replaces an earlier draft of this doc that
graded the gate by estimated risk per flow; a uniform rule is simpler to
reason about and enforce, and the actual review cost (glancing at a small,
focused diff) is cheap enough that grading it case by case bought little.
Two stages are genuinely exempt, but *because the rule doesn't apply to
them*, not because they're graded as safe enough to skip it: `council
draft` and Editor write only to GCS, never touch a git file at all, so
there is no file change for the rule to gate.

**Two more rules that follow directly from "one PR per run" (Part 4):**

1. **Every stage within a run operates on that run's own branch HEAD, never
   a fresh checkout of `main`.** If Refiner commits a code change and the
   run then continues into another stage — another Refiner target in the
   same run, a Fixer response to something Editor flagged, anything — that
   next stage's checkout is the branch as it currently stands, including
   every commit made earlier in the same run. Concretely: each job/step in
   the workflow checks out `${{ github.head_ref }}` (the run's own branch),
   not `main`, and pulls before it starts. Getting this wrong is exactly
   how a later stage would silently redo or conflict with work an earlier
   stage in the *same* run already did.
2. **The PR is the single, comprehensive review surface for everything the
   run touched** — not a bare pointer plus "go check GCS for the rest."
   Every git-tracked diff appears in the PR normally. For GCS-only output
   (`INVESTIGATIONS.md`), the PR carries a real machine-generated
   summary — which hypotheses were tested, their status
   (Finding/Null/Banked), and the headline classification of each — not
   just a one-line "see GCS" pointer. The one thing that still can't go in,
   for the same reason it's gitignored in the first place: verbatim
   findings prose about named individuals. A PR is exactly as public as a
   merged file, closed or not, so that constraint doesn't loosen just
   because the goal here is maximal reviewability — the summary can say
   *what kind* of thing was found and where, never restate the risk-bearing
   content itself. Where Flow C's preview draft exists for the branch (see
   below), the PR links it too, so "what would this actually change on the
   site" is one click away, not a separate thing to remember to check.

**`council.db` can't be committed to a PR** (it's a private GCS blob, not
a git file — see Part 1), so the DB-update pipeline's "file change" is a
small, git-trackable **summary** standing in for it, not the database
itself. This is the one place the rule needed a concrete mechanism worked
out rather than just "open a PR":

```
 FLOW 0 — the DB-update pipeline (PIPELINE.md "Production scale")
 ────────────────────────────────────────────────────────────────
 scheduled trigger
        │
   scrape → census → inventory → typology CHECK → (extract if it
   passes) → validate → dedup/relationships/geocode
        │
        ▼
   uploads the candidate DB to a STAGED GCS path (never overwrites
   the canonical gs://$BUCKET/council.db directly)
        │
        ▼
   commits a summary (new doc count, date range, validation metrics,
   staged GCS path — plus any real schema/prompt diff, if the
   typology check failed and an escalation revision was proposed)
   to a new branch, opens a PR
        │
        ▼
   GATE: you read the summary (+ any code diff), merge
        │
        ▼
   merge triggers a promotion job: staged DB → canonical GCS path
        │
        ▼
   promotion triggers the agents pipeline (Explorer below, continuing
   into Refiner within the SAME run if something's worth codifying —
   see Part 4) — sequenced, never running concurrently against a DB
   update still pending review
```

The two boxes below show Explorer and Refiner as if they always open
separate PRs — that's the simple case. **Part 4 covers the other one: when
Refiner runs as a direct continuation of the same triggered run that just
ran Explorer, its output lands in that run's one PR alongside Explorer's,
not a second one.** Read both before assuming which applies.

```
 FLOW A — Explorer / Runner (report only)
 ──────────────────────────────────────────────────────────────────
 council.db (GCS) + INVESTIGATIONS.md (GCS)
        │
   Explorer appends findings to INVESTIGATIONS.md (GCS — stays out
   of git, see the note below) + writes scratchpad/*.py (git)
        │
        ▼
   opens a PR: the scratchpad scripts, plus a machine-generated
   SUMMARY — hypothesis numbers, status (Finding/Null/Banked), headline
   classification, and the GCS path — never the verbatim findings prose
        │
        ▼
   GATE: you read the summary + scripts, merge — this merge is also
   the recommended eligibility signal for Refiner (see below)


 FLOW B — Refiner (changes CODE)
 ──────────────────────────────────────────────────────────────────
 council.db (GCS) + INVESTIGATIONS.md (GCS) + Refiner_prompt.txt (git)
        │
   edits src/analysis/queries.py + tests.py; appends to
   INVESTIGATIONS.md (GCS)
        │
        ▼
   opens a PR (branch: refiner/<slug>) with the code diff + Refiner's
   own six-dimension score block
        │
        ▼
   GATE: you read the diff + score block, merge
        │
        ▼
   merge to main → triggers FLOW C automatically (push to main,
   paths: src/analysis/**)


 FLOW C — council draft            FLOW D — Editor (+ Fixer)
 ──────────────────────            ──────────────────────
 writes only to GCS (drafts/)      writes only to GCS (the review
 — no git file touched, so         sidecar, inside the draft dir)
 the branch/PR rule doesn't        — same reasoning, no git file,
 apply; runs automatically         no PR possible or needed. Kept
                                   human-run for now (see reasoning
                                   below) — PASS writes the sidecar,
                                   which unblocks FLOW E.


 FLOW E — council publish                    FLOW F — Vercel
 ──────────────────────────                  ─────────────────
 the one stage that DOES write                already fully
 to git (frontend/public/data/)               automatic, no PR,
 but keeps its own existing,                  no change
 stronger-than-a-generic-PR gate
 (hash-verified draft integrity +
 --confirm or a validated Editor
 PASS record) rather than switching
 to a branch+PR — open question,
 see the note below
```

**Flow 0 (the DB-update pipeline) — PR-gated, sequenced before the agents
pipeline runs.** The full stage detail (typology check vs. escalation,
validation, the sanity cap on document volume) lives in `PIPELINE.md`
"Production scale" — this doc only adds the branch/PR/promotion mechanics.
The sequencing matters as much as the gate itself: the agents pipeline
reads `council.db` as an input, so it should never run against a DB update
that's still sitting in an unmerged PR — Flow A/B's trigger is the
promotion job completing, not the scheduled job itself.

**Flow A (Explorer/Runner) — PR-gated, with a summary standing in for the
verbatim findings.** `INVESTIGATIONS.md` stays in GCS regardless of this
rule — not an exception to it, a separate constraint that was already true
before this design (see Part 1: it names real individuals with
risk-adjacent framing, and a PR is exactly as public as a merged file,
closed or not). The PR carries the git-safe artifacts (`scratchpad/*.py`)
plus a machine-generated summary — hypothesis numbers, status, headline
classification, GCS path — everything short of the risk-bearing prose
itself. Worth wiring the merge of that PR into Refiner's Step 0 as an
eligibility check *for later, separately-triggered Refiner runs* (see Part
4 for why this doesn't apply when Refiner chains directly off Explorer in
the same run) — a hypothesis nobody's acknowledged yet doesn't get picked
up for codification by a future run. That gives "merge the PR" real teeth
for investigation work too, not just a formality around low-stakes content.

**Flow B (Refiner — changes code) — PR-gated.** This flow changes the
logic that decides what every future battery result *is*. Refiner's own
dimension 1–2 hard gates already do real, independent verification before
proposing a change — but per this project's stated invariant everywhere
else (`CONDUCTOR.md`: "never any single agent's self-assessment"), that
verification is Refiner checking its own homework, not a second party
checking it. A human reading the diff plus the six-dimension score block is
the second party — the smallest, cheapest form real review can take, since
Refiner's own verification is already done for the reviewer to check rather
than redo, not a bureaucratic add-on.

**Flow C (`council draft`) — no PR, because there's no git file change to
gate.** `draft.yml` writes only to GCS. Auto-triggering it on `push: main,
paths: ["src/analysis/**"]` (after a Refiner PR merges) and on relevant PR
updates (a preview draft for the reviewer, checked out against the PR's own
branch — see the `ref`-aware `draft.yml` design) are both consistent with
the rule, not exceptions to it: nothing here ever touches a tracked file.

**Flow D (Editor) — no PR possible (no git file), and kept human-run
regardless.** Two concrete reasons, not caution for its own sake:
`PIPELINE.md`'s own "Production scale" section reaches the same conclusion
independently — "the likely resolution isn't removing the human, it's
shrinking what the human has to do per cycle." First, this is the stage
that exists because of a documented MODERATE-to-HIGH defamation exposure
(`PRIVATE_ASSESSMENT.md`) — the only stage whose entire job is catching
that risk before it becomes public. Second, it has never run to completion
successfully even once as of this writing (`REVIEW.md`'s status note) —
zero calibration data exists yet on how reliable it is. `CONDUCTOR.md`
already states the general principle for this exact situation: automating
a dispatch policy nobody has run yet just moves the unproven part somewhere
harder to inspect. Once Editor has a real track record — several genuine
PASS/FAIL cycles, ideally across more than one draft — revisiting this is
reasonable, not before.

**Flow E (`council publish`) — the one open question this rule raises,
flagged rather than decided here.** This is the one stage that *does* write
a git file (`frontend/public/data/`) but doesn't currently use a branch+PR —
it uses its own mechanism (hash-verified draft integrity, plus `--confirm`
or a validated Editor PASS record), which is arguably a *stronger* gate
than a generic PR review, since it cryptographically ties the commit to one
specific, already-reviewed draft rather than relying on a human reading a
diff. Whether that existing mechanism should be kept as-is, or replaced
with a branch+PR for full consistency with the uniform rule, is worth a
deliberate answer rather than silently picking one — noted here as open,
not resolved.

**Flow F (Vercel) — already fully automatic, no git write of its own.** No
change.

---

## Part 4 — One PR per triggered pipeline run, not per role

The unit that gets its own branch and PR is a **run** — one triggered
invocation of the agents pipeline — not each role inside it. If a single
run executes Explorer, finds something worth codifying, and continues
straight into Refiner in the same job, both stages' output accumulates on
the one branch that run created and lands in the one PR it opens:
`scratchpad/*.py` + the findings summary from Explorer, and the
`queries.py`/`tests.py` diff + six-dimension score block from Refiner,
reviewed together as one story — "found X, codified it into Y" — instead
of split across two PRs a reviewer has to cross-reference.

**What this trades away, worth stating plainly rather than glossing over:**
Refiner acting on Explorer's output from the same run means it's building
code on a finding nobody has reviewed yet — the finding and the code change
only reach review *together*, after the fact, not the finding first with
Refiner waiting on a separate acknowledgment before touching it. The
earlier idea of gating Refiner's Step 0 on a merged Explorer PR (Part 3)
only applies across separate runs — a *later*, independently-triggered
Refiner run picking up a Banked finding from a *prior*, already-merged
Explorer run — not within one continuous run that chains straight through.

**What still doesn't share a branch**: genuinely separate, independently
triggered runs — the DB-update pipeline and a later agents-pipeline run;
two agents-pipeline runs triggered on different days. Those aren't one
story, and coupling them would mean either serialising unrelated work or
risking a merge conflict between commits that have nothing to do with each
other. The rule is "one branch per run," not "one branch per role" *or*
"one branch for everything" — the run boundary is what decides it.

---

## Part 5 — What's still open, not resolved by this doc

- **Whether Explorer/Refiner run on `workflow_dispatch` or a schedule** — the same
  "reflects a decision, not the passage of time" question `draft.yml`
  already answered one way for drafting; investigation work is arguably
  closer to "the passage of time is exactly when there's new corpus data
  to look at" than drafting is, but that's a decision to make deliberately,
  not a default to fall into.
- **The exact CI mechanics** (Claude Code CLI install/auth, permission
  flags) — covered in `docs/AGENT_PROMPTS.md`'s GitHub Actions section, not
  duplicated here.
- **GCS backup/versioning shape** for `investigations/` and `backups/` —
  same open questions `CICD_DECISIONS.md`'s 2026-08-22 entry already logs
  for `council.db` backups; likely the same answer applies to both.
