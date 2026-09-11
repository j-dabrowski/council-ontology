"""
Unit tests for src/publish_gate.py:
  - check_clearance() in both gate profiles — interactive (unchanged-behavior
    regression) and auto (the new, code-enforced Editor-record re-validation)
  - load_draft_manifest() / verify_draft_integrity() — no prior coverage existed

All of these take a tmp_path standing in for a data/draft/<council>/<run_id>/
directory and plain data — no real database, no CLI invocation.
"""
import json

import pytest

from src.publish_gate import (
    DraftManifest,
    check_clearance,
    load_draft_manifest,
    snapshot_hash,
    verify_draft_integrity,
)


# ---------------------------------------------------------------------------
# check_clearance — interactive gate profile (regression: must match the
# pre-existing --confirm behavior exactly)
# ---------------------------------------------------------------------------

def test_interactive_clears_on_real_confirm_note(tmp_path):
    result = check_clearance(tmp_path, "reviewed by josef 2026-08-20", "run_1", gate_profile="interactive")
    assert result.cleared is True


def test_interactive_rejects_missing_confirm_note(tmp_path):
    result = check_clearance(tmp_path, None, "run_1", gate_profile="interactive")
    assert result.cleared is False
    assert "no --confirm note" in result.reason


def test_interactive_rejects_blank_confirm_note(tmp_path):
    result = check_clearance(tmp_path, "   ", "run_1", gate_profile="interactive")
    assert result.cleared is False
    assert "no --confirm note" in result.reason


def test_interactive_rejects_too_short_confirm_note(tmp_path):
    result = check_clearance(tmp_path, "short", "run_1", gate_profile="interactive")
    assert result.cleared is False
    assert "too short" in result.reason


def test_interactive_ignores_draft_dir_contents(tmp_path):
    # A PASS record on disk must not matter in interactive mode — the two
    # profiles are independent gates, not fallbacks for each other.
    _write_review(tmp_path, n=1, run_id="run_1", status="PASS", tracks=[])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="interactive")
    assert result.cleared is False


def test_default_gate_profile_is_interactive(tmp_path):
    result = check_clearance(tmp_path, "reviewed by josef 2026-08-20", "run_1")
    assert result.cleared is True


def test_unknown_gate_profile_raises():
    with pytest.raises(ValueError):
        check_clearance(None, None, "run_1", gate_profile="yolo")


# ---------------------------------------------------------------------------
# check_clearance — auto gate profile
# ---------------------------------------------------------------------------

def _write_review(draft_dir, *, n, run_id, status, tracks, council="cambridge"):
    record = {
        "run_id": run_id,
        "council": council,
        "pass": n,
        "status": status,
        "tracks": tracks,
        "reviewed_at": "2026-08-20T12:00:00Z",
    }
    (draft_dir / f"defamation_review_{n}.json").write_text(json.dumps(record))
    return record


def test_auto_rejects_when_no_review_record(tmp_path):
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is False
    assert "no defamation_review_" in result.reason


def test_auto_rejects_unparseable_json(tmp_path):
    (tmp_path / "defamation_review_1.json").write_text("{not valid json")
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is False
    assert "not valid JSON" in result.reason


def test_auto_rejects_run_id_mismatch(tmp_path):
    _write_review(tmp_path, n=1, run_id="run_OTHER", status="PASS", tracks=[])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is False
    assert "does not match" in result.reason


def test_auto_rejects_non_pass_status(tmp_path):
    _write_review(tmp_path, n=1, run_id="run_1", status="FAIL", tracks=["frontend"])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is False
    assert "not PASS" in result.reason


def test_auto_rejects_pass_with_nonempty_tracks(tmp_path):
    # A PASS with tracks listed is an internally inconsistent record, not
    # given the benefit of the doubt.
    _write_review(tmp_path, n=1, run_id="run_1", status="PASS", tracks=["frontend"])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is False
    assert "inconsistent record" in result.reason


def test_auto_clears_on_valid_pass_record(tmp_path):
    _write_review(tmp_path, n=1, run_id="run_1", status="PASS", tracks=[])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is True
    assert "defamation_review_1.json" in result.reason


def test_auto_uses_highest_numbered_review_record(tmp_path):
    # Pass 1 failed, was fixed, pass 2 is the real verdict — auto must look
    # at the latest record, not the first one it finds.
    _write_review(tmp_path, n=1, run_id="run_1", status="FAIL", tracks=["frontend"])
    _write_review(tmp_path, n=2, run_id="run_1", status="PASS", tracks=[])
    result = check_clearance(tmp_path, None, "run_1", gate_profile="auto")
    assert result.cleared is True
    assert "defamation_review_2.json" in result.reason


def test_auto_ignores_confirm_note_entirely(tmp_path):
    # auto mode must not accidentally fall back to trusting free text.
    result = check_clearance(tmp_path, "some note nobody checks", "run_1", gate_profile="auto")
    assert result.cleared is False


# ---------------------------------------------------------------------------
# load_draft_manifest / verify_draft_integrity — no prior coverage existed
# ---------------------------------------------------------------------------

def test_load_draft_manifest_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_draft_manifest(tmp_path)


def test_load_draft_manifest_round_trips_fields(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "run_id": "run_1",
        "council": "cambridge",
        "generated_at": "2026-08-20T12:00:00Z",
        "snapshots": ["overview"],
        "file_hashes": {"overview": "deadbeef"},
        "tiers": {"overview": "public"},
    }))
    manifest = load_draft_manifest(tmp_path)
    assert manifest.run_id == "run_1"
    assert manifest.council == "cambridge"
    assert manifest.snapshots == ["overview"]
    assert manifest.tiers == {"overview": "public"}


def test_verify_draft_integrity_clean_when_hashes_match(tmp_path):
    snapshot_path = tmp_path / "overview.json"
    snapshot_path.write_text('{"a": 1}')
    manifest = DraftManifest(
        run_id="run_1", council="cambridge", generated_at="2026-08-20T12:00:00Z",
        snapshots=["overview"], file_hashes={"overview": snapshot_hash(snapshot_path)},
        tiers={"overview": "public"},
    )
    assert verify_draft_integrity(tmp_path, manifest) == []


def test_verify_draft_integrity_flags_missing_file(tmp_path):
    manifest = DraftManifest(
        run_id="run_1", council="cambridge", generated_at="2026-08-20T12:00:00Z",
        snapshots=["overview"], file_hashes={"overview": "deadbeef"},
        tiers={"overview": "public"},
    )
    assert verify_draft_integrity(tmp_path, manifest) == ["overview"]


def test_verify_draft_integrity_flags_hash_drift(tmp_path):
    snapshot_path = tmp_path / "overview.json"
    snapshot_path.write_text('{"a": 1}')
    manifest = DraftManifest(
        run_id="run_1", council="cambridge", generated_at="2026-08-20T12:00:00Z",
        snapshots=["overview"], file_hashes={"overview": "not-the-real-hash"},
        tiers={"overview": "public"},
    )
    assert verify_draft_integrity(tmp_path, manifest) == ["overview"]


# ---------------------------------------------------------------------------
# The moved draft/publish boundary (docs/frontend/WATCH_FEED_PLAN.md B.3/
# B.4/Step 5): the single-meeting digest and the period digest (`cmd_draft`,
# src/cli.py) must stay invisible to both `council publish` and Editor —
# they land in a `local/` subdirectory, outside the manifest's `snapshots`
# list and outside the non-recursive `*.json` glob both of them use
# (docs/review/editor/Editor_prompt.txt v0.7's `local/` exclusion). watch.json
# is the opposite case: a root-level, manifest-listed, publishable snapshot
# like any other, because its own claims are filtered and re-verified
# per-claim (project_watch_feed_to_public()) before cmd_draft ever writes it.
# Both directions are asserted here so neither can silently regress.
# ---------------------------------------------------------------------------

def test_digest_and_period_digest_stay_excluded_watch_is_a_real_snapshot(tmp_path):
    overview_path = tmp_path / "overview.json"
    overview_path.write_text('{"a": 1}')
    watch_path = tmp_path / "watch.json"
    watch_path.write_text('{"data": {"n_meetings": 1, "meetings": []}}')

    (tmp_path / "manifest.json").write_text(json.dumps({
        "run_id": "run_1",
        "council": "cambridge",
        "generated_at": "2026-08-27T12:00:00Z",
        "snapshots": ["overview", "watch"],
        "file_hashes": {
            "overview": snapshot_hash(overview_path),
            "watch": snapshot_hash(watch_path),
        },
        "tiers": {"overview": "public", "watch": "public"},
    }))

    local_dir = tmp_path / "local"
    local_dir.mkdir()
    (local_dir / "digest.json").write_text('{"data": {"tests": []}}')
    (local_dir / "period_digest.json").write_text('{"quiet": true}')

    manifest = load_draft_manifest(tmp_path)
    # digest.json / period_digest.json: still local/-only, still invisible.
    assert "digest" not in manifest.snapshots
    assert "period_digest" not in manifest.snapshots
    assert "digest" not in {p.stem for p in tmp_path.glob("*.json")}
    assert "period_digest" not in {p.stem for p in tmp_path.glob("*.json")}
    # watch.json: a real, root-level, manifest-listed, publishable snapshot.
    assert "watch" in manifest.snapshots
    assert "watch" in {p.stem for p in tmp_path.glob("*.json")}
    assert manifest.tiers["watch"] == "public"
    assert verify_draft_integrity(tmp_path, manifest) == []


# ---------------------------------------------------------------------------
# SNAPSHOT_TIER / _tier_of (ENTITY_RESOLUTION_SECTION_PLAN.md Step 3):
# method.json moved to public tier once its entity_resolution block was
# made name-free by construction (B.1/B.2) — a static entry, not
# claim-derived, since it carries no TestResult (src/cli.py's SNAPSHOT_TIER
# comment). Regression-checked here so a future edit can't silently drop it
# back to full-tier (an empty live /method) or newly-derived-full snapshot
# can't slip out as public (the fail-safe direction both ways).
# ---------------------------------------------------------------------------

def test_method_snapshot_is_public_tier():
    from src.cli import SNAPSHOT_TIER, _tier_of
    assert SNAPSHOT_TIER["method"] == "public"
    assert _tier_of("method") == "public"


def test_unlisted_non_claim_snapshot_defaults_to_full_tier():
    from src.cli import _tier_of
    assert _tier_of("some_snapshot_nobody_has_listed") == "full"
