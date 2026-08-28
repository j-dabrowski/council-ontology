"""
Scripted replacement for the Conductor role — docs/review/CONDUCTOR.md.

Conductor's own design deliberately keeps a Claude Code session driving
the draft -> Editor -> Fixer loop, not a plain script, while Editor/Fixer
have zero completed real-world runs to calibrate against (see
CONDUCTOR.md: "don't build [a headless version] before that [real chain
data]"). This script is the other half of that same argument: the LOOP
MECHANICS (count passes, read Editor's stage-contract verdict, dispatch
the right Fixer mode(s)) don't actually need an LLM's judgment -- Editor
already writes a machine-readable `defamation_review_<n>.json` sidecar
specifically so code can trust the verdict without parsing prose
(Editor_prompt.txt v0.3). What still needs an agent is Editor's own
review (real judgment: is this claim defensible) and Fixer's own fix
(real judgment: how do I fix it) -- those two invocations are still real
`claude -p` calls, dispatched the same way `run_draft()` below dispatches
`council draft`: by shelling out to `council editor` / `council fixer`
(`run_editor`/`run_fixer`), the same standalone commands a human could
run by hand, not a private, duplicated implementation of "how do I run
Editor" that only this script has. Everything *between* those calls --
did it pass, which track(s) got flagged, have we hit the cap -- is
exactly the kind of thing this script does instead of an LLM.

The one invariant carries over unchanged and is enforced here the same
way CONDUCTOR.md states it: this script NEVER calls `council publish`,
under any circumstances. It stops at a clean PASS or a cap-hit escalation
and prints the exact command a human would run next.

**Billing: subscription auth only, never the pay-per-token API.** Every
`claude` invocation below strips `ANTHROPIC_API_KEY` from the child
process's environment before launching it, so it can never be picked up
even if it happens to be set in the calling shell for an unrelated
reason. Authenticate the account this script runs as via `claude login`
(interactive) or a `CLAUDE_CODE_OAUTH_TOKEN` (subscription-based, for
CI — generate once locally with `claude setup-token`) before running
this. If neither is configured, `claude -p` will simply fail to
authenticate and this script surfaces that as a normal step failure
(exit 2) — it does not fall back to API-key billing under any condition.

Usage:
    python scripts/conductor_loop.py cambridge
    python scripts/conductor_loop.py cambridge --max-passes 3
    python scripts/conductor_loop.py cambridge --dry-run   # print the plan, run nothing

Exit codes: 0 = clean PASS reached. 1 = escalated, needs a human -- either
the pass cap was reached with blocking flags still open, or (checked
first, every pass) a Fixer track reported BLOCKED, meaning it correctly
declined a decision that isn't its to make. Either way this script stops
immediately rather than re-drafting into another pass that would just
rediscover the same open item. 2 = something in the loop itself failed
unexpectedly (bad JSON, missing file, a `claude` invocation erroring) --
distinct from either normal escalation, which is expected loop behaviour,
not an error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DRAFT = ROOT / "data" / "draft"
CONFIG = ROOT / "config" / "agent_switches.json"

# Same three modes Fixer has always had -- see docs/review/fixer/. This is
# also the set of valid `council fixer <track>` CLI choices -- "human"
# below is deliberately NOT part of it, since no Fixer mode exists for it.
FIXER_TRACKS = {"frontend", "pipeline", "doc"}

# The full track vocabulary a Editor flag may carry -- FIXER_TRACKS plus
# "human", added 2026-08-24 for the generation/scoring split's
# holistic-flag outlet (docs/GENERATION_SCORING_SPLIT.md §2.2): a
# review-wide concern no Fixer mode can act on. A FAIL carrying a
# "human"-track flag escalates immediately (escalate_blocked(), below)
# instead of dispatching Fixer -- see run_conductor_loop.
VALID_TRACKS = FIXER_TRACKS | {"human"}

# Same tool set Refiner/Fixer need locally -- see docs/AGENT_PROMPTS.md.
ALLOWED_TOOLS = "Read,Edit,Write,Bash,Grep,Glob"

# Editor's and Fixer's own prompt TEXT lives in docs/agent_prompts/ -- the
# single source of truth also used by AGENT_PROMPTS.md's documented
# commands (see that doc's "Editor alone" / "Fixer" sections for the same
# placeholders filled the same way). Loaded and substituted here rather
# than duplicated inline, so there is exactly one copy of each prompt
# anywhere in this repo, not a third one drifting out of sync with the
# other two.
AGENT_PROMPTS_DIR = ROOT / "docs" / "agent_prompts"


def load_prompt(name: str, **placeholders: str) -> str:
    """Loads docs/agent_prompts/<name>.txt and fills any `<placeholder>`
    tokens. Public (no leading underscore) because `src/cli.py`'s `explore`
    /`refine`/`render` commands import this directly, alongside `run_claude`
    below, so there stays exactly one copy of "how to invoke a `claude -p`
    prompt" in this repo rather than a second one drifting out of sync.
    """
    text = (AGENT_PROMPTS_DIR / f"{name}.txt").read_text()
    for key, value in placeholders.items():
        text = text.replace(f"<{key}>", value)
    return text


def load_max_passes() -> int:
    return json.loads(CONFIG.read_text())["conductor_max_passes"]


def run_draft(council: str, period_end: str | None = None, interval: str | None = None) -> str:
    """Runs `council draft <council>`, returns the new run_id.

    Mirrors draft.yml's own approach: glob for the one freshly-created
    run directory rather than parsing the command's stdout, so this has
    no dependency on log formatting.

    `period_end`/`interval`, when given, are passed straight through to
    `council draft`'s own same-named flags (src/cli.py) — every re-draft in
    the loop then targets the same historical period consistently, rather
    than only the first draft doing so and every later pass silently
    reverting to "today" (`council draft`'s own default).
    """
    cmd = ["council", "draft", council]
    if period_end:
        cmd += ["--period-end", period_end]
    if interval:
        cmd += ["--interval", interval]
    before = {p.name for p in (DATA_DRAFT / council).glob("*")} if (DATA_DRAFT / council).exists() else set()
    print(f"\n>>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT)
    after = {p.name for p in (DATA_DRAFT / council).glob("*")}
    new_dirs = after - before
    if len(new_dirs) != 1:
        raise RuntimeError(
            f"expected exactly one new draft dir, found {len(new_dirs)}: {new_dirs!r}"
        )
    return new_dirs.pop()


def run_claude(prompt: str, label: str) -> None:
    """Invokes Claude Code as a subscription user, never the pay-per-token
    API, via two independent layers:

    1. `ANTHROPIC_API_KEY` is stripped from the child process's OS-level
       environment unconditionally -- even if it's set in the calling
       shell for some unrelated reason (e.g. direct API dev work on the
       same machine), the `claude` process launched here never sees it
       at that layer.
    2. `--setting-sources project,local` excludes the user-level Claude
       Code settings source (`~/.claude/settings.json`), which can inject
       `ANTHROPIC_API_KEY` via its own `env` block independent of the
       child process's OS environment -- see `docs/CICD_DECISIONS.md`'s
       2026-08-24 entry for why layer 1 alone isn't enough.

    Together these mean the `claude` process launched here can only
    authenticate via a login session or `CLAUDE_CODE_OAUTH_TOKEN`, never
    an API key. See this module's docstring, "Billing", for why that
    matters. Does not apply to `src/extraction/extractor.py`, which uses
    `ANTHROPIC_API_KEY` directly via the Anthropic SDK for real,
    cost-tracked extraction -- a separate code path that never calls this
    function."""
    print(f"\n>>> {label}")
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    subprocess.run(
        [
            "claude", "-p", prompt,
            "--permission-mode", "dontAsk",
            "--allowedTools", ALLOWED_TOOLS,
            "--setting-sources", "project,local",
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )


def latest_review_record(draft_dir: Path) -> dict:
    """The highest-pass-numbered defamation_review_<n>.json in draft_dir.

    Same selection logic as src/publish_gate.py's _latest_review_record —
    kept as an independent implementation here rather than importing that
    private helper, since this script is a standalone entry point, not a
    library consumer of publish_gate's internals.
    """
    candidates = list(draft_dir.glob("defamation_review_*.json"))
    if not candidates:
        raise RuntimeError(f"no defamation_review_<n>.json found in {draft_dir} — did Editor actually run?")

    def _pass_num(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[-1])
        except ValueError:
            return -1

    latest = max(candidates, key=_pass_num)
    record = json.loads(latest.read_text())
    for field in ("run_id", "status", "tracks", "pass"):
        if field not in record:
            raise RuntimeError(f"{latest} is missing required field {field!r} — malformed sidecar")
    return record


def latest_fix_report(draft_dir: Path, track: str) -> dict:
    """The highest-pass-numbered fix_report_<track>_<n>.json in draft_dir.

    Mirrors latest_review_record's selection logic exactly, scoped to one
    track's reports. Fixer_prompt.txt v0.2 added this sidecar (alongside
    Editor's own, already read above) specifically so a BLOCKED verdict
    can be detected mechanically -- see that file's changelog for the
    incident this closes: a Fixer pass correctly declined a hard-to-reverse
    decision in prose, and nothing downstream was reading prose.
    """
    candidates = list(draft_dir.glob(f"fix_report_{track}_*.json"))
    if not candidates:
        raise RuntimeError(
            f"no fix_report_{track}_<n>.json found in {draft_dir} — did Fixer[{track}] actually run?"
        )

    def _pass_num(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[-1])
        except ValueError:
            return -1

    latest = max(candidates, key=_pass_num)
    report = json.loads(latest.read_text())
    for field in ("run_id", "track", "status", "blocked_on"):
        if field not in report:
            raise RuntimeError(f"{latest} is missing required field {field!r} — malformed sidecar")
    return report


def escalate_blocked(council: str, run_id: str, blocked_reports: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print("ESCALATING — Fixer flagged something it correctly won't decide alone.")
    print(f"Draft: data/draft/{council}/{run_id}/")
    for report in blocked_reports:
        print(f"\n[{report['track']}]")
        for item in report["blocked_on"]:
            print(f"  - {item.get('flag', '<no summary given>')}")
            print(f"    reason: {item.get('reason', '<no reason given>')}")
    print(
        "\nNot re-drafting or re-reviewing — see docs/review/fixer/Fixer_prompt.txt's "
        "\"A single BLOCKED flag...\" rule and the full fix_report_<track>_<n>.md for detail."
    )
    print(f"{'=' * 70}\n")


def escalate(council: str, run_id: str, record: dict, max_passes: int) -> None:
    print(f"\n{'=' * 70}")
    print(f"ESCALATING — pass cap ({max_passes}) reached with blocking flags still open.")
    print(f"Draft: data/draft/{council}/{run_id}/")
    print(f"Last verdict: {record['status']}, tracks still flagged: {record['tracks']}")
    print("A human needs to look at this draft directly — see docs/review/CONDUCTOR.md")
    print("'The chain loop' for what happens after a cap-hit escalation.")
    print(f"{'=' * 70}\n")


def run_editor(council: str, run_id: str, pass_num: int) -> None:
    """Shells out to `council editor` — the same standalone command a human
    could run by hand — rather than dispatching the `claude -p` call inline.
    Mirrors run_draft()'s subprocess pattern above: this loop is built out
    of the same CLI entry points a person could call individually, so every
    step it takes is independently runnable, even though in practice this
    loop is what calls them almost all the time.
    """
    print(f"\n>>> Editor, pass {pass_num}, run {run_id}")
    subprocess.run(["council", "editor", council, run_id], check=True, cwd=ROOT)


def run_fixer(track: str, council: str, run_id: str, pass_num: int) -> None:
    """Shells out to `council fixer` — see run_editor's docstring above;
    the same reasoning applies."""
    print(f"\n>>> Fixer [{track}], pass {pass_num}, run {run_id}")
    subprocess.run(["council", "fixer", track, council, run_id], check=True, cwd=ROOT)


def run_conductor_loop(
    council: str, max_passes: int, dry_run: bool,
    period_end: str | None = None, interval: str | None = None,
) -> int:
    if dry_run:
        print(f"[DRY RUN] Would run the loop for {council!r}, up to {max_passes} passes.")
        if period_end or interval:
            print(f"Every draft would target period_end={period_end!r} interval={interval!r}.")
        print("Would never call `council publish` at any point.")
        return 0

    for pass_num in range(1, max_passes + 1):
        run_id = run_draft(council, period_end=period_end, interval=interval)
        draft_dir = DATA_DRAFT / council / run_id

        run_editor(council, run_id, pass_num)

        record = latest_review_record(draft_dir)
        if record["run_id"] != run_id:
            raise RuntimeError(
                f"Editor's sidecar run_id ({record['run_id']!r}) doesn't match "
                f"the draft just reviewed ({run_id!r}) — refusing to trust a "
                "verdict that isn't provably about this exact draft."
            )

        if record["status"] == "PASS":
            print(f"\n{'=' * 70}")
            print(f"PASS on pass {pass_num}. Draft: data/draft/{council}/{run_id}/")
            print("Next step (human action, never this script):")
            print(
                f"  council publish {council} --from-draft data/draft/{council}/{run_id} "
                f'--confirm "reviewed by <you>, <date>"'
            )
            print(f"{'=' * 70}\n")
            return 0

        # FAIL — dispatch only the tracks actually flagged, nothing else.
        tracks = record["tracks"]
        unknown = set(tracks) - VALID_TRACKS
        if unknown:
            raise RuntimeError(f"unknown track(s) in Editor's sidecar: {unknown!r} — not one of {VALID_TRACKS}")
        if not tracks:
            raise RuntimeError("status is FAIL but tracks is empty — malformed sidecar, cannot dispatch a fix")

        # A "human" tag is the holistic-flag outlet
        # (docs/GENERATION_SCORING_SPLIT.md §2.2): Editor's own judgment
        # that some part of this FAIL isn't a Fixer's decision to make.
        # Escalate immediately, on the same path a Fixer BLOCKED report
        # uses -- it's the same thing declared one step earlier. No Fixer
        # is dispatched this pass, including for any co-flagged ordinary
        # tracks -- the human's decision may change what those fixes
        # should be, and the pass cap shouldn't burn passes while a human
        # item is open.
        if "human" in tracks:
            human_flags = [f for f in record.get("flags", []) if "human" in (f.get("tracks") or [])]
            escalate_blocked(council, run_id, [{
                "track": "human",
                "blocked_on": [
                    {"flag": f.get("summary", "<no summary given>"), "reason": f.get("reasoning", "<no reason given>")}
                    for f in human_flags
                ],
            }])
            return 1

        if pass_num == max_passes:
            escalate(council, run_id, record, max_passes)
            return 1

        fix_reports = []
        for track in tracks:
            # No pass_num substitution here on purpose -- fixer.txt tells
            # Fixer to find the review file by listing the directory, not
            # by a predicted filename. Editor's <n> is directory-scoped
            # (always 1 under this design, one draft per pass), not the
            # Conductor's chain-wide pass_num -- passing the latter in
            # here is exactly the bug this fixed (see EDITOR_PROTOCOL.md's
            # "<n> numbering: per run-directory or per-chain?").
            run_fixer(track, council, run_id, pass_num)
            fix_reports.append(latest_fix_report(draft_dir, track))

        # Run every dispatched track before checking, not stop-on-first-BLOCKED:
        # tracks are independent, and a track that finished cleanly shouldn't
        # be left undone just because a different one hit a human decision.
        blocked = [r for r in fix_reports if r["status"] == "BLOCKED"]
        if blocked:
            escalate_blocked(council, run_id, blocked)
            return 1

        # loop continues -> next iteration re-drafts fresh, per CONDUCTOR.md:
        # "every pass's draft must be freshly generated"

    # Unreachable given the pass_num == max_passes check above, but keeps
    # the function's contract explicit rather than relying on the loop
    # falling through silently.
    raise RuntimeError("loop exited without a PASS or an escalation — this is a bug in this script")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scripted draft -> Editor -> Fixer loop (bypasses the Conductor agent role)"
    )
    parser.add_argument("council")
    parser.add_argument(
        "--max-passes", type=int, default=None,
        help="override conductor_max_passes from config/agent_switches.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--period-end", default=None,
        help="YYYY-MM-DD, passed through to every `council draft` re-draft in the "
             "loop — targets a historical period consistently across passes instead "
             "of only the first draft doing so",
    )
    parser.add_argument(
        "--interval", default=None, choices=["meeting", "week", "fortnight", "month"],
        help="passed through to every `council draft` re-draft in the loop",
    )
    args = parser.parse_args()

    max_passes = args.max_passes if args.max_passes is not None else load_max_passes()

    try:
        sys.exit(run_conductor_loop(
            args.council, max_passes, args.dry_run,
            period_end=args.period_end, interval=args.interval,
        ))
    except subprocess.CalledProcessError as exc:
        print(f"\nA step in the loop failed (exit {exc.returncode}): {exc.cmd}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"\nLoop error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
