"""
Unit tests for src/editor_score.py — the Editor scoring stage's Layer 1
(deterministic validator, docs/GENERATION_SCORING_SPLIT.md §2.3):
  - a clean PASS review
  - a FAIL with valid flags
  - a sidecar/markdown mismatch
  - an invalid track on a flag
  - a missing criterion on a flag
  - a FAIL with zero blocking flags (verdict-integrity failure)
  - a human-track flag with and without reasoning (valid / invalid)
  - the dimension-8 fixture (a flag re-litigating an S7-passed claim)

All plain dicts and a tmp_path standing in for a
data/draft/<council>/<run_id>/ directory — no real database, no CLI
invocation, no claude call.
"""
import json

import pytest

from src.editor_score import next_score_pass, run_layer1


def _markdown(status: str, pass_num: int, tracks: list[str]) -> str:
    tracks_str = ", ".join(tracks)
    return f"""# Defamation review — cambridge run_1 — 2026-08-24 — pass {pass_num}

**This is an editorial risk screen, not legal advice. A PASS here does not
clear legal risk and does not by itself authorize a live publish.**

## Claims reviewed: 1
## Flagged: 0

## Verdict

<!-- stage-contract block -->
status: {status}
pass: {pass_num}
tracks: [{tracks_str}]
next: whatever
"""


def _write_review(tmp_path, sidecar: dict, markdown: str | None = None, n: int = 1):
    draft_dir = tmp_path / "cambridge" / "run_1"
    draft_dir.mkdir(parents=True)
    (draft_dir / f"defamation_review_{n}.json").write_text(json.dumps(sidecar))
    if markdown is None:
        markdown = _markdown(sidecar["status"], sidecar["pass"], sidecar["tracks"])
    (draft_dir / f"defamation_review_{n}.md").write_text(markdown)
    return draft_dir


def _base_sidecar(**overrides) -> dict:
    fields = dict(
        run_id="run_1",
        council="cambridge",
        pass_=1,  # placeholder, replaced below
        status="PASS",
        tracks=[],
        reviewed_at="2026-08-24T00:00:00Z",
        claims=[],
        flags=[],
    )
    fields["pass"] = fields.pop("pass_")
    fields.update(overrides)
    return fields


# ---------------------------------------------------------------------------
# Clean PASS
# ---------------------------------------------------------------------------

def test_clean_pass_is_structurally_ok(tmp_path):
    sidecar = _base_sidecar(
        claims=[{"location": "scorecard.json:t1", "snapshot": "scorecard", "named_individual": False, "scorecard_test_id": "t1"}],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is True
    assert result.findings == []


# ---------------------------------------------------------------------------
# FAIL with valid flags
# ---------------------------------------------------------------------------

def test_fail_with_valid_flags_is_structurally_ok(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["frontend"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["frontend"], "criterion": "placement",
            "location": "power.json:hero", "summary": "ungated hero stat", "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is True
    assert result.measurements["flags_blocking"] == 1


# ---------------------------------------------------------------------------
# Sidecar/markdown mismatch
# ---------------------------------------------------------------------------

def test_sidecar_markdown_mismatch_is_structural_failure(tmp_path):
    sidecar = _base_sidecar(status="PASS", tracks=[])
    # Markdown disagrees: says FAIL with a track.
    markdown = _markdown("FAIL", 1, ["frontend"])
    draft_dir = _write_review(tmp_path, sidecar, markdown=markdown)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "sidecar-markdown-mismatch" for f in result.findings)


# ---------------------------------------------------------------------------
# Invalid track
# ---------------------------------------------------------------------------

def test_invalid_track_is_structural_failure(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["nonsense"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["nonsense"], "criterion": "placement",
            "location": "power.json:hero", "summary": "bad track", "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "invalid-track" for f in result.findings)


# ---------------------------------------------------------------------------
# Missing criterion
# ---------------------------------------------------------------------------

def test_missing_criterion_is_structural_failure(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["frontend"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["frontend"], "criterion": "",
            "location": "power.json:hero", "summary": "no criterion", "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "missing-criterion" for f in result.findings)


# ---------------------------------------------------------------------------
# Period-claim criteria (EDITOR_PROTOCOL.md dimension 9, added 2026-08-27) —
# jigsaw-identification / digest-fidelity must be accepted vocabulary, not
# rejected as unknown, the same way every other enumerated criterion is.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("criterion", ["jigsaw-identification", "digest-fidelity"])
def test_period_claim_criterion_is_valid_vocabulary(tmp_path, criterion):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["human"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["human"], "criterion": criterion,
            "location": "local/digest_summary.md", "summary": "period-claim risk",
            "reasoning": "identifies a committee member by elimination",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert not any(f.check == "missing-criterion" for f in result.findings)


# ---------------------------------------------------------------------------
# Verdict integrity: FAIL with zero blocking flags
# ---------------------------------------------------------------------------

def test_fail_with_zero_blocking_flags_is_verdict_integrity_failure(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["doc"],
        flags=[{
            "severity": "ADVISORY", "tracks": ["doc"], "criterion": "caveat-integration",
            "location": "power.json:note", "summary": "advisory only", "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "verdict-integrity" for f in result.findings)


def test_pass_with_a_blocking_flag_is_also_verdict_integrity_failure(tmp_path):
    sidecar = _base_sidecar(
        status="PASS",
        tracks=[],
        flags=[{
            "severity": "BLOCKING", "tracks": ["frontend"], "criterion": "placement",
            "location": "power.json:hero", "summary": "should not coexist with PASS", "reasoning": "",
        }],
    )
    # Markdown must agree with the (self-inconsistent) sidecar to isolate
    # this specific check from the sidecar/markdown mismatch check above.
    markdown = _markdown("PASS", 1, [])
    draft_dir = _write_review(tmp_path, sidecar, markdown=markdown)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "verdict-integrity" for f in result.findings)


# ---------------------------------------------------------------------------
# Human-track flag: with and without reasoning
# ---------------------------------------------------------------------------

def test_human_track_flag_with_reasoning_is_valid(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["human"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["human"], "criterion": "balance",
            "location": "draft-level", "summary": "systemic framing imbalance",
            "reasoning": "observed X across every panel; can't localise to one claim; reviewer must decide Y",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is True


def test_human_track_flag_without_reasoning_is_structural_failure(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["human"],
        flags=[{
            "severity": "BLOCKING", "tracks": ["human"], "criterion": "balance",
            "location": "draft-level", "summary": "systemic framing imbalance",
            "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "missing-human-reasoning" for f in result.findings)


# ---------------------------------------------------------------------------
# Dimension 8: false positive vs S7
# ---------------------------------------------------------------------------

def test_flag_relitigating_s7_passed_claim_is_a_false_positive(tmp_path):
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["pipeline"],
        claims=[{
            "location": "scorecard.json:battery.foo", "snapshot": "scorecard",
            "named_individual": False, "scorecard_test_id": "battery.foo",
        }],
        flags=[{
            "severity": "ADVISORY", "tracks": ["pipeline"], "criterion": "small-n",
            "location": "scorecard.json:battery.foo", "summary": "re-litigating small-n",
            "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    (draft_dir / "gate_report.json").write_text(json.dumps({
        "run_id": "run_1", "council": "cambridge", "passed": True, "violations": [],
    }))
    (draft_dir / "scorecard.json").write_text(json.dumps({
        "data": {"tests": [{"test_id": "battery.foo", "n": 50}]},
    }))

    result = run_layer1(draft_dir, "run_1")
    assert result.structural_ok is False
    assert any(f.check == "false-positive-vs-s7" for f in result.findings)
    assert len(result.false_positives) == 1
    assert result.false_positives[0]["scorecard_test_id"] == "battery.foo"


def test_flag_matching_an_actual_s7_violation_is_not_a_false_positive(tmp_path):
    """The same shape as above, but gate_report.json shows this exact
    check actually failed for this test_id — Editor re-flagging a real S7
    violation is not re-litigation, it's agreement, and must not be
    counted as a false positive."""
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["pipeline"],
        claims=[{
            "location": "scorecard.json:battery.foo", "snapshot": "scorecard",
            "named_individual": True, "scorecard_test_id": "battery.foo",
        }],
        flags=[{
            "severity": "BLOCKING", "tracks": ["pipeline"], "criterion": "small-n",
            "location": "scorecard.json:battery.foo", "summary": "agrees with S7",
            "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    (draft_dir / "gate_report.json").write_text(json.dumps({
        "run_id": "run_1", "council": "cambridge", "passed": False,
        "violations": [{"test_id": "battery.foo", "check": "min-n", "detail": "n=1"}],
    }))

    result = run_layer1(draft_dir, "run_1")
    assert result.false_positives == []


def test_false_positive_check_skipped_without_gate_report(tmp_path):
    """Pre-S7 drafts have no gate_report.json — nothing to cross-reference,
    not a failure."""
    sidecar = _base_sidecar(
        status="FAIL",
        tracks=["pipeline"],
        claims=[{
            "location": "scorecard.json:battery.foo", "snapshot": "scorecard",
            "named_individual": False, "scorecard_test_id": "battery.foo",
        }],
        flags=[{
            "severity": "BLOCKING", "tracks": ["pipeline"], "criterion": "small-n",
            "location": "scorecard.json:battery.foo", "summary": "no gate report to check against",
            "reasoning": "",
        }],
    )
    draft_dir = _write_review(tmp_path, sidecar)
    result = run_layer1(draft_dir, "run_1")
    assert result.false_positives == []
    assert not any(f.check == "false-positive-vs-s7" for f in result.findings)


# ---------------------------------------------------------------------------
# next_score_pass
# ---------------------------------------------------------------------------

def test_next_score_pass_starts_at_one(tmp_path):
    draft_dir = tmp_path / "cambridge" / "run_1"
    draft_dir.mkdir(parents=True)
    assert next_score_pass(draft_dir) == 1


def test_next_score_pass_increments_past_existing(tmp_path):
    draft_dir = tmp_path / "cambridge" / "run_1"
    draft_dir.mkdir(parents=True)
    (draft_dir / "editor_score_1.json").write_text("{}")
    (draft_dir / "editor_score_2.json").write_text("{}")
    assert next_score_pass(draft_dir) == 3


# ---------------------------------------------------------------------------
# Missing sidecar altogether
# ---------------------------------------------------------------------------

def test_run_layer1_raises_when_no_review_exists(tmp_path):
    draft_dir = tmp_path / "cambridge" / "run_1"
    draft_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no defamation_review"):
        run_layer1(draft_dir, "run_1")
