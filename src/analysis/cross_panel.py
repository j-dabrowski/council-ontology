"""
C-06, the cross-panel critic (docs/uplift/03-critic-agents.md) — mechanized
where the target's own division-of-labour rule says it should be: "Do not
build critics that duplicate linter rules. If a critic finding recurs and
is mechanisable, promote it to a linter rule." Every one of C-06's listed
checks ("denominator reconciliation, entity-naming consistency,
duplicated individuals...") is exactly this — the target calls C-06
"structurally the only critic that can catch" D-04/D-05/D-07/D-20 because
it runs once per build over every claim simultaneously, not because its
checks need judgment an LLM has to supply. This module is that whole-
build pass, built as pure functions over a batch of claims, not an agent
prompt.

Two checks are mechanized here:
- CP-01 (denominator reconciliation): wraps `claim_linter.py`'s existing
  `check_l06_shared_denominator` as typed Findings, rather than
  reimplementing it — the same rule, the same reasoning, just batch-scoped
  the way C-06 needs it and the single-claim linter (Step 5) never was.
- CP-02 (entity-naming consistency, the narrow, safe case): flags when the
  SAME real person is named with two RAW strings that normalise (case/
  whitespace) to the same value across different claims — genuinely
  mechanisable with zero false positives. Catching two genuinely DIFFERENT
  spellings of one person (D-07's actual shape — "Carr" as two
  unresolved entities) needs real entity-resolution data (a canonical
  silver-table id, per L-17's own stated gap) this module doesn't have
  access to generically; not attempted here, not silently claimed either.

Not mechanized, an honest gap for whichever critic-prompt pass eventually
covers it: grade-scale drift, contradictory headlines across panels
(needs actual language understanding, not a string rule), and confound
handled in one panel but not another (needs judgment about what counts as
"the same confound" across differently-worded claims).
"""

from __future__ import annotations

from src.analysis.claim_linter import LintStatus, check_l06_shared_denominator
from src.analysis.claims import Claim
from src.analysis.findings import SEVERITY_SHOULD_FIX, Finding


def _cp01_denominator_reconciliation(claims: list[Claim]) -> list[Finding]:
    results = check_l06_shared_denominator(claims)
    findings = []
    for claim_id, result in results.items():
        if result.status == LintStatus.FAIL:
            findings.append(Finding(
                id=f"CP-01:{claim_id}",
                critic="C-06",
                claim_id=claim_id,
                severity=SEVERITY_SHOULD_FIX,
                statement=result.message,
                proposed_remedy="reconcile the population.definition or its denominator.n so claims "
                                "describing the same population agree",
            ))
    return findings


def _normalise_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _cp02_entity_naming_consistency(claims: list[Claim]) -> list[Finding]:
    """Group every named individual's RAW name string by its normalised
    form, across all claims. A normalised form backed by more than one
    distinct raw string is the same person named inconsistently (a real,
    if narrow, instance of D-05/D-07's shape)."""
    raw_by_normalised: dict[str, set[str]] = {}
    claims_by_raw_name: dict[str, list[str]] = {}
    for claim in claims:
        for individual in claim.individuals:
            norm = _normalise_name(individual.name)
            raw_by_normalised.setdefault(norm, set()).add(individual.name)
            claims_by_raw_name.setdefault(individual.name, []).append(claim.id)

    findings = []
    for norm, raw_names in raw_by_normalised.items():
        if len(raw_names) <= 1:
            continue
        involved_claims = sorted({c for raw in raw_names for c in claims_by_raw_name[raw]})
        findings.append(Finding(
            id=f"CP-02:{norm}",
            critic="C-06",
            claim_id=involved_claims[0],  # a batch-level finding; see statement for the full set
            severity=SEVERITY_SHOULD_FIX,
            statement=f"the same person appears as {sorted(raw_names)!r} across claims {involved_claims} "
                      "— inconsistent spelling/whitespace, not necessarily two different people",
            proposed_remedy="normalise to one canonical spelling at the point each claim is generated",
        ))
    return findings


def run_cross_panel(claims: list[Claim]) -> list[Finding]:
    """The whole-build pass itself: every mechanized C-06 check, run once
    over the full batch of claims from a single `council draft` run.
    Not wired into any live path — additive, same as the rest of this
    migration."""
    return _cp01_denominator_reconciliation(claims) + _cp02_entity_naming_consistency(claims)
