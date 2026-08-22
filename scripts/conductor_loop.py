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
`claude -p` calls. Everything *between* them -- did it pass, which
track(s) got flagged, have we hit the cap -- is exactly the kind of
thing this script does instead of an LLM.

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

Exit codes: 0 = clean PASS reached. 1 = cap hit, escalated, needs a human.
2 = something in the loop itself failed unexpectedly (bad JSON, missing
file, a `claude` invocation erroring) -- distinct from a normal FAIL
review, which is expected loop behaviour, not an error.
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

# Same three modes Fixer has always had -- see docs/review/fixer/.
VALID_TRACKS = {"frontend", "pipeline", "doc"}

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


def _load_prompt(name: str, **placeholders: str) -> str:
    text = (AGENT_PROMPTS_DIR / f"{name}.txt").read_text()
    for key, value in placeholders.items():
        text = text.replace(f"<{key}>", value)
    return text


def load_max_passes() -> int:
    return json.loads(CONFIG.read_text())["conductor_max_passes"]


def run_draft(council: str) -> str:
    """Runs `council draft <council>`, returns the new run_id.

    Mirrors draft.yml's own approach: glob for the one freshly-created
    run directory rather than parsing the command's stdout, so this has
    no dependency on log formatting.
    """
    before = {p.name for p in (DATA_DRAFT / council).glob("*")} if (DATA_DRAFT / council).exists() else set()
    print(f"\n>>> council draft {council}")
    subprocess.run(["council", "draft", council], check=True, cwd=ROOT)
    after = {p.name for p in (DATA_DRAFT / council).glob("*")}
    new_dirs = after - before
    if len(new_dirs) != 1:
        raise RuntimeError(
            f"expected exactly one new draft dir, found {len(new_dirs)}: {new_dirs!r}"
        )
    return new_dirs.pop()


def run_claude(prompt: str, label: str) -> None:
    """Invokes Claude Code as a subscription user, never the pay-per-token
    API. `ANTHROPIC_API_KEY` is stripped from the child process's
    environment unconditionally -- even if it's set in the calling shell
    for some unrelated reason (e.g. direct API dev work on the same
    machine), the `claude` process launched here never sees it, so it
    can only authenticate via a login session or CLAUDE_CODE_OAUTH_TOKEN.
    See this module's docstring, "Billing", for the reasoning."""
    print(f"\n>>> {label}")
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    subprocess.run(
        [
            "claude", "-p", prompt,
            "--permission-mode", "dontAsk",
            "--allowedTools", ALLOWED_TOOLS,
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


def escalate(council: str, run_id: str, record: dict, max_passes: int) -> None:
    print(f"\n{'=' * 70}")
    print(f"ESCALATING — pass cap ({max_passes}) reached with blocking flags still open.")
    print(f"Draft: data/draft/{council}/{run_id}/")
    print(f"Last verdict: {record['status']}, tracks still flagged: {record['tracks']}")
    print("A human needs to look at this draft directly — see docs/review/CONDUCTOR.md")
    print("'The chain loop' for what happens after a cap-hit escalation.")
    print(f"{'=' * 70}\n")


def run_conductor_loop(council: str, max_passes: int, dry_run: bool) -> int:
    if dry_run:
        print(f"[DRY RUN] Would run the loop for {council!r}, up to {max_passes} passes.")
        print("Would never call `council publish` at any point.")
        return 0

    for pass_num in range(1, max_passes + 1):
        run_id = run_draft(council)
        draft_dir = DATA_DRAFT / council / run_id

        editor_prompt = _load_prompt("editor", council=council, run_id=run_id)
        run_claude(editor_prompt, f"Editor, pass {pass_num}, run {run_id}")

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

        if pass_num == max_passes:
            escalate(council, run_id, record, max_passes)
            return 1

        for track in tracks:
            fixer_prompt = _load_prompt(
                "fixer", council=council, run_id=run_id, pass_num=str(pass_num), track=track
            )
            run_claude(fixer_prompt, f"Fixer [{track}], pass {pass_num}, run {run_id}")

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
    args = parser.parse_args()

    max_passes = args.max_passes if args.max_passes is not None else load_max_passes()

    try:
        sys.exit(run_conductor_loop(args.council, max_passes, args.dry_run))
    except subprocess.CalledProcessError as exc:
        print(f"\nA step in the loop failed (exit {exc.returncode}): {exc.cmd}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"\nLoop error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
