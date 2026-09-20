"""
The typed-findings schema and ledger (docs/uplift/03-critic-agents.md
"Findings"/"Loop mechanics"; docs/uplift/migration/03-critic-agents.md
Step 2). Depends on the claim object (`02-claim-layer.md` Step 1, done).

Three severities, not the current Editor's two (BLOCKING/ADVISORY per
`docs/review/editor/Editor_prompt.txt`) — `note` is new: an unresolved
`note`-severity finding is meant to publish as a visible limitations
section (Step 7, not built here) rather than blocking forever or being
silently dropped. This is the target's own named fix for "caveat mush":
critics always find something -> builder always hedges -> panels become
unreadable.

Persistence: a JSON sidecar per draft run, structured per-finding (`id`,
`state`, `rounds_seen`) rather than per-review-document the way today's
`defamation_review_<n>.json` is — queryable by `claim_id` and `state`, per
the target's own "Done when" for this step.

Explicitly NOT built here (see docs/uplift/migration/03-critic-agents.md's
own dependency notes): the 11 critic prompts themselves (agent-prompt
design + calibration work, a different kind of task than this module);
the regeneration-routing that decides whether a blocking finding sends a
claim back to the analyst or the builder (Step 6, needs the actual
critics running first to have real findings to route).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

SEVERITY_BLOCKING = "blocking"
SEVERITY_SHOULD_FIX = "should_fix"
SEVERITY_NOTE = "note"
_SEVERITIES = frozenset({SEVERITY_BLOCKING, SEVERITY_SHOULD_FIX, SEVERITY_NOTE})

STATE_OPEN = "open"
STATE_CLOSED = "closed"
STATE_WONTFIX = "wontfix"
_STATES = frozenset({STATE_OPEN, STATE_CLOSED, STATE_WONTFIX})


@dataclass(frozen=True)
class Finding:
    id: str                          # stable across rounds, keyed on content
    critic: str
    claim_id: str
    severity: str                    # blocking | should_fix | note
    statement: str
    proposed_remedy: str | None = None
    state: str = STATE_OPEN          # open | closed | wontfix
    wontfix_reason: str | None = None
    rounds_seen: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(_SEVERITIES)}, got {self.severity!r}")
        if self.state not in _STATES:
            raise ValueError(f"state must be one of {sorted(_STATES)}, got {self.state!r}")
        if self.state == STATE_WONTFIX and not self.wontfix_reason:
            raise ValueError("a wontfix finding requires wontfix_reason — the target spec's own rule")


def load_ledger(path: Path) -> list[Finding]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [Finding(**{**f, "rounds_seen": tuple(f.get("rounds_seen", ()))}) for f in data]


def save_ledger(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(f) for f in findings], indent=2) + "\n")


def record_round(findings: list[Finding], new: Finding, round_number: int) -> list[Finding]:
    """Add `new`'s round to an existing finding with the same `id` (the
    persistent-ledger side of regression protection — Step 4's own
    "Done when": a finding re-surfacing in a later round is the SAME
    finding, not a fresh one), or append it as a first-seen finding
    otherwise. Never mutates `findings` in place — returns the updated
    list, matching this module's other functions.

    Critic-capture note (G-07's own warning): this ledger is for humans
    and reporting. It must never be read back into a critic's own context
    before that critic re-judges a claim cold — that wiring belongs to
    whichever orchestrator calls critics, not to this module, and is
    exactly the property to test for once that orchestrator exists
    (docs/uplift/03-critic-agents.md Step 8).
    """
    existing_ids = {f.id: i for i, f in enumerate(findings)}
    if new.id in existing_ids:
        i = existing_ids[new.id]
        old = findings[i]
        updated = [*findings]
        updated[i] = Finding(
            id=old.id, critic=old.critic, claim_id=old.claim_id, severity=old.severity,
            statement=new.statement, proposed_remedy=new.proposed_remedy,
            state=new.state, wontfix_reason=new.wontfix_reason,
            rounds_seen=tuple(sorted(set(old.rounds_seen) | {round_number})),
        )
        return updated
    return [*findings, Finding(**{**asdict(new), "rounds_seen": (round_number,)})]


def blocking_open(findings: list[Finding], claim_id: str | None = None) -> list[Finding]:
    """What actually gates publication — per the target's own rule, only
    `blocking` severity does, and only while still `open`."""
    return [
        f for f in findings
        if f.severity == SEVERITY_BLOCKING and f.state == STATE_OPEN
        and (claim_id is None or f.claim_id == claim_id)
    ]


def unresolved_notes(findings: list[Finding], claim_id: str | None = None) -> list[Finding]:
    """Open `note`-severity findings — Step 7's own input: these publish
    as a visible limitations section rather than blocking or vanishing."""
    return [
        f for f in findings
        if f.severity == SEVERITY_NOTE and f.state == STATE_OPEN
        and (claim_id is None or f.claim_id == claim_id)
    ]


@dataclass(frozen=True)
class DroppedClaim:
    """Step 6's per-claim drop registry: a claim that hit the round cap
    with a blocking finding still open. Counted and published, per the
    target's own framing — "we tested 47 hypotheses, 12 reached the
    reporting threshold, 3 were dropped after review" is a credibility
    asset, not something to hide."""
    claim_id: str
    rounds_attempted: int
    open_blocking_findings: tuple[str, ...]  # finding ids, for traceability


def load_dropped(path: Path) -> list[DroppedClaim]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [DroppedClaim(**{**d, "open_blocking_findings": tuple(d.get("open_blocking_findings", ()))}) for d in data]


def save_dropped(dropped: list[DroppedClaim], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(d) for d in dropped], indent=2) + "\n")
