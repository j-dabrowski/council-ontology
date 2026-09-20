"""
Claim battery CI report — docs/uplift/migration/02-claim-layer.md Step 9,
attempted (not completed — see docs/TESTING.md's "Claim battery report"
section for why full Step 9 isn't safe to attempt yet).

Runs `run_claim_battery()` (src/analysis/tests.py) against the `testville`
"baseline" synthetic corpus (src/fixtures/testville.py — no data/council.db
dependency, so this runs in CI same as everything else under tests/), lints
the result, and prints a summary: how many of the 26 registered claim
generators produced a claim, how many raised, and how many linter FAILs
per rule.

Always exits 0, even on a per-claim generation error — this is a report,
not a gate, full stop (the deliberate choice over a stricter variant that
would fail CI on a claim-generation exception specifically). Most of the
26 migrated claims carry at least one *known, systemic* linter FAIL today
(no achieved_power computation exists anywhere yet; no clustered
two-proportion difference estimator exists; the target schema's
numerator/denominator pair can't represent a two-group comparison's
per-group rates) — the exact same reasoning `council draft`'s own
claim-lint step (src/cli.py) already uses to stay non-blocking. This
script exists so that reporting is visible on every CI run without needing
a real `council draft` run (which needs data/council.db, gitignored and
absent from CI).

Usage:
    python scripts/claim_battery_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.claim_linter import LintStatus, lint_batch
from src.analysis.tests import _CLAIM_GENERATORS, CLAIM_GENERATOR_COVERAGE_GAP, run_claim_battery
from src.fixtures.testville import seed_profile
from src.models import Base
from src.storage.database import _enable_wal_and_fk


def main() -> int:
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    council_id, _created = seed_profile(session, "baseline")

    try:
        claims, errors = run_claim_battery(session, council_id)
    except Exception as exc:  # noqa: BLE001 - a real regression, not a per-claim issue
        print(f"FATAL: run_claim_battery() itself raised {type(exc).__name__}: {exc}")
        return 1

    n_registered = len(_CLAIM_GENERATORS)
    n_no_data = n_registered - len(claims) - len(errors)
    print(f"Claim battery report (testville baseline, {n_registered} generators registered)")
    print(f"  {len(claims)} produced a claim")
    print(f"  {n_no_data} returned None (no data for this corpus)")
    print(f"  {len(errors)} raised an exception")
    print(f"  {len(CLAIM_GENERATOR_COVERAGE_GAP)} test_ids not yet covered by any generator: "
          f"{sorted(CLAIM_GENERATOR_COVERAGE_GAP)}")

    if errors:
        print("\nGeneration errors (a real regression — investigate):")
        for e in errors:
            print(f"  [{e.test_id}] {e.error}")

    if claims:
        results = lint_batch(list(claims.values()))
        fail_counts: dict[str, int] = {}
        for claim_results in results.values():
            for r in claim_results:
                if r.status == LintStatus.FAIL:
                    fail_counts[r.rule_id] = fail_counts.get(r.rule_id, 0) + 1
        total_fails = sum(fail_counts.values())
        print(f"\n{total_fails} linter FAIL(s) across {len(claims)} claims, by rule:")
        for rule_id in sorted(fail_counts):
            print(f"  {rule_id}: {fail_counts[rule_id]}")
        print(
            "(Non-blocking — most FAILs here are known, systemic gaps, not per-claim bugs; "
            "see docs/TESTING.md.)"
        )

    # Always 0 here - a per-claim generation error is printed above (worth
    # a human noticing) but doesn't fail the build, same as an ordinary
    # linter FAIL. Only run_claim_battery() itself raising (caught above)
    # is treated as a real, build-failing regression - that would mean
    # this report is broken, not just one claim.
    return 0


if __name__ == "__main__":
    sys.exit(main())
