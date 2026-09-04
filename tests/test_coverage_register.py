"""
Unit tests for src/analysis/coverage_register.py — the S4 coverage register
verifier:
  - extract_shipped_test_ids() / extract_meeting_scope_test_ids() against a
    small synthetic registry fixture (JSON, the same shape as
    config/test_registry.json)
  - verify_register() catching each drift direction (unknown-test-id,
    orphan-generator) and confirming clean input
  - the real register (docs/investigator/coverage_register.json) against
    the real battery (config/test_registry.json) — this is the actual
    always-on CI check: it fails the moment a battery test is added,
    renamed, or removed without updating the register

All hermetic: extract_shipped_test_ids reads a JSON file (no DB, no
execution of the extraction pipeline itself).
"""
import json

import pytest

from src.analysis.coverage_register import (
    extract_meeting_scope_test_ids,
    extract_shipped_test_ids,
    granularity_report,
    load_register,
    verify_register,
)


def _write_registry(tmp_path, rows):
    path = tmp_path / "fixture_registry.json"
    path.write_text(json.dumps(rows))
    return path


def _row(id_, meeting_scope=False):
    """A minimal registry row — only the two fields extract_* reads."""
    return {"id": id_, "meeting_scope": meeting_scope}


# ---------------------------------------------------------------------------
# extract_shipped_test_ids
# ---------------------------------------------------------------------------

def test_extract_shipped_test_ids_reads_every_row(tmp_path):
    path = _write_registry(tmp_path, [_row("dim.alpha"), _row("dim.beta"), _row("dim.gamma")])
    assert extract_shipped_test_ids(path) == {"dim.alpha", "dim.beta", "dim.gamma"}


def test_extract_shipped_test_ids_empty_registry_gives_empty_set(tmp_path):
    path = _write_registry(tmp_path, [])
    assert extract_shipped_test_ids(path) == set()


def test_extract_shipped_test_ids_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_shipped_test_ids(tmp_path / "does_not_exist.json")


def test_extract_shipped_test_ids_raises_when_not_a_list(tmp_path):
    path = tmp_path / "fixture_registry.json"
    path.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="JSON array"):
        extract_shipped_test_ids(path)


# ---------------------------------------------------------------------------
# extract_meeting_scope_test_ids
# ---------------------------------------------------------------------------

def test_extract_meeting_scope_finds_only_flagged_rows(tmp_path):
    path = _write_registry(tmp_path, [
        _row("dim.alpha", meeting_scope=True),
        _row("dim.beta", meeting_scope=False),
    ])
    assert extract_meeting_scope_test_ids(path) == {"dim.alpha"}
    # dim.beta ships but isn't meeting-scoped — correctly absent.
    assert extract_shipped_test_ids(path) == {"dim.alpha", "dim.beta"}


def test_extract_meeting_scope_empty_when_no_row_is_flagged(tmp_path):
    path = _write_registry(tmp_path, [_row("dim.alpha"), _row("dim.beta")])
    assert extract_meeting_scope_test_ids(path) == set()


# ---------------------------------------------------------------------------
# verify_register
# ---------------------------------------------------------------------------

def _register(dimensions):
    return {"dimensions": dimensions}


def test_verify_clean_when_register_matches_shipped_ids():
    register = _register([
        {"id": 1, "name": "Dim 1", "tests": ["a.one", "a.two"]},
    ])
    assert verify_register(register, {"a.one", "a.two"}) == []


def test_verify_flags_unknown_test_id_in_register():
    register = _register([
        {"id": 1, "name": "Dim 1", "tests": ["a.one", "a.renamed"]},
    ])
    problems = verify_register(register, {"a.one"})
    assert len(problems) == 1
    assert problems[0].kind == "unknown-test-id"
    assert problems[0].dimension_id == 1


def test_verify_flags_orphan_shipped_test_id():
    register = _register([
        {"id": 1, "name": "Dim 1", "tests": ["a.one"]},
    ])
    problems = verify_register(register, {"a.one", "a.new_and_unclaimed"})
    assert len(problems) == 1
    assert problems[0].kind == "orphan-generator"
    assert problems[0].dimension_id is None
    assert "a.new_and_unclaimed" in problems[0].detail


def test_verify_catches_both_directions_at_once():
    register = _register([
        {"id": 1, "name": "Dim 1", "tests": ["a.stale"]},
    ])
    problems = verify_register(register, {"a.new"})
    kinds = {p.kind for p in problems}
    assert kinds == {"unknown-test-id", "orphan-generator"}


def test_verify_empty_register_flags_every_shipped_id_as_orphan():
    problems = verify_register(_register([]), {"a.one", "a.two"})
    assert len(problems) == 2
    assert all(p.kind == "orphan-generator" for p in problems)


# ---------------------------------------------------------------------------
# the real thing: docs/investigator/coverage_register.json vs. the real
# battery in config/test_registry.json — fails if either drifts from the other
# ---------------------------------------------------------------------------

def test_real_register_matches_real_battery():
    register = load_register()
    shipped_ids = extract_shipped_test_ids()
    problems = verify_register(register, shipped_ids)
    assert problems == [], "\n".join(p.detail for p in problems)


def test_real_register_is_well_formed():
    register = load_register()
    seen_ids = set()
    for dim in register["dimensions"]:
        assert isinstance(dim["id"], int)
        assert dim["id"] not in seen_ids, f"duplicate dimension id {dim['id']}"
        seen_ids.add(dim["id"])
        assert dim["verdict"] in ("DENSE", "MODERATE", "THIN", "EMPTY")
        assert isinstance(dim["data_blocked"], bool)
        assert isinstance(dim["out_of_scope"], bool)
        assert isinstance(dim["tests"], list)


def test_real_test_registry_file_exists_at_expected_path():
    # extract_shipped_test_ids' default path is derived, not hardcoded twice
    from src.analysis.coverage_register import DEFAULT_TEST_REGISTRY_PATH
    assert DEFAULT_TEST_REGISTRY_PATH.exists()
    assert json.loads(DEFAULT_TEST_REGISTRY_PATH.read_text())  # parses without error


def test_real_meeting_battery_source_parses_and_is_a_subset_of_shipped_ids():
    meeting_ids = extract_meeting_scope_test_ids()
    shipped_ids = extract_shipped_test_ids()
    assert meeting_ids  # the real registry has at least one meeting-scoped row
    assert meeting_ids <= shipped_ids


# ---------------------------------------------------------------------------
# granularity_report
# ---------------------------------------------------------------------------

def test_granularity_report_computes_verdict_thresholds():
    register = _register([
        {"id": 1, "name": "Empty dim", "verdict": "DENSE", "tests": ["a.one", "a.two"]},
        {"id": 2, "name": "Thin dim", "verdict": "DENSE", "tests": ["b.one", "b.two"]},
        {"id": 3, "name": "Moderate dim", "verdict": "DENSE", "tests": ["c.one", "c.two", "c.three"]},
        {"id": 4, "name": "Dense dim", "verdict": "DENSE", "tests": ["d.one", "d.two", "d.three", "d.four"]},
    ])
    meeting_ids = {"b.one", "c.one", "c.two", "d.one", "d.two", "d.three", "d.four"}
    report = {row.dimension_id: row for row in granularity_report(register, meeting_ids)}
    assert report[1].meeting_verdict == "EMPTY"
    assert report[2].meeting_verdict == "THIN"
    assert report[3].meeting_verdict == "MODERATE"
    assert report[4].meeting_verdict == "DENSE"


def test_granularity_report_preserves_corpus_verdict_unchanged():
    register = _register([
        {"id": 1, "name": "Dim", "verdict": "MODERATE", "tests": []},
    ])
    report = granularity_report(register, set())
    assert report[0].corpus_verdict == "MODERATE"


def test_granularity_report_excludes_data_blocked_and_out_of_scope_rows():
    register = _register([
        {"id": 1, "name": "Blocked", "verdict": "EMPTY", "tests": [], "data_blocked": True},
        {"id": 2, "name": "Out of scope", "verdict": "EMPTY", "tests": [], "out_of_scope": True},
        {"id": 3, "name": "Normal", "verdict": "EMPTY", "tests": []},
    ])
    report = granularity_report(register, set())
    assert {row.dimension_id for row in report} == {3}


def test_granularity_report_meeting_tests_is_the_intersection():
    register = _register([
        {"id": 1, "name": "Dim", "verdict": "DENSE", "tests": ["a.one", "a.two", "a.three"]},
    ])
    report = granularity_report(register, {"a.two", "a.not_in_dimension"})
    assert report[0].meeting_tests == ["a.two"]


def test_real_register_granularity_report_runs_clean():
    # The real register/battery — dimension 1 (Conflict-of-interest) is the
    # design doc's own motivating example: DENSE at corpus scope, THIN at
    # meeting scope (only conflict.recusal_management ships a _meeting sibling).
    register = load_register()
    meeting_ids = extract_meeting_scope_test_ids()
    report = {row.dimension_id: row for row in granularity_report(register, meeting_ids)}
    assert report[1].corpus_verdict == "DENSE"
    assert report[1].meeting_verdict == "THIN"
    assert report[1].meeting_tests == ["conflict.recusal_management"]
