"""
S9: right of reply — packet assembly (docs/INFORMATION_ARCHITECTURE.md §3,
docs/AGENT_DESIGN.md §3 Q4).

Scripted, no LLM: claims are already structured (`TestResult`,
`src/analysis/tests.py`), so building the packet a named person receives is
a filter-and-template operation, not a judgment call. What stays human, by
design, never automated here:

- **Sending.** Words addressed to a real person leave the building only on
  a human's authorization — this module only ever writes a packet to disk
  for a human to send.
- **Deciding how a response is weighed.** A response that *disputes* a
  claim re-enters as an S8-class fix item for Editor to weigh (amend,
  annotate, withdraw); this module only records what was said, verbatim,
  never edits or interprets it.

Scope: only `unit_of_analysis = individual` claims get a packet.
`individual_implicating` claims enter the deep product whole but the
per-claim "reduced form" reply treatment is out of scope until one exists
in the real battery (same deferral as Step 2's tier derivation) — see
`docs/AGENT_DESIGN.md` §6 Step 2's own logged deviation for why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from src.analysis.tests import TestResult, UNIT_INDIVIDUAL

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "reply_policy.json"

DECLINED_TEXT = "was offered the opportunity to respond and declined"
NO_RESPONSE_TEXT = "was offered the opportunity to respond and did not respond"


@dataclass
class ReplyPacket:
    person: str
    claims: list[TestResult]
    generated_at: str
    response_window_days: int


def load_response_window_days(path: Path = DEFAULT_POLICY_PATH) -> int:
    """Response window, in days — fixed per pack config (council pack: 14,
    the conventional journalistic floor for non-urgent findings). Config,
    not a magic number, per the redesign's hard rule — see
    docs/AGENT_DESIGN.md §3 Q4.
    """
    if not path.exists():
        raise FileNotFoundError(f"No reply policy config at {path}")
    data = json.loads(path.read_text())
    days = data.get("response_window_days")
    if not isinstance(days, int) or days <= 0:
        raise ValueError(f"response_window_days must be a positive integer, got {days!r}")
    return days


def assemble_reply_packets(
    claims: list[TestResult], response_window_days: int, generated_at: str
) -> list[ReplyPacket]:
    """One packet per named person, covering every `individual`-unit claim
    that names them and hasn't already been sent a reply (`reply is None`).
    A claim naming more than one person appears in each of their packets.
    """
    by_person: dict[str, list[TestResult]] = {}
    for c in claims:
        if c.unit_of_analysis != UNIT_INDIVIDUAL or c.reply is not None:
            continue
        for person in c.named_entities:
            by_person.setdefault(person, []).append(c)

    return [
        ReplyPacket(
            person=person,
            claims=person_claims,
            generated_at=generated_at,
            response_window_days=response_window_days,
        )
        for person, person_claims in sorted(by_person.items())
    ]


def render_packet_template(packet: ReplyPacket) -> str:
    """The fixed template: the claims, their evidence, the response window,
    how responses are published. A human copies this into the actual
    message sent — this function never sends anything.
    """
    lines = [
        f"# Right of reply — {packet.person}",
        "",
        f"Generated: {packet.generated_at}",
        f"Response window: {packet.response_window_days} days from the date this is sent.",
        "",
        "The following claims about you are being prepared for publication. "
        "You are invited to respond before publication. A response that "
        "disputes a claim will be weighed and may result in the claim being "
        "amended, annotated, or withdrawn. A response that comments will be "
        "attached to the claim verbatim and published alongside it. If you "
        "do not respond within the window, the claim will publish noting "
        f'"{NO_RESPONSE_TEXT}."',
        "",
        "## Claims",
        "",
    ]
    for c in packet.claims:
        lines += [
            f"### {c.title}",
            f"- Headline: {c.headline}",
            f"- Verdict: {c.verdict}",
            f"- n: {c.n}" + (f" (base rate: {c.base_rate})" if c.base_rate else ""),
            f"- Era: {c.era}" if c.era else "- Era: (not stated)",
            f"- Severity grade: {c.grade}",
            "",
        ]
    return "\n".join(lines)


def attach_reply(
    claim: TestResult, *, sent_at: str, response: str | None = None, declined: bool = False
) -> TestResult:
    """Record what happened after a packet was sent, on a copy of the claim
    (claims are otherwise immutable data, not mutated in place). `response`
    is stored verbatim — never edited or summarised by any role. A response
    that disputes the claim's substance is a separate, human/Editor
    decision about the claim's content, not something this function makes.
    """
    return replace(claim, reply={"sent_at": sent_at, "response": response, "declined": declined})


def non_response_text(claim: TestResult) -> str | None:
    """The standard formula for a claim's `reply` state, or None if a
    response was actually given (nothing to summarise) or no packet has
    been sent yet.
    """
    if claim.reply is None or claim.reply.get("response"):
        return None
    return DECLINED_TEXT if claim.reply.get("declined") else NO_RESPONSE_TEXT
