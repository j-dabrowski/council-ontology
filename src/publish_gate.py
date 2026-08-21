"""
The draft → publish gate.

`council draft` writes candidate snapshots to data/draft/<council>/<run_id>/
for review (investigator + a defamation-auditor pass). `council publish` is
the only thing allowed to copy that output into frontend/public/data/ (the
public, git-tracked, Vercel-served directory), and only after this module
says the draft is cleared.

This module is the seam between the two. `check_clearance` supports two gate
profiles:

- `"interactive"` (default) — a human-supplied `--confirm` note, 10+
  characters, vouching for the draft. This is still exactly the minimal stub
  it always was — a real name/length check, nothing more.
- `"auto"` — a real, code-enforced gate: it independently re-validates the
  Editor role's own on-disk PASS record (a `defamation_review_<n>.json`
  sidecar in the draft directory — see `docs/review/editor/Editor_prompt.txt`)
  against the exact draft being published, rather than trusting any caller's
  say-so. See `docs/review/CONDUCTOR.md`'s "Gate profiles" section for what
  this guarantee does and doesn't cover.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DraftManifest:
    run_id: str
    council: str
    generated_at: str
    snapshots: list[str]
    file_hashes: dict[str, str]  # snapshot name -> sha256 of its JSON file's bytes
    tiers: dict[str, str]  # snapshot name -> "public" | "full"


@dataclass
class ClearanceResult:
    cleared: bool
    reason: str


def snapshot_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_draft_manifest(draft_dir: Path) -> DraftManifest:
    manifest_path = draft_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest.json in {draft_dir} — is this a `council draft` output directory?"
        )
    data = json.loads(manifest_path.read_text())
    return DraftManifest(
        run_id=data["run_id"],
        council=data["council"],
        generated_at=data["generated_at"],
        snapshots=data["snapshots"],
        file_hashes=data["file_hashes"],
        tiers=data["tiers"],
    )


def verify_draft_integrity(draft_dir: Path, manifest: DraftManifest) -> list[str]:
    """Return snapshot names whose on-disk hash no longer matches the draft
    manifest — tampering or drift since the draft was reviewed. Empty list
    means every file is exactly what was hashed at draft time."""
    drifted: list[str] = []
    for name in manifest.snapshots:
        path = draft_dir / f"{name}.json"
        if not path.exists():
            drifted.append(name)
            continue
        if snapshot_hash(path) != manifest.file_hashes.get(name):
            drifted.append(name)
    return drifted


def _latest_review_record(draft_dir: Path) -> Path | None:
    """The highest-pass-numbered defamation_review_<n>.json in draft_dir, if any."""
    candidates = list(draft_dir.glob("defamation_review_*.json"))
    if not candidates:
        return None

    def _pass_num(p: Path) -> int:
        try:
            return int(p.stem.rsplit("_", 1)[-1])
        except ValueError:
            return -1

    return max(candidates, key=_pass_num)


def check_clearance(
    draft_dir: Path,
    confirm_note: str | None,
    run_id: str,
    gate_profile: str = "interactive",
) -> ClearanceResult:
    """The gate itself. See module docstring for what each gate_profile means.

    `run_id` is always required (even though `interactive` mode ignores it)
    so callers can't accidentally omit the one piece of information `auto`
    mode needs to prove a clearance record is actually about the draft being
    published, not just any PASS record sitting in the directory.
    """
    if gate_profile not in ("interactive", "auto"):
        raise ValueError(f"unknown gate_profile: {gate_profile!r}")

    if gate_profile == "interactive":
        note = (confirm_note or "").strip()
        if not note:
            return ClearanceResult(cleared=False, reason="no --confirm note provided")
        if len(note) < 10:
            return ClearanceResult(
                cleared=False,
                reason="--confirm note too short to be a real review signal (need 10+ characters)",
            )
        return ClearanceResult(cleared=True, reason="human-confirmed (interactive gate profile)")

    # gate_profile == "auto"
    latest = _latest_review_record(draft_dir)
    if latest is None:
        return ClearanceResult(
            cleared=False,
            reason=(
                "auto gate profile: no defamation_review_<n>.json clearance record "
                f"found in {draft_dir} — auto mode requires a real Editor PASS record, "
                "not just a flag"
            ),
        )

    try:
        record = json.loads(latest.read_text())
    except json.JSONDecodeError as exc:
        return ClearanceResult(
            cleared=False,
            reason=f"auto gate profile: {latest.name} is not valid JSON ({exc})",
        )

    if record.get("run_id") != run_id:
        return ClearanceResult(
            cleared=False,
            reason=(
                f"auto gate profile: {latest.name} run_id "
                f"({record.get('run_id')!r}) does not match the draft being "
                f"published ({run_id!r})"
            ),
        )
    if record.get("status") != "PASS":
        return ClearanceResult(
            cleared=False,
            reason=(
                f"auto gate profile: latest Editor pass ({latest.name}) is "
                f"{record.get('status')!r}, not PASS"
            ),
        )
    if record.get("tracks"):
        return ClearanceResult(
            cleared=False,
            reason=(
                f"auto gate profile: {latest.name} is PASS but lists tracks "
                f"{record.get('tracks')!r} — a real PASS always carries empty "
                "tracks, so this is treated as an inconsistent record, not "
                "given the benefit of the doubt"
            ),
        )

    return ClearanceResult(
        cleared=True,
        reason=f"auto-cleared — {latest.name}: Editor pass {record.get('pass')} PASS",
    )
