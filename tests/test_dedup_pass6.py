"""Pass 6 — given-name variants adjudicated against the electoral roll.

The shape Passes 1-5 structurally miss: two well-formed councillor records
sharing a correctly-spelled family name, differing only in the given name
("Andres" / "Andrew" Timmermanis). Flagged by an Editor pass 2026-08-24 and
escalated to a human on every run since, because nothing was looking for it.

These tests cover the adjudicator and the merge executor. The safety
properties matter more than the merges: a wrong merge fabricates a composite
councillor whose published voting record belongs to nobody, and there is no
undo.
"""
import sqlite3

import pytest

from scripts.dedup_councillors import (
    adjudicate_pair,
    apply_merge,
    is_given_variant,
    roll_given_tokens,
)


def _roll(*rows):
    return [
        {"election_date": d, "ward": w, "given_name": g, "family_name": f}
        for d, w, g, f in rows
    ]


# ── the roll's own name forms ────────────────────────────────────────────────
def test_parenthesised_alternate_yields_both_forms():
    # The 2019 Cambridge ballot literally reads "Catherine (Kate)". This is the
    # roll stating that two forms name one candidate.
    assert roll_given_tokens("Catherine (Kate)") == {"Catherine", "Kate"}
    assert roll_given_tokens("Tracey Anne") == {"Tracey", "Anne"}
    assert roll_given_tokens("") == set()


# ── similarity is a narrowing filter, never the evidence ─────────────────────
@pytest.mark.parametrize("a,b", [("Rob", "Robert"), ("Andre", "Andres"),
                                 ("Andres", "Andrew"), ("Tracey", "Tracy"),
                                 ("H", "Hilary")])
def test_orthographic_variants(a, b):
    assert is_given_variant(a, b)


@pytest.mark.parametrize("a,b", [("Kate", "Catherine"), ("Kate", "Stephanie"),
                                 ("Tracey", "David"), ("Gavin", "Darren")])
def test_non_variants(a, b):
    # Kate/Catherine is the important row: the same person, scoring far below
    # threshold. Pass 6 catches it from the roll, never from similarity — which
    # is exactly why similarity alone may not merge anything.
    assert not is_given_variant(a, b)


# ── the adjudicator ──────────────────────────────────────────────────────────
def test_one_entry_naming_both_forms_is_conclusive():
    roll = _roll(("2019-10-19", "Wembley", "Catherine (Kate)", "Barlow"))
    verdict, evidence = adjudicate_pair(roll, "Barlow", "Kate", "Catherine")
    assert verdict == "SAME_COMBINED"
    assert "Catherine (Kate)" in evidence


def test_only_one_form_ever_on_a_ballot():
    roll = _roll(("2015-10-17", "Coast", "Andres", "Timmermanis"))
    verdict, _ = adjudicate_pair(roll, "Timmermanis", "Andres", "Andrew")
    assert verdict == "ONE_ATTESTED"


def test_both_forms_in_different_elections_is_not_settled_by_the_roll():
    # Rob Fredericks stood in 2015 and Robert Fredericks in 2021. Very likely
    # one person standing twice — but the roll cannot prove it, so it holds.
    roll = _roll(("2015-10-17", "Wembley", "Rob", "Fredericks"),
                 ("2021-10-16", "Wembley", "Robert", "Fredericks"))
    verdict, _ = adjudicate_pair(roll, "Fredericks", "Robert", "Rob")
    assert verdict == "BOTH_ATTESTED"


def test_same_election_proves_two_people():
    roll = _roll(("2015-10-17", "Coast", "John", "Smith"),
                 ("2015-10-17", "Coast", "James", "Smith"))
    verdict, evidence = adjudicate_pair(roll, "Smith", "John", "James")
    assert verdict == "DISTINCT"
    assert "2015-10-17" in evidence


def test_absent_family_falls_through_to_no_data():
    verdict, _ = adjudicate_pair(_roll(), "Delmenico", "Matt", "M")
    assert verdict == "NO_ROLL_DATA"


# ── the merge executor ───────────────────────────────────────────────────────
@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE councillors (id INTEGER PRIMARY KEY, given_name TEXT,
                                  family_name TEXT, slug TEXT);
        CREATE TABLE votes (id INTEGER PRIMARY KEY, motion_id INTEGER,
                            councillor_id INTEGER,
                            UNIQUE(motion_id, councillor_id));
        CREATE TABLE motions (id INTEGER PRIMARY KEY, moved_by_id INTEGER,
                              seconded_by_id INTEGER);
        CREATE TABLE appointments (id INTEGER PRIMARY KEY, councillor_id INTEGER);
        CREATE TABLE interest_declarations (id INTEGER PRIMARY KEY, councillor_id INTEGER);
    """)
    conn.executemany("INSERT INTO councillors VALUES (?,?,?,?)",
                     [(1, "Andres", "Timmermanis", "andres-timmermanis"),
                      (2, "Andrew", "Timmermanis", "andrew-timmermanis")])
    return conn


def test_merge_repoints_every_foreign_key(db):
    db.executemany("INSERT INTO votes (motion_id, councillor_id) VALUES (?,?)",
                   [(10, 1), (11, 2)])
    db.execute("INSERT INTO motions VALUES (100, 2, 2)")
    db.execute("INSERT INTO appointments VALUES (200, 2)")
    db.execute("INSERT INTO interest_declarations VALUES (300, 2)")

    apply_merge(db, 2, 1)

    assert db.execute("SELECT COUNT(*) FROM councillors WHERE id=2").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM votes WHERE councillor_id=1").fetchone()[0] == 2
    assert db.execute("SELECT moved_by_id, seconded_by_id FROM motions").fetchone() == (1, 1)
    assert db.execute("SELECT councillor_id FROM appointments").fetchone()[0] == 1
    assert db.execute("SELECT councillor_id FROM interest_declarations").fetchone()[0] == 1


def test_merge_survives_a_shared_motion_without_violating_the_unique(db):
    # votes carries UNIQUE(motion_id, councillor_id): a naive UPDATE across a
    # motion both records voted on raises IntegrityError. The source row is
    # dropped first. (A pair like this should never reach a merge in the first
    # place — merge_pair refuses it — but the executor must not corrupt the DB
    # if one ever does.)
    db.executemany("INSERT INTO votes (motion_id, councillor_id) VALUES (?,?)",
                   [(10, 1), (10, 2), (11, 2)])
    apply_merge(db, 2, 1)
    rows = db.execute(
        "SELECT motion_id, councillor_id FROM votes ORDER BY motion_id").fetchall()
    assert rows == [(10, 1), (11, 1)]
