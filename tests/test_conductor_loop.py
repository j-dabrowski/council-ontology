"""
Unit tests for scripts/conductor_loop.py's run_conductor_loop():
  - a FAIL carrying a human-track flag escalates immediately (exit 1),
    with no Fixer dispatched, including when ordinary tracks are co-flagged
  - a FAIL with only ordinary tracks still dispatches Fixer as today
  - unknown tracks still raise

All subprocess-touching functions (run_draft/run_editor/run_fixer) and the
sidecar readers (latest_review_record/latest_fix_report) are monkeypatched
to plain in-memory stand-ins — no real `council`/`claude` subprocess, no
filesystem draft directory needs to exist.
"""
import pytest

import scripts.conductor_loop as cl


def test_human_track_fail_escalates_immediately_no_fixer_dispatched(monkeypatch, tmp_path, capsys):
    council = "cambridge"
    run_id = "draft_human_1"

    monkeypatch.setattr(cl, "DATA_DRAFT", tmp_path)
    monkeypatch.setattr(cl, "run_draft", lambda c: run_id)
    monkeypatch.setattr(cl, "run_editor", lambda c, r, p: None)

    fixer_calls = []
    monkeypatch.setattr(cl, "run_fixer", lambda t, c, r, p: fixer_calls.append(t))

    record = {
        "run_id": run_id, "council": council, "pass": 1, "status": "FAIL",
        "tracks": ["frontend", "human"],
        "flags": [
            {"severity": "BLOCKING", "tracks": ["frontend"], "criterion": "placement",
             "location": "power.json:hero", "summary": "ungated stat", "reasoning": ""},
            {"severity": "BLOCKING", "tracks": ["human"], "criterion": "balance",
             "location": "draft-level", "summary": "systemic framing imbalance",
             "reasoning": "observed across every panel; reviewer must decide framing policy"},
        ],
    }
    monkeypatch.setattr(cl, "latest_review_record", lambda d: record)

    exit_code = cl.run_conductor_loop(council, max_passes=3, dry_run=False)

    assert exit_code == 1
    assert fixer_calls == []
    out = capsys.readouterr().out
    assert "ESCALATING" in out
    assert "systemic framing imbalance" in out


def test_ordinary_track_fail_dispatches_fixer_as_today(monkeypatch, tmp_path):
    council = "cambridge"
    run_ids = iter(["draft_1", "draft_2"])

    monkeypatch.setattr(cl, "DATA_DRAFT", tmp_path)
    monkeypatch.setattr(cl, "run_draft", lambda c: next(run_ids))
    monkeypatch.setattr(cl, "run_editor", lambda c, r, p: None)

    fixer_calls = []
    monkeypatch.setattr(cl, "run_fixer", lambda t, c, r, p: fixer_calls.append((t, r)))

    records = {
        "draft_1": {
            "run_id": "draft_1", "council": council, "pass": 1, "status": "FAIL",
            "tracks": ["frontend"], "flags": [],
        },
        "draft_2": {
            "run_id": "draft_2", "council": council, "pass": 2, "status": "PASS",
            "tracks": [], "flags": [],
        },
    }
    monkeypatch.setattr(cl, "latest_review_record", lambda d: records[d.name])
    monkeypatch.setattr(
        cl, "latest_fix_report",
        lambda d, t: {"run_id": d.name, "track": t, "status": "DONE", "blocked_on": []},
    )

    exit_code = cl.run_conductor_loop(council, max_passes=3, dry_run=False)

    assert exit_code == 0
    assert fixer_calls == [("frontend", "draft_1")]


def test_unknown_track_raises(monkeypatch, tmp_path):
    council = "cambridge"

    monkeypatch.setattr(cl, "DATA_DRAFT", tmp_path)
    monkeypatch.setattr(cl, "run_draft", lambda c: "draft_1")
    monkeypatch.setattr(cl, "run_editor", lambda c, r, p: None)

    record = {
        "run_id": "draft_1", "council": council, "pass": 1, "status": "FAIL",
        "tracks": ["not-a-real-track"], "flags": [],
    }
    monkeypatch.setattr(cl, "latest_review_record", lambda d: record)

    with pytest.raises(RuntimeError, match="unknown track"):
        cl.run_conductor_loop(council, max_passes=3, dry_run=False)
