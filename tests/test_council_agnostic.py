"""
Council-agnosticism gate (docs/SECOND_COUNCIL_PLAN.md Phase 0.2).

Runs the standard battery against two synthetic councils built by the one
shared fixture (`src/fixtures/testville.py`) — a Cambridge-*shaped*
baseline, and Testville, engineered to invert baseline's numbers wherever
a test has a direction — and checks two things the plan calls out
separately:

- **No leakage**: nothing in Testville's own battery output should read
  like it's describing Cambridge — a literal "Cambridge"/"Authorised
  Inquiry" mention, or a year outside Testville's own corpus span.
- **Direction tracking**: a test whose `valence`/`grade` is actually
  *derived* from the data should disagree between baseline and Testville,
  since Testville's numbers are the deliberate inverse. One that doesn't
  disagree is either genuinely non-directional, or — the real B2 finding
  this test exists to catch mechanically — hardcoded to baseline's
  (Cambridge's) conclusion regardless of what the data says.

Both checks are landed with an explicit, annotated allow-list rather than
a weakened assertion (per this session's working rules) — every entry
names *why* it's there, so the list is Phase 1's worklist, not a black
box, and both directions of drift are caught: a still-broken test staying
on the list, and a newly-broken test that isn't on it yet.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.tests import G_NODATA, TestResult, run_test_battery
from src.fixtures.testville import PROFILES, seed_profile
from src.models import Base
from src.storage.database import _enable_wal_and_fk
from src.test_registry import load_test_registry

# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def session():
    """Module-scoped: building both corpora is the expensive part of this
    file (~1,300 synthetic meetings across the two councils), and no test
    here mutates the DB or the TestResult objects it reads back — sharing
    one build across every test in this file is safe and roughly 3x faster
    than rebuilding it per test."""
    engine = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


@pytest.fixture(scope="module")
def council_ids(session) -> tuple[int, int]:
    cid_a, _ = seed_profile(session, "baseline")
    cid_b, _ = seed_profile(session, "testville")
    return cid_a, cid_b


@pytest.fixture(scope="module")
def batteries(session, council_ids) -> tuple[dict[str, TestResult], dict[str, TestResult]]:
    """(baseline battery, testville battery), keyed by test_id."""
    cid_a, cid_b = council_ids
    battery_a = {r.test_id: r for r in run_test_battery(session, cid_a)}
    battery_b = {r.test_id: r for r in run_test_battery(session, cid_b)}
    return battery_a, battery_b


# ── registry join ───────────────────────────────────────────────────────


def test_registry_join_has_no_orphan(batteries):
    """Every config/test_registry.json row resolves against Testville's
    battery, and vice versa — the same guarantee `run_test_battery`
    already enforces internally (`_load_registry_or_raise`), asserted here
    against a corpus that isn't Cambridge, so it can't be passing only
    because the registry and `_GENERATORS` happen to agree on Cambridge's
    own shape."""
    _, battery_b = batteries
    registry_ids = {row.id for row in load_test_registry()}
    assert set(battery_b) == registry_ids


# ── data_ok honesty ──────────────────────────────────────────────────────


def test_data_ok_honesty(batteries):
    """A test that can't run on a corpus reports `data_ok=False` with the
    `_nodata()` shape (grade=G_NODATA, an explicit "not computable"
    headline) — never a bare zero dressed up as a real result."""
    for label, battery in zip(("baseline", "testville"), batteries):
        for r in battery.values():
            if r.data_ok:
                continue
            assert r.grade == G_NODATA, (
                f"[{label}] {r.test_id}: data_ok=False but grade={r.grade!r}, "
                f"not {G_NODATA!r} — looks like a real result mislabelled, "
                "not an honest 'can't compute this' return"
            )
            assert r.headline == "Not computable on this corpus", (
                f"[{label}] {r.test_id}: data_ok=False but headline={r.headline!r}"
            )


# ── no leakage ───────────────────────────────────────────────────────────

_LEAKED_NAMES = ("Cambridge", "Authorised Inquiry")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_LEAKAGE_FIELDS = ("title", "headline", "verdict", "base_rate", "era")

# Annotated allow-list — Phase 1's worklist (docs/SECOND_COUNCIL_PLAN.md
# 1.1/1.2), not a permanent exemption. Every entry here is a real, already
# fixed-point-identified case of a hardcoded Cambridge-specific era/prose
# literal (`era="1995–2026"`, `era="pre-2018 / 2018–21 / post-2022"`, or,
# for `engagement.question_responsiveness`, a literal "Cambridge... its
# Authorised Inquiry" sentence in `verdict`) surviving into Testville's own
# battery output. None of these are direction bugs — they're B3's known,
# already-tracked hardcoded-era-boundary gap (Refiner_prompt.txt Step 4)
# plus B2's hardcoded-prose pattern, one field over from where B2's own
# audit looked (`era`/`verdict` literals, not `valence`/`grade`). Phase
# 1.2 (`config/council_eras.json`) and 1.1 empty this list test_id by
# test_id — shrink it as each is fixed, don't add exemption logic instead.
LEAKAGE_ALLOW: dict[str, str] = {
    "procurement.incumbency": "era hardcoded '1995-2026'",
    "procurement.concentration": "era hardcoded '1995-2026'",
    "procurement.decider_supplier_conflict": "era hardcoded '1995-2026'",
    "conflict.recusal_management": "era hardcoded '1995-2026'",
    "governance.power_spread": "era hardcoded '2003-2026 (contested motions)'",
    "governance.oversight_body_capture": "era hardcoded '1995-2026, era-pooled'",
    "governance.unanimity_trend": "era hardcoded '1995-2026 (years with >=30 carried motions)'",
    "governance.chair_capture": "era hardcoded '1999-2026 (mayors with dated terms)'",
    "governance.durable_faction": (
        "headline hardcoded '...clique existed and fragmented in 2008...'; "
        "era hardcoded '1996-2023 (electoral terms)'"
    ),
    "governance.incumbency": "era hardcoded '1995-2026'",
    "governance.freshman_effect": "era hardcoded '1995-2026'",
    "governance.election_cycle": "era hardcoded '1995-2026'",
    "governance.attendance": "era hardcoded '1995-2026'",
    "transparency.confidential_share": "era hardcoded '1995-2026'",
    "transparency.confidential_tender_size": "era hardcoded '1995-2026 . DIRECTIONAL (n<30)'",
    "transparency.confidential_topics": "era hardcoded '1995-2026'",
    "finance.eoy_spending": "era hardcoded '1995-2026'",
    "engagement.participation": "era hardcoded '1995-2026'",
    "engagement.deputation_dissent": "era hardcoded '1995-2026'",
}


def test_no_leakage(batteries):
    """Nothing in Testville's own battery output should read as a claim
    about Cambridge. Real leaks fail outright; the annotated cases above
    are asserted the *other* way (still leaking, not yet fixed) so this
    test also catches the day someone fixes one without updating the list.
    """
    _, battery_b = batteries
    still_leaking: set[str] = set()
    for test_id, r in battery_b.items():
        hit = None
        for field in _LEAKAGE_FIELDS:
            text = getattr(r, field) or ""
            for bad in _LEAKED_NAMES:
                if bad in text:
                    hit = f"[{field}] contains {bad!r}: {text[:160]!r}"
            for m in _YEAR_RE.finditer(text):
                year = int(m.group())
                profile = PROFILES["testville"]
                if not (profile.start_year <= year <= profile.end_year):
                    hit = (
                        f"[{field}] year {year} outside Testville's own span "
                        f"{profile.start_year}-{profile.end_year}: {text[:160]!r}"
                    )
            if hit:
                break
        if hit is None:
            continue
        still_leaking.add(test_id)
        if test_id not in LEAKAGE_ALLOW:
            pytest.fail(f"{test_id}: new leakage, not on LEAKAGE_ALLOW — {hit}")

    fixed = set(LEAKAGE_ALLOW) - still_leaking
    assert not fixed, (
        f"LEAKAGE_ALLOW entries no longer leak — remove from the allow-list: {sorted(fixed)}"
    )


# ── direction tracking ───────────────────────────────────────────────────

# Annotated allow-list — the Phase 1.1 worklist (docs/SECOND_COUNCIL_PLAN.md
# B2/1.1): every `test_id` here computes the SAME valence/grade for
# baseline and Testville despite Testville's data being the deliberate
# inverse, because `valence`/`grade` is a literal in the TestResult
# construction, never branched on the data at all (B2's actual finding).
#
# `planning.big_dollar_leniency`/`planning.repeat_applicant` used to be
# here too, for a different and more serious reason this fixture
# surfaced (2026-09-15, not on docs/SECOND_COUNCIL_PLAN.md's B1-B7 list):
# both queried `PlanningApplication` directly in `src/analysis/tests.py`
# with no join to Meeting/Motion and therefore no `council_id` filter at
# all, silently pooling BOTH councils' applications into every council's
# report. Fixed by joining through Motion -> Meeting, same shape their
# own meeting-scoped siblings already used; verified against the real
# Cambridge corpus (`data/council.db`) that the fix only drops the small
# number of applications with no linked motion (a pre-existing, already-
# documented coverage gap), not a real number.
#
# `conflict.recusal_management` is a third kind of entry: as of this
# session it's genuinely derived (branches on the real stay-and-vote
# rate, not a literal), and both fixture profiles still land CRITICAL —
# honestly, not a hardcode. Impartiality-type declared interests never
# require stepping out (lawful — see `_MUST_LEAVE_TYPES`), and both
# profiles' declared interests are ~50% impartiality/other by the
# fixture's own even split, which drags the *blended* stay rate toward
# "stay" regardless of either profile's must-leave era trend. That trend
# is real and does diverge — see `conflict.recusal_trend`, which reports
# it directly instead of blended — this test's own blended metric just
# isn't sensitive to it at this fixture's declaration-type mix. A fixture
# change worth making later, not a code correctness issue now.
#
# Every other battery test's valence/grade construction was checked by
# hand against this exact list (`grep -n "valence=.* if " src/analysis/
# tests.py` — seven conditional constructions in the whole battery as of
# this session; six clear this test on this fixture: procurement.threshold_gaming,
# procurement.incumbency, planning.big_dollar_leniency,
# planning.repeat_applicant, finance.eoy_spending, conflict.recusal_trend).
DIRECTION_ALLOW: dict[str, str] = {
    "procurement.concentration": "no direction by design (see comment in tests.py) — always NEUTRAL",
    "procurement.decider_supplier_conflict": (
        "derived, not hardcoded (branches on raw collision count) — this "
        "fixture's synthetic surnames/firm names don't happen to collide, "
        "so both profiles land SUPPORTIVE on the zero-collision branch"
    ),
    "conflict.recusal_management": (
        "derived, not hardcoded — both fixture profiles land the same side "
        "of the blended stay-rate metric (see comment above)"
    ),
    "governance.unanimity_trend": "hardcoded: valence=NEUTRAL always (descriptive, no branch)",
    "governance.durable_faction": (
        "deeper than a valence hardcode — headline/verdict are static Cambridge "
        "prose, and the query layer itself hardcodes an era calendar + narrative "
        "(see comment in tests.py); not attempted this pass"
    ),
    "governance.incumbency": "no direction by design (see comment in tests.py) — always NEUTRAL",
    "governance.freshman_effect": "hardcoded: valence=NEUTRAL always (descriptive, no branch)",
    "governance.election_cycle": "hardcoded: valence=NEUTRAL always (descriptive, no branch)",
    "governance.attendance": "hardcoded: valence=NEUTRAL always (descriptive, no branch)",
    "transparency.confidential_share": (
        "derived, not hardcoded (branches on peak-vs-baseline spike size) — "
        "the fixture gives both profiles the same inquiry-era confidentiality "
        "bump (not one of Testville's inverted signals), so both land CRITICAL"
    ),
    "transparency.confidential_topics": (
        "derived, not hardcoded (branches on whether 'named development' is "
        "actually the least-closed theme) — the fixture gives both profiles "
        "the same theme-closure shape (not one of Testville's inverted "
        "signals), so both land SUPPORTIVE"
    ),
    "engagement.participation": "no direction by design (see comment in tests.py) — always NEUTRAL",
    "engagement.deputation_dissent": "hardcoded: valence=NEUTRAL always (descriptive, no branch)",
}


def test_direction_tracking(batteries):
    """For every test where both councils actually computed a result
    (`data_ok=True` on both sides), baseline's and Testville's
    valence/grade should disagree — Testville's numbers are the
    deliberate inverse of baseline's. A test not on DIRECTION_ALLOW that
    fails this is a live B2 finding: derive the branch from the data
    (Phase 1.1), don't add it to the list.
    """
    battery_a, battery_b = batteries
    same: set[str] = set()
    for test_id in battery_a:
        a, b = battery_a[test_id], battery_b[test_id]
        if not (a.data_ok and b.data_ok):
            continue  # nothing to compare a direction on
        if (a.valence, a.grade) == (b.valence, b.grade):
            same.add(test_id)
            if test_id not in DIRECTION_ALLOW:
                pytest.fail(
                    f"{test_id}: valence/grade identical across baseline "
                    f"({a.valence}/{a.grade}) and Testville ({b.valence}/{b.grade}) "
                    "despite inverted data, and not on DIRECTION_ALLOW — "
                    "new B2 hardcode, or the fixture needs a stronger signal"
                )

    fixed = set(DIRECTION_ALLOW) - same
    assert not fixed, (
        f"DIRECTION_ALLOW entries now correctly diverge — remove from the allow-list: {sorted(fixed)}"
    )
