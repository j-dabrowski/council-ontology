"""
Critic routing (docs/uplift/03-critic-agents.md "Routing";
docs/uplift/migration/03-critic-agents.md Step 5): which of the 11 critics
should run on a given claim, so cheap/always-relevant checks always run
and expensive/specialist ones only run when triggered — not all eleven on
every claim.

Returns critic IDs as plain strings regardless of whether that critic has
a real implementation yet (today, only C-06 does — `cross_panel.py`, and
it's routed separately below since it's a whole-build pass, not a
per-claim one). This is deliberate: the routing LOGIC is fully specified
by the target and doesn't need to wait on the prompts themselves — a
caller can route today and simply no-op on any critic ID it can't yet
dispatch to.

One trigger is not mechanically derivable from the Claim object alone:
"metric is behavioural / could be gamed" has no corresponding field
anywhere in `src/analysis/claims.py`. Exposed as an optional
`gameable_test_ids` parameter (a caller-supplied allow-list) rather than
invented as a heuristic — an honest gap, not a fabricated signal.
"""

from __future__ import annotations

from collections.abc import Collection

from src.analysis.claim_linter import DEFAULT_EXTRACTION_PRECISION_THRESHOLD
from src.analysis.claims import GRADE_CONCERN, GRADE_CRITICAL, Claim

C01_AUDITOR = "C-01"
C02_STATISTICIAN = "C-02"
C03_JURISDICTION = "C-03"
C04_DEFENCE_COUNSEL = "C-04"
C05_EXTRACTION_SCEPTIC = "C-05"
C06_CROSS_PANEL = "C-06"          # whole-build, not per-claim — see route_cross_panel()
C07_SUBJECT_FAIRNESS = "C-07"
C08_VISUAL_QA = "C-08"
C09_GOODHART = "C-09"
C10_LAYMAN = "C-10"
C11_EDITOR_IN_CHIEF = "C-11"

_ALWAYS = (C08_VISUAL_QA, C10_LAYMAN, C11_EDITOR_IN_CHIEF)


def route_claim(
    claim: Claim, *,
    gameable_test_ids: Collection[str] = (),
    extraction_precision_threshold: float = DEFAULT_EXTRACTION_PRECISION_THRESHOLD,
) -> tuple[str, ...]:
    """The per-claim routing decision — everything in `docs/uplift/
    03-critic-agents.md`'s trigger table except C-06, which runs once per
    build over every claim simultaneously (`route_cross_panel()` below),
    not per claim."""
    critics: list[str] = list(_ALWAYS)

    if claim.grade in (GRADE_CRITICAL, GRADE_CONCERN):
        critics += [C02_STATISTICIAN, C04_DEFENCE_COUNSEL]

    if claim.names_individuals:
        critics += [C07_SUBJECT_FAIRNESS, C01_AUDITOR]

    if claim.framework_refs:
        critics.append(C03_JURISDICTION)

    if any(f.precision < extraction_precision_threshold for f in claim.extraction_error.fields):
        critics.append(C05_EXTRACTION_SCEPTIC)

    if claim.id in gameable_test_ids:
        critics.append(C09_GOODHART)

    # Stable order, no duplicates - a claim matching several triggers
    # still gets each critic exactly once.
    seen: set[str] = set()
    ordered = []
    for c in critics:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return tuple(ordered)


def route_cross_panel() -> tuple[str, ...]:
    """C-06 always runs, exactly once, over the whole build — not routed
    by any per-claim property. A separate function rather than a claim
    argument, so a caller can't accidentally invoke it per-claim."""
    return (C06_CROSS_PANEL,)
