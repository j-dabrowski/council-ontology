"""
End-to-end demonstration: Claim -> linter -> Builder, against real corpus
data. Not a gate, not wired into any live path — proves the seam this
migration built actually connects (`docs/uplift/02-claim-layer.md`'s
"analyst emits claims, a linter runs, the builder renders them" chain),
using the same real database the rest of this project's manual
verification passes use (`data/council.db`, gitignored, absent from CI —
this script is a hand-run tool, not a test; see docs/TESTING.md).

Prints one line per covered test_id: the grade, whether it lints clean,
and the chart's value/CI if present — enough to eyeball that a real
claim's structured fields actually flow all the way through to something
panel-shaped, without needing a full frontend render.

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
        print(f"  [{p.grade:<11}] {test_id:<45} {chart:<45} {status}")

    if errors:
        print("\nGeneration errors:")
        for e in errors:
            print(f"  [{e.test_id}] {e.error}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
