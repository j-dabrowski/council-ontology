"""
Tests for src/council_eras.py (docs/uplift/migration/04-jurisdiction.md
Step 3): multiple named era windows per council, with era_window_for()'s
default "inquiry" window_name kept backward-compatible for its one real
caller (queries.py's _council_era_window()).
"""
import json

import pytest

from src.council_eras import EraWindow, era_window_for, fiscal_year_start_month, load_council_eras


@pytest.fixture
def eras_path(tmp_path):
    path = tmp_path / "council_eras.json"
    path.write_text(json.dumps({
        "cambridge": {
            "inquiry": {"label": "Authorised Inquiry", "from": 2018, "to": 2021},
            "model_code_2021": {"label": "Model Code of Conduct 2021 (WA)", "from": 2021, "to": None},
        },
        "perth": {
            "model_code_2021": {"label": "Model Code of Conduct 2021 (WA)", "from": 2021, "to": None},
        },
    }))
    return path


def test_default_window_name_is_inquiry(eras_path):
    w = era_window_for("Cambridge", path=eras_path)
    assert w == EraWindow(label="Authorised Inquiry", from_year=2018, to_year=2021)


def test_named_window_lookup(eras_path):
    w = era_window_for("Cambridge", "model_code_2021", path=eras_path)
    assert w.label == "Model Code of Conduct 2021 (WA)"
    assert w.to_year is None


def test_missing_window_name_returns_none(eras_path):
    assert era_window_for("Perth", "inquiry", path=eras_path) is None


def test_missing_council_returns_none(eras_path):
    assert era_window_for("Nonexistent", path=eras_path) is None


def test_case_insensitive_council_match(eras_path):
    assert era_window_for("CAMBRIDGE", path=eras_path) is not None


def test_load_council_eras_returns_nested_structure(eras_path):
    eras = load_council_eras(eras_path)
    assert set(eras["cambridge"]) == {"inquiry", "model_code_2021"}
    assert set(eras["perth"]) == {"model_code_2021"}


def test_missing_file_degrades_to_empty(tmp_path):
    assert load_council_eras(tmp_path / "nope.json") == {}
    assert era_window_for("Cambridge", path=tmp_path / "nope.json") is None


def test_fiscal_year_start_month_still_works(tmp_path):
    # Unrelated to the era-window redesign — same module, different config
    # file. Guards against a shared-import mistake breaking this function.
    assert fiscal_year_start_month("Cambridge") == 7
