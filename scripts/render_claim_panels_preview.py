"""
End-to-end demonstration: Claim -> linter -> Builder -> critic routing ->
cross-panel checks, against real corpus data. Not a gate, not wired into
any live path — proves the seams this migration built actually connect
(`docs/uplift/02-claim-layer.md`'s "analyst emits claims, a linter runs,
the builder renders them" chain, plus `03-claim-layer.md`'s per-claim
routing and whole-build C-06 pass), using the same real database the rest
of this project's manual verification passes use (`data/council.db`,
gitignored, absent from CI — this script is a hand-run tool, not a test;
see docs/TESTING.md).

Prints one line per covered test_id: the grade, whether it lints clean,
the chart's value/CI if present, and which critics it routes to — enough
to eyeball that a real claim's structured fields flow all the way through
to something panel-shaped and correctly triaged, without needing a full
frontend render or any of the 11 critic prompts to actually exist yet.
Then the whole-build C-06 cross-panel findings, if any.

Usage:
    python scripts/render_claim_panels_preview.py [council_id]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.builder import build_panels
from src.analysis.critic_routing import route_claim
from src.analysis.cross_panel import run_cross_panel
from src.analysis.tests import CLAIM_GENERATOR_COVERAGE_GAP, run_claim_battery


def main() -> int:
    council_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    engine = create_engine("sqlite:///data/council.db")
    session = sessionmaker(bind=engine)()

    claims, errors = run_claim_battery(session, council_id)
    panels = build_panels(claims)

    print(f"council_id={council_id}: {len(claims)} claims, {len(errors)} generation error(s), "
          f"{len(CLAIM_GENERATOR_COVERAGE_GAP)} test_id(s) not yet covered\n")

    for test_id in sorted(panels):
        p = panels[test_id]
        chart = f"value={p.chart.value}"
        if p.chart.ci_low is not None:
            chart += f" ci=[{round(p.chart.ci_low, 3)}, {round(p.chart.ci_high, 3)}]"
        status = "clean" if p.lint_clean else f"{len(p.lint_failures)} lint failure(s)"
        critics = ",".join(route_claim(claims[test_id]))
        print(f"  [{p.grade:<11}] {test_id:<45} {chart:<45} {status:<20} -> {critics}")

    if errors:
        print("\nGeneration errors:")
        for e in errors:
            print(f"  [{e.test_id}] {e.error}")

    findings = run_cross_panel(list(claims.values()))
    print(f"\nC-06 cross-panel: {len(findings)} finding(s)")
    for f in findings:
        print(f"  [{f.id}] {f.claim_id}: {f.statement}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
