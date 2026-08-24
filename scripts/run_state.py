"""
run_state.json — the coordination record for the staging escalation model
(docs/AUTOMATION_ARCHITECTURE.md Part 4). Lives at `.github/run_state.json`,
git-tracked, written by every segment (discovery.yml or maintenance.yml)
regardless of outcome.

It is coordination state, not findings — safe in git per Part 1 (the DB,
drafts, and INVESTIGATIONS.md are the things that stay in GCS; this is not
one of them). Its two jobs:

  1. Tell the next dispatch of the same workflow, in `resume` mode, which
     segment number to continue at (`segment` + 1).
  2. Tell `.github/workflows/resume.yml` — triggered on every push to
     `staging` — whether that push was an escalation-PR merge worth acting
     on (`status == "escalated"`) or something else (a `fresh` dispatch's
     own reset-push, or a push that isn't part of this model at all), so
     it can auto-continue the run only in the former case.

No workflow file parses JSON inline for this — see the module docstring's
sibling in `conductor_loop.py` for why shelling out to one script beats
duplicating jq/python -c one-liners across two YAML files.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
RUN_STATE_PATH = ROOT / ".github" / "run_state.json"


@dataclass
class RunState:
    run_id: str
    workflow: str  # "discovery" | "maintenance"
    council: str
    segment: int
    mode: str  # "fresh" | "resume"
    status: str  # "escalated" | "completed"
    escalation_reason: str | None = None
    conductor_loop: dict | None = None  # maintenance only: {"pass_count": int, "exit_code": int}
    publish_requested: bool = False
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


def write(state: RunState, path: Path = RUN_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")


def read(path: Path = RUN_STATE_PATH) -> RunState | None:
    """Returns None if the file doesn't exist — a legitimate state (no
    prior run, or a `staging` push that isn't part of this model at all),
    never an error. Raises on a malformed file: an existing-but-broken
    run_state.json is a real problem, not a case to silently treat as
    "no state"."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return RunState(**data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_write = sub.add_parser("write", help="write a new run_state.json")
    p_write.add_argument("--run-id", required=True)
    p_write.add_argument("--workflow", required=True, choices=["discovery", "maintenance"])
    p_write.add_argument("--council", required=True)
    p_write.add_argument("--segment", required=True, type=int)
    p_write.add_argument("--mode", required=True, choices=["fresh", "resume"])
    p_write.add_argument("--status", required=True, choices=["escalated", "completed"])
    p_write.add_argument("--escalation-reason", default=None)
    p_write.add_argument("--conductor-loop-json", default=None, help="JSON object, maintenance only")
    p_write.add_argument("--publish-requested", action="store_true")

    sub.add_parser("read", help="print run_state.json as JSON, or {} if absent")

    p_segment = sub.add_parser(
        "next-segment",
        help="print the next segment number for --mode (1 for fresh; prior segment + 1 for resume)",
    )
    p_segment.add_argument("--mode", required=True, choices=["fresh", "resume"])

    sub.add_parser(
        "should-resume",
        help="exit 0 and print the workflow name if run_state.json is status=escalated, else exit 1",
    )

    args = parser.parse_args()

    if args.cmd == "write":
        state = RunState(
            run_id=args.run_id,
            workflow=args.workflow,
            council=args.council,
            segment=args.segment,
            mode=args.mode,
            status=args.status,
            escalation_reason=args.escalation_reason,
            conductor_loop=json.loads(args.conductor_loop_json) if args.conductor_loop_json else None,
            publish_requested=args.publish_requested,
        )
        # Explicit path, not write()'s default: the default is bound once
        # at function-definition time, so a test (or any caller) that
        # monkeypatches the module-level RUN_STATE_PATH after import needs
        # this call site to re-read that name at call time instead.
        write(state, RUN_STATE_PATH)
        print(json.dumps(state.to_dict(), indent=2))

    elif args.cmd == "read":
        state = read(RUN_STATE_PATH)
        print(json.dumps(state.to_dict(), indent=2) if state else "{}")

    elif args.cmd == "next-segment":
        state = read(RUN_STATE_PATH)
        if args.mode == "fresh":
            print(1)
        else:
            if state is None:
                print("resume requested but no .github/run_state.json found at staging HEAD — "
                      "nothing to resume; dispatch with mode=fresh instead", file=sys.stderr)
                sys.exit(1)
            print(state.segment + 1)

    elif args.cmd == "should-resume":
        state = read(RUN_STATE_PATH)
        if state is None or state.status != "escalated":
            sys.exit(1)
        print(state.workflow)

    else:  # pragma: no cover — argparse enforces this
        raise AssertionError(f"unhandled subcommand {args.cmd!r}")


if __name__ == "__main__":
    main()
