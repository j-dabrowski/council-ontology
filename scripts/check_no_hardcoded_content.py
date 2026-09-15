"""
Static content gate — docs/SECOND_COUNCIL_PLAN.md Phase 0.3.

Fails (non-zero exit) if `frontend/src/**` or `src/analysis/tests.py` contain
a string literal naming a specific council, an era label, or a hardcoded
corpus span — the same class of bug the 2026-08-06 hardcoded-names incident
was, one level up: a council-specific *claim* baked into source rather than
computed from data, not a councillor's name this time. Neither `tsc`/`eslint`
nor the draft/publish gate (which only ever checks *data reaching*
`frontend/public/data/`) can catch this — see docs/frontend/INTERACTIVITY.md's
hard rule, which this script is the mechanical check for (widened to cover
council names/era labels/corpus spans, not just councillor names, by
docs/SECOND_COUNCIL_PLAN.md Phase 3.1).

Checked patterns:
  - a council name from `src.cli.COUNCILS` (any entry, real or synthetic —
    `if council == "cambridge"` is exactly as much a bug as a literal
    "Cambridge" string; docs/SECOND_COUNCIL_PLAN.md Phase 3.2's own note
    against keeping prose behind a `council === "cambridge"` conditional),
  - "Town of X" / "City of X" / "Shire of X" (a second council may not be
    a Town — B7),
  - an era label ("Authorised Inquiry", "pre-2018", "2018-21"/"2018–21"),
  - a hardcoded corpus span ("1995-2026"-shaped, "30-year", "N Years of").

Seeded with an explicit, annotated allow-list of today's known offenders
(the B2/B6 worklist) so this lands green; Phases 1 and 3 empty it file by
file, not by weakening the patterns. Wired into `.github/workflows/ci.yml`'s
python job, alongside ruff/pytest — see docs/TESTING.md.

Usage:
    python scripts/check_no_hardcoded_content.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.cli import COUNCILS  # noqa: E402

_SCAN_TARGETS: list[Path] = [
    *sorted((REPO_ROOT / "frontend" / "src").rglob("*.ts")),
    *sorted((REPO_ROOT / "frontend" / "src").rglob("*.tsx")),
    REPO_ROOT / "src" / "analysis" / "tests.py",
]

_COUNCIL_NAME_RE = re.compile(
    "|".join(re.escape(entry["short_name"]) for entry in COUNCILS.values())
)
_GENERIC_LGA_RE = re.compile(r"\b(?:Town|City|Shire) of [A-Z][a-zA-Z]+")
_ERA_RE = re.compile(r"Authorised Inquiry|pre-2018|2018[–-]2?1\b")
_SPAN_RE = re.compile(r"19\d\d[–-]20\d\d|30-year|\d+\s*[Yy]ears? of\b")

_CHECKS: list[tuple[str, re.Pattern]] = [
    ("council-name", _COUNCIL_NAME_RE),
    ("generic-lga", _GENERIC_LGA_RE),
    ("era-label", _ERA_RE),
    ("corpus-span", _SPAN_RE),
]

# Annotated allow-list — today's known offenders (docs/SECOND_COUNCIL_PLAN.md
# B2/B6), seeded so this check lands green rather than blocking on a backlog
# it exists to track. Keyed by (path relative to repo root, 1-indexed line
# number); Phases 1 (src/analysis/tests.py) and 3 (frontend/src) empty this
# file by file — shrink it as each hardcode is fixed, never widen a pattern
# to stop matching instead.
ALLOWLIST: dict[tuple[str, int], str] = {
    ("frontend/src/components/AlignmentHeatmap.tsx", 49): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/CoMoverGraph.tsx", 33): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/CoMoverGraph.tsx", 61): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/CouncilHeader.tsx", 19): "B6: hardcoded council name/identity",
    ("frontend/src/components/CouncilHeader.tsx", 25): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/CouncilHeader.tsx", 26): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/EngagementChart.tsx", 84): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/InterestsChart.tsx", 93): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/OverviewPanel.tsx", 28): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/OverviewPanel.tsx", 135): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/OverviewPanel.tsx", 158): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/OverviewPanel.tsx", 159): "B6: hardcoded council name/identity",
    ("frontend/src/components/OverviewPanel.tsx", 163): "B6: hardcoded council name/identity",
    ("frontend/src/components/PlanningObjectionsPanel.tsx", 26): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/PlanningTrendChart.tsx", 48): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/PlanningTrendChart.tsx", 49): "B6: hardcoded council name/identity",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 15): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 16): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 20): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 21): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 125): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 130): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 148): "B6: hardcoded council name/identity",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 150): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/QuestionResponsivenessPanel.tsx", 164): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 15): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 16): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 30): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 31): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 164): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 187): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/RecusalTrendPanel.tsx", 205): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/ScorecardPanel.tsx", 109): "B6: hardcoded council name/identity",
    ("frontend/src/components/SponsorshipNetworkPanel.tsx", 214): "B6: hardcoded council name/identity",
    ("frontend/src/components/TenurePanel.tsx", 94): "B6: hardcoded council name/identity",
    ("frontend/src/components/TransparencyTrendPanel.tsx", 98): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/TransparencyTrendPanel.tsx", 138): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/TransparencyTrendPanel.tsx", 171): "B6: hardcoded council name/identity",
    ("frontend/src/components/TrendsChart.tsx", 63): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/pages/AboutPage.tsx", 25): "B6: hardcoded council name/identity",
    ("frontend/src/pages/AboutPage.tsx", 127): "B6: hardcoded council name/identity",
    ("frontend/src/pages/AboutPage.tsx", 128): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/pages/AnalysisPage.tsx", 64): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MapPage.tsx", 9): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MapPage.tsx", 27): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MapPage.tsx", 171): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MethodPage.tsx", 676): "B6: hardcoded council name/identity",
    ("frontend/src/pages/OverviewPage.tsx", 25): "B6: hardcoded council name/identity",
    ("frontend/src/pages/RecordPage.tsx", 154): "B6: hardcoded council name/identity",
    ("frontend/src/pages/WatchPage.tsx", 212): "B6: hardcoded council name/identity",
    ("src/analysis/tests.py", 228): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 302): "B6: hardcoded Authorised-Inquiry era label",
    ("src/analysis/tests.py", 316): "B6: hardcoded Authorised-Inquiry era label",
    ("src/analysis/tests.py", 392): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 409): "docstring prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", 431): "docstring prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", 461): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 475): "docstring prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", 651): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 675): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 696): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 726): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 810): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 895): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1043): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1230): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1304): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1356): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1399): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1430): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1515): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1648): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1722): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1864): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", 1913): "docstring prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", 1929): "B6: hardcoded council name/identity",
    ("src/analysis/tests.py", 1935): "B6: hardcoded Authorised-Inquiry era label",
    ("src/analysis/tests.py", 1936): "B6: hardcoded Authorised-Inquiry era label",
}


def _relpath(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def scan() -> tuple[list[tuple[str, int, str, str]], set[tuple[str, int]]]:
    """Returns (violations, allowlist_keys_still_hit)."""
    violations: list[tuple[str, int, str, str]] = []
    still_hit: set[tuple[str, int]] = set()
    for path in _SCAN_TARGETS:
        if not path.exists():
            continue
        rel = _relpath(path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for check_name, pattern in _CHECKS:
                if pattern.search(line):
                    key = (rel, lineno)
                    if key in ALLOWLIST:
                        still_hit.add(key)
                    else:
                        violations.append((rel, lineno, check_name, line.strip()))
                    break  # one hit per line is enough to report/allow it
    return violations, still_hit


def main() -> int:
    violations, still_hit = scan()
    stale = set(ALLOWLIST) - still_hit
    ok = True

    if violations:
        ok = False
        print("Hardcoded council-specific content found (not on ALLOWLIST):\n")
        for rel, lineno, check_name, line in violations:
            print(f"  {rel}:{lineno} [{check_name}] {line}")
        print(
            "\nEvery name/number a panel or battery test renders must be computed "
            "from data, not typed as a literal — see docs/frontend/INTERACTIVITY.md's "
            "hard rule. Fix it, or add an annotated ALLOWLIST entry in "
            "scripts/check_no_hardcoded_content.py if this is already-tracked backlog."
        )

    if stale:
        ok = False
        print("\nALLOWLIST entries no longer match — remove them (Phase 1/3 progress):\n")
        for rel, lineno in sorted(stale):
            print(f"  {rel}:{lineno} — {ALLOWLIST[(rel, lineno)]}")

    if ok:
        print(f"check_no_hardcoded_content: clean ({len(_SCAN_TARGETS)} files scanned, "
              f"{len(ALLOWLIST)} allow-listed).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
