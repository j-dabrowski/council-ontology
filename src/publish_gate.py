"""
The draft → publish gate.

`council draft` writes candidate snapshots to data/draft/<council>/<run_id>/
for review (investigator + a defamation-auditor pass, built separately).
`council publish` is the only thing allowed to copy that output into
frontend/public/data/ (the public, git-tracked, Vercel-served directory), and
only after this module says the draft is cleared.

This module is the seam between the two: a clearly-named, deliberately
minimal interface so the auditor project has one obvious place to plug in.
Today `check_clearance` is satisfied by an explicit human --confirm note —
real, but a placeholder for actual automated review. Don't extend its
internals speculatively; confirm the auditor's actual clearance-record shape
with that session first.
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


def check_clearance(_draft_dir: Path, confirm_note: str | None) -> ClearanceResult:
    """STUB — the gate the defamation-auditor eventually plugs into.

    Today: cleared iff confirm_note is a real, non-trivial string (a human
    explicitly vouching for this draft — not just a flag). `_draft_dir` is
    accepted but unused for now; it's there so a future implementation can
    read an auditor-written clearance record from the draft directory
    instead of (or in addition to) trusting free text. Don't build that
    lookup yet — the auditor's actual output format isn't decided.
    """
    note = (confirm_note or "").strip()
    if not note:
        return ClearanceResult(cleared=False, reason="no --confirm note provided")
    if len(note) < 10:
        return ClearanceResult(
            cleared=False,
            reason="--confirm note too short to be a real review signal (need 10+ characters)",
        )
    return ClearanceResult(
        cleared=True,
        reason="human-confirmed — no automated defamation-auditor gate wired up yet",
    )
