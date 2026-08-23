"""
Scripted Level 1 inventory-improvement loop — docs/pipeline/PIPELINE.md's
"Iteration loop (repeat until other_content_rate <= 20%)".

That loop has always been a documented, six-step manual recipe: run
inventory on a sample, run typology, paste the generated instructions into
Claude Code by hand, re-run, re-check, repeat. Every mechanical piece of it
was already scriptable — `council typology` already computes
`other_content_rate` and already generates the exact "paste into Claude
Code" instructions a human currently copies. This script is that same
recipe, composed entirely out of standalone `council` commands (`inventory`,
`typology`, `inventory-refine`) rather than a private duplicate of any of
them — same principle `conductor_loop.py` uses for the review loop, and for
the same reason: every step this loop takes should be independently
runnable through the same command a human would use.

What still needs an agent: writing the actual prompt/schema edit that
reduces `other_content_rate` (`council inventory-refine`, one real
`claude -p` call per pass). Everything else — running inventory, computing
the rate, checking it against the threshold, deciding whether to keep
iterating — is exactly the kind of thing this script does instead of an
LLM.

**Billing:** the sample-size inventory re-runs and the final full-corpus
run are billed API calls (Haiku, cheap but real) — not free like the
Editor/Fixer loop's `council draft`. `inventory-refine`'s own `claude -p`
call follows the same subscription-auth, `ANTHROPIC_API_KEY`-stripped
discipline as `conductor_loop.py` (see that module's docstring).

Usage:
    python scripts/inventory_loop.py cambridge
    python scripts/inventory_loop.py cambridge --limit 20 --max-passes 5
    python scripts/inventory_loop.py cambridge --dry-run

Exit codes: 0 = converged, confirmed at full-corpus scale. 1 = escalated —
either the pass cap was reached on the sample with the rate still above
threshold, or the sample converged but a full-corpus re-run didn't (the
sample wasn't representative; needs a human to pick a different one or
investigate). 2 = a genuine script/subprocess error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
QUALITY_DIR = ROOT / "data" / "inventory_quality"

DEFAULT_LIMIT = 20


def _run(cmd: list[str], label: str) -> None:
    print(f"\n>>> {label}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def run_inventory(council: str, limit: int | None) -> None:
    cmd = ["council", "inventory", council, "--force"]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    _run(cmd, f"council inventory {council}" + (f" --force --limit {limit}" if limit else " --force"))


def run_typology(council: str, limit: int | None) -> dict:
    """Runs `council typology`, then reads back the quality dict it just
    wrote to data/inventory_quality/latest_<council>.json — the same
    "read structured state, don't parse console output" pattern
    conductor_loop.py uses for Editor's JSON sidecar.
    """
    cmd = ["council", "typology", council, "--quiet"]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    _run(cmd, f"council typology {council}" + (f" --limit {limit}" if limit else ""))
    quality_path = QUALITY_DIR / f"latest_{council}.json"
    if not quality_path.exists():
        raise RuntimeError(f"{quality_path} missing after `council typology` — did it run?")
    return json.loads(quality_path.read_text())


def run_inventory_refine(council: str, limit: int | None) -> None:
    cmd = ["council", "inventory-refine", council]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    _run(cmd, f"Inventory refine, {council}")


def escalate_pass_cap(council: str, max_passes: int, quality: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"ESCALATING — pass cap ({max_passes}) reached, other_content_rate still")
    print(f"{quality['other_content_pct']}% (threshold 20%).")
    print("A human needs to look at the typology report directly — see")
    print("docs/pipeline/PIPELINE.md's 'Level 1: Inventory' section.")
    print(f"{'=' * 70}\n")


def escalate_full_corpus_mismatch(council: str, sample_quality: dict, full_quality: dict) -> None:
    print(f"\n{'=' * 70}")
    print("ESCALATING — the sample converged but the full corpus didn't.")
    print(f"Sample other_content_rate: {sample_quality['other_content_pct']}%")
    print(f"Full corpus other_content_rate: {full_quality['other_content_pct']}%")
    print("The sample wasn't representative. A human should pick a different")
    print("sample (or inspect the full-corpus typology report directly) rather")
    print("than this script guessing at a fix.")
    print(f"{'=' * 70}\n")


def run_inventory_loop(council: str, limit: int, max_passes: int, dry_run: bool) -> int:
    if dry_run:
        print(f"[DRY RUN] Would run the loop for {council!r}, sample size {limit}, "
              f"up to {max_passes} passes, then confirm at full-corpus scale.")
        print("Would make real (cheap) inventory API calls once run for real.")
        return 0

    for pass_num in range(1, max_passes + 1):
        run_inventory(council, limit)
        quality = run_typology(council, limit)

        if quality["other_content_rate"] <= 0.20:
            print(f"\nSample converged ({quality['other_content_pct']}%) on pass {pass_num} — "
                  "confirming at full-corpus scale.")
            run_inventory(council, None)
            full_quality = run_typology(council, None)
            if full_quality["other_content_rate"] <= 0.20:
                print(f"\n{'=' * 70}")
                print(f"PASS — {full_quality['other_content_pct']}% at full-corpus scale "
                      f"(sample: {quality['other_content_pct']}%).")
                print("Level 1 is complete. Next: Level 2 schema update — re-run")
                print(f"`council typology {council}` (no --limit) once more to get the")
                print("schema-update prompt it now prints instead.")
                print(f"{'=' * 70}\n")
                return 0
            escalate_full_corpus_mismatch(council, quality, full_quality)
            return 1

        if pass_num == max_passes:
            escalate_pass_cap(council, max_passes, quality)
            return 1

        run_inventory_refine(council, limit)
        # loop continues -> next pass re-runs inventory under the edited prompt

    raise RuntimeError("loop exited without converging or escalating — this is a bug in this script")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scripted Level 1 inventory-improvement loop (bypasses the manual paste-into-Claude-Code recipe)"
    )
    parser.add_argument("council")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"sample size for iteration passes (default: {DEFAULT_LIMIT})")
    parser.add_argument("--max-passes", type=int, default=5, dest="max_passes")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args()

    try:
        sys.exit(run_inventory_loop(args.council, args.limit, args.max_passes, args.dry_run))
    except subprocess.CalledProcessError as exc:
        print(f"\nA step in the loop failed (exit {exc.returncode}): {exc.cmd}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"\nLoop error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
