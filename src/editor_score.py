"""
The Editor scoring stage (docs/GENERATION_SCORING_SPLIT.md §2.3) — Layer 1
of `council editor-score <council> <run_id>`.

`Editor_prompt.txt` v0.5 no longer reads its own rubric or grades its own
review (docs/review/editor/EDITOR_PROTOCOL.md, "The two-layer scoring
stage"); this module is the deterministic half of what replaced that
self-score. It reads only the run directory plus `gate_report.json` and
`scorecard.json` — no LLM call, free, runs every time. `run_layer1()` is
the entry point; `council editor-score` (`src/cli.py`) calls it, embeds the
result into `docs/agent_prompts/editor_scorer.txt` as the `<layer1_json>`
placeholder, and hands that off to a fresh-context agent (Layer 2) which
never sees `Editor_prompt.txt` or this run's own generating session.

Checks (EDITOR_PROTOCOL.md's dimension table):
  - contract hygiene: sidecar/markdown stage-contract agreement, all
    required fields present, run_id matches the directory
  - flag routability: tracks non-empty and known, criterion in the
    enumerated slug vocabulary, location non-empty, human-track flags
    carry a non-empty reasoning
  - verdict integrity: FAIL iff >= 1 BLOCKING flag
  - the disclaimer string (dimension 7)
  - dimension 8 (false positives vs S7): a flag re-litigating a claim
    gate_report.json already shows S7 passed on that exact check
  - descriptive measurements (dimensions 1-6, as stats, not verdict inputs)

Any of the first five bullets failing sets `structural_ok=False` on the
returned Layer1Result -- these are hard problems with the review's own
machine contract, independent of whether the review's judgment was good.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from scripts.conductor_loop import VALID_TRACKS

# The nine criteria Editor_prompt.txt's output template instructs the
# review session to use, plus the two S7-boundary checks (name-free-schema,
# entity-resolution) it is instructed NOT to use but might anyway -- those
# two are recognised, not rejected as unknown vocabulary, because a flag
# carrying one of them on an S7-passed scorecard claim is exactly what
# dimension 8 exists to catch, not a routing error.
CRITERION_SLUGS = {
    "placement",
    "overclaim-language",
    "innocent-explanation",
    "singling-out-fairness",
    "blended-statistics",
    "caveat-integration",
    "balance",
    "small-n",
    "risk-item-drift",
    "name-free-schema",
    "entity-resolution",
}

# Maps an Editor criterion slug to the S7 invariant-gate check name it
# would be re-litigating (src/invariant_gate.py's Violation.check values).
_S7_CHECK_FOR_CRITERION = {
    "small-n": "min-n",
    "name-free-schema": "name-free-schema",
    "entity-resolution": "entity-resolution",
}

_STAGE_CONTRACT_RE = re.compile(
    r"status:\s*(?P<status>PASS|FAIL)\s*\n"
    r"pass:\s*(?P<pass>\d+)\s*\n"
    r"tracks:\s*\[(?P<tracks>[^\]]*)\]",
)


@dataclass
class Layer1Finding:
    check: str
    detail: str


@dataclass
class Layer1Result:
    run_id: str
    council: str
    reviewed_pass: int | None
    structural_ok: bool
    findings: list[Layer1Finding] = field(default_factory=list)
    false_positives: list[dict] = field(default_factory=list)
    measurements: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "council": self.council,
            "reviewed_pass": self.reviewed_pass,
            "structural_ok": self.structural_ok,
            "findings": [{"check": f.check, "detail": f.detail} for f in self.findings],
            "false_positives": self.false_positives,
            "measurements": self.measurements,
        }


def latest_review_files(draft_dir: Path) -> tuple[Path, Path]:
    """The highest-pass-numbered defamation_review_<n>.json/.md pair in
    draft_dir. Same directory-scoped selection logic as
    scripts/conductor_loop.py's latest_review_record and
    src/publish_gate.py's _latest_review_record — kept as an independent
    implementation here for the same reason those two are independent of
    each other: this module is a standalone entry point, not a library
    consumer of either.
    """
    json_candidates = list(draft_dir.glob("defamation_review_*.json"))
    if not json_candidates:
        raise RuntimeError(f"no defamation_review_<n>.json found in {draft_dir} — did Editor actually run?")

    def _pass_num(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[-1])
        except ValueError:
            return -1

    latest_json = max(json_candidates, key=_pass_num)
    n = latest_json.stem.rsplit("_", 1)[-1]
    latest_md = draft_dir / f"defamation_review_{n}.md"
    if not latest_md.exists():
        raise RuntimeError(f"{latest_json} has no matching {latest_md.name}")
    return latest_json, latest_md


def parse_stage_contract(md_text: str) -> dict | None:
    """Pull status/pass/tracks out of the markdown's stage-contract block.
    Returns None if no recognisable block is found (a structural problem
    the caller reports, not something this function raises on)."""
    m = _STAGE_CONTRACT_RE.search(md_text)
    if not m:
        return None
    tracks_raw = m.group("tracks").strip()
    tracks = [t.strip() for t in tracks_raw.split(",") if t.strip()]
    return {"status": m.group("status"), "pass": int(m.group("pass")), "tracks": tracks}


def _check_false_positives(claims: list[dict], flags: list[dict], draft_dir: Path) -> list[dict]:
    """Dimension 8: a flag whose criterion re-litigates an S7 check that
    `gate_report.json` already shows passed for that exact claim. Returns
    [] (not a hard failure) when gate_report.json doesn't exist -- older,
    pre-S7 drafts have nothing to cross-reference against.
    """
    gate_path = draft_dir / "gate_report.json"
    if not gate_path.exists():
        return []
    gate = json.loads(gate_path.read_text())
    violated = {(v["test_id"], v["check"]) for v in gate.get("violations", [])}

    claim_by_location = {c["location"]: c for c in claims if c.get("location")}

    false_positives = []
    for flag in flags:
        s7_check = _S7_CHECK_FOR_CRITERION.get(flag.get("criterion"))
        if s7_check is None:
            continue
        claim = claim_by_location.get(flag.get("location"))
        if claim is None or not claim.get("scorecard_test_id"):
            continue
        test_id = claim["scorecard_test_id"]
        if (test_id, s7_check) not in violated:
            false_positives.append({
                "location": flag.get("location"),
                "criterion": flag.get("criterion"),
                "scorecard_test_id": test_id,
                "summary": flag.get("summary"),
            })
    return false_positives


def _compute_measurements(claims: list[dict], flags: list[dict], disclaimer_present: bool) -> dict:
    """Descriptive stats only (EDITOR_PROTOCOL.md: "no longer verdict
    inputs") — what a calibration pass reads, not what gates PASS/FAIL."""
    blocking = [f for f in flags if f.get("severity") == "BLOCKING"]
    advisory = [f for f in flags if f.get("severity") == "ADVISORY"]
    return {
        "claims_reviewed": len(claims),
        "flags_total": len(flags),
        "flags_blocking": len(blocking),
        "flags_advisory": len(advisory),
        "small_n_flags": sum(1 for f in flags if f.get("criterion") == "small-n"),
        "disclaimer_present": disclaimer_present,
    }


def run_layer1(draft_dir: Path, run_id: str) -> Layer1Result:
    """The Layer 1 validator itself. `run_id` is the directory being
    scored, checked against the sidecar's own claim so a caller can't
    accidentally score a stale sidecar left over in the wrong directory.
    """
    json_path, md_path = latest_review_files(draft_dir)
    sidecar = json.loads(json_path.read_text())
    md_text = md_path.read_text()

    findings: list[Layer1Finding] = []

    required_fields = ("run_id", "council", "pass", "status", "tracks", "reviewed_at", "claims", "flags")
    missing = [f for f in required_fields if f not in sidecar]
    if missing:
        findings.append(Layer1Finding("missing-fields", f"{json_path.name} missing required field(s): {missing}"))

    if sidecar.get("run_id") != run_id:
        findings.append(Layer1Finding(
            "run-id-mismatch",
            f"{json_path.name} run_id {sidecar.get('run_id')!r} does not match the directory being scored {run_id!r}",
        ))

    contract = parse_stage_contract(md_text)
    if contract is None:
        findings.append(Layer1Finding("markdown-missing-stage-contract", f"no readable stage-contract block in {md_path.name}"))
    else:
        if contract["status"] != sidecar.get("status"):
            findings.append(Layer1Finding(
                "sidecar-markdown-mismatch",
                f"status: markdown says {contract['status']!r}, sidecar says {sidecar.get('status')!r}",
            ))
        if contract["pass"] != sidecar.get("pass"):
            findings.append(Layer1Finding(
                "sidecar-markdown-mismatch",
                f"pass: markdown says {contract['pass']!r}, sidecar says {sidecar.get('pass')!r}",
            ))
        if sorted(contract["tracks"]) != sorted(sidecar.get("tracks", [])):
            findings.append(Layer1Finding(
                "sidecar-markdown-mismatch",
                f"tracks: markdown says {contract['tracks']!r}, sidecar says {sidecar.get('tracks')!r}",
            ))

    claims = sidecar.get("claims", [])
    flags = sidecar.get("flags", [])

    blocking_count = 0
    for i, flag in enumerate(flags):
        tag = flag.get("summary", f"flag[{i}]")
        tracks = flag.get("tracks") or []
        unknown = set(tracks) - VALID_TRACKS
        if not tracks or unknown:
            findings.append(Layer1Finding("invalid-track", f"{tag!r} has tracks={tracks!r} — not a non-empty subset of {sorted(VALID_TRACKS)}"))
        criterion = flag.get("criterion")
        if not criterion or criterion not in CRITERION_SLUGS:
            findings.append(Layer1Finding("missing-criterion", f"{tag!r} has criterion={criterion!r}, not in the enumerated vocabulary"))
        if not flag.get("location"):
            findings.append(Layer1Finding("missing-location", f"{tag!r} has no location"))
        if "human" in tracks and not (flag.get("reasoning") or "").strip():
            findings.append(Layer1Finding("missing-human-reasoning", f"{tag!r} is tagged human but has no reasoning"))
        if flag.get("severity") == "BLOCKING":
            blocking_count += 1

    status = sidecar.get("status")
    if status == "FAIL" and blocking_count == 0:
        findings.append(Layer1Finding("verdict-integrity", "status is FAIL but zero BLOCKING flags are present"))
    if status == "PASS" and blocking_count > 0:
        findings.append(Layer1Finding("verdict-integrity", f"status is PASS but {blocking_count} BLOCKING flag(s) are present"))

    disclaimer_present = "not legal advice" in md_text.lower()
    if not disclaimer_present:
        findings.append(Layer1Finding("disclaimer-missing", f"{md_path.name} does not contain the required disclaimer language"))

    false_positives = _check_false_positives(claims, flags, draft_dir)
    if false_positives:
        findings.append(Layer1Finding(
            "false-positive-vs-s7",
            f"{len(false_positives)} flag(s) re-litigate a claim gate_report.json already shows S7 passed on that check",
        ))

    measurements = _compute_measurements(claims, flags, disclaimer_present)

    return Layer1Result(
        run_id=run_id,
        council=sidecar.get("council", ""),
        reviewed_pass=sidecar.get("pass"),
        structural_ok=not findings,
        findings=findings,
        false_positives=false_positives,
        measurements=measurements,
    )


def next_score_pass(draft_dir: Path) -> int:
    """Directory-scoped, same convention as Editor's own `<n>`: the next
    unused editor_score_<n>.json number in this run directory."""
    existing = list(draft_dir.glob("editor_score_*.json"))
    if not existing:
        return 1

    def _pass_num(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[-1])
        except ValueError:
            return 0

    return max(_pass_num(p) for p in existing) + 1
