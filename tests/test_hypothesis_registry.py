"""
Tests for src/hypothesis_registry.py (docs/uplift/migration/02-claim-layer.md
Step 8): load/save/append/family_size over a temp registry file.
"""
import pytest

from src.hypothesis_registry import (
    OUTCOME_NULL,
    OUTCOME_REPORTED,
    HypothesisEntry,
    append_entry,
    family_size,
    load_registry,
    save_registry,
)


def _entry(id="h1", outcome=OUTCOME_REPORTED, **overrides):
    defaults = dict(
        id=id, question="Does X happen?", pre_registered_at="2026-09-20",
        gold_tables_used=("vote_fact",), outcome=outcome,
    )
    defaults.update(overrides)
    return HypothesisEntry(**defaults)


def test_load_registry_missing_file_returns_empty(tmp_path):
    assert load_registry(tmp_path / "does_not_exist.json") == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "registry.json"
    entries = [_entry("h1"), _entry("h2", outcome=OUTCOME_NULL, drop_reason="no effect found")]
    save_registry(entries, path)
    loaded = load_registry(path)
    assert loaded == entries


def test_entry_rejects_invalid_outcome():
    with pytest.raises(ValueError, match="outcome must be one of"):
        _entry(outcome="maybe")


def test_append_entry_adds_to_existing_registry(tmp_path):
    path = tmp_path / "registry.json"
    save_registry([_entry("h1")], path)
    append_entry(_entry("h2"), path)
    loaded = load_registry(path)
    assert {e.id for e in loaded} == {"h1", "h2"}


def test_append_entry_rejects_duplicate_id(tmp_path):
    path = tmp_path / "registry.json"
    save_registry([_entry("h1")], path)
    with pytest.raises(ValueError, match="already registered"):
        append_entry(_entry("h1"), path)


def test_append_entry_creates_missing_parent_dir(tmp_path):
    path = tmp_path / "nested" / "registry.json"
    append_entry(_entry("h1"), path)
    assert load_registry(path) == [_entry("h1")]


def test_family_size_counts_whole_registry(tmp_path):
    path = tmp_path / "registry.json"
    save_registry([_entry("h1"), _entry("h2"), _entry("h3")], path)
    assert family_size(path=path) == 3


def test_family_size_accepts_entries_directly():
    assert family_size([_entry("h1"), _entry("h2")]) == 2


def test_family_size_empty_registry_is_zero(tmp_path):
    assert family_size(path=tmp_path / "missing.json") == 0
