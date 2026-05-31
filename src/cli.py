"""
council-ontology CLI

Pipeline commands:
  scrape <council>          Discover and download PDFs only
  census <council>          Level 0: keyword scan across all PDFs
  inventory <council>       Level 1: cheap LLM inventory (Haiku)
  typology <council>        Level 1→2: corpus typology report
  sample <council>          Level 3a: stratified sample selection
  extract-sample <council>  Level 3b: extract the saved sample
  validate-sample <council> Level 3c: validate sample extractions
  extract <council>         Level 5: extract all/pending PDFs
  validate <council>        Level 4: per-doc confidence scoring

Other commands:
  status    DB summary across all councils
  docs      Per-document download/extraction status
  compare   Side-by-side model comparison for one PDF (dev tool)
  costs     Estimate extraction API costs
  analyse   Analysis queries against the DB
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


def _parse_max_chars(value: str) -> "int | None":
    """Argparse type for --max-chars: accepts an integer or 'full'/'none'/'unlimited'."""
    if value.lower() in ("full", "none", "unlimited"):
        return None
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--max-chars must be an integer or 'full', got: {value!r}")

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


def _classify_error(exc: Exception) -> str:
    """Return a short groupable key for an extraction error (mirrors batch_extract.py)."""
    import json as _json
    import pydantic
    if isinstance(exc, pydantic.ValidationError):
        errs = exc.errors(include_url=False)
        if errs:
            e = errs[0]
            loc = ".".join(
                "[]" if isinstance(part, int) else str(part)
                for part in e["loc"]
            ) if e["loc"] else "(root)"
            return f"ValidationError:{e['type']}@{loc}"
        return "ValidationError:unknown"
    if isinstance(exc, (ValueError, _json.JSONDecodeError)) and "JSON" in str(exc):
        return "JSONDecodeError"
    return type(exc).__name__


def cmd_extract(args) -> None:
    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    short_name = COUNCILS[key]["short_name"]
    raw_dir = Path("data/raw") / key

    import json as _json
    from src.extraction.extractor import MinutesExtractor, save_extraction, _MODEL as _EXTRACT_MODEL
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

    from src.extraction.extractor import DEFAULT_MAX_CHARS
    max_chars = getattr(args, "max_chars", DEFAULT_MAX_CHARS)

    # ── Pre-flight cost estimate ───────────────────────────────────────────
    if pdfs:
        from src.cost_estimator import (
            estimate_extraction, format_preflight, load_census, model_key_from_string,
        )
        _census = load_census()
        _est = estimate_extraction(pdfs, max_chars, model_key_from_string(_EXTRACT_MODEL), _census)
        console.print(format_preflight(_est))
        console.print()

    if getattr(args, "dry_run", False):
        console.print("[dim]--dry-run: no API calls made[/dim]")
        return

    console.print(Panel(f"Extracting [bold]{len(pdfs)}[/bold] PDFs for [bold]{key}[/bold]", style="blue"))

    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    council_full_name = council.name
    extractor = MinutesExtractor()

    succeeded = 0
    failed = 0
    failures: list[dict] = []

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
                extracted, raw_text = extractor.extract_from_pdf(
                    pdf,
                    council_name=council_full_name,
                    meeting_date_hint=meeting_date_hint,
                    max_chars=max_chars,
                )
                meeting_id = save_extraction(
                    session, council_id, extracted, pdf,
                    text=raw_text, pdf_url=meta.get("source_url"),
                )
                msg = f"{pdf.name} → meeting {meeting_id} ({extracted.meeting_date}, {len(extracted.motions)} motions)"
                console.print(f"  [green]✓[/green] {msg}")
                _log.info("OK: %s", msg)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                console.print(f"  [red]✗[/red] {pdf.name}: {exc}")
                _log.error("FAIL: %s: %s", pdf.name, exc)
                failed += 1
                failures.append({
                    "filename": pdf.name,
                    "error_class": _classify_error(exc),
                    "error_type": type(exc).__qualname__,
                    "error_message": str(exc),
                    "raw_llm_response": getattr(exc, "raw_llm_response", None),
                })
            finally:
                progress.advance(task)

    session.close()
    console.print(
        f"\n[bold]Done:[/bold] {succeeded} extracted, {failed} failed, {skipped} skipped"
    )
    _log.info("Done: %d extracted, %d failed, %d skipped", succeeded, failed, skipped)

    if failures:
        import json as _json
        from collections import defaultdict
        from datetime import datetime, timezone
        error_path = Path("data/extraction_errors.json")
        errors_by_class: dict = defaultdict(list)
        for entry in failures:
            errors_by_class[entry["error_class"]].append(entry)
        errors_by_class = dict(sorted(errors_by_class.items(), key=lambda kv: -len(kv[1])))
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "council": key,
            "attempted": succeeded + failed,
            "succeeded": succeeded,
            "failed": failed,
            "errors_by_class": errors_by_class,
        }
        error_path.write_text(_json.dumps(report, indent=2))
        console.print("\n[bold]Error breakdown:[/bold]")
        for cls, entries in errors_by_class.items():
            console.print(f"  {len(entries):3d}×  {cls}")
        console.print(f"[dim]Full report → {error_path}[/dim]")




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
# Script-backed sub-commands
# ---------------------------------------------------------------------------


def cmd_compare(args) -> None:
    from scripts.compare_models import run
    run(args)


def cmd_costs(args) -> None:
    import estimate_costs
    estimate_costs.run(args)


def cmd_census(args) -> None:
    from scripts.census import run
    run(args)


def cmd_inventory(args) -> None:
    from scripts.inventory import run
    run(args)


def cmd_typology(args) -> None:
    from scripts.inventory_typology import run
    run(args)


def cmd_sample(args) -> None:
    from scripts.stratified_sample import run
    run(args)


def cmd_extract_sample(args) -> None:
    from scripts.stratified_sample import canonical_sample_path
    import json as _json

    path = canonical_sample_path(args.council)
    if not path.exists():
        console.print(f"[red]No sample file found at {path}. Run 'council sample {args.council}' first.[/red]")
        sys.exit(1)

    data = _json.loads(path.read_text())
    files = data["files"]
    selected_at = data.get("selected_at", "unknown")

    console.print(f"[yellow]Note: extract-sample always re-extracts all docs (--force is implicit).[/yellow]")
    console.print(f"[dim]Sample: {len(files)} files selected at {selected_at}[/dim]")

    args.files = files
    args.force = True
    args.limit = None
    args.from_year = None
    args.to_year = None
    cmd_extract(args)


def cmd_validate_sample(args) -> None:
    from scripts.validate_sample import run
    run(args)


def cmd_validate(args) -> None:
    from scripts.validate_extraction import run
    run(args)


def cmd_analyse(args) -> None:
    from sqlalchemy import func
    from src.analysis.queries import (
        voting_alignment_matrix,
        contested_motions,
        top_planning_sites,
        councillor_vote_summary,
        motions_by_tag,
    )
    from src.models import Councillor, Meeting, Motion, Vote
    from src.storage.database import init_db, make_session_factory

    short_name = COUNCILS[args.council]["short_name"]
    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    q = args.query

    if q == "councillors":
        rows = (
            session.query(Councillor, func.count(Vote.id).label("n"))
            .join(Vote, Vote.councillor_id == Councillor.id)
            .join(Motion, Vote.motion_id == Motion.id)
            .join(Meeting, Motion.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id)
            .group_by(Councillor.id)
            .order_by(func.count(Vote.id).desc())
            .all()
        )
        table = Table(title=f"{short_name} — Councillors ({len(rows)})")
        table.add_column("Name")
        table.add_column("Votes", justify="right")
        for c, n in rows:
            table.add_row(f"{c.given_name} {c.family_name}".strip(), str(n))
        console.print(table)

    elif q == "alignment":
        pairs = voting_alignment_matrix(session, council_id)
        pairs = [p for p in pairs if p.total_shared_votes >= args.min_shared]
        table = Table(title=f"{short_name} — Voting Alignment (≥{args.min_shared} shared votes)")
        table.add_column("Councillor A")
        table.add_column("Councillor B")
        table.add_column("Shared", justify="right")
        table.add_column("Agree", justify="right")
        table.add_column("Rate", justify="right")
        for p in pairs[:args.limit]:
            rate = p.agreement_rate
            color = "green" if rate >= 0.85 else "red" if rate < 0.5 else "yellow"
            table.add_row(
                p.councillor_a, p.councillor_b,
                str(p.total_shared_votes), str(p.agreements),
                f"[{color}]{rate:.0%}[/{color}]",
            )
        console.print(table)

    elif q == "contested":
        motions = contested_motions(session, council_id, min_against=args.min_against)
        table = Table(title=f"{short_name} — Contested Motions (≥{args.min_against} against)")
        table.add_column("Date")
        table.add_column("Item")
        table.add_column("Title")
        table.add_column("For", justify="right")
        table.add_column("Against", justify="right")
        for m in motions[:args.limit]:
            mtg = session.get(Meeting, m.meeting_id)
            table.add_row(
                str(mtg.meeting_date) if mtg else "?",
                m.item_number or "–",
                (m.title or "")[:60],
                str(m.votes_for) if m.votes_for is not None else "–",
                str(m.votes_against) if m.votes_against is not None else "–",
            )
        console.print(table)

    elif q == "planning":
        sites = top_planning_sites(session, council_id, limit=args.limit)
        table = Table(title=f"{short_name} — Top Planning Sites")
        table.add_column("Address")
        table.add_column("Applications", justify="right")
        for address, n in sites:
            table.add_row(address, str(n))
        console.print(table)

    elif q == "councillor":
        if not args.name:
            console.print("[red]--name required for 'councillor' query (family name, partial match)[/red]")
            raise SystemExit(1)
        match = (
            session.query(Councillor)
            .filter(Councillor.family_name.ilike(f"%{args.name}%"))
            .first()
        )
        if not match:
            console.print(f"[red]No councillor found matching '{args.name}'[/red]")
            raise SystemExit(1)
        summary = councillor_vote_summary(session, match.id, council_id)
        table = Table(
            title=f"{match.given_name} {match.family_name}".strip(),
            show_header=False, box=None, pad_edge=False,
        )
        table.add_column("", style="dim")
        table.add_column("", justify="right")
        table.add_row("Total votes", str(summary["total_votes"]))
        table.add_row("For", str(summary["for"]))
        table.add_row("Against", str(summary["against"]))
        table.add_row("Abstain", str(summary["abstain"]))
        table.add_row("Declared interests", str(summary["declared_interests"]))
        table.add_row("Dissent rate", f"{summary['dissent_rate']:.1%}")
        console.print(table)

    elif q == "motions":
        if not args.tag:
            console.print("[red]--tag required for 'motions' query[/red]")
            raise SystemExit(1)
        results = motions_by_tag(session, council_id, args.tag)
        showing = min(len(results), args.limit)
        table = Table(title=f"{short_name} — Motions tagged '{args.tag}' ({len(results)} total, showing {showing})")
        table.add_column("Date")
        table.add_column("Item")
        table.add_column("Title")
        table.add_column("Outcome")
        for m in results[:args.limit]:
            mtg = session.get(Meeting, m.meeting_id)
            table.add_row(
                str(mtg.meeting_date) if mtg else "?",
                m.item_number or "–",
                (m.title or "")[:60],
                m.outcome.value if m.outcome else "–",
            )
        console.print(table)

    session.close()


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

    # scrape
    p_scrape = sub.add_parser("scrape", help="Discover and download PDFs only")
    p_scrape.add_argument("council", choices=list(COUNCILS))
    p_scrape.add_argument("--since-year", type=int, metavar="YYYY", default=2020,
                          dest="since_year", help="Only include meetings from this year (default: 2020)")
    p_scrape.set_defaults(func=cmd_scrape)

    # extract
    p_extract = sub.add_parser("extract", help="Extract already-downloaded PDFs",
                              usage="council extract {cambridge} [--limit N] [--from-year YYYY] [--to-year YYYY] [--files PDF [PDF ...]] [--force]")
    p_extract.add_argument("council", choices=list(COUNCILS))
    p_extract.add_argument("--limit", type=int, metavar="N", help="Process at most N PDFs")
    p_extract.add_argument("--from-year", type=int, metavar="YYYY", dest="from_year",
                           help="Only extract meetings from this year onward (uses manifest date)")
    p_extract.add_argument("--to-year", type=int, metavar="YYYY", dest="to_year",
                           help="Only extract meetings up to and including this year")
    p_extract.add_argument("--files", nargs="+", metavar="PDF",
                           help="Process only these specific PDFs (basenames); ignores --limit and date filters")
    p_extract.add_argument("--force", action="store_true", help="Re-extract already-extracted PDFs")
    from src.extraction.extractor import DEFAULT_MAX_CHARS as _DMC
    p_extract.add_argument("--max-chars", type=_parse_max_chars, default=_DMC, metavar="N|full",
                           dest="max_chars",
                           help=f"Extraction limit per document (default: {_DMC}). Use 'full' for multi-chunk extraction of the entire document.")
    p_extract.add_argument("--dry-run", action="store_true", dest="dry_run",
                           help="Show cost estimate only; make no API calls")
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

    # compare
    p_compare = sub.add_parser("compare", help="Side-by-side model comparison for one PDF (scripts/compare_models.py)")
    p_compare.add_argument("pdf", metavar="PDF", help="PDF basename (e.g. bde23c99.pdf)")
    p_compare.add_argument("--council", default="cambridge", choices=list(COUNCILS))
    p_compare.add_argument("--no-save", action="store_true", dest="no_save",
                           help="Don't save JSON report to data/model_comparison/")
    p_compare.set_defaults(func=cmd_compare)

    # costs
    p_costs = sub.add_parser("costs", help="Estimate extraction API costs for pending PDFs (estimate_costs.py)")
    p_costs.add_argument("--from-year", type=int, metavar="YYYY", dest="from_year")
    p_costs.add_argument("--to-year", type=int, metavar="YYYY", dest="to_year")
    p_costs.add_argument("--max-chars", default="80000", metavar="N|full", dest="max_chars",
                         help="Truncation limit or 'full' (default: 80000)")
    p_costs.add_argument("--quiet", "-q", action="store_true",
                         help="(no-op; kept for compatibility)")
    p_costs.add_argument("--force", action="store_true",
                         help="Estimate cost for all docs, not just pending/uninventoried (as if running --force)")
    p_costs.add_argument("--show", action="store_true",
                         help="Print latest saved report without regenerating")
    p_costs.set_defaults(func=cmd_costs)

    # census
    p_census = sub.add_parser("census", help="Level 0: keyword scan and census across all PDFs (scripts/census.py)")
    p_census.add_argument("council", choices=list(COUNCILS))
    p_census.add_argument("--force", action="store_true",
                          help="Rescan all PDFs, ignoring cached results")
    p_census.add_argument("--quiet", "-q", action="store_true",
                          help="Suppress per-document output and summary")
    p_census.add_argument("--workers", type=int, default=None, metavar="N",
                          help="Parallel worker processes (default: min(8, cpu_count))")
    p_census.set_defaults(func=cmd_census)

    # inventory
    p_inventory = sub.add_parser("inventory", help="Level 1: LLM inventory — one cheap Haiku call per document (scripts/inventory.py)")
    p_inventory.add_argument("council", choices=list(COUNCILS))
    p_inventory.add_argument("--limit", "-n", type=int, default=None, metavar="N",
                             help="Process at most N PDFs")
    p_inventory.add_argument("--force", action="store_true",
                             help="Re-run even if inventory exists (cached LLM responses still reused)")
    p_inventory.add_argument("--quiet", "-q", action="store_true",
                             help="Suppress progress output")
    p_inventory.add_argument("--dry-run", action="store_true", dest="dry_run",
                             help="Show cost estimate only; make no API calls")
    p_inventory.set_defaults(func=cmd_inventory)

    # typology
    p_typology = sub.add_parser("typology", help="Level 1→2: analyse inventory typology for schema review (scripts/inventory_typology.py)")
    p_typology.add_argument("council", choices=list(COUNCILS))
    p_typology.add_argument("--quiet", "-q", action="store_true",
                            help="Write to file only, suppress stdout")
    p_typology.add_argument("--history", action="store_true",
                            help="Show inventory quality score history and exit")
    p_typology.add_argument("--limit", "-n", type=int, default=None, metavar="N",
                            help="Analyse only the N most-recently-updated inventory files")
    p_typology.set_defaults(func=cmd_typology)

    # sample
    p_sample = sub.add_parser("sample", help="Level 3a: select a stratified 15-20 doc sample; saves to data/{council}_sample.json (scripts/stratified_sample.py)")
    p_sample.add_argument("council", choices=list(COUNCILS))
    p_sample.add_argument("--count", type=int, default=18, metavar="N",
                          help="Target sample size (default: 18)")
    p_sample.add_argument("--output-file", metavar="PATH",
                          help="Write filenames to file instead of stdout")
    p_sample.set_defaults(func=cmd_sample)

    # extract-sample
    from src.extraction.extractor import DEFAULT_MAX_CHARS as _DMC2
    p_extract_sample = sub.add_parser("extract-sample", help="Level 3b: extract the saved sample (always --force); reads data/{council}_sample.json")
    p_extract_sample.add_argument("council", choices=list(COUNCILS))
    p_extract_sample.add_argument("--max-chars", type=_parse_max_chars, default=_DMC2, metavar="N|full",
                                  dest="max_chars",
                                  help=f"Extraction limit per document (default: {_DMC2}). Use 'full' for multi-chunk extraction of the entire document.")
    p_extract_sample.add_argument("--dry-run", action="store_true", dest="dry_run",
                                  help="Show cost estimate only; make no API calls")
    p_extract_sample.set_defaults(func=cmd_extract_sample)

    # validate-sample
    from src.extraction.extractor import DEFAULT_MAX_CHARS as _DMC3
    p_validate_sample = sub.add_parser("validate-sample", help="Level 3c: validate sample extractions against evidence table and L1 inventory (scripts/validate_sample.py)")
    p_validate_sample.add_argument("council", choices=list(COUNCILS))
    p_validate_sample.add_argument("--max-chars", type=_parse_max_chars, default=_DMC3, metavar="N|full",
                                   dest="max_chars",
                                   help=f"Coverage denominator cap (default: {_DMC3}). Use 'full' when extraction was run with --max-chars full.")
    p_validate_sample.set_defaults(func=cmd_validate_sample)

    # validate
    from src.extraction.extractor import DEFAULT_MAX_CHARS as _DMC4
    p_validate = sub.add_parser("validate", help="Level 4: per-doc confidence scoring for all extracted meetings (scripts/validate_extraction.py)")
    p_validate.add_argument("council", choices=list(COUNCILS))
    p_validate.add_argument("--limit", "-n", type=int, metavar="N",
                            help="Validate only the first N extracted docs")
    p_validate.add_argument("--files", nargs="+", metavar="PDF",
                            help="Validate only these specific PDFs (basenames)")
    p_validate.add_argument("--from-year", type=int, metavar="YYYY", dest="from_year",
                            help="Only validate meetings from this year onward")
    p_validate.add_argument("--to-year", type=int, metavar="YYYY", dest="to_year",
                            help="Only validate meetings up to and including this year")
    p_validate.add_argument("--max-chars", type=_parse_max_chars, default=_DMC4, metavar="N|full",
                            dest="max_chars",
                            help=f"Coverage denominator cap (default: {_DMC4}). Use 'full' when extraction was run with --max-chars full.")
    p_validate.add_argument("--force", action="store_true",
                            help="Re-validate even if data/validation/{stem}.json already exists")
    p_validate.set_defaults(func=cmd_validate)

    # analyse
    p_analyse = sub.add_parser("analyse", help="Run analysis queries against the DB")
    p_analyse.add_argument("council", choices=list(COUNCILS))
    p_analyse.add_argument(
        "query",
        choices=["councillors", "alignment", "contested", "planning", "councillor", "motions"],
        help=(
            "councillors: all councillors by vote count  |  "
            "alignment: pairwise voting agreement  |  "
            "contested: carried motions with opposition  |  "
            "planning: top sites by application count  |  "
            "councillor: one councillor's vote summary (--name)  |  "
            "motions: motions by tag (--tag)"
        ),
    )
    p_analyse.add_argument("--min-against", type=int, default=2, dest="min_against",
                           help="Min against votes for 'contested' (default: 2)")
    p_analyse.add_argument("--min-shared", type=int, default=5, dest="min_shared",
                           help="Min shared votes for 'alignment' (default: 5)")
    p_analyse.add_argument("--limit", type=int, default=20,
                           help="Max rows to display (default: 20)")
    p_analyse.add_argument("--name", metavar="NAME",
                           help="Councillor family name for 'councillor' query (partial match)")
    p_analyse.add_argument("--tag", metavar="TAG",
                           help="Tag to filter by for 'motions' query")
    p_analyse.set_defaults(func=cmd_analyse)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    args.func(args)


if __name__ == "__main__":
    main()
