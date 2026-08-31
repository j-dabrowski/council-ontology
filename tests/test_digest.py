"""
Unit tests for src/analysis/digest.py — the period digest:
  - score_salience(): novelty percentile math, floor override, thin-baseline
    suppression, wrong-body-class isolation
  - meeting_inventory() / public_inventory_projection(): mover/seconder
    names in the deep view, dropped in the public projection; "Nil items"
    placeholder rows excluded (same fix as transparency_by_year)
  - compose_period_digest(): empty-period quiet record, a digest_floor-
    triggered claim surviving into highlights, a committee meeting's claims
    not scored against a full_council baseline, invalid interval rejected

sqlite:///:memory: engine + Base.metadata.create_all, same pattern as
test_profile.py.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.digest import (
    compose_period_digest,
    meeting_inventory,
    public_inventory_projection,
    score_salience,
)
from src.analysis.meeting_baselines import MeetingBaselines, TestBaseline
from src.analysis.tests import G_OBSERVATION, NEUTRAL, TestResult
from src.models import Base, Council, Councillor, Meeting, Motion, MotionOutcome, OtherItem, Tender
from src.storage.database import _enable_wal_and_fk


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    _enable_wal_and_fk(eng)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.rollback()
    sess.close()


def _council(session, short_name="TestCouncil") -> int:
    c = Council(name=f"{short_name} Full Name", short_name=short_name, state="WA")
    session.add(c)
    session.flush()
    return c.id


def _councillor(session, given, family) -> int:
    slug = f"{given}-{family}".lower()
    p = Councillor(given_name=given, family_name=family, slug=slug)
    session.add(p)
    session.flush()
    return p.id


def _meeting(session, council_id, meeting_date, meeting_type="Ordinary Council Meeting",
             document_type="minutes") -> int:
    m = Meeting(council_id=council_id, meeting_date=meeting_date, document_type=document_type,
                meeting_type=meeting_type)
    session.add(m)
    session.flush()
    return m.id


def _motion(session, meeting_id, moved_by_id=None, seconded_by_id=None,
            outcome=MotionOutcome.CARRIED, item_number="1", title="A motion") -> int:
    mo = Motion(meeting_id=meeting_id, title=title, item_number=item_number, outcome=outcome,
                moved_by_id=moved_by_id, seconded_by_id=seconded_by_id)
    session.add(mo)
    session.flush()
    return mo.id


def _claim(**overrides) -> TestResult:
    fields = dict(
        test_id="fixture.claim", title="Fixture claim", genre="Fixture", principle="—",
        question="—", valence=NEUTRAL, grade=G_OBSERVATION, headline="headline", verdict="verdict",
    )
    fields.update(overrides)
    return TestResult(**fields)


_DEFAULT_POLICY = {
    "min_salience": 0.7, "max_highlights": 4, "min_baseline_meetings": 8,
    "empty_period_behaviour": "emit_quiet_record",
}


def _baselines(entries: dict | None = None) -> MeetingBaselines:
    return MeetingBaselines(
        council="test", generated_at="x", n_meetings_considered=0, baselines=entries or {},
    )


# ---------------------------------------------------------------------------
# score_salience
# ---------------------------------------------------------------------------

def test_score_salience_floor_only_when_no_baseline_at_all():
    claim = _claim(stat={"value": 5, "denominator": None, "unit": "count"}, digest_floor=0.3)
    assert score_salience(claim, _baselines(), "full_council", _DEFAULT_POLICY) == 0.3


def test_score_salience_novelty_disabled_below_min_baseline_meetings():
    tb = TestBaseline(n_meetings=3, values=[1.0, 2.0, 3.0])  # below min_baseline_meetings=8
    claim = _claim(test_id="a", stat={"value": 10, "denominator": None, "unit": "count"})
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "full_council", _DEFAULT_POLICY) == 0.0


def test_score_salience_extreme_value_scores_near_one():
    tb = TestBaseline(n_meetings=20, values=[float(v) for v in range(1, 21)])
    claim = _claim(test_id="a", stat={"value": 100, "denominator": None, "unit": "count"})
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "full_council", _DEFAULT_POLICY) == 1.0


def test_score_salience_median_value_scores_near_zero():
    tb = TestBaseline(n_meetings=20, values=[float(v) for v in range(1, 21)])
    claim = _claim(test_id="a", stat={"value": 10, "denominator": None, "unit": "count"})
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "full_council", _DEFAULT_POLICY) < 0.2


def test_score_salience_floor_overrides_low_novelty():
    tb = TestBaseline(n_meetings=20, values=[float(v) for v in range(1, 21)])
    claim = _claim(test_id="a", stat={"value": 10, "denominator": None, "unit": "count"},
                    digest_floor=0.9)
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "full_council", _DEFAULT_POLICY) == 0.9


def test_score_salience_wrong_body_class_has_no_baseline_so_novelty_is_disabled():
    tb = TestBaseline(n_meetings=20, values=[float(v) for v in range(1, 21)])
    claim = _claim(test_id="a", stat={"value": 100, "denominator": None, "unit": "count"})
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "committee_policy_legislation", _DEFAULT_POLICY) == 0.0


def test_score_salience_falls_back_to_n_when_stat_is_none():
    tb = TestBaseline(n_meetings=20, values=[float(v) for v in range(1, 21)])
    claim = _claim(test_id="a", stat=None, n=100)
    baselines = _baselines({"a": {"full_council": tb}})
    assert score_salience(claim, baselines, "full_council", _DEFAULT_POLICY) == 1.0


# ---------------------------------------------------------------------------
# meeting_inventory / public_inventory_projection
# ---------------------------------------------------------------------------

def test_meeting_inventory_includes_mover_and_seconder(session):
    council_id = _council(session)
    cid1 = _councillor(session, "Jane", "Citizen")
    cid2 = _councillor(session, "Bo", "Sample")
    meeting_id = _meeting(session, council_id, date(2026, 5, 12),
                          meeting_type="Policy and Legislation Committee Meeting")
    _motion(session, meeting_id, moved_by_id=cid1, seconded_by_id=cid2,
            item_number="4", title="Parking Local Law review")

    inv = meeting_inventory(session, council_id, meeting_id)
    assert inv["motions"][0]["moved_by"] == "Jane Citizen"
    assert inv["motions"][0]["seconded_by"] == "Bo Sample"
    assert inv["motions"][0]["item_id"] == f"{meeting_id}:motion:4"
    assert inv["meeting_type"] == "Policy and Legislation Committee Meeting"


def test_public_inventory_projection_drops_mover_and_seconder(session):
    council_id = _council(session)
    cid1 = _councillor(session, "Jane", "Citizen")
    meeting_id = _meeting(session, council_id, date(2026, 5, 12))
    _motion(session, meeting_id, moved_by_id=cid1, item_number="1")

    inv = meeting_inventory(session, council_id, meeting_id)
    public = public_inventory_projection(inv)
    assert "moved_by" not in public["motions"][0]
    assert "seconded_by" not in public["motions"][0]
    assert public["motions"][0]["title"] == inv["motions"][0]["title"]


def test_meeting_inventory_excludes_nil_item_placeholder_rows(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2026, 5, 12))
    session.add(OtherItem(meeting_id=meeting_id, item_type="confidential_item",
                           description="Confidential Reports - Nil items", is_confidential=True))
    session.add(OtherItem(meeting_id=meeting_id, item_type="correspondence",
                           description="17 submissions on the Parking Local Law review",
                           is_confidential=False))
    session.flush()

    inv = meeting_inventory(session, council_id, meeting_id)
    assert "confidential_item" not in inv["other_items_by_type"]
    assert "correspondence" in inv["other_items_by_type"]
    assert inv["other_items_by_type"]["correspondence"][0]["item_id"] == f"{meeting_id}:other:correspondence:0"


def test_meeting_inventory_excludes_nil_placeholder_with_no_items_word(session):
    # Regression: the original substring-only check here (`"nil item" in
    # description.lower()`) missed this exact real-corpus shape — no
    # "item(s)" word at all — the same gap Editor's defamation_review_1
    # flag (draft_20260828_094239) found in the sibling confidential_topics
    # call sites, fixed there via Fixer, then closed here too (2026-08-29).
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2025, 12, 9))
    session.add(OtherItem(meeting_id=meeting_id, item_type="confidential_item",
                           description="Confidential Reports - Nil", is_confidential=True))
    session.flush()

    inv = meeting_inventory(session, council_id, meeting_id)
    assert "confidential_item" not in inv["other_items_by_type"]


# ---------------------------------------------------------------------------
# compose_period_digest
# ---------------------------------------------------------------------------

def test_compose_period_digest_invalid_interval_raises(session):
    council_id = _council(session)
    with pytest.raises(ValueError):
        compose_period_digest(session, council_id, "fortnite", date(2026, 6, 1),
                              _baselines(), _DEFAULT_POLICY, min_n=3)


def test_compose_period_digest_empty_window_emits_quiet_record(session):
    council_id = _council(session)
    old_meeting_id = _meeting(session, council_id, date(2025, 1, 1))
    _motion(session, old_meeting_id)

    result = compose_period_digest(session, council_id, "week", date(2026, 6, 1),
                                   _baselines(), _DEFAULT_POLICY, min_n=3)
    assert result["quiet"] is True
    assert result["most_recent_meeting"]["meeting_id"] == old_meeting_id
    assert result["highlights"] == []
    assert result["candidates"] == []


def test_compose_period_digest_quiet_record_respects_period_end(session):
    # Regression: _most_recent_content_bearing_meeting() used to have no
    # date filter at all, so the quiet-record fallback always named the
    # corpus's true latest meeting regardless of period_end — a historical
    # digest for an empty week would wrongly point at a meeting from months
    # after that week. Found 2026-08-31 trying to target a specific past
    # meeting via --interval meeting --period-end.
    council_id = _council(session)
    old_meeting_id = _meeting(session, council_id, date(2025, 1, 1))
    _motion(session, old_meeting_id)
    future_meeting_id = _meeting(session, council_id, date(2026, 12, 1))
    _motion(session, future_meeting_id)

    result = compose_period_digest(session, council_id, "week", date(2025, 6, 1),
                                   _baselines(), _DEFAULT_POLICY, min_n=3)
    assert result["quiet"] is True
    assert result["most_recent_meeting"]["meeting_id"] == old_meeting_id


def test_compose_period_digest_meeting_interval_respects_period_end(session):
    # Regression, same bug: interval="meeting" ignored period_end entirely
    # and always grabbed the corpus's true latest meeting.
    council_id = _council(session)
    target_meeting_id = _meeting(session, council_id, date(2026, 3, 24))
    _motion(session, target_meeting_id)
    later_meeting_id = _meeting(session, council_id, date(2026, 5, 12))
    _motion(session, later_meeting_id)

    result = compose_period_digest(session, council_id, "meeting", date(2026, 3, 24),
                                   _baselines(), _DEFAULT_POLICY, min_n=3)
    assert result["meetings_covered"][0]["meeting_id"] == target_meeting_id
    assert len(result["meetings_covered"]) == 1


def test_compose_period_digest_floor_triggered_claim_becomes_a_highlight(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2026, 5, 12))
    _motion(session, meeting_id)
    session.add(Tender(meeting_id=meeting_id, description="Playground upgrade", amount=50000,
                        awarded_to="Acme Constructions", is_confidential=False))
    session.flush()

    result = compose_period_digest(session, council_id, "week", date(2026, 5, 15),
                                   _baselines(), _DEFAULT_POLICY, min_n=3)
    assert result["quiet"] is False
    highlighted_ids = {h["deep"]["test_id"] for h in result["highlights"]}
    assert "procurement.concentration" in highlighted_ids
    tender_highlight = next(h for h in result["highlights"] if h["deep"]["test_id"] == "procurement.concentration")
    assert tender_highlight["salience"] >= 0.7
    assert tender_highlight["tier"] == "public"
    assert tender_highlight["claim_id"] == f"{meeting_id}:procurement.concentration"


def test_compose_period_digest_committee_meeting_not_scored_against_full_council_baseline(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2026, 5, 12),
                          meeting_type="Policy and Legislation Committee Meeting")
    _motion(session, meeting_id)

    # A rich full_council baseline exists, but this meeting is a committee —
    # body_class routing must not let the committee's claim borrow it.
    tb = TestBaseline(n_meetings=20, values=[0.0] * 20)
    baselines = _baselines({"governance.attendance": {"full_council": tb}})

    result = compose_period_digest(session, council_id, "week", date(2026, 5, 15),
                                   baselines, _DEFAULT_POLICY, min_n=3)
    attendance = next(c for c in result["candidates"] if c["deep"]["test_id"] == "governance.attendance")
    assert attendance["salience"] == 0.0


def test_compose_period_digest_meetings_covered_records_body_class(session):
    council_id = _council(session)
    meeting_id = _meeting(session, council_id, date(2026, 5, 12),
                          meeting_type="Policy and Legislation Committee Meeting")
    _motion(session, meeting_id)

    result = compose_period_digest(session, council_id, "week", date(2026, 5, 15),
                                   _baselines(), _DEFAULT_POLICY, min_n=3)
    assert result["meetings_covered"][0]["body_class"] == "committee_policy_legislation"
