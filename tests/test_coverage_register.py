"""
Unit tests for src/analysis/coverage_register.py — the S4 coverage register
verifier:
  - extract_shipped_test_ids() against a small synthetic source string
    (both the TestResult(test_id=...) and _nodata(...) call shapes)
  - verify_register() catching each drift direction (unknown-test-id,
    orphan-generator) and confirming clean input
  - the real register (docs/investigator/coverage_register.json) against
    the real battery (src/analysis/tests.py) — this is the actual
    always-on CI check: it fails the moment a battery test is added,
    renamed, or removed without updating the register

All hermetic: extract_shipped_test_ids parses source text (no DB, no
execution of the extraction pipeline itself).
"""
import ast

import pytest

from src.analysis.coverage_register import (
    extract_meeting_scope_test_ids,
    extract_shipped_test_ids,
    granularity_report,
    load_register,
    verify_register,
)

FIXTURE_SOURCE = '''
def _t_a(session, council_id, pc):
    return TestResult(
        test_id="dim.alpha",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


def _t_b(session, council_id, pc):
    if not ok:
        return _nodata("dim.beta", "title", "genre", "principle", "question")
    return TestResult(
        test_id="dim.beta",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


def _t_placeholder(session, council_id, pc):
    return _nodata("dim.gamma", "title", "genre", "principle", "question")


def _t_unregistered(session, council_id, pc):
    return TestResult(
        test_id="dim.not_in_battery",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


_BATTERY = [_t_a, _t_b, _t_placeholder]
'''


# ---------------------------------------------------------------------------
# extract_shipped_test_ids
# ---------------------------------------------------------------------------

def test_extract_finds_keyword_and_nodata_shapes(tmp_path):
    path = tmp_path / "fixture_tests.py"
    path.write_text(FIXTURE_SOURCE)
    ids = extract_shipped_test_ids(path)
    assert ids == {"dim.alpha", "dim.beta", "dim.gamma"}


def test_extract_ignores_functions_not_in_battery(tmp_path):
    path = tmp_path / "fixture_tests.py"
    path.write_text(FIXTURE_SOURCE)
    ids = extract_shipped_test_ids(path)
    assert "dim.not_in_battery" not in ids


def test_extract_empty_battery_gives_empty_set(tmp_path):
    path = tmp_path / "fixture_tests.py"
    path.write_text("_BATTERY = []\n")
    assert extract_shipped_test_ids(path) == set()


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
# battery in src/analysis/tests.py — fails if either drifts from the other
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


def test_real_battery_source_file_exists_at_expected_path():
    # extract_shipped_test_ids' default path is derived, not hardcoded twice
    from src.analysis.coverage_register import TESTS_SOURCE_PATH
    assert TESTS_SOURCE_PATH.exists()
    assert ast.parse(TESTS_SOURCE_PATH.read_text())  # parses without error


def test_extract_shipped_test_ids_raises_when_battery_shape_is_unrecognised(tmp_path):
    # A refactor like `_BATTERY = _CORE + _EXTRA` yields no names. Failing
    # loudly here beats returning an empty set, which would report every
    # register entry as an unknown test_id and send the maintainer to the
    # wrong file.
    src = tmp_path / "tests.py"
    src.write_text("_CORE = []\n_EXTRA = []\n_BATTERY = _CORE + _EXTRA\n")
    with pytest.raises(ValueError, match="_BATTERY"):
        extract_shipped_test_ids(src)


def test_extract_shipped_test_ids_handles_an_annotated_battery_assignment(tmp_path):
    src = tmp_path / "tests.py"
    src.write_text(
        "def _t_x():\n"
        "    return TestResult(test_id='fixture.x')\n"
        "_BATTERY: list = [_t_x]\n"
    )
    assert extract_shipped_test_ids(src) == {"fixture.x"}


# ---------------------------------------------------------------------------
# extract_meeting_scope_test_ids — the granularity axis's real-data input
# (digest design plan, Explorer v3.1)
# ---------------------------------------------------------------------------

_MEETING_FIXTURE_SOURCE = '''
def _t_a(session, council_id, pc, meeting_id=None):
    if meeting_id is not None:
        return _t_a_meeting(session, council_id, meeting_id)
    return TestResult(
        test_id="dim.alpha",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


def _t_a_meeting(session, council_id, meeting_id):
    return TestResult(
        test_id="dim.alpha",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


def _t_b(session, council_id, pc):
    return TestResult(
        test_id="dim.beta",
        title="t", genre="g", principle="p", question="q",
        valence="neutral", grade="g", headline="h", verdict="v",
    )


_BATTERY = [_t_a, _t_b]
_MEETING_BATTERY = [_t_a]
'''


def test_extract_meeting_scope_finds_only_meeting_battery_members(tmp_path):
    path = tmp_path / "fixture_tests.py"
    path.write_text(_MEETING_FIXTURE_SOURCE)
    assert extract_meeting_scope_test_ids(path) == {"dim.alpha"}
    # dim.beta ships in _BATTERY but has no _meeting sibling / isn't in
    # _MEETING_BATTERY — correctly absent from the meeting-scope set.
    assert extract_shipped_test_ids(path) == {"dim.alpha", "dim.beta"}


def test_extract_meeting_scope_empty_when_no_meeting_battery(tmp_path):
    path = tmp_path / "fixture_tests.py"
    path.write_text("_BATTERY = []\n_MEETING_BATTERY = []\n")
    assert extract_meeting_scope_test_ids(path) == set()


def test_real_meeting_battery_source_parses_and_is_a_subset_of_shipped_ids():
    meeting_ids = extract_meeting_scope_test_ids()
    shipped_ids = extract_shipped_test_ids()
    assert meeting_ids  # the real _MEETING_BATTERY is non-empty
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
