"""
Tests for src/analysis/findings.py (docs/uplift/03-critic-agents.md Step
2): the typed-findings ledger and dropped-claims registry.
"""
import pytest

from src.analysis.findings import (
    SEVERITY_BLOCKING,
    SEVERITY_NOTE,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_WONTFIX,
    DroppedClaim,
    Finding,
    blocking_open,
    load_dropped,
    load_ledger,
    record_round,
    save_dropped,
    save_ledger,
    unresolved_notes,
)


def _finding(id="f1", severity=SEVERITY_BLOCKING, state=STATE_OPEN, claim_id="c1", **overrides):
    defaults = dict(id=id, critic="C-02", claim_id=claim_id, severity=severity,
                     statement="something is wrong", state=state)
    defaults.update(overrides)
    return Finding(**defaults)


def test_finding_rejects_invalid_severity():
    with pytest.raises(ValueError, match="severity must be one of"):
        _finding(severity="urgent")


def test_finding_rejects_invalid_state():
    with pytest.raises(ValueError, match="state must be one of"):
        _finding(state="pending")


def test_finding_wontfix_requires_reason():
    with pytest.raises(ValueError, match="wontfix finding requires"):
        _finding(state=STATE_WONTFIX)


def test_finding_wontfix_with_reason_is_valid():
    f = _finding(state=STATE_WONTFIX, wontfix_reason="already covered by L-06")
    assert f.state == STATE_WONTFIX


def test_save_and_load_ledger_round_trip(tmp_path):
    path = tmp_path / "ledger.json"
    findings = [_finding("f1"), _finding("f2", severity=SEVERITY_NOTE)]
    save_ledger(findings, path)
    assert load_ledger(path) == findings


def test_load_ledger_missing_file_returns_empty(tmp_path):
    assert load_ledger(tmp_path / "missing.json") == []


def test_record_round_appends_new_finding():
    findings = record_round([], _finding("f1"), round_number=1)
    assert len(findings) == 1
    assert findings[0].rounds_seen == (1,)


def test_record_round_same_id_merges_rounds_not_duplicates():
    findings = record_round([], _finding("f1"), round_number=1)
    findings = record_round(findings, _finding("f1"), round_number=2)
    assert len(findings) == 1
    assert findings[0].rounds_seen == (1, 2)


def test_record_round_preserves_original_critic_and_severity():
    findings = record_round([], _finding("f1", critic="C-02", severity=SEVERITY_BLOCKING), round_number=1)
    # A later round's re-statement can update the statement/state but not
    # silently change who raised it or how severe it originally was.
    updated_statement = Finding(
        id="f1", critic="C-09-imposter", claim_id="c1", severity=SEVERITY_NOTE,
        statement="revised statement", state=STATE_CLOSED,
    )
    findings = record_round(findings, updated_statement, round_number=2)
    assert findings[0].critic == "C-02"
    assert findings[0].severity == SEVERITY_BLOCKING
    assert findings[0].statement == "revised statement"
    assert findings[0].state == STATE_CLOSED


def test_blocking_open_filters_correctly():
    findings = [
        _finding("f1", severity=SEVERITY_BLOCKING, state=STATE_OPEN),
        _finding("f2", severity=SEVERITY_BLOCKING, state=STATE_CLOSED),
        _finding("f3", severity=SEVERITY_NOTE, state=STATE_OPEN),
    ]
    assert [f.id for f in blocking_open(findings)] == ["f1"]


def test_blocking_open_filters_by_claim_id():
    findings = [
        _finding("f1", claim_id="a", severity=SEVERITY_BLOCKING),
        _finding("f2", claim_id="b", severity=SEVERITY_BLOCKING),
    ]
    assert [f.id for f in blocking_open(findings, claim_id="a")] == ["f1"]


def test_unresolved_notes_filters_correctly():
    findings = [
        _finding("f1", severity=SEVERITY_NOTE, state=STATE_OPEN),
        _finding("f2", severity=SEVERITY_NOTE, state=STATE_CLOSED),
        _finding("f3", severity=SEVERITY_BLOCKING, state=STATE_OPEN),
    ]
    assert [f.id for f in unresolved_notes(findings)] == ["f1"]


def test_dropped_registry_round_trip(tmp_path):
    path = tmp_path / "dropped.json"
    dropped = [DroppedClaim(claim_id="c1", rounds_attempted=3, open_blocking_findings=("f1", "f2"))]
    save_dropped(dropped, path)
    assert load_dropped(path) == dropped


def test_dropped_registry_missing_file_returns_empty(tmp_path):
    assert load_dropped(tmp_path / "missing.json") == []
