"""
Import councillor term records from a CSV into the councillor_terms table.

Accepts two CSV formats:

1. Terms format (from derive_terms.py or hand-edited):
     councillor_id, given_name, family_name, ward, role,
     term_start, term_end, source, notes

2. Elections format (from extract_<council>_elections.py):
     election_date, ward, role, given_name, family_name, elected, votes
   Auto-detected when election_date + elected columns are present.
   Non-elected rows are silently skipped. term_start = election_date;
   term_end = election_date + 4 years (approximate WA 4-year term), or
   None if the calculated end date is still in the future (still serving).
   source defaults to "elections_wa".

councillor_id takes precedence over name matching. If both are present and
disagree, councillor_id wins and a warning is printed.

Name matching: exact match attempted first, then first-given-name-only fallback
(handles "Alan John Langer" → "Alan Langer", "Gary Norman Mack" → "Gary Mack").
Middle names and parentheticals are stripped in the fallback.

Existing terms for each affected councillor+council pair are REPLACED.
This makes the import idempotent — re-run after editing the CSV.

Usage:
    council import-terms cambridge data/cambridge_elections_raw.csv      # dry run
    council import-terms cambridge data/cambridge_elections_raw.csv --apply
    council import-terms cambridge data/cambridge_terms_seed.csv --apply
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import date
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "council.db"

_REQUIRED = {"councillor_id", "given_name", "family_name", "term_start", "term_end"}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add source/notes columns to councillor_terms if they don't exist yet."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(councillor_terms)")}
    if "source" not in existing:
        conn.execute("ALTER TABLE councillor_terms ADD COLUMN source TEXT")
    if "notes" not in existing:
        conn.execute("ALTER TABLE councillor_terms ADD COLUMN notes TEXT")
    conn.commit()


def run(council_slug: str, csv_path: Path, apply: bool = False) -> None:
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL")

    council_row = conn.execute(
        "SELECT id, name FROM councils WHERE short_name = ? OR LOWER(name) LIKE ?",
        (council_slug, f"%{council_slug}%"),
    ).fetchone()
    if not council_row:
        print(f"Council not found: {council_slug!r}")
        return
    council_id, council_name = council_row
    print(f"Council: {council_name} (id={council_id})")

    # Build a name→id lookup for fallback matching
    name_index: dict[tuple[str, str], int] = {
        (r[1].strip().lower(), r[2].strip().lower()): r[0]
        for r in conn.execute("SELECT id, given_name, family_name FROM councillors")
    }

    valid_rows: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    skipped_non_elected = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("Empty or header-less CSV.")
            return

        fields = set(reader.fieldnames or [])
        elections_format = "election_date" in fields and "elected" in fields
        if elections_format:
            print("Detected elections format (election_date + elected columns).")

        today = date.today()

        for row_num, row in enumerate(reader, 2):
            # Elections format: skip non-elected candidates silently
            if elections_format:
                if row.get("elected", "").strip().upper() != "TRUE":
                    skipped_non_elected += 1
                    continue

            cid_raw = row.get("councillor_id", "").strip()
            given = row.get("given_name", "").strip()
            family = row.get("family_name", "").strip()

            resolved_id: int | None = None

            # Resolve by ID first
            if cid_raw and cid_raw.isdigit():
                rec = conn.execute(
                    "SELECT id, given_name, family_name FROM councillors WHERE id = ?",
                    (int(cid_raw),),
                ).fetchone()
                if rec:
                    resolved_id = rec[0]
                    # Warn if name doesn't match
                    if given and family:
                        rec_name = (rec[1] or "").strip().lower(), (rec[2] or "").strip().lower()
                        if rec_name != (given.lower(), family.lower()):
                            warnings.append(
                                f"  Row {row_num}: id={cid_raw} is {rec[1]} {rec[2]}, "
                                f"not {given} {family} — using id"
                            )
                else:
                    errors.append(f"  Row {row_num}: councillor_id={cid_raw} not found")
                    continue

            # Fallback: name lookup with progressive relaxation
            if resolved_id is None:
                if given and family:
                    resolved_id = name_index.get((given.lower(), family.lower()))
                    if resolved_id is None:
                        # Strip middle names and parentheticals: "Alan John" → "alan",
                        # "Gary Norman" → "gary", "Catherine (Kate)" → "catherine"
                        first_given = given.split()[0].strip("()")
                        resolved_id = name_index.get((first_given.lower(), family.lower()))
                        if resolved_id is not None:
                            warnings.append(
                                f"  Row {row_num}: matched '{given} {family}' "
                                f"as '{first_given} {family}' (middle name stripped)"
                            )
                    if resolved_id is None:
                        errors.append(
                            f"  Row {row_num}: no match for '{given} {family}'"
                        )
                        continue
                else:
                    errors.append(
                        f"  Row {row_num}: need councillor_id or given_name+family_name"
                    )
                    continue

            # Derive term dates
            if elections_format:
                election_date_str = row.get("election_date", "").strip()
                if election_date_str:
                    ed = date.fromisoformat(election_date_str)
                    term_start = election_date_str
                    # Approximate 4-year WA LG term; leave open if still in the future
                    approx_end = date(ed.year + 4, ed.month, ed.day)
                    term_end = None if approx_end > today else approx_end.isoformat()
                else:
                    term_start = None
                    term_end = None
                source = "elections_wa"
                notes = None
            else:
                term_start = row.get("term_start", "").strip() or None
                term_end = row.get("term_end", "").strip() or None
                source = row.get("source", "manual").strip() or "manual"
                notes = row.get("notes", "").strip() or None

            ward = row.get("ward", "").strip() or None
            role = row.get("role", "").strip() or None

            valid_rows.append(
                {
                    "councillor_id": resolved_id,
                    "council_id": council_id,
                    "ward": ward,
                    "role": role,
                    "term_start": term_start,
                    "term_end": term_end,
                    "source": source,
                    "notes": notes,
                }
            )

    if elections_format and skipped_non_elected:
        print(f"Skipped {skipped_non_elected} non-elected candidates.")

    # Report
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(w)

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(e)

    print(f"\nRows: {len(valid_rows)} valid, {len(errors)} errors")

    if not valid_rows:
        print("Nothing to import.")
        return

    # Build display name lookup
    name_lookup = {
        r[0]: f"{r[1] or ''} {r[2] or ''}".strip()
        for r in conn.execute("SELECT id, given_name, family_name FROM councillors")
    }

    print(f"\n{'[DRY RUN] ' if not apply else ''}Terms to import:")
    for r in valid_rows:
        name = name_lookup.get(r["councillor_id"], f"id={r['councillor_id']}")
        role_str = r["role"] or "—"
        ward_str = r["ward"] or "—"
        start_str = r["term_start"] or "?"
        end_str = r["term_end"] or "present"
        src = r["source"]
        print(f"  [{r['councillor_id']}] {name:30s}  {ward_str:15s}  {role_str:15s}  {start_str} → {end_str}  [{src}]")

    if not apply:
        print(f"\n[DRY RUN] Pass --apply to write changes to DB.\n")
        return

    _ensure_columns(conn)

    # Group by councillor_id to delete-then-insert per councillor
    affected_ids = sorted({r["councillor_id"] for r in valid_rows})
    placeholders = ",".join("?" * len(affected_ids))
    deleted = conn.execute(
        f"DELETE FROM councillor_terms WHERE council_id = ? AND councillor_id IN ({placeholders})",
        (council_id, *affected_ids),
    ).rowcount

    for r in valid_rows:
        conn.execute(
            """
            INSERT INTO councillor_terms
                (councillor_id, council_id, ward, role, term_start, term_end, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["councillor_id"], r["council_id"],
                r["ward"], r["role"],
                r["term_start"], r["term_end"],
                r["source"], r["notes"],
            ),
        )

    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM councillor_terms").fetchone()[0]
    print(
        f"\nDone. Replaced {deleted} existing term records; inserted {len(valid_rows)} rows. "
        f"Total terms in DB: {after}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import councillor term records from CSV into councillor_terms"
    )
    parser.add_argument("council", help="Council slug (e.g. cambridge)")
    parser.add_argument("csv", type=Path, help="Path to terms CSV")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to DB (default: dry run)",
    )
    args = parser.parse_args()
    run(args.council, args.csv, apply=args.apply)


if __name__ == "__main__":
    main()
