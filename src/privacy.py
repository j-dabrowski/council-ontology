"""Pattern-based redaction of private individuals' names in planning
evidence quotes (docs/frontend/RECORD_PAGE_PLAN.md B.1).

Unlike `usable_roster_names()` (src/invariant_gate.py), which matches a
known councillor roster, private residents are not enumerable — there is
no roster to check a quote against. This matches *shapes* in the text
instead:

1. A labelled owner/applicant field — "Owner: Mr Peter Northcott",
   "LANDOWNER: Y Xie APPLICANT: Delstrat Pty Ltd", newline- or
   space-delimited, bounded by the next recognised field label, a
   newline, or the end of the string. The whole field value is stripped,
   not just a name inside it — a company name in an Applicant field is
   collateral (over-redaction is the safe direction here; there is no
   reliable way to tell a person from a company by regex alone).
2. A bare personal title in front of a capitalised name — "Mr Peter
   Northcott" — wherever it appears, labelled or not.

RECORD_PAGE_PLAN.md A.1 measured both shapes against a sample of planning
evidence quotes: ~12% carry a field label, ~3% carry a personal title.
`scripts/measure_private_name_patterns.py` re-measures this against the
live corpus.

LIMITATION, permanent and documented here rather than assumed away: a
name with neither a label nor a title in front of it (e.g. "the
objection lodged by Peter Northcott") is not caught.
tests/test_privacy.py::test_bare_name_with_no_label_or_title_is_not_caught
exists to keep this honest, not to be quietly fixed later without
updating this docstring. `applicant_name` itself is never projected into
a /record payload at all (RECORD_PAGE_PLAN.md B.1) — this redactor only
helps with free-text quotes, where a structured field can't.

Never synthesise or tidy: this only removes matched spans, it never
rewrites or trims anything else in the text (same rule as
EVIDENCE_CHAIN_PLAN.md B.6).

Patterns live in config/private_name_patterns.json, not hardcoded here,
so the frontend mirror (frontend/src/guardrail.tsx) builds its regexes
from the identical data (via the @patterns Vite alias in
frontend/vite.config.ts) instead of a hand-copied pattern that can
silently drift from this one. Python and TypeScript still each compile
their own `RegExp`/`re.Pattern` — the shared part is the pattern data,
not compiled code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

DEFAULT_PATH: Final = Path(__file__).resolve().parent.parent / "config" / "private_name_patterns.json"


def _load_patterns(path: Path = DEFAULT_PATH) -> dict:
    return json.loads(path.read_text())


def _build_regexes(patterns: dict) -> tuple[re.Pattern, re.Pattern]:
    field_labels = sorted(patterns["field_labels"], key=len, reverse=True)
    redacted_labels = sorted(patterns["redacted_labels"], key=len, reverse=True)
    titles = sorted(patterns["personal_titles"], key=len, reverse=True)

    field_alt = "|".join(re.escape(label) for label in field_labels)
    redacted_alt = "|".join(re.escape(label) for label in redacted_labels)
    title_alt = "|".join(re.escape(title) for title in titles)

    # Matches the label, the colon, and everything up to the next
    # recognised field label / newline / end of string — that trailing
    # span is the name (or company name) being stripped. The lookahead's
    # `\s+` (not `.*?`) owns the separating whitespace before the next
    # field, so that whitespace survives the substitution instead of
    # being swallowed into the removed span (which would glue the next
    # field's label onto the placeholder with no space between them).
    line_re = re.compile(
        rf"\b(?:{redacted_alt})S?:\s*.*?(?=\n|$|\s+(?:{field_alt})S?:)",
        re.IGNORECASE,
    )
    # A title, then 1-4 capitalised tokens, each *preceded* by whitespace
    # rather than followed by it — same reason: no trailing separator
    # gets consumed into the match. Self-limiting on its own, since a
    # lowercase word (e.g. "and", "raised") ends the run.
    title_re = re.compile(
        rf"\b(?:{title_alt})\.?\s+[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*){{0,3}}",
    )
    return line_re, title_re


_PATTERNS = _load_patterns()
_LINE_RE, _TITLE_RE = _build_regexes(_PATTERNS)
PLACEHOLDER: Final[str] = _PATTERNS["placeholder"]


def redact_private_names(text: str | None) -> str | None:
    """Strip Owner:/Applicant:/Landowner: field values and bare
    Mr/Mrs/Ms/Dr-prefixed names from `text`. `None`/empty input passes
    through unchanged."""
    if not text:
        return text

    def _line_sub(match: re.Match) -> str:
        label = match.group(0).split(":", 1)[0]
        return f"{label}: {PLACEHOLDER}"

    redacted = _LINE_RE.sub(_line_sub, text)
    redacted = _TITLE_RE.sub(PLACEHOLDER, redacted)
    return redacted


def contains_private_name_pattern(text: str | None) -> bool:
    """True if either shape is present in `text` — used to measure
    coverage (scripts/measure_private_name_patterns.py), not to redact."""
    if not text:
        return False
    return bool(_LINE_RE.search(text) or _TITLE_RE.search(text))
