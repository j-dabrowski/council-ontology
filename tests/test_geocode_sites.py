"""
Unit tests for scripts/geocode_sites.py's address-cleaning/classification
logic (docs/frontend/MAP_PAGE_PLAN.md Phase 4.1/4.2/4.3/4.7) — synthetic
inputs (the real B.4 examples), no network, no DB, per docs/TESTING.md's
"Adding coverage" convention.
"""

from __future__ import annotations

from scripts.geocode_sites import (
    _clean_address,
    classify_unaddressable,
    derive_suburb,
    split_multi_site,
)

# ── _clean_address (4.1) — one real B.4 example per class ──────────────────


def test_clean_address_single_number_in_parens():
    cleaned, applied = _clean_address("Lot 82 (No. 25) Brighton Street, West Leederville")
    assert cleaned == "25 Brighton Street, West Leederville"
    assert applied == ["lot_paren_number"]


def test_clean_address_plain_lot_no_number():
    cleaned, applied = _clean_address("Lot 395 Brighton Street, West Leederville")
    assert cleaned == "Brighton Street, West Leederville"
    assert applied == ["lot_plain"]


def test_clean_address_ranged_street_numbers():
    cleaned, applied = _clean_address("Lot 4 (Nos 346-350) Cambridge Street, Wembley")
    assert cleaned == "346 Cambridge Street, Wembley"
    assert applied == ["lot_paren_number"]


def test_clean_address_compound_number_and():
    cleaned, applied = _clean_address("Lot 37 (No. 77A and 77B) Lake Monger Drive")
    assert cleaned == "77A Lake Monger Drive"
    assert applied == ["lot_paren_number"]


def test_clean_address_compound_number_slash():
    cleaned, applied = _clean_address("Lot 37 (No. 94/5) Lake Monger Drive")
    assert cleaned == "94 Lake Monger Drive"
    assert applied == ["lot_paren_number"]


def test_clean_address_reversed_lot_order():
    cleaned, applied = _clean_address("No 15 (Lot 301) Bernard Street, Leederville")
    assert cleaned == "15 Bernard Street, Leederville"
    assert applied == ["reversed_lot_order"]


def test_clean_address_trailing_plan_notation():
    cleaned, applied = _clean_address(
        "20 Norbury Crescent, City Beach (Lot 5 on Deposited Plan 27017)"
    )
    assert cleaned == "20 Norbury Crescent, City Beach"
    assert applied == ["trailing_plan_notation"]


def test_clean_address_untouched_when_no_lot_notation():
    cleaned, applied = _clean_address("12 Salvado Road, Wembley")
    assert cleaned == "12 Salvado Road, Wembley"
    assert applied == []


# ── classify_unaddressable (4.7) ────────────────────────────────────────────


def test_classify_precinct_name_has_no_street_number():
    assert classify_unaddressable("Floreat Activity Centre") == "no_street_number"


def test_classify_intersection():
    assert (
        classify_unaddressable("Jersey Street and Grantham Street intersection, Wembley")
        == "intersection"
    )


def test_classify_road_reserve():
    assert classify_unaddressable("Salvado Road, road reserve adjoining number 12") == "road_reserve"


def test_classify_ordinary_address_is_addressable():
    assert classify_unaddressable("25 Brighton Street, West Leederville") is None


def test_classify_lot_only_address_has_a_number_via_lot_and_is_addressable():
    # "Lot 395 ..." has a digit (from "395"), so it's not flagged
    # unaddressable even before _clean_address strips the Lot prefix —
    # classify_unaddressable runs on the raw address, same as the real
    # pipeline order in run().
    assert classify_unaddressable("Lot 395 Brighton Street, West Leederville") is None


# ── split_multi_site (4.2) ──────────────────────────────────────────────────


def test_split_multi_site_on_semicolon():
    parts = split_multi_site("104 Branksome Gardens, City Beach; 2 Adina Way, City Beach")
    assert parts == ["104 Branksome Gardens, City Beach", "2 Adina Way, City Beach"]


def test_split_multi_site_on_ampersand():
    parts = split_multi_site("104 Branksome Gardens, City Beach & 2 Adina Way, City Beach")
    assert parts == ["104 Branksome Gardens, City Beach", "2 Adina Way, City Beach"]


def test_split_multi_site_never_splits_inside_parens():
    # The compound-number case: "and" here is part of one lot's number,
    # not a second site — must come back as a single component.
    parts = split_multi_site("Lot 37 (No. 77A and 77B) Lake Monger Drive")
    assert parts == ["Lot 37 (No. 77A and 77B) Lake Monger Drive"]


def test_split_multi_site_single_site_is_a_one_element_list():
    parts = split_multi_site("25 Brighton Street, West Leederville")
    assert parts == ["25 Brighton Street, West Leederville"]


# ── derive_suburb (4.3) ─────────────────────────────────────────────────────


def test_derive_suburb_from_address_tail():
    assert derive_suburb("25 Brighton Street, West Leederville") == "West Leederville"


def test_derive_suburb_none_without_a_comma():
    assert derive_suburb("Brighton Street") is None
