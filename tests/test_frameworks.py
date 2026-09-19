"""
Tests for src/frameworks.py (docs/uplift/migration/04-jurisdiction.md
Steps 1-2) — the WA instrument table + demoted Nolan/CIPFA mapping.
"""
import json

from src.frameworks import instrument, primary_instruments, secondary_mapping


def test_all_seven_wa_instruments_present():
    instruments = primary_instruments()
    assert set(instruments) == {
        "LGA_1995", "ADMIN_REGS", "FG_REGS", "CONDUCT_REGS",
        "MODEL_CODE_2021", "DLGSC", "SAT",
    }
    for key, inst in instruments.items():
        assert inst.key == key
        assert inst.name
        assert inst.relevance


def test_instrument_lookup_by_key():
    inst = instrument("LGA_1995")
    assert inst is not None
    assert "Local Government Act 1995" in inst.name


def test_instrument_lookup_missing_key_returns_none():
    assert instrument("NOT_A_REAL_KEY") is None


def test_secondary_mapping_has_nolan_and_cipfa():
    mapping = secondary_mapping()
    assert set(mapping["nolan"]) == {
        "selflessness", "integrity", "objectivity", "accountability",
        "openness", "honesty", "leadership",
    }
    assert set(mapping["cipfa"]) == {"A", "B", "C", "D", "E", "F", "G"}


def test_missing_config_file_degrades_to_empty(tmp_path):
    missing = tmp_path / "nope.json"
    assert primary_instruments(missing) == {}
    assert secondary_mapping(missing) == {}


def test_config_file_is_valid_json_on_disk():
    from src.frameworks import DEFAULT_PATH
    json.loads(DEFAULT_PATH.read_text())
