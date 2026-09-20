"""
Tests for the redesigned sponsorship_network() (docs/uplift/01-known-
defects.md's sponsorship gap, closed): council-agnostic era windows
(`_sponsorship_era_windows()`), computed structure labels
(`_sponsorship_structure_label()`), and the real hypergeometric
durable-faction persistence test, replacing the old hardcoded
`_SPON_ERAS`/`_OLDGUARD`/`_STRUCT` Cambridge-specific constants.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.queries import (
    _sponsorship_era_windows,
    _sponsorship_structure_label,
    sponsorship_network,
)
from src.models import Base, Council, Councillor, Meeting, Motion
from src.storage.database import _enable_wal_and_fk


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine, expire_on_commit=False)()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture
def council_id(session):
    c = Council(name="Test Council", short_name="TestCouncil", state="WA")
    session.add(c)
    session.flush()
    return c.id


def _meeting(session, council_id, d):
    m = Meeting(council_id=council_id, meeting_date=d, document_type="minutes")
    session.add(m)
    session.flush()
    return m.id


def _councillor(session, given, family):
    c = Councillor(given_name=given, family_name=family, slug=f"{given}-{family}".lower())
    session.add(c)
    session.flush()
    return c.id


def _motion(session, meeting_id, item_number, mover_id, seconder_id):
    m = Motion(
        meeting_id=meeting_id, item_number=item_number, title="A motion",
        moved_by_id=mover_id, seconded_by_id=seconder_id,
    )
    session.add(m)
    session.flush()
    return m.id


# ── _sponsorship_era_windows ─────────────────────────────────────────────

def test_era_windows_empty_corpus_returns_empty(session, council_id):
    assert _sponsorship_era_windows(session, council_id) == []


def test_era_windows_single_year_span(session, council_id):
    _meeting(session, council_id, date(2010, 3, 1))
    windows = _sponsorship_era_windows(session, council_id)
    assert windows == [("2010", 2010, 2010)]


def test_era_windows_multi_year_span_is_consecutive_and_council_agnostic(session, council_id):
    _meeting(session, council_id, date(2001, 1, 1))
    _meeting(session, council_id, date(2009, 12, 31))
    windows = _sponsorship_era_windows(session, council_id)
    assert windows == [
        ("2001–2004", 2001, 2004),
        ("2005–2008", 2005, 2008),
        ("2009", 2009, 2009),
    ]
    # Non-overlapping: no year is claimed by two windows.
    seen_years: set[int] = set()
    for _label, f, t in windows:
        for y in range(f, t + 1):
            assert y not in seen_years
            seen_years.add(y)
    # No hardcoded absolute years leak in - every window falls inside this
    # council's own corpus span.
    for _label, f, t in windows:
        assert 2001 <= f <= 2009
        assert 2001 <= t <= 2009


# ── _sponsorship_structure_label ─────────────────────────────────────────

def test_structure_label_no_active_sponsors():
    assert _sponsorship_structure_label(0, 0) == "no active sponsors"


def test_structure_label_no_cluster():
    assert _sponsorship_structure_label(10, 0) == "no cluster (lift < 1.8 throughout)"


def test_structure_label_small_nucleus():
    assert "small nucleus" in _sponsorship_structure_label(20, 4)  # 20%


def test_structure_label_core_cluster():
    assert "core cluster" in _sponsorship_structure_label(20, 8)  # 40%


def test_structure_label_broad_cluster():
    assert "broad cluster" in _sponsorship_structure_label(20, 15)  # 75%


# ── sponsorship_network(): the persistence test itself ───────────────────

def _seed_trio(session, meeting_id, start_item, a, b, c, n=20):
    """`n` co-sponsorship events for each of the 3 ordered pairs within
    (a, b, c) - concentrates sponsorship inside the trio well above what
    each member's overall volume would predict under independence, which
    is what makes the resulting edges high-lift (see the module docstring
    on why a diffuse background trio does NOT trigger this)."""
    item = start_item
    for _ in range(n):
        _motion(session, meeting_id, str(item), a, b)
        item += 1
        _motion(session, meeting_id, str(item), b, c)
        item += 1
        _motion(session, meeting_id, str(item), c, a)
        item += 1
    return item


def _seed_diffuse_background(session, meeting_id, start_item, members, n_each=16):
    """`n_each` moves per background member, seconder rotated round-robin
    among the OTHER background members so no single pair accumulates
    enough mutual sponsorships (min_obs=8) to form its own high-lift edge,
    while each member still individually clears the min_moved/min_sec=15
    activity floor."""
    item = start_item
    k = len(members)
    for i, mover in enumerate(members):
        for j in range(n_each):
            seconder = members[(i + 1 + j % (k - 1)) % k]
            if seconder == mover:
                seconder = members[(i + 2) % k]
            _motion(session, meeting_id, str(item), mover, seconder)
            item += 1
    return item


def test_sponsorship_network_detects_durable_faction(session, council_id):
    a, b, c = (_councillor(session, "A", "One"), _councillor(session, "B", "Two"),
               _councillor(session, "C", "Three"))
    background = [_councillor(session, f"Bg{i}", "Member") for i in range(6)]

    m1 = _meeting(session, council_id, date(2001, 6, 1))
    item = _seed_trio(session, m1, 1, a, b, c)
    _seed_diffuse_background(session, m1, item, background)

    m2 = _meeting(session, council_id, date(2005, 6, 1))
    item = _seed_trio(session, m2, 1, a, b, c)
    _seed_diffuse_background(session, m2, item, background)
    session.flush()

    s = sponsorship_network(session, council_id)
    assert len(s.eras) == 2
    assert s.persistence_family_size == 1
    assert s.has_durable_faction is True
    assert s.persistence_era_pair == ("2001–2004", "2005")
    assert set(s.persistent_core_names) == {"A One", "B Two", "C Three"}


def test_sponsorship_network_no_persistence_when_clusters_differ(session, council_id):
    a, b, c = (_councillor(session, "A", "One"), _councillor(session, "B", "Two"),
               _councillor(session, "C", "Three"))
    d, e, f = (_councillor(session, "D", "Four"), _councillor(session, "E", "Five"),
               _councillor(session, "F", "Six"))
    background = [_councillor(session, f"Bg{i}", "Member") for i in range(6)]

    m1 = _meeting(session, council_id, date(2001, 6, 1))
    item = _seed_trio(session, m1, 1, a, b, c)
    _seed_diffuse_background(session, m1, item, background)

    m2 = _meeting(session, council_id, date(2005, 6, 1))
    item = _seed_trio(session, m2, 1, d, e, f)  # a completely different trio
    _seed_diffuse_background(session, m2, item, background)
    session.flush()

    s = sponsorship_network(session, council_id)
    assert s.persistence_family_size == 1
    assert s.has_durable_faction is False
    assert s.persistent_core_names == []


def test_sponsorship_network_empty_corpus_returns_no_data(session, council_id):
    s = sponsorship_network(session, council_id)
    assert s.eras == []
    assert s.persistence_family_size == 0
    assert s.has_durable_faction is False
    assert s.oldguard_label == ""
