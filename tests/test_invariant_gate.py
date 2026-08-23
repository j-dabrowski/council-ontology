"""
Unit tests for src/invariant_gate.py — the S7 invariant gate:
  - run_invariant_gate() against a clean battery and against each of the
    three violation classes (name-free schema, MIN_N, entity-resolution)
  - load_min_n() reading the real config/invariants.json

All plain TestResult objects and plain data — no DB, no CLI invocation.
"""
from src.analysis.tests import (
    CRITICAL,
    G_CONCERN,
    SUPPORTIVE,
    G_SOUND,
    ENTITY_RESOLUTION_CLEAN,
    ENTITY_RESOLUTION_OPEN_SPLITS,
    TestResult,
    UNIT_INDIVIDUAL,
    UNIT_INDIVIDUAL_IMPLICATING,
    UNIT_INSTITUTIONAL,
)
from src.invariant_gate import load_min_n, run_invariant_gate


def _claim(**overrides) -> TestResult:
    fields = dict(
        test_id="fixture.claim",
        title="Fixture claim",
        genre="Fixture",
        principle="—",
        question="—",
        valence=SUPPORTIVE,
        grade=G_SOUND,
        headline="headline",
        verdict="verdict",
    )
    fields.update(overrides)
    return TestResult(**fields)


# ---------------------------------------------------------------------------
# run_invariant_gate — clean battery
# ---------------------------------------------------------------------------

def test_clean_institutional_battery_passes():
    battery = [_claim(test_id="a"), _claim(test_id="b", n=2)]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is True
    assert result.violations == []


def test_not_computable_claim_is_skipped_even_if_it_would_violate():
    # data_ok=False already failed to compute — a different, already-visible
    # condition, not a gate violation.
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=1,
        entity_resolution=ENTITY_RESOLUTION_OPEN_SPLITS,
        data_ok=False,
    )]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is True


# ---------------------------------------------------------------------------
# name-free institutional schema
# ---------------------------------------------------------------------------

def test_institutional_claim_with_named_entities_is_blocked():
    battery = [_claim(
        test_id="governance.leaked_names",
        unit_of_analysis=UNIT_INSTITUTIONAL,
        named_entities=["Jane Citizen"],
    )]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.test_id == "governance.leaked_names"
    assert v.check == "name-free-schema"


def test_institutional_claim_with_no_named_entities_passes():
    battery = [_claim(unit_of_analysis=UNIT_INSTITUTIONAL, named_entities=[])]
    assert run_invariant_gate(battery, min_n=3).passed is True


# ---------------------------------------------------------------------------
# MIN_N
# ---------------------------------------------------------------------------

def test_individual_implicating_claim_at_min_n_is_blocked():
    # n == min_n must fail (n must exceed MIN_N, not just meet it).
    battery = [_claim(
        test_id="governance.per_person_cell",
        unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING,
        n=3,
    )]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is False
    assert any(v.check == "min-n" for v in result.violations)


def test_individual_implicating_claim_above_min_n_passes():
    battery = [_claim(unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING, n=4)]
    assert run_invariant_gate(battery, min_n=3).passed is True


def test_individual_claim_with_no_n_is_blocked():
    battery = [_claim(
        test_id="conduct.named_lapse",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=None,
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is False
    assert any(v.check == "min-n" for v in result.violations)


# ---------------------------------------------------------------------------
# entity-resolution clean bill
# ---------------------------------------------------------------------------

def test_individual_claim_with_open_splits_is_blocked_even_with_healthy_n():
    battery = [_claim(
        test_id="conduct.named_lapse",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=25,
        entity_resolution=ENTITY_RESOLUTION_OPEN_SPLITS,
    )]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is False
    assert len(result.violations) == 1
    assert result.violations[0].check == "entity-resolution"


def test_individual_implicating_claim_is_not_held_to_entity_resolution():
    # entity_resolution only gates UNIT_INDIVIDUAL claims per §4 — an
    # individual_implicating claim with healthy n and the default
    # entity_resolution value must not be flagged on that check.
    battery = [_claim(
        unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING,
        n=10,
        entity_resolution=ENTITY_RESOLUTION_OPEN_SPLITS,
    )]
    assert run_invariant_gate(battery, min_n=3).passed is True


def test_individual_claim_clean_with_healthy_n_passes():
    battery = [_claim(
        test_id="conduct.named_lapse",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=25,
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
    )]
    assert run_invariant_gate(battery, min_n=3).passed is True


# ---------------------------------------------------------------------------
# a realistic mixed battery: one clean institutional claim alongside one
# violating individual claim — the gate must fail the whole draft on the
# one bad claim, not silently drop it.
# ---------------------------------------------------------------------------

def test_mixed_battery_fails_on_the_one_violating_claim():
    battery = [
        _claim(test_id="procurement.concentration", valence=CRITICAL, grade=G_CONCERN, n=40),
        _claim(
            test_id="conduct.named_lapse",
            unit_of_analysis=UNIT_INDIVIDUAL,
            named_entities=["Jane Citizen"],
            n=2,
            entity_resolution=ENTITY_RESOLUTION_CLEAN,
        ),
    ]
    result = run_invariant_gate(battery, min_n=3)
    assert result.passed is False
    assert [v.test_id for v in result.violations] == ["conduct.named_lapse"]


# ---------------------------------------------------------------------------
# load_min_n
# ---------------------------------------------------------------------------

def test_load_min_n_reads_real_config():
    assert load_min_n() == 3


def test_load_min_n_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_min_n(tmp_path / "does_not_exist.json")


def test_load_min_n_rejects_negative(tmp_path):
    import json

    import pytest
    path = tmp_path / "invariants.json"
    path.write_text(json.dumps({"min_n": -1}))
    with pytest.raises(ValueError):
        load_min_n(path)
