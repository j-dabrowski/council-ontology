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

import hashlib
import json
import re
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


def person_slug(person: str) -> str:
    """Filesystem-safe, collision-resistant slug for a person's name.

    Every packet is one real person's right-of-reply document, so a slug
    collision silently destroys one of them. Anything outside [a-z0-9] folds
    to a single dash, which alone would make "O'Connor, Pauline" and
    "O'Connor Pauline" collide — and that pair is precisely the split-identity
    shape this corpus already contains — so every slug carries a short digest
    of the exact name. A name that reduces to nothing keeps just the digest,
    so no packet is ever written as a hidden file or escapes `output_dir`
    via a `/` in the name.
    """
    digest = hashlib.sha256(person.encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", person.strip().lower()).strip("-")
    return f"{slug}-{digest}" if slug else f"person-{digest}"


def load_sent_ledger(path: Path) -> dict[str, list[str]]:
    """Which claims each person has already been approached about, keyed by
    person, valued by `test_id` list. Missing file = nobody approached yet.
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {str(k): list(v) for k, v in data.items()}


def update_sent_ledger(
    ledger: dict[str, list[str]], packets: list[ReplyPacket]
) -> dict[str, list[str]]:
    """Fold newly-generated packets into the ledger (pure — returns a copy)."""
    updated = {k: list(v) for k, v in ledger.items()}
    for packet in packets:
        seen = updated.setdefault(packet.person, [])
        for claim in packet.claims:
            if claim.test_id not in seen:
                seen.append(claim.test_id)
    return updated


def assemble_reply_packets(
    claims: list[TestResult],
    response_window_days: int,
    generated_at: str,
    sent_ledger: dict[str, list[str]] | None = None,
) -> list[ReplyPacket]:
    """One packet per named person, covering every `individual`-unit claim
    that names them and that they haven't already been approached about.

    Two independent guards, because they cover different lifetimes: `reply
    is not None` catches a claim already answered in this process, and
    `sent_ledger` — persisted across runs — catches one a previous run
    already generated a packet for. Without the ledger the battery is
    recomputed fresh each run with `reply` always None, so every run would
    re-emit every packet, and the concrete harm is approaching a real person
    twice with the same claim. A claim naming more than one person appears
    in each of their packets.
    """
    ledger = sent_ledger or {}
    by_person: dict[str, list[TestResult]] = {}
    for c in claims:
        if c.unit_of_analysis != UNIT_INDIVIDUAL or c.reply is not None:
            continue
        for person in c.named_entities:
            if c.test_id in ledger.get(person, []):
                continue
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
