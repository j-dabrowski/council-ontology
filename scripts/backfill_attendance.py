"""
Backfill MeetingAttendance rows for meetings already in the database, from
already-archived LLM responses (data/llm_archive/) — no new Claude API calls.

Context: councillors_present/councillors_apology have always been extracted
(present in every chunk-0 raw response) but were discarded before persistence
until docs/uplift/migration/01-known-defects.md G-09's fix landed in
save_extraction(). This script recovers attendance for meetings extracted
before that fix, without re-running extraction or touching any other table.

Deliberately narrow: unlike scripts/archive_import.py --force (which re-runs
the full save_extraction() pipeline and would touch votes/motions/tenders
too), this only ever inserts MeetingAttendance rows, matched to an existing
Meeting by minutes_pdf_path. A meeting with no archived chunk-0, or no match
in the DB, is left alone and counted as such — never invented.

Usage:
    python scripts/backfill_attendance.py [--data-dir data]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import json_repair
from rich.console import Console

console = Console()


def _strip_fences(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    return re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)


def _parse_chunk0(raw: str) -> dict | None:
    """Extract just councillors_present/councillors_apology from a chunk-0
    raw response — never validates the full ExtractedMeeting schema, so a
    change elsewhere in the document can't block attendance recovery."""
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = json.loads(json_repair.repair_json(text))
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    return {
        "present": data.get("councillors_present") or [],
        "apology": data.get("councillors_apology") or [],
    }


def _name_of(entry) -> tuple[str | None, str | None]:
    """A roster entry is either {"given_name":..,"family_name":..} or a bare
    name string ("Cr John Smith") — mirrors ExtractedCouncillor's own
    before-validator for the string case."""
    if isinstance(entry, dict):
        return entry.get("given_name"), entry.get("family_name")
    if isinstance(entry, str):
        from src.extraction.extractor import _normalise_councillor_name
        given, family = _normalise_councillor_name(entry, "")
        return given or None, family or entry
    return None, None


def run(data_dir: Path = Path("data")) -> None:
    from src.extraction.extractor import _get_or_create_councillor
    from src.models import AttendanceStatus, Meeting, MeetingAttendance
    from src.storage.database import init_db, make_session_factory

    archive_root = data_dir / "llm_archive"
    if not archive_root.exists():
        console.print(f"[red]No archive at {archive_root}[/red]")
        sys.exit(1)

    chunk_files = [
        f for f in archive_root.rglob("*.json")
        if f.name not in ("index.json", "manifest.json")
    ]
    console.print(f"[dim]Scanning {len(chunk_files)} archived chunk files...[/dim]")

    engine = init_db()
    session = make_session_factory(engine)()

    scanned = matched = already_populated = inserted_rows = unreadable = no_match = 0

    for cf in chunk_files:
        try:
            entry = json.loads(cf.read_text())
        except Exception:
            unreadable += 1
            continue
        if entry.get("chunk_idx", 0) != 0:
            continue  # only chunk 0 carries meeting-level attendance
        if entry.get("status") == "error" or not entry.get("raw_response"):
            unreadable += 1
            continue
        scanned += 1

        pdf_path = entry.get("pdf_path")
        if not pdf_path:
            no_match += 1
            continue
        meeting = session.query(Meeting).filter_by(minutes_pdf_path=str(pdf_path)).first()
        if meeting is None:
            no_match += 1
            continue

        already = session.query(MeetingAttendance).filter_by(meeting_id=meeting.id).count()
        if already:
            already_populated += 1
            continue

        parsed = _parse_chunk0(entry["raw_response"])
        if parsed is None:
            unreadable += 1
            continue
        matched += 1

        seen: set[int] = set()
        for status, roster in (
            (AttendanceStatus.PRESENT, parsed["present"]),
            (AttendanceStatus.APOLOGY, parsed["apology"]),
        ):
            for raw_entry in roster:
                given, family = _name_of(raw_entry)
                if not given and not family:
                    continue
                councillor = _get_or_create_councillor(session, given, family)
                if councillor.id in seen:
                    continue
                seen.add(councillor.id)
                session.add(MeetingAttendance(
                    meeting_id=meeting.id, councillor_id=councillor.id, status=status,
                ))
                inserted_rows += 1
        session.flush()

    session.commit()
    console.print(
        f"[bold]Done.[/bold] {scanned} chunk-0 archives scanned, {matched} matched an "
        f"existing meeting with no prior attendance ({inserted_rows} rows inserted), "
        f"{already_populated} already had attendance, {no_match} had no matching meeting "
        f"in the DB, {unreadable} unreadable/error chunks."
    )
    total_minutes = session.query(Meeting).filter_by(document_type="minutes").count()
    with_attendance = (
        session.query(Meeting.id)
        .join(MeetingAttendance, MeetingAttendance.meeting_id == Meeting.id)
        .filter(Meeting.document_type == "minutes")
        .distinct()
        .count()
    )
    console.print(
        f"[dim]Coverage: {with_attendance}/{total_minutes} minutes meetings now have "
        "at least one attendance row.[/dim]"
    )
    session.close()


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", default="data", help="Root data directory (default: data)")
    args = p.parse_args()
    run(data_dir=Path(args.data_dir))


if __name__ == "__main__":
    main()
