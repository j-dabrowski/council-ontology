# Automation Architecture — Stage-by-Stage Data Flow, and the GitHub Actions Design

Cross-cutting infra doc (see `MAP.md`) — not owned by one track, since it
maps the full path from a manually-updated database through every agent
role to the live Vercel site. **Partially built as of 2026-08-23**
(`docs/AGENT_DESIGN.md` §6 Step 7): Flow A (Explorer, optionally chaining
Refiner) and Flows C+D (`council draft` → the Editor/Fixer loop) are real,
`workflow_dispatch`-only GitHub Actions workflows (`discovery.yml`,
`maintenance.yml`) — see Part 3 for exactly what each covers and, just as
importantly, what it deliberately doesn't yet. **Flow 0 (the DB-update
pipeline — scrape/extract/dedup) remains a design sketch, not built** —
same status as `pipeline/PIPELINE.md`'s "Production scale" section, which
this doc extends into the investigator/review tracks that section doesn't
cover; read that section first for the scrape/extract half of the
automation story. Neither built workflow runs on a schedule yet — both are
deliberately dispatch-only until their own stated activation conditions
are met (Part 3).

**Companion docs, not duplicates:** `docs/TESTING.md` documents the
workflows that already exist (`draft.yml`, `publish.yml`, and — as of this
update — `discovery.yml`, `maintenance.yml`) and the GCP one-time setup;
`docs/AGENT_PROMPTS.md` holds the fixed prompt string for each role;
`docs/CICD_DECISIONS.md` logs *why* each infra choice was made,
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
`Explorer_prompt.txt`, `Refiner_prompt.txt`) are
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
| **Scrape/census/inventory/extract** (`README.md`'s pipeline table) | manual → scheduled cron (`PIPELINE.md` "Production scale") | council website, `data/council.db` | `data/council.db` (updated in place) | **today:** local, then uploaded to GCS by hand (`gcloud storage cp`). **proposed (Flow 0):** candidate DB uploaded to a *staged* GCS path + a git-trackable summary opens a PR — see Part 3. Still not built (unchanged by the 2026-08-23 redesign) |
| **dedup / build-relationships / geocode** | manual (`council dedup`, etc.) → part of the same scheduled Flow 0 run | `data/council.db` | `data/council.db` (in place) | same as above — staged GCS path, promoted only once Flow 0's PR is merged. Still not built |
| **`council profile`** (S2 corpus profile, `docs/AGENT_DESIGN.md` §6 Step 3) | manual → part of a future Flow 0 run, once built | `council.db` (GCS) | `data/<council>_profile.json` | not yet wired into any workflow — Flow 0 doesn't exist to wire it into. Scripted (no LLM), so wiring it in is a small addition whenever Flow 0 is built, not new machinery of its own |
| **Explorer** (generate/test hypotheses) | manual/GCS round-trip → **built:** `workflow_dispatch` (`discovery.yml`), never scheduled by design (`docs/AGENT_DESIGN.md` §5 — discovery changes the instrument, the register says when, not the calendar) | `council.db` (GCS), `INVESTIGATIONS.md` (GCS), `Investigator_prompt.txt` + `Explorer_prompt.txt` (git) | appends to `INVESTIGATIONS.md`; new `scratchpad/*.py` scripts; calibration-log entries in `Explorer_prompt.txt` | `INVESTIGATIONS.md` → **GCS** (re-upload); `scratchpad/*.py` + `Explorer_prompt.txt` edits → **git** (already-tracked file types, see Part 1) |
| **Refiner** (codify a finding) | **built:** same `discovery.yml` run, chained when `refine=true` (Part 4's one-PR-per-run rule) | same as Explorer, plus `REFINEMENT_PROTOCOL.md` (git) | edits `src/analysis/queries.py` + `tests.py` (code); declaration block + coverage-register update (v1.2); appends to `INVESTIGATIONS.md` | code + `coverage_register.json` → **git, via the same PR as Explorer** when chained (see Part 3); `INVESTIGATIONS.md` → GCS |
| S7 invariant gate | n/a — always runs, inside `council draft`, no separate trigger | the battery `council draft` just computed | `gate_report.json`; blocks the draft on failure | wherever `council draft` runs (GCS `drafts/`) — same location, not a separate stage in this table |
| **`council draft`** | manual `workflow_dispatch` (existing `draft.yml`) → **also built:** the first step of `maintenance.yml`'s loop | `council.db` (GCS), current `queries.py`/`tests.py` (git checkout) | `data/draft/<run_id>/*.json` (S7 gate report included) | **GCS** (`drafts/`) — existing, unchanged |
| **Editor** (defamation review) | **built:** `workflow_dispatch` (`maintenance.yml`, via `scripts/conductor_loop.py` — the scripted loop mechanics, still a real `claude -p` call for Editor's own judgment) | a draft directory (GCS) + `Investigator_prompt.txt` Part 4 (git) + `PRIVATE_ASSESSMENT.md` (gitignored, local-only — see Part 3 note) | `defamation_review_<n>.md` + `.json` sidecar | **GCS**, written into the same draft directory |
| **Fixer** (3 modes, dispatched on FAIL) | **built:** same `maintenance.yml` run, dispatched by `conductor_loop.py` per Editor's tagged tracks | Editor's flagged issues + the relevant track's files | edits to `frontend/src/`, `src/`, or doc files | **git, via its own PR** on any real change (never `frontend/public/data/`, which stays `council publish`'s direct-commit path) — see Part 3's Flow D note; publish is held while that PR is open |
| **`council publish`** | always manual (`--confirm`), OR **built, opt-in:** `maintenance.yml`'s `publish=true` input (`--gate-profile auto`) | one specific draft dir (GCS or local, depending on trigger), hash-verified | `frontend/public/data/*.json` | **git**, direct commit (existing behaviour, unchanged — see Part 3) |
| Renderer (plain-language / synthesis, `docs/AGENT_DESIGN.md` §6 Step 6) | manual only — not wired into any workflow | a draft directory (institutional or deep product) | `plain_language_summary.md` / `deep_synthesis.md` in the draft directory | not GCS-uploaded by any workflow yet; no calibration data exists for either mode (`RENDERER_PROTOCOL.md`), so wiring it into `maintenance.yml` is deliberately deferred, not forgotten |
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
 FLOW A — Explorer (report only)              [BUILT: discovery.yml,
 ──────────────────────────────────────        workflow_dispatch only]
 council.db (GCS) + INVESTIGATIONS.md (GCS)
        │
   Explorer appends findings to INVESTIGATIONS.md (GCS — stays out
   of git, see the note below) + writes scratchpad/*.py (git)
        │
        ▼
   opens a PR: the scratchpad scripts + git-tracked changes, plus a
   PR body listing what git files changed and the GCS findings path
   (see the simplification note in Part 3's Flow A/B section below —
   discovery.yml's PR body is not yet the machine-parsed hypothesis-
   number/status summary this paragraph originally specified)
        │
        ▼
   GATE: you read the diff + PR body, merge


 FLOW B — Refiner (changes CODE)              [BUILT: same discovery.yml
 ──────────────────────────────────────        run, only when refine=true
 council.db (GCS) + INVESTIGATIONS.md (GCS)     is set on dispatch]
   + Refiner_prompt.txt (git)
        │
   edits src/analysis/queries.py + tests.py; declaration block +
   coverage_register.json update (v1.2); appends to INVESTIGATIONS.md
        │
        ▼
   lands in the SAME PR as Flow A above (Part 4's one-PR-per-run rule)
   — not a separately-triggered run in the built version; a
   standalone "Refiner only, against an older merged Explorer
   finding" dispatch isn't wired yet (Refiner_prompt.txt's own Step 0
   self-selection still works fine run locally/interactively for
   that case)
        │
        ▼
   GATE: you read the diff + Refiner's seven-dimension score block, merge
        │
        ▼
   merge to main → triggers FLOW C automatically (push to main,
   paths: src/analysis/**) — NOT YET WIRED: draft.yml is
   workflow_dispatch only today, no push-triggered auto-draft exists


 FLOW C — council draft            FLOW D — Editor (+ Fixer)
 ──────────────────────            ──────────────────────    [BUILT:
 writes only to GCS (drafts/)      writes only to GCS (the review     maintenance.yml,
 — no git file touched, so         sidecar, inside the draft dir)     workflow_dispatch
 the branch/PR rule doesn't        — same reasoning, no git file,     only]
 apply; runs automatically         no PR possible or needed. Now
 as maintenance.yml's first        wired via scripts/conductor_loop.py
 step (in addition to the          inside maintenance.yml — still a
 existing standalone draft.yml)    real `claude -p` call for Editor's
                                   and Fixer's own judgment, the LOOP
                                   MECHANICS (pass counting, dispatch-
                                   by-track) are scripted. PASS writes
                                   the sidecar, which unblocks FLOW E.
                                   Fixer's edits commit directly on the
                                   runner within the job — not yet a
                                   separate PR (see the note below).


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
 see the note below. NOW REACHABLE
 from maintenance.yml too, behind
 an explicit publish=true opt-in
 (default false — see that
 workflow's own activation
 checklist)
```

**Flow 0 (the DB-update pipeline) — PR-gated, sequenced before the agents
pipeline runs.** The full stage detail (typology check vs. escalation,
validation, the sanity cap on document volume) lives in `PIPELINE.md`
"Production scale" — this doc only adds the branch/PR/promotion mechanics.
The sequencing matters as much as the gate itself: the agents pipeline
reads `council.db` as an input, so it should never run against a DB update
that's still sitting in an unmerged PR — Flow A/B's trigger is the
promotion job completing, not the scheduled job itself.

**Flow A (Explorer) — PR-gated, with a summary standing in for the
verbatim findings. Built (`discovery.yml`, `workflow_dispatch` only, never
scheduled — see `docs/AGENT_DESIGN.md` §5's reasoning for why this stays
permanently dispatch-only, unlike Flow D below).** `INVESTIGATIONS.md`
stays in GCS regardless of this rule — not an exception to it, a separate
constraint that was already true before this design (see Part 1: it names
real individuals with risk-adjacent framing, and a PR is exactly as public
as a merged file, closed or not). The PR carries the git-safe artifacts
(`scratchpad/*.py`) plus a PR body — **the built version is a
simplification of what this paragraph originally specified**: it lists
which git-tracked files changed and points at the GCS findings path,
rather than a machine-generated hypothesis-number/status/headline-
classification summary. No role in this pipeline has a structured
"session summary" stage-contract field to extract that from yet — building
one is real, separate future work, not done here (`discovery.yml`'s own
header comment logs this same note). Worth wiring the merge of that PR
into Refiner's Step 0 as an eligibility check *for later, separately-
triggered Refiner runs* (see Part 4 for why this doesn't apply when
Refiner chains directly off Explorer in the same run) — not done yet
either; today's built version doesn't support a standalone,
Refiner-only dispatch at all (see Flow B below).

**Flow B (Refiner — changes code) — PR-gated. Built, but narrower than
originally specified: only as a same-run chain off Explorer
(`discovery.yml`'s `refine=true` input), never a standalone,
separately-triggered dispatch.** This flow changes the logic that decides
what every future battery result *is*. Refiner's own dimension 1–2 (and,
as of v1.2, dimension 7) hard gates already do real, independent
verification before proposing a change — but per this project's stated
invariant everywhere else (`CONDUCTOR.md`: "never any single agent's
self-assessment"), that verification is Refiner checking its own homework,
not a second party checking it. A human reading the diff plus the
seven-dimension score block is the second party — the smallest, cheapest
form real review can take, since Refiner's own verification is already
done for the reviewer to check rather than redo, not a bureaucratic
add-on. **Gap versus the original design:** a human wanting to codify an
older, already-merged Explorer finding without re-running Explorer has no
workflow for that yet — `Refiner_prompt.txt`'s own Step 0 self-selection
still works for it locally/interactively, just not through
`workflow_dispatch`. Worth a small `discovery.yml` addition (a
`refiner_only` input that skips the Explorer step) if this gap turns out
to matter in practice; not built speculatively ahead of that.

**Flow C (`council draft`) — no PR, because there's no git file change to
gate.** `draft.yml` writes only to GCS. Auto-triggering it on `push: main,
paths: ["src/analysis/**"]` (after a Refiner PR merges) and on relevant PR
updates (a preview draft for the reviewer, checked out against the PR's own
branch — see the `ref`-aware `draft.yml` design) are both consistent with
the rule, not exceptions to it: nothing here ever touches a tracked file.

**Flow D (Editor + Fixer) — Editor's own review still writes no git file
(no PR possible for that part), but the loop mechanics are now built and
CI-wired (`maintenance.yml`, `workflow_dispatch` only, never scheduled
yet), and a Fixer repair now follows the uniform rule like everything
else.** `PIPELINE.md`'s "Production scale" section framed the right
resolution before this was built — "the likely resolution isn't removing
the human, it's shrinking what the human has to do per cycle" — and
that's exactly what `scripts/conductor_loop.py` does: pass-counting and
dispatch-by-track are scripted (no judgment in that gap), while Editor's
own review and Fixer's own fix stay real `claude -p` calls. Whenever
Fixer actually changes a git-tracked file (source, prompts, docs — never
`frontend/public/data`, which is `council publish`'s own output, not a
Fixer repair) `maintenance.yml`'s "Capture Fixer's source edits into a
PR" step opens one, per this uniform rule, exactly like Refiner's Flow B —
first built as a direct-commit shortcut, corrected the same day a code
review of the build caught it discarding real repairs (logged in
`CICD_DECISIONS.md`'s 2026-08-24 entry, which also records the
alternatives considered). What `maintenance.yml` deliberately does
**not** do is auto-publish or schedule itself — both are gated behind
explicit conditions, not removed altogether:

- **Publish** is an opt-in `publish=true` dispatch input (default false),
  **and** is held automatically whenever the run just opened a Fixer-repair
  PR, regardless of that input — publishing refreshed data against the
  exact code Editor just flagged would defeat the review that produced
  the fix. The job summary always prints the exact `council publish`
  command to run by hand once that PR merges. A human dispatching with
  `publish=true` on a run with no pending fix is still a deliberate act
  each time — the gate is "not automatic," not "impossible."
- **Scheduling** is a commented-out `cron:` block in `maintenance.yml`
  itself, with an **activation checklist** stated both there and here
  (single source of intent, kept in sync manually — update both if the
  checklist changes):

  1. ≥ 3 real Editor v0.4 PASS/FAIL cycles have completed via
     `maintenance.yml` (`workflow_dispatch`), each independently reviewed
     by a human against their own judgment of the same draft.
  2. Editor's false-positive dimension (`EDITOR_PROTOCOL.md`, added
     2026-08-23 alongside the S7 narrowing) has real calibration data,
     not just the pre-narrowing prediction that flag volume would drop.
  3. Zero missed real risks (false negatives) across those cycles — per
     `EDITOR_PROTOCOL.md`, this is the one failure mode that actually
     matters; false positives are safe, just wasteful.
  4. The project owner has explicitly signed off on that calibration data
     in the PR that uncomments the `cron:` block — not a self-certified
     "looks calibrated enough," a real, separate review of the evidence.

  **Who flips it:** the project owner, via a PR that uncomments the
  `cron:` block in `maintenance.yml` once all four boxes are checked in
  `EDITOR_PROTOCOL.md`'s calibration log — a one-line change once the
  evidence exists, not a rebuild. No one else (including a future
  Conductor-adjacent agent session) should uncomment it unprompted.

This is the same reasoning `CONDUCTOR.md` already states in general: don't
automate a dispatch policy nobody has run yet. The difference from the
pre-2026-08-23 state is that "run yet" now means "run via
`workflow_dispatch`, which is real infrastructure a human can dispatch
today" — not "build the infrastructure later, once trust exists."

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
not resolved. **Now reachable from `maintenance.yml` too** (in addition to
the existing standalone `publish.yml`), behind the `publish=true` opt-in
input described in Flow D's activation-checklist note above — the
mechanism itself (hash-verified integrity + `--gate-profile auto`) is
unchanged, only a second caller was added.

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
`queries.py`/`tests.py` diff + seven-dimension score block from Refiner,
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

**Closed 2026-08-23 — schedule vs. dispatch for Explorer/Refiner vs.
maintenance.** `docs/AGENT_DESIGN.md` §5 answers this structurally, not
just as a project-specific call: there are two *kinds* of run, not one
question repeated per role.

- **Discovery** (Explorer, optionally chained Refiner — `discovery.yml`) is
  `workflow_dispatch` *permanently*, never scheduled. It changes the
  instrument itself, and the coverage register — not the calendar — says
  when that's worth doing; "new corpus data exists" is a maintenance-run
  trigger, not a discovery one.
- **Maintenance** (`council draft` → S7 → Editor/Fixer → optionally publish
  — `maintenance.yml`) is the one where "the passage of time is exactly
  when there's new corpus data to look at" actually applies, so it's the
  one built with a schedule *slot* — commented out, gated behind the
  activation checklist in Part 3's Flow D section, not decided open-endedly
  here.

This closes the question this bullet used to leave open; see Part 3 for
the concrete gate rather than a restated principle here.

- **The exact CI mechanics** (Claude Code CLI install/auth, permission
  flags) — covered in `docs/AGENT_PROMPTS.md`'s GitHub Actions section, not
  duplicated here. `discovery.yml`/`maintenance.yml` follow that section's
  patterns exactly (subscription auth via `CLAUDE_CODE_OAUTH_TOKEN`, never
  `ANTHROPIC_API_KEY`).
- **GCS backup/versioning shape** for `investigations/` and `backups/` —
  same open questions `CICD_DECISIONS.md`'s 2026-08-22 entry already logs
  for `council.db` backups; likely the same answer applies to both. Still
  open — `discovery.yml` round-trips `investigations/INVESTIGATIONS.md`
  through GCS on every run (overwriting, no versioning) as of this update,
  which is the simplest thing that works, not a considered answer to this
  question.
- **Closed 2026-08-24 — Fixer's edits are now PR-gated inside
  `maintenance.yml`.** Built as a direct-commit-on-the-runner shortcut,
  matching the reasoning above about converging on a clean draft before a
  human looks at anything — but a code review of the redesign build caught
  the actual consequence the same day: the edits died with the runner
  while the data they justified was published, since only
  `frontend/public/data/` was ever staged. See Flow D's note in Part 3 for
  the fix (a Fixer-repairs PR, publish held while it's open) and
  `CICD_DECISIONS.md`'s 2026-08-24 entry for the alternatives weighed.
- **New, not yet resolved: `discovery.yml` doesn't support a standalone
  Refiner-only dispatch.** See Flow B's note in Part 3 — a real, logged
  gap versus the original design, not forgotten.
