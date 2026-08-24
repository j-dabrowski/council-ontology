"""
Unit tests for scripts/run_state.py: round-trip read/write, and the CLI
subcommands the workflow YAML actually shells out to — `next-segment`
(fresh always 1; resume = prior + 1, or a clear error with no prior state)
and `should-resume` (prints the workflow name and exits 0 only when
status=escalated; exits 1 on a missing file or status=completed).
"""
import pytest

import scripts.run_state as rs


def test_read_missing_file_returns_none(tmp_path):
    assert rs.read(tmp_path / "run_state.json") is None


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "run_state.json"
    state = rs.RunState(
        run_id="run-1", workflow="maintenance", council="cambridge",
        segment=2, mode="resume", status="escalated",
        escalation_reason="conductor_cap_hit",
        conductor_loop={"pass_count": 3, "exit_code": 1},
        publish_requested=True,
    )
    rs.write(state, path)

    loaded = rs.read(path)
    assert loaded == state


@pytest.fixture
def run_state_path(tmp_path, monkeypatch):
    path = tmp_path / "run_state.json"
    monkeypatch.setattr(rs, "RUN_STATE_PATH", path)
    return path


def run_cli(monkeypatch, capsys, *args):
    monkeypatch.setattr("sys.argv", ["run_state.py", *args])
    try:
        rs.main()
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr()


def test_cli_next_segment_fresh_is_always_one_even_with_prior_state(run_state_path, monkeypatch, capsys):
    rs.write(rs.RunState(
        run_id="run-1", workflow="maintenance", council="cambridge",
        segment=5, mode="fresh", status="escalated",
    ), run_state_path)

    code, out = run_cli(monkeypatch, capsys, "next-segment", "--mode", "fresh")
    assert code == 0
    assert out.out.strip() == "1"


def test_cli_next_segment_resume_is_prior_plus_one(run_state_path, monkeypatch, capsys):
    rs.write(rs.RunState(
        run_id="run-1", workflow="maintenance", council="cambridge",
        segment=2, mode="fresh", status="escalated",
    ), run_state_path)

    code, out = run_cli(monkeypatch, capsys, "next-segment", "--mode", "resume")
    assert code == 0
    assert out.out.strip() == "3"


def test_cli_next_segment_resume_with_no_prior_state_errors(run_state_path, monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, "next-segment", "--mode", "resume")
    assert code == 1
    assert "nothing to resume" in out.err


def test_cli_should_resume_true_when_escalated(run_state_path, monkeypatch, capsys):
    rs.write(rs.RunState(
        run_id="run-1", workflow="discovery", council="cambridge",
        segment=1, mode="fresh", status="escalated",
    ), run_state_path)

    code, out = run_cli(monkeypatch, capsys, "should-resume")
    assert code == 0
    assert out.out.strip() == "discovery"


@pytest.mark.parametrize("status", ["completed"])
def test_cli_should_resume_false_when_not_escalated(run_state_path, monkeypatch, capsys, status):
    rs.write(rs.RunState(
        run_id="run-1", workflow="maintenance", council="cambridge",
        segment=1, mode="fresh", status=status,
    ), run_state_path)

    code, _ = run_cli(monkeypatch, capsys, "should-resume")
    assert code == 1


def test_cli_should_resume_false_when_no_file(run_state_path, monkeypatch, capsys):
    code, _ = run_cli(monkeypatch, capsys, "should-resume")
    assert code == 1


def test_cli_write_then_read_round_trips(run_state_path, monkeypatch, capsys):
    code, _ = run_cli(
        monkeypatch, capsys, "write",
        "--run-id", "run-2", "--workflow", "discovery", "--council", "cambridge",
        "--segment", "1", "--mode", "fresh", "--status", "completed",
    )
    assert code == 0

    code, out = run_cli(monkeypatch, capsys, "read")
    assert code == 0
    assert '"run_id": "run-2"' in out.out
    assert '"status": "completed"' in out.out
