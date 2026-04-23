"""
council-ontology CLI

Commands:
  run <council>      Full pipeline: scrape → extract → save to DB
  scrape <council>   Discover and download PDFs only
  extract <council>  Process already-downloaded PDFs (no HTTP)
  status             Show DB summary across all councils
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

console = Console()
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry: add new councils here
# ---------------------------------------------------------------------------

COUNCILS = {
    "cambridge": {
        "short_name": "Cambridge",
        "scraper": "src.scraper.cambridge:CambridgeScraper",
    },
}


def _get_scraper(council_key: str, since_year: int | None = None):
    entry = COUNCILS[council_key]
    module_path, cls_name = entry["scraper"].split(":")
    import importlib
    mod = importlib.import_module(module_path)
    kwargs = {"since_year": since_year} if since_year is not None else {}
    return getattr(mod, cls_name)(**kwargs)


def _get_council(session, short_name: str):
    from src.models import Council
    obj = session.query(Council).filter_by(short_name=short_name).first()
    if obj is None:
        raise SystemExit(
            f"[red]Council '{short_name}' not found in DB. Run init first.[/red]"
        )
    return obj


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _filter_pdfs_by_year(
    pdfs: list,
    manifest: dict,
    from_year: int | None,
    to_year: int | None,
) -> tuple[list, int]:
    """
    Filter a PDF list to those whose manifest date falls within [from_year, to_year].
    PDFs not in the manifest (no known date) are excluded when any filter is active.

    Returns (filtered_list, n_excluded_no_date).
    """
    if not from_year and not to_year:
        return pdfs, 0
    filtered = []
    n_no_date = 0
    for pdf in pdfs:
        date_str = manifest.get(pdf.name, {}).get("meeting_date", "")
        if not date_str:
            n_no_date += 1
            continue
        try:
            year = int(date_str[:4])
        except ValueError:
            n_no_date += 1
            continue
        if from_year and year < from_year:
            continue
        if to_year and year > to_year:
            continue
        filtered.append(pdf)
    return filtered, n_no_date


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_scrape(args) -> None:
    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}. Available: {', '.join(COUNCILS)}[/red]")
        sys.exit(1)

    console.print(Panel(f"Scraping [bold]{key}[/bold] (since {args.since_year})", style="blue"))
    scraper = _get_scraper(key, since_year=args.since_year)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Discovering documents...", total=None)
        result = scraper.run(download_pdfs=True)
        progress.update(task, total=len(result.documents), completed=len(result.documents))

    ok = [d for d in result.documents if d.local_path]
    console.print(f"[green]Downloaded {len(ok)}/{len(result.documents)} documents[/green]")
    if result.errors:
        for err in result.errors:
            console.print(f"  [yellow]Warning:[/yellow] {err}")

    _print_docs_table(result.documents)


def cmd_extract(args) -> None:
    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    short_name = COUNCILS[key]["short_name"]
    raw_dir = Path("data/raw") / key

    import json as _json
    from src.extraction.extractor import MinutesExtractor, save_extraction
    from src.storage.database import init_db, make_session_factory

    # Load scraper manifest for meeting dates (written during scrape/run)
    manifest_path = raw_dir / "manifest.json"
    manifest = _json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    if getattr(args, "files", None):
        # Targeted mode: process only the specified PDFs; ignore date filters and limit
        pdfs = []
        for f in args.files:
            pdf_path = raw_dir / Path(f).name
            if pdf_path.exists():
                pdfs.append(pdf_path)
            else:
                console.print(f"  [yellow]Warning: {Path(f).name} not found in {raw_dir}[/yellow]")
        if not pdfs:
            console.print("[red]No valid PDF files found.[/red]")
            sys.exit(1)
        console.print(f"[dim]Targeted mode: {len(pdfs)} specific file(s)[/dim]")
    else:
        # Normal mode: scan directory, apply date filter, then limit
        pdfs = sorted(raw_dir.glob("*.pdf"))
        if not pdfs:
            console.print(f"[yellow]No PDFs found in {raw_dir}. Run 'scrape' first.[/yellow]")
            sys.exit(0)

        from_year = getattr(args, "from_year", None)
        to_year = getattr(args, "to_year", None)
        pdfs, n_no_date = _filter_pdfs_by_year(pdfs, manifest, from_year, to_year)
        if from_year or to_year:
            yr_range = f"{from_year or '∞'}–{to_year or '∞'}"
            console.print(f"[dim]Date filter {yr_range}: {len(pdfs)} PDFs match"
                          + (f" ({n_no_date} skipped — no manifest date)" if n_no_date else "") + "[/dim]")

        if args.limit:
            pdfs = pdfs[: args.limit]

    console.print(Panel(f"Extracting [bold]{len(pdfs)}[/bold] PDFs for [bold]{key}[/bold]", style="blue"))

    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    council_full_name = council.name
    extractor = MinutesExtractor()

    succeeded = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting...", total=len(pdfs))

        from src.models import Meeting as _Meeting
        skipped = 0

        for pdf in pdfs:
            progress.update(task, description=f"[cyan]{pdf.name}[/cyan]")
            if not args.force:
                existing = session.query(_Meeting).filter_by(minutes_pdf_path=str(pdf)).first()
                if existing:
                    console.print(f"  [dim]–[/dim] {pdf.name} already extracted (meeting {existing.id}), skipping")
                    _log.info("SKIP: %s (meeting %d)", pdf.name, existing.id)
                    skipped += 1
                    progress.advance(task)
                    continue
            meta = manifest.get(pdf.name, {})
            meeting_date_hint = meta.get("meeting_date")
            try:
                extracted = extractor.extract_from_pdf(
                    pdf,
                    council_name=council_full_name,
                    meeting_date_hint=meeting_date_hint,
                )
                meeting_id = save_extraction(session, council_id, extracted, pdf)
                msg = f"{pdf.name} → meeting {meeting_id} ({extracted.meeting_date}, {len(extracted.motions)} motions)"
                console.print(f"  [green]✓[/green] {msg}")
                _log.info("OK: %s", msg)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                console.print(f"  [red]✗[/red] {pdf.name}: {exc}")
                _log.error("FAIL: %s: %s", pdf.name, exc)
                failed += 1
            finally:
                progress.advance(task)

    session.close()
    console.print(
        f"\n[bold]Done:[/bold] {succeeded} extracted, {failed} failed, {skipped} skipped"
    )
    _log.info("Done: %d extracted, %d failed, %d skipped", succeeded, failed, skipped)


def cmd_run(args) -> None:
    """Full pipeline: scrape then extract."""
    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    short_name = COUNCILS[key]["short_name"]
    console.print(Panel(f"Full pipeline for [bold]{short_name}[/bold] (since {args.since_year})", style="bold blue"))

    # --- Scrape ---
    console.rule("[blue]Step 1 / 2 — Scrape[/blue]")
    scraper = _get_scraper(key, since_year=args.since_year)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as p:
        t = p.add_task("Discovering and downloading minutes PDFs...")
        result = scraper.run(download_pdfs=True)
        p.update(t, completed=True)

    pdfs_downloaded = [d for d in result.documents if d.local_path]
    console.print(f"[green]Downloaded {len(pdfs_downloaded)} PDFs[/green]")
    if result.errors:
        for err in result.errors:
            console.print(f"  [yellow]Warning:[/yellow] {err}")

    # Limit if requested
    if args.limit:
        pdfs_downloaded = pdfs_downloaded[: args.limit]
        console.print(f"[dim]Limiting to {args.limit} PDFs[/dim]")

    if not pdfs_downloaded:
        console.print("[yellow]No PDFs to extract. Exiting.[/yellow]")
        return

    # --- Extract ---
    console.rule("[blue]Step 2 / 2 — Extract & Save[/blue]")

    from src.extraction.extractor import MinutesExtractor, save_extraction
    from src.storage.database import init_db, make_session_factory

    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    council_full_name = council.name
    extractor = MinutesExtractor()

    succeeded = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting...", total=len(pdfs_downloaded))

        for doc in pdfs_downloaded:
            pdf = doc.local_path
            progress.update(task, description=f"[cyan]{pdf.name}[/cyan]")
            try:
                extracted = extractor.extract_from_pdf(pdf, council_name=council_full_name)
                meeting_id = save_extraction(session, council_id, extracted, pdf)
                msg = f"{pdf.name} → meeting {meeting_id} ({extracted.meeting_date}, {len(extracted.motions)} motions)"
                console.print(f"  [green]✓[/green] {msg}")
                _log.info("OK: %s", msg)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                console.print(f"  [red]✗[/red] {pdf.name}: {exc}")
                _log.error("FAIL: %s: %s", pdf.name, exc)
                failed += 1
            finally:
                progress.advance(task)

    session.close()
    console.print(f"\n[bold green]Pipeline complete:[/bold green] {succeeded} meetings saved, {failed} failed")
    _log.info("Done: %d extracted, %d failed", succeeded, failed)


def cmd_status(args) -> None:  # noqa: ARG001
    import json as _json
    from collections import Counter
    from src.models import Councillor, Meeting, Motion, Vote
    from src.storage.database import init_db, make_session_factory

    engine = init_db()
    session = make_session_factory(engine)()

    from src.models import Council
    councils = session.query(Council).all()

    if not councils:
        console.print("[yellow]No councils in database.[/yellow]")
        return

    for council in councils:
        key = council.short_name.lower()
        raw_dir = Path("data/raw") / key
        manifest_path = raw_dir / "manifest.json"
        manifest = _json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

        n_pdfs = len(list(raw_dir.glob("*.pdf"))) if raw_dir.exists() else 0
        n_ingested = session.query(Meeting).filter(
            Meeting.council_id == council.id,
            Meeting.minutes_pdf_path.isnot(None),
        ).count()

        # Build per-year breakdown from manifest
        by_year: dict[str, Counter] = {}
        for meta in manifest.values():
            year = (meta.get("meeting_date") or "")[:4]
            if not year:
                continue
            mt = meta.get("meeting_type", "unknown")
            by_year.setdefault(year, Counter())[mt] += 1

        # Per-year ingested counts from DB
        from sqlalchemy import func, extract
        ingested_by_year: dict[str, int] = {
            str(int(row[0])): row[1]
            for row in session.query(
                extract("year", Meeting.meeting_date),
                func.count(Meeting.id),
            )
            .filter(
                Meeting.council_id == council.id,
                Meeting.minutes_pdf_path.isnot(None),
            )
            .group_by(extract("year", Meeting.meeting_date))
            .all()
        }

        # Pipeline summary
        pipeline_table = Table(
            title=f"{council.name} — Pipeline Status",
            show_lines=False,
            box=None,
            pad_edge=False,
        )
        pipeline_table.add_column("", style="dim")
        pipeline_table.add_column("", justify="right")
        pipeline_table.add_row("Downloaded", str(n_pdfs))
        pipeline_table.add_row("In manifest", str(len(manifest)))
        pipeline_table.add_row("Ingested in DB", str(n_ingested))
        pipeline_table.add_row("[yellow]Pending extraction[/yellow]", f"[yellow]{n_pdfs - n_ingested}[/yellow]")
        console.print(pipeline_table)
        console.print()

        # Per-year breakdown
        year_table = Table(
            title=f"{council.name} — Downloaded by Year",
            show_lines=False,
        )
        year_table.add_column("Year", style="bold", justify="right")
        year_table.add_column("Total", justify="right")
        year_table.add_column("Ingested", justify="right")
        year_table.add_column("Meeting types (downloaded)")

        for year in sorted(by_year):
            total = sum(by_year[year].values())
            ingested = ingested_by_year.get(year, 0)
            types_str = "  ".join(
                f"{mt} [dim]×{n}[/dim]"
                for mt, n in sorted(by_year[year].items(), key=lambda x: -x[1])
            )
            ingested_cell = (
                f"[green]{ingested}[/green]"
                if ingested >= total
                else f"[yellow]{ingested}[/yellow]"
                if ingested > 0
                else "[dim]0[/dim]"
            )
            year_table.add_row(year, str(total), ingested_cell, types_str)

        console.print(year_table)
        console.print()

        # DB detail
        n_motions = (
            session.query(Motion).join(Meeting)
            .filter(Meeting.council_id == council.id).count()
        )
        n_votes = (
            session.query(Vote).join(Motion).join(Meeting)
            .filter(Meeting.council_id == council.id).count()
        )
        n_councillors = (
            session.query(Councillor).join(Vote).join(Motion).join(Meeting)
            .filter(Meeting.council_id == council.id).distinct().count()
        )
        earliest = (
            session.query(Meeting.meeting_date)
            .filter_by(council_id=council.id)
            .order_by(Meeting.meeting_date).limit(1).scalar()
        )
        latest = (
            session.query(Meeting.meeting_date)
            .filter_by(council_id=council.id)
            .order_by(Meeting.meeting_date.desc()).limit(1).scalar()
        )
        db_table = Table(title=f"{council.name} — Database Detail", show_lines=False, box=None, pad_edge=False)
        db_table.add_column("", style="dim")
        db_table.add_column("", justify="right")
        db_table.add_row("Meetings ingested", str(n_ingested))
        db_table.add_row("Motions extracted", str(n_motions))
        db_table.add_row("Votes recorded", str(n_votes))
        db_table.add_row("Councillors seen", str(n_councillors))
        db_table.add_row("Date range", f"{earliest} – {latest}" if earliest else "—")
        console.print(db_table)

    session.close()


def cmd_docs(args) -> None:
    import json as _json
    from src.models import Meeting
    from src.storage.database import init_db, make_session_factory

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    raw_dir = Path("data/raw") / key
    if not raw_dir.exists():
        console.print(f"[yellow]No raw directory for {key}. Run 'scrape' first.[/yellow]")
        sys.exit(0)

    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        console.print(f"[yellow]No PDFs found in {raw_dir}.[/yellow]")
        sys.exit(0)

    manifest_path = raw_dir / "manifest.json"
    manifest = _json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    engine = init_db()
    session = make_session_factory(engine)()

    # Build lookup: filename → meeting row
    db_by_filename = {}
    for meeting in session.query(Meeting).filter(Meeting.minutes_pdf_path.isnot(None)).all():
        fname = Path(meeting.minutes_pdf_path).name
        db_by_filename[fname] = meeting
    session.close()

    table = Table(
        title=f"{COUNCILS[key]['short_name']} — Document Status ({len(pdfs)} PDFs)",
        show_lines=False,
    )
    table.add_column("File", style="dim")
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("Manifest", justify="center")
    table.add_column("DB", justify="center")
    table.add_column("Meeting ID", justify="right")

    counts = {"manifest": 0, "db": 0}
    for pdf in pdfs:
        meta = manifest.get(pdf.name, {})
        meeting = db_by_filename.get(pdf.name)
        in_manifest = bool(meta)
        in_db = meeting is not None
        if in_manifest:
            counts["manifest"] += 1
        if in_db:
            counts["db"] += 1

        if args.filter == "pending" and in_db:
            continue
        if args.filter == "ingested" and not in_db:
            continue
        if args.filter == "no-manifest" and in_manifest:
            continue

        table.add_row(
            pdf.name,
            meta.get("meeting_date", "[dim]unknown[/dim]"),
            meta.get("meeting_type", "[dim]unknown[/dim]"),
            "[green]✓[/green]" if in_manifest else "[dim]–[/dim]",
            "[green]✓[/green]" if in_db else "[yellow]pending[/yellow]",
            str(meeting.id) if meeting else "",
        )

    console.print(table)
    console.print(
        f"[bold]Summary:[/bold] {len(pdfs)} downloaded · "
        f"{counts['manifest']} in manifest · "
        f"{counts['db']} ingested · "
        f"[yellow]{len(pdfs) - counts['db']} pending extraction[/yellow]"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_docs_table(docs) -> None:
    if not docs:
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("File")
    table.add_column("Status")
    for doc in docs[:30]:
        table.add_row(
            str(doc.meeting_date),
            doc.meeting_type,
            doc.local_path.name if doc.local_path else "—",
            "[green]OK[/green]" if doc.local_path else "[red]FAIL[/red]",
        )
    if len(docs) > 30:
        table.add_row("...", "...", f"(+{len(docs)-30} more)", "")
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    log_file = Path("council.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    rich_handler = RichHandler(console=console, show_path=False, rich_tracebacks=True)
    rich_handler.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(rich_handler)
    root.addHandler(file_handler)
    # Suppress verbose debug logs from HTTP/API client libraries
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Surface INFO from our own modules when --verbose
    logger = logging.getLogger("src")

    parser = argparse.ArgumentParser(
        prog="council",
        description="council-ontology — scrape, extract, and analyse Perth council minutes",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Full pipeline: scrape → extract → save")
    p_run.add_argument("council", choices=list(COUNCILS), help="Council to process")
    p_run.add_argument("--limit", type=int, metavar="N", help="Process at most N PDFs")
    p_run.add_argument("--since-year", type=int, metavar="YYYY", default=2020,
                       dest="since_year", help="Only include meetings from this year (default: 2020)")
    p_run.set_defaults(func=cmd_run)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Discover and download PDFs only")
    p_scrape.add_argument("council", choices=list(COUNCILS))
    p_scrape.add_argument("--since-year", type=int, metavar="YYYY", default=2020,
                          dest="since_year", help="Only include meetings from this year (default: 2020)")
    p_scrape.set_defaults(func=cmd_scrape)

    # extract
    p_extract = sub.add_parser("extract", help="Extract already-downloaded PDFs")
    p_extract.add_argument("council", choices=list(COUNCILS))
    p_extract.add_argument("--limit", type=int, metavar="N", help="Process at most N PDFs")
    p_extract.add_argument("--from-year", type=int, metavar="YYYY", dest="from_year",
                           help="Only extract meetings from this year onward (uses manifest date)")
    p_extract.add_argument("--to-year", type=int, metavar="YYYY", dest="to_year",
                           help="Only extract meetings up to and including this year")
    p_extract.add_argument("--files", nargs="+", metavar="PDF",
                           help="Process only these specific PDFs (basenames); ignores --limit and date filters")
    p_extract.add_argument("--force", action="store_true", help="Re-extract already-extracted PDFs")
    p_extract.set_defaults(func=cmd_extract)

    # status
    p_status = sub.add_parser("status", help="Show pipeline and DB summary")
    p_status.set_defaults(func=cmd_status)

    # docs
    p_docs = sub.add_parser("docs", help="Show per-document download/extraction status")
    p_docs.add_argument("council", choices=list(COUNCILS))
    p_docs.add_argument(
        "--filter",
        choices=["all", "pending", "ingested", "no-manifest"],
        default="all",
        help="Filter: all (default), pending (not yet in DB), ingested, no-manifest",
    )
    p_docs.set_defaults(func=cmd_docs)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    args.func(args)


if __name__ == "__main__":
    main()
