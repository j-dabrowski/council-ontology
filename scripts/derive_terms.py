"""
Derive approximate councillor term records from vote date spans.

Generates a seed CSV (data/{council}_terms_seed.csv) with one row per
continuous service period per councillor. A gap of > --gap-years calendar
years in voting activity triggers a split into separate rows, flagged as
a possible separate term or different person.

The generated CSV is a STARTING POINT — all rows are marked
source=derived_from_votes and notes=VERIFY. Edit the CSV to:
  - Fill in ward and role
  - Correct term_start / term_end to actual election dates
  - Split or merge rows as appropriate
  - Change source to elections_wa / council_website / manual

Then import with:
    council import-terms <council> data/<council>_terms_seed.csv

Usage:
    python scripts/derive_terms.py cambridge
    python scripts/derive_terms.py cambridge --gap-years 3
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "council.db"
DATA = Path(__file__).parent.parent / "data"


def run(council_slug: str, gap_years: int = 2) -> None:
    conn = sqlite3.connect(DB)

    council_row = conn.execute(
        "SELECT id, name FROM councils WHERE short_name = ? OR LOWER(name) LIKE ?",
        (council_slug, f"%{council_slug}%"),
    ).fetchone()
    if not council_row:
        print(f"Council not found: {council_slug!r}")
        return
    council_id, council_name = council_row
    print(f"Council: {council_name} (id={council_id})")

    # Per-councillor vote activity: sorted list of distinct active years
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.given_name,
            c.family_name,
            COUNT(v.id)                                              AS total_votes,
            GROUP_CONCAT(DISTINCT strftime('%Y', m.meeting_date))   AS active_years,
            MIN(m.meeting_date)                                      AS first_vote,
            MAX(m.meeting_date)                                      AS last_vote
        FROM councillors c
        JOIN votes v ON v.councillor_id = c.id
        JOIN motions mt ON v.motion_id = mt.id
        JOIN meetings m ON mt.meeting_id = m.id
        WHERE m.council_id = ?
        GROUP BY c.id
        ORDER BY c.family_name, c.given_name
        """,
        (council_id,),
    ).fetchall()

    out_path = DATA / f"{council_slug}_terms_seed.csv"

    total_periods = 0
    split_councillors: list[str] = []

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "councillor_id",
                "given_name",
                "family_name",
                "ward",
                "role",
                "term_start",
                "term_end",
                "source",
                "notes",
            ]
        )

        for cid, given, family, total_votes, years_str, first_vote, last_vote in rows:
            years = sorted({int(y) for y in years_str.split(",") if y.strip()})

            # Detect gaps > gap_years calendar years between consecutive active years
            splits: list[tuple[int, int]] = []  # (gap_start_year, gap_end_year)
            for i in range(1, len(years)):
                if years[i] - years[i - 1] > gap_years:
                    splits.append((years[i - 1], years[i]))

            if not splits:
                # Single continuous period
                notes = "DERIVED from vote dates — VERIFY and correct"
                writer.writerow(
                    [cid, given or "", family or "", "", "", first_vote, last_vote,
                     "derived_from_votes", notes]
                )
                total_periods += 1
            else:
                # Multiple periods — split at each gap
                split_councillors.append(
                    f"{given or ''} {family or ''} (id={cid}): "
                    + ", ".join(f"{a}→{b} ({b - a}yr)" for a, b in splits)
                )

                # Build list of (period_years) groups
                boundaries = [years[0]] + [y for pair in splits for y in pair] + [years[-1]]
                # Group into pairs: [start1, end1, start2, end2, ...]
                for idx in range(0, len(boundaries), 2):
                    p_start_year = boundaries[idx]
                    p_end_year = boundaries[idx + 1]

                    # Get first/last vote date within this year range
                    p_first, p_last = conn.execute(
                        """
                        SELECT MIN(m.meeting_date), MAX(m.meeting_date)
                        FROM votes v
                        JOIN motions mt ON v.motion_id = mt.id
                        JOIN meetings m ON mt.meeting_id = m.id
                        WHERE v.councillor_id = ?
                          AND m.council_id = ?
                          AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) BETWEEN ? AND ?
                        """,
                        (cid, council_id, p_start_year, p_end_year),
                    ).fetchone()

                    period_num = idx // 2 + 1
                    if idx // 2 < len(splits):
                        gap_note = (
                            f"POSSIBLE GAP AFTER THIS PERIOD: {splits[idx // 2][0]}→"
                            f"{splits[idx // 2][1]} ({splits[idx // 2][1] - splits[idx // 2][0]}yr) — "
                            "may be separate person or separate term"
                        )
                    else:
                        gap_note = f"period {period_num}"

                    notes = f"DERIVED from vote dates — VERIFY; {gap_note}"
                    writer.writerow(
                        [cid, given or "", family or "", "", "", p_first, p_last,
                         "derived_from_votes", notes]
                    )
                    total_periods += 1

    print(f"Written {total_periods} rows for {len(rows)} councillors to {out_path}")

    if split_councillors:
        print(f"\nSplit into multiple periods ({len(split_councillors)} councillors with gaps):")
        for s in split_councillors:
            print(f"  {s}")
        print(
            "\nFor each split councillor, check whether the periods belong to the same "
            "person (re-elected) or different people with the same surname."
        )

    print("\nNext steps:")
    print(f"  1. Edit {out_path} — fill in ward, role; correct dates to actual election dates")
    print(f"  2. council import-terms {council_slug} {out_path} --apply")
    print(f"  3. council dedup {council_slug} --use-terms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive councillor term records from vote date spans"
    )
    parser.add_argument("council", help="Council slug (e.g. cambridge)")
    parser.add_argument(
        "--gap-years",
        type=int,
        default=2,
        dest="gap_years",
        help="Gap in calendar years that triggers a period split (default: 2)",
    )
    args = parser.parse_args()
    run(args.council, gap_years=args.gap_years)


if __name__ == "__main__":
    main()
