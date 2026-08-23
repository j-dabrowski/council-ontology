"""
Scripted Level 3 sample-extraction-improvement loop —
docs/pipeline/PIPELINE.md's extraction convergence loop.

Same shape and reasoning as scripts/inventory_loop.py (read that module's
docstring first if this is unfamiliar): a documented manual recipe —
extract a stratified sample, validate it, read the paraphrase report to
identify failure patterns, hand-edit system_prompt.txt, re-extract, repeat —
composed here entirely out of standalone `council` commands
(`extract-sample`, `validate-sample`, `extraction-refine`) rather than a
private duplicate of any of them. Every step this loop takes is
independently runnable through the same command a human would use.

What still needs an agent: writing the actual prompt edit that improves the
metrics (`council extraction-refine`, one real `claude -p` call per pass).
Everything else — extracting, validating, checking the four target
thresholds, deciding whether to keep iterating — is exactly the kind of
thing this script does instead of an LLM. The "converged" check
(scripts/validate_sample.py's `compute_verdict`) is the single source of
truth this loop, `council extraction-refine`, and the human-facing
report.txt all read — they can never disagree about whether the loop
should keep going.

**Billing:** extract-sample calls the real extraction model (Sonnet/Opus
tier, not the cheap Haiku inventory calls) — this loop is not free to run
for real, even on an 18-doc sample. `extraction-refine`'s own `claude -p`
call follows the same subscription-auth, `ANTHROPIC_API_KEY`-stripped
discipline as conductor_loop.py (see that module's docstring).

Usage:
    python scripts/extraction_loop.py cambridge
    python scripts/extraction_loop.py cambridge --max-passes 5
    python scripts/extraction_loop.py cambridge --dry-run

Exit codes: 0 = converged (all four target metrics met, zero FAILs).
1 = escalated — the pass cap was reached with the verdict still not
converged; a human needs to look at report.txt directly. 2 = a genuine
script/subprocess error.

Requires `council sample <council>` to have already selected a stratified
sample (data/{council}_sample.json) — this loop iterates the prompt
against that fixed sample, it doesn't pick one.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
VALIDATION_DIR = ROOT / "data" / "sample_validation"


def _run(cmd: list[str], label: str) -> None:
    print(f"\n>>> {label}")
    subprocess.run(cmd, check=True, cwd=ROOT)


def run_extract_sample(council: str) -> None:
    _run(["council", "extract-sample", council], f"council extract-sample {council}")


def run_validate_sample(council: str) -> dict:
    """Runs `council validate-sample`, then reads back the verdict it just
    wrote to data/sample_validation/summary.json — same "read structured
    state, don't parse console/report text" pattern as
    scripts/inventory_loop.py's run_typology().
    """
    _run(["council", "validate-sample", council], f"council validate-sample {council}")
    summary_path = VALIDATION_DIR / "summary.json"
    if not summary_path.exists():
        raise RuntimeError(f"{summary_path} missing after `council validate-sample` — did it run?")
    return json.loads(summary_path.read_text())


def run_extraction_refine(council: str) -> None:
    _run(["council", "extraction-refine", council], f"Extraction refine, {council}")


def escalate(council: str, max_passes: int, verdict: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"ESCALATING — pass cap ({max_passes}) reached, not yet converged.")
    print(f"completeness={verdict['avg_completeness']*100:.1f}% "
          f"paraphrase={verdict['avg_paraphrase']*100:.1f}% "
          f"coverage={verdict['avg_coverage']*100:.2f}% "
          f"keyword_gap={verdict['avg_keyword_gap']*100:.1f}% "
          f"({verdict['passes']} PASS / {verdict['reviews']} REVIEW / {verdict['fails']} FAIL)")
    print(f"A human needs to look at {VALIDATION_DIR}/report.txt directly.")
    print(f"{'=' * 70}\n")


def run_extraction_loop(council: str, max_passes: int, dry_run: bool) -> int:
    if dry_run:
        print(f"[DRY RUN] Would run the loop for {council!r}, up to {max_passes} passes.")
        print("Would make real (extraction-tier) API calls once run for real.")
        return 0

    for pass_num in range(1, max_passes + 1):
        run_extract_sample(council)
        verdict = run_validate_sample(council)

        if verdict["converged"]:
            print(f"\n{'=' * 70}")
            print(f"PASS on pass {pass_num} — all four metrics within target, "
                  f"{verdict['fails']} FAIL.")
            print("Level 3 is complete. Next: Level 4 — council validate "
                  f"{council} (full-corpus confidence scoring), then Level 5:")
            print(f"  council extract {council}")
            print(f"{'=' * 70}\n")
            return 0

        if pass_num == max_passes:
            escalate(council, max_passes, verdict)
            return 1

        run_extraction_refine(council)
        # loop continues -> next pass re-extracts the same sample under the edited prompt

    raise RuntimeError("loop exited without converging or escalating — this is a bug in this script")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scripted Level 3 extraction-improvement loop (bypasses the manual edit-and-rerun recipe)"
    )
    parser.add_argument("council")
    parser.add_argument("--max-passes", type=int, default=5, dest="max_passes")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args()

    try:
        sys.exit(run_extraction_loop(args.council, args.max_passes, args.dry_run))
    except subprocess.CalledProcessError as exc:
        print(f"\nA step in the loop failed (exit {exc.returncode}): {exc.cmd}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"\nLoop error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
