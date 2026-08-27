"""
Unit tests for src/invariant_gate.py — the S7 invariant gate:
  - run_invariant_gate() against a clean battery and against each of the
    three violation classes (name-free schema, MIN_N, entity-resolution)
  - load_min_n() reading the real config/invariants.json
  - derive_claim_tier() — tier derivation (§4/§7): public iff every claim
    in the batch is institutional-unit

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
from src.invariant_gate import (
    INSTITUTIONAL_PROJECTIONS,
    derive_claim_tier,
    derive_claim_tiers,
    load_min_n,
    project_to_institutional,
    run_invariant_gate,
    usable_roster_names,
)


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


# ---------------------------------------------------------------------------
# derive_claim_tier
# ---------------------------------------------------------------------------

def test_all_institutional_batch_derives_public():
    battery = [_claim(test_id="a"), _claim(test_id="b", n=2)]
    assert derive_claim_tier(battery) == "public"


def test_one_individual_implicating_claim_drops_whole_batch_to_full():
    battery = [
        _claim(test_id="a"),
        _claim(test_id="b", unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING, n=10),
    ]
    assert derive_claim_tier(battery) == "full"


def test_one_individual_claim_drops_whole_batch_to_full():
    battery = [
        _claim(test_id="a"),
        _claim(
            test_id="b", unit_of_analysis=UNIT_INDIVIDUAL,
            named_entities=["Jane Citizen"], n=25, entity_resolution=ENTITY_RESOLUTION_CLEAN,
        ),
    ]
    assert derive_claim_tier(battery) == "full"


def test_not_computable_claim_does_not_block_public_tier():
    battery = [
        _claim(test_id="a"),
        _claim(test_id="b", data_ok=False, unit_of_analysis=UNIT_INDIVIDUAL, n=1),
    ]
    assert derive_claim_tier(battery) == "public"


def test_empty_battery_derives_public():
    assert derive_claim_tier([]) == "public"


# ---------------------------------------------------------------------------
# name-free TEXT — the check that makes "provably name-free" true rather than
# merely declared. named_entities is a declaration a generator can fail to set.
# ---------------------------------------------------------------------------

_ROSTER = {("Ada", "Fixture"), ("Bo", "Sample")}


def test_institutional_claim_with_a_full_name_in_its_headline_is_blocked():
    # The review's scenario: a generator interpolates a name into the headline
    # and leaves unit/named_entities at their institutional defaults, so the
    # schema check passes and tier derivation would promote it to public.
    claim = _claim(
        unit_of_analysis=UNIT_INSTITUTIONAL,
        headline="Ada Fixture recused 3 times",
    )
    result = run_invariant_gate([claim], min_n=3, known_names=_ROSTER)
    assert not result.passed
    assert [v.check for v in result.violations] == ["name-free-text"]
    assert "Ada Fixture" in result.violations[0].detail


def test_institutional_claim_with_a_titled_surname_is_blocked():
    claim = _claim(unit_of_analysis=UNIT_INSTITUTIONAL, verdict="Cr Sample voted against.")
    result = run_invariant_gate([claim], min_n=3, known_names=_ROSTER)
    assert [v.check for v in result.violations] == ["name-free-text"]


def test_a_name_hidden_in_a_chart_label_is_blocked():
    claim = _claim(
        unit_of_analysis=UNIT_INSTITUTIONAL,
        chart={"kind": "bars", "unit": "", "refline": None,
               "bars": [{"label": "Ada Fixture", "value": 4, "highlight": False}]},
    )
    result = run_invariant_gate([claim], min_n=3, known_names=_ROSTER)
    assert [v.check for v in result.violations] == ["name-free-text"]


def test_clean_institutional_claim_passes_the_text_scan():
    claim = _claim(unit_of_analysis=UNIT_INSTITUTIONAL, headline="41% of motions were contested")
    assert run_invariant_gate([claim], min_n=3, known_names=_ROSTER).passed


def test_bare_surname_is_not_matched_so_ordinary_words_do_not_block():
    # "Sample" alone must not trip the gate — a gate that blocks on every
    # common word gets worked around rather than trusted.
    claim = _claim(unit_of_analysis=UNIT_INSTITUTIONAL, headline="A sample of 20 motions")
    assert run_invariant_gate([claim], min_n=3, known_names=_ROSTER).passed


def test_individual_claim_may_name_the_person_it_is_about():
    claim = _claim(
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Ada Fixture"],
        entity_resolution=ENTITY_RESOLUTION_CLEAN,
        n=25,
        headline="Ada Fixture recused 25 times",
    )
    assert run_invariant_gate([claim], min_n=3, known_names=_ROSTER).passed


def test_text_scan_is_skipped_when_no_roster_is_supplied():
    claim = _claim(unit_of_analysis=UNIT_INSTITUTIONAL, headline="Ada Fixture recused 3 times")
    assert run_invariant_gate([claim], min_n=3).passed


# ---------------------------------------------------------------------------
# usable_roster_names — the real councillors table carries extraction debris,
# and matching on it blocked every draft on words like "The".
# ---------------------------------------------------------------------------

def test_roster_filter_drops_debris_rows():
    debris = {("", "The"), ("", ""), (" ", " "), ("Director", "Gibson, Luke"), ("A", "B")}
    assert usable_roster_names(debris) == set()


def test_roster_filter_keeps_real_names_with_punctuation_and_spaces():
    real = {("Michael", "Le Page"), ("Dale", "O'Callghan"), ("Brett", "Wood-Gush")}
    assert usable_roster_names(real) == real


def test_debris_roster_entry_cannot_block_ordinary_prose():
    claim = _claim(
        unit_of_analysis=UNIT_INSTITUTIONAL,
        headline="The council contested 41% of motions",
    )
    assert run_invariant_gate([claim], min_n=3, known_names={("", "The")}).passed


# ---------------------------------------------------------------------------
# INSTITUTIONAL_PROJECTIONS — the three digest-battery generators that can
# name someone (digest design plan §2/§3): each reduction must strip both
# named_entities and any name still sitting in headline/verdict text.
# ---------------------------------------------------------------------------

def test_recusal_management_projection_strips_names():
    claim = _claim(
        test_id="conflict.recusal_management",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen", "Ada Fixture"],
        n=2,
        headline="2 conflict(s) of interest declared this meeting, by 2 councillor(s)",
        verdict="Jane Citizen declared an interest on Item 4 — stepped out",
    )
    reduced = INSTITUTIONAL_PROJECTIONS["conflict.recusal_management"](claim)
    assert reduced.unit_of_analysis == UNIT_INSTITUTIONAL
    assert reduced.named_entities == []
    assert "Jane Citizen" not in reduced.headline
    assert "Jane Citizen" not in reduced.verdict
    assert "2" in reduced.verdict


def test_attendance_projection_strips_names():
    claim = _claim(
        test_id="governance.attendance",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=40,
        headline="Jane Citizen had at least one unexplained absence this meeting",
        verdict="Jane Citizen had at least one vote recorded ABSENT this meeting with no declared interest.",
    )
    reduced = INSTITUTIONAL_PROJECTIONS["governance.attendance"](claim)
    assert reduced.unit_of_analysis == UNIT_INSTITUTIONAL
    assert reduced.named_entities == []
    assert "Jane Citizen" not in reduced.headline
    assert "Jane Citizen" not in reduced.verdict
    assert "1 councillor" in reduced.headline


def test_decider_supplier_conflict_projection_strips_names():
    claim = _claim(
        test_id="procurement.decider_supplier_conflict",
        unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"],
        n=5,
        headline="1 surname collision(s) found between a tender winner and a voting councillor "
                 "this meeting — unconfirmed, provenance not checked",
        verdict="Jane Citizen's surname appears in winner 'Citizen Constructions' ($50,000)",
    )
    reduced = INSTITUTIONAL_PROJECTIONS["procurement.decider_supplier_conflict"](claim)
    assert reduced.unit_of_analysis == UNIT_INSTITUTIONAL
    assert reduced.named_entities == []
    assert "Jane Citizen" not in reduced.verdict
    assert "Citizen Constructions" not in reduced.verdict


# ---------------------------------------------------------------------------
# project_to_institutional
# ---------------------------------------------------------------------------

def test_project_to_institutional_is_identity_for_institutional_claims():
    claim = _claim(unit_of_analysis=UNIT_INSTITUTIONAL)
    assert project_to_institutional(claim) is claim


def test_project_to_institutional_returns_none_for_unregistered_individual_claim():
    claim = _claim(
        test_id="some.other_test", unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"], n=5,
    )
    assert project_to_institutional(claim) is None


def test_project_to_institutional_returns_none_for_individual_implicating():
    # No generator produces one yet (invariant_gate.py's own module docstring) —
    # the registry has no entries for this unit at all.
    claim = _claim(
        test_id="conflict.recusal_management",
        unit_of_analysis=UNIT_INDIVIDUAL_IMPLICATING,
        named_entities=["Jane Citizen"], n=5,
    )
    # recusal_management IS registered, but only individual claims are — an
    # individual_implicating claim with the same test_id still gets reduced,
    # since the registry keys on test_id, not unit. This documents that
    # behaviour rather than asserting the opposite.
    assert project_to_institutional(claim) is not None


# ---------------------------------------------------------------------------
# derive_claim_tiers — per-claim (not whole-batch) tier derivation
# ---------------------------------------------------------------------------

def test_derive_claim_tiers_institutional_claim_is_public():
    claims = [_claim(test_id="a", unit_of_analysis=UNIT_INSTITUTIONAL, named_entities=[])]
    assert derive_claim_tiers(claims, min_n=3) == {"a": "public"}


def test_derive_claim_tiers_institutional_claim_with_leaked_name_is_full():
    claims = [_claim(
        test_id="a", unit_of_analysis=UNIT_INSTITUTIONAL, named_entities=[],
        headline="Ada Fixture recused 3 times",
    )]
    assert derive_claim_tiers(claims, min_n=3, known_names=_ROSTER) == {"a": "full"}


def test_derive_claim_tiers_individual_claim_with_projection_is_public():
    claims = [_claim(
        test_id="governance.attendance", unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"], n=40,
        headline="Jane Citizen had at least one unexplained absence this meeting",
        verdict="Jane Citizen had at least one vote recorded ABSENT this meeting.",
    )]
    assert derive_claim_tiers(claims, min_n=3) == {"governance.attendance": "public"}


def test_derive_claim_tiers_individual_claim_without_projection_is_full():
    claims = [_claim(
        test_id="some.other_test", unit_of_analysis=UNIT_INDIVIDUAL,
        named_entities=["Jane Citizen"], n=5,
    )]
    assert derive_claim_tiers(claims, min_n=3) == {"some.other_test": "full"}


def test_derive_claim_tiers_not_computable_claim_is_full():
    claims = [_claim(test_id="a", unit_of_analysis=UNIT_INSTITUTIONAL, data_ok=False)]
    assert derive_claim_tiers(claims, min_n=3) == {"a": "full"}


def test_derive_claim_tiers_is_per_claim_not_whole_batch():
    # The whole-batch behaviour (one bad claim drops everything) must NOT
    # apply here — that's the entire point of the per-claim function.
    claims = [
        _claim(test_id="clean", unit_of_analysis=UNIT_INSTITUTIONAL, named_entities=[]),
        _claim(test_id="some.other_test", unit_of_analysis=UNIT_INDIVIDUAL,
               named_entities=["Jane Citizen"], n=5),
    ]
    tiers = derive_claim_tiers(claims, min_n=3)
    assert tiers["clean"] == "public"
    assert tiers["some.other_test"] == "full"
