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
# it exists to track. Keyed by (path relative to repo root, exact stripped
# line text) rather than line number — Phase 1.1 edits `src/analysis/
# tests.py` a line at a time, and a line-number key would go stale on every
# unrelated edit above the line it names, not just when that specific line
# is actually fixed. Phases 1 (src/analysis/tests.py) and 3 (frontend/src)
# empty this file by file — shrink it as each hardcode is fixed, never widen
# a pattern to stop matching instead.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("frontend/src/components/OverviewPanel.tsx", "<>Four independent panels pivot on the 2018\u201321 Authorised Inquiry. Stepping out"): "B6: hardcoded Authorised-Inquiry era label",
    ("frontend/src/components/OverviewPanel.tsx", "statLabel: \"confidential business across two decades (1995\u20132017) \u2014 a genuinely open baseline\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/OverviewPanel.tsx", "title=\"What 30 Years of Minutes Say \u2014 the Big Picture\""): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/components/OverviewPanel.tsx", "subtitle={`A synthesis across every panel below \u00b7 Town of Cambridge \u00b7 ${d.span} \u00b7 ${d.n_minutes} minutes`}"): "B6: hardcoded council name/identity",
    ("frontend/src/components/OverviewPanel.tsx", "On the evidence, Cambridge is a <strong>broadly sound council with specific,"): "B6: hardcoded council name/identity",
    ("frontend/src/pages/AboutPage.tsx", "Town of Cambridge against City of Fremantle against City of Perth on"): "B6: hardcoded council name/identity",
    ("frontend/src/pages/AboutPage.tsx", "Currently live: <strong>Town of Cambridge, Western Australia</strong>{\" \"}"): "B6: hardcoded council name/identity",
    ("frontend/src/pages/AboutPage.tsx", "(1995\u20132026 \u00b7 537 documents \u00b7 30-year corpus)."): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("frontend/src/pages/MapPage.tsx", "\"Cambridge\": \"cambridge\","): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MapPage.tsx", "// Score \u2192 fill colour.  Amber for Cambridge's current 6 supportive / 5 critical."): "B6: hardcoded council name/identity",
    ("frontend/src/pages/MapPage.tsx", "label: \"Town of Cambridge\","): "B6: hardcoded council name/identity",
    ("frontend/src/pages/RecordPage.tsx", "placeholder=\"e.g. Cambridge Street\""): "B6: hardcoded council name/identity",
    ("src/analysis/tests.py", "era=\"1995\u20132026\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "# rather than assuming Cambridge's own rose-then-fell shape. A \u00b15pp"): "B6: hardcoded council name/identity",
    ("src/analysis/tests.py", "title=\"Did recusal compliance track the Authorised Inquiry?\","): "B6: hardcoded Authorised-Inquiry era label",
    ("src/analysis/tests.py", "era=\"pre-2018 / 2018\u201321 / post-2022\","): "B6: hardcoded Authorised-Inquiry era label",
    ("src/analysis/tests.py", "era=\"1995\u20132026 \u00b7 DIRECTIONAL (thin n per body)\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "meeting regardless of body. Cambridge's corpus is ~90% full_council, so a"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "# Cambridge's specific 2000s-old-guard history, not derived from `s` at"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "# 1996-2023 electoral-term calendar and a hand-written era-by-era"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "# On a second council this renders the exact same Cambridge sentence"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "# against a corpus with real raw collisions (Cambridge has 2 \u2014 see"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "A body-matched baseline is the comparable one but can be thin (Cambridge's"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "`meeting_id` \u2014 every meeting sharing a body class (Cambridge's ~90%"): "docstring/comment prose, not rendered text \u2014 not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "era=\"1995\u20132026, era-pooled\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "era=\"1999\u20132026 (mayors with dated terms)\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "era=\"1996\u20132023 (electoral terms)\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "era=\"1995\u20132026 (years with \u226530 carried motions)\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "era=\"1995\u20132026 \u00b7 DIRECTIONAL (n<30)\","): "B6: hardcoded corpus span (1995-2026 / 30-year)",
    ("src/analysis/tests.py", "# unconditional text were Cambridge-specific statistics this function"): "docstring/comment prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
    ("src/analysis/tests.py", "# the verdict, which used to name Cambridge and its Authorised Inquiry"): "docstring/comment prose, not rendered text — not a real leak, just this line-based scanner's lack of AST awareness",
}


def _relpath(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def scan() -> tuple[list[tuple[str, int, str, str]], set[tuple[str, str]]]:
    """Returns (violations, allowlist_keys_still_hit). Violations carry the
    current line number (for navigating to the hit); ALLOWLIST itself is
    keyed by content, not line number — see its own comment for why."""
    violations: list[tuple[str, int, str, str]] = []
    still_hit: set[tuple[str, str]] = set()
    for path in _SCAN_TARGETS:
        if not path.exists():
            continue
        rel = _relpath(path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            for check_name, pattern in _CHECKS:
                if pattern.search(line):
                    key = (rel, stripped)
                    if key in ALLOWLIST:
                        still_hit.add(key)
                    else:
                        violations.append((rel, lineno, check_name, stripped))
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
        for rel, text in sorted(stale):
            print(f"  {rel}: {text!r} — {ALLOWLIST[(rel, text)]}")

    if ok:
        print(f"check_no_hardcoded_content: clean ({len(_SCAN_TARGETS)} files scanned, "
              f"{len(ALLOWLIST)} allow-listed).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
