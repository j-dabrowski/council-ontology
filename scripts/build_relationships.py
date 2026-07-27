"""
Compute voting alignment and persist ALLY/OPPONENT edges to the relationships table.

Thresholds (all configurable via CLI):
  agreement_rate >= ally_threshold AND shared_votes >= min_shared   → ALLY
  agreement_rate <= opponent_threshold AND shared_votes >= min_shared → OPPONENT

Clears existing ALLY/OPPONENT rows for the council before re-inserting, so this
is safe to re-run — it produces a fresh snapshot each time.

CLI: council build-relationships cambridge [--min-shared N] [--ally F] [--opponent F] [--dry-run]
"""

import argparse
from datetime import date

from rich.console import Console
from rich.table import Table
from sqlalchemy import select

console = Console()

DEFAULT_MIN_SHARED = 10
DEFAULT_ALLY_THRESHOLD = 0.85
DEFAULT_OPPONENT_THRESHOLD = 0.40
DEFAULT_FROM_YEAR = 2024


def run(
    council_name: str,
    min_shared: int = DEFAULT_MIN_SHARED,
    ally_threshold: float = DEFAULT_ALLY_THRESHOLD,
    opponent_threshold: float = DEFAULT_OPPONENT_THRESHOLD,
    from_year: int | None = DEFAULT_FROM_YEAR,
    to_year: int | None = None,
    dry_run: bool = False,
) -> None:
    from src.cli import COUNCILS, _get_council
    from src.storage.database import init_db, make_session_factory
    from src.models import Councillor, Meeting, Motion, Vote, Relationship, RelationshipKind
    from src.analysis.queries import voting_alignment_matrix

    key = council_name.lower()
    if key not in COUNCILS:
        raise SystemExit(f"Unknown council: {key}")

    short_name = COUNCILS[key]["short_name"]
    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id

    # Councillors who have voted in this council's meetings, keyed by full name
    stmt = (
        select(Councillor.id, Councillor.given_name, Councillor.family_name)
        .join(Vote, Vote.councillor_id == Councillor.id)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .where(Meeting.council_id == council_id)
        .distinct()
    )
    name_to_id: dict[str, int] = {}
    for cid, given, family in session.execute(stmt):
        full = f"{given or ''} {family or ''}".strip()
        name_to_id[full] = cid

    year_label = f"{from_year}+" if from_year and not to_year else \
                 f"–{to_year}" if to_year and not from_year else \
                 f"{from_year}–{to_year}" if from_year and to_year else "all years"
    alignments = voting_alignment_matrix(session, council_id, from_year=from_year, to_year=to_year)

    allies = [a for a in alignments
              if a.agreement_rate >= ally_threshold and a.total_shared_votes >= min_shared]
    opponents = [a for a in alignments
                 if a.agreement_rate <= opponent_threshold and a.total_shared_votes >= min_shared]

    today = date.today()

    # Preview table
    table = Table(title=f"Voting relationships — {short_name} ({year_label}, min_shared={min_shared})")
    table.add_column("Kind", style="bold")
    table.add_column("Councillor A")
    table.add_column("Councillor B")
    table.add_column("Agreement", justify="right")
    table.add_column("Shared votes", justify="right")

    for a in allies:
        table.add_row("ALLY", a.councillor_a, a.councillor_b,
                      f"{a.agreement_rate:.0%}", str(a.total_shared_votes), style="green")
    for a in sorted(opponents, key=lambda x: x.agreement_rate):
        table.add_row("OPPONENT", a.councillor_a, a.councillor_b,
                      f"{a.agreement_rate:.0%}", str(a.total_shared_votes), style="red")

    console.print(table)
    console.print(f"\n{len(allies)} ally pairs, {len(opponents)} opponent pairs "
                  f"(of {len(alignments)} total pairs with any shared votes)")

    if dry_run:
        console.print("[yellow]--dry-run: no changes written[/yellow]")
        return

    # Clear existing ALLY/OPPONENT edges for this council's councillors
    existing = session.query(Relationship).filter(
        Relationship.kind.in_([RelationshipKind.ALLY, RelationshipKind.OPPONENT]),
        Relationship.source_type == "councillors",
        Relationship.target_type == "councillors",
    ).all()
    councillor_ids = set(name_to_id.values())
    to_delete = [r for r in existing
                 if r.source_id in councillor_ids or r.target_id in councillor_ids]
    for r in to_delete:
        session.delete(r)
    session.flush()

    # Insert new edges
    inserted = 0
    skipped = 0
    for a, kind in [(a, RelationshipKind.ALLY) for a in allies] + \
                   [(a, RelationshipKind.OPPONENT) for a in opponents]:
        src_id = name_to_id.get(a.councillor_a)
        tgt_id = name_to_id.get(a.councillor_b)
        if src_id is None or tgt_id is None:
            console.print(f"[yellow]Skipping {a.councillor_a} / {a.councillor_b} — name not found in councillors table[/yellow]")
            skipped += 1
            continue
        edge = Relationship(
            kind=kind,
            source_type="councillors",
            source_id=src_id,
            target_type="councillors",
            target_id=tgt_id,
            weight=a.agreement_rate,
            evidence=f"{a.agreements}/{a.total_shared_votes} shared votes",
            observed_at=today,
        )
        session.add(edge)
        inserted += 1

    session.commit()
    console.print(f"\n[green]Wrote {inserted} relationship edges[/green]"
                  + (f" ({skipped} skipped — name mismatch)" if skipped else ""))


def main():
    parser = argparse.ArgumentParser(description="Build ALLY/OPPONENT relationship edges from voting alignment")
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--min-shared", type=int, default=DEFAULT_MIN_SHARED,
                        help=f"Minimum shared votes to qualify (default: {DEFAULT_MIN_SHARED})")
    parser.add_argument("--ally", type=float, default=DEFAULT_ALLY_THRESHOLD,
                        help=f"Agreement rate threshold for ALLY (default: {DEFAULT_ALLY_THRESHOLD})")
    parser.add_argument("--opponent", type=float, default=DEFAULT_OPPONENT_THRESHOLD,
                        help=f"Agreement rate threshold for OPPONENT (default: {DEFAULT_OPPONENT_THRESHOLD})")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year",
                        help=f"Only include votes from this year onwards (default: {DEFAULT_FROM_YEAR})")
    parser.add_argument("--to-year", type=int, default=None, dest="to_year",
                        help="Only include votes up to this year (default: no limit)")
    parser.add_argument("--all-years", action="store_true", dest="all_years",
                        help="Include all years (overrides --from-year)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    from_year = None if args.all_years else args.from_year
    run(args.council, min_shared=args.min_shared, ally_threshold=args.ally,
        opponent_threshold=args.opponent, from_year=from_year, to_year=args.to_year,
        dry_run=args.dry_run)


if __name__ == "__main__":
    main()
