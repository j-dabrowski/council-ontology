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
  draft <council>           Generate candidate snapshots to data/draft/ for review
  publish <council>         Gate: copy a reviewed draft into frontend/public/data/

Other commands:
  status    DB summary across all councils
  docs      Per-document download/extraction status
  compare   Side-by-side model comparison for one PDF (dev tool)
  costs     Estimate extraction API costs
  analyse   Analysis queries against the DB
"""

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

console = Console()
_log = logging.getLogger(__name__)


def _extract_pdf_text_worker(pdf_str: str, q) -> None:
    """Subprocess worker: extract plain text from one PDF, put result in queue.
    Deliberately imports only pypdf and fitz — no Anthropic client, no dotenv —
    so subprocess startup is fast and the full timeout is available for PDF I/O.
    Runs in a child process so the parent can SIGKILL it if a library hangs.

    pypdf is tried first: the census proved it doesn't hang on any Cambridge PDF.
    fitz is the fallback for files pypdf can't read (corrupted streams etc.)."""
    try:
        from pypdf import PdfReader as _PdfReader
        reader = _PdfReader(pdf_str)
        parts = [t for page in reader.pages for t in [page.extract_text() or ""] if t]
        text = "\n\n".join(parts)
        if text.strip():
            q.put(("ok", text))
            return
    except Exception:
        pass  # fall through to fitz

    try:
        import fitz as _fitz
        doc = _fitz.open(pdf_str)
        parts = [p for page in doc for p in [page.get_text()] if p]
        doc.close()
        q.put(("ok", "\n\n".join(parts)))
    except Exception as exc:
        q.put(("error", str(exc)))


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
# Archive helpers
# ---------------------------------------------------------------------------


def _update_archive_index(archive_base: Path, entry: dict) -> None:
    """Upsert a run entry in data/llm_archive/index.json."""
    import json as _json
    archive_base.mkdir(parents=True, exist_ok=True)
    index_file = archive_base / "index.json"
    index = _json.loads(index_file.read_text()) if index_file.exists() else []
    index = [e for e in index if e.get("run_id") != entry["run_id"]]
    index.append({k: entry[k] for k in (
        "run_id", "source", "council", "model", "created_at",
        "n_docs", "n_chunks", "imported", "imported_at",
    ) if k in entry})
    index.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    index_file.write_text(_json.dumps(index, indent=2))


def cmd_archive_status(args) -> None:
    import json as _json
    from rich.table import Table

    key = args.council
    archive_base = Path("data/llm_archive")
    index_file = archive_base / "index.json"

    index = _json.loads(index_file.read_text()) if index_file.exists() else []
    runs = [e for e in index if e.get("council") == key]

    if runs:
        table = Table(title=f"LLM Response Archive — {key}")
        table.add_column("Run ID", style="cyan", no_wrap=True)
        table.add_column("Source", style="dim")
        table.add_column("Model", style="dim")
        table.add_column("Docs", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("Archived", style="dim")
        table.add_column("Imported")

        for run in runs:
            if run.get("imported"):
                imported = f"[green]✓[/green] {(run.get('imported_at') or '')[:10]}"
            else:
                imported = "[dim]—[/dim]"
            model = run.get("model") or "?"
            model_short = model.replace("claude-", "").replace("-20251001", "")
            table.add_row(
                run["run_id"],
                run.get("source", "?"),
                model_short,
                str(run.get("n_docs", "?")),
                str(run.get("n_chunks", "?")),
                (run.get("created_at") or "?")[:19].replace("T", " "),
                imported,
            )

        console.print(table)
        console.print(f"\n[dim]Archive directory: {archive_base.resolve()}[/dim]")
        console.print(f"[dim]Import a run:  council archive-import {key} <run_id>[/dim]")
        console.print(f"[dim]Import with re-extract:  council archive-import {key} <run_id> --force[/dim]")

    # Warn about batch jobs not yet in archive
    import json as _json
    archived_ids = {r["run_id"] for r in runs}
    job_dir = Path("data/batch_jobs")
    unarchived = [
        f.stem for f in sorted(job_dir.glob("*.json"))
        if f.stem not in archived_ids
        and _json.loads(f.read_text()).get("council") == key
    ]
    if unarchived:
        console.print(
            f"\n[yellow]{len(unarchived)} batch job(s) not yet in archive:[/yellow]"
        )
        for bid in unarchived:
            console.print(f"  [dim]{bid}[/dim]")
        console.print(
            f"[dim]Download all:  council archive-download {key} --all[/dim]"
        )


def cmd_archive_import(args) -> None:
    from scripts.archive_import import run as _run
    _run(
        council=args.council,
        run_id=args.run_id,
        force=getattr(args, "force", False),
    )


def cmd_archive_download(args) -> None:
    """Download historical batch results from Anthropic API into local archive (no DB write)."""
    import json as _json

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    job_dir = Path("data/batch_jobs")

    if getattr(args, "all_batches", False):
        # Collect all batch IDs for this council from data/batch_jobs/
        batch_ids = []
        for job_file in sorted(job_dir.glob("*.json")):
            try:
                job = _json.loads(job_file.read_text())
                if job.get("council") == key:
                    batch_ids.append(job_file.stem)
            except Exception:
                continue
        if not batch_ids:
            console.print(f"[yellow]No batch job files found for council: {key}[/yellow]")
            return
        console.print(f"[dim]Found {len(batch_ids)} batch job files for {key}[/dim]")
    else:
        if not getattr(args, "batch_id", None):
            console.print("[red]Provide a batch_id or use --all[/red]")
            sys.exit(1)
        batch_ids = [args.batch_id]

    from src.extraction.extractor import MinutesExtractor
    extractor = MinutesExtractor()

    archive_base = Path("data/llm_archive")
    n_downloaded = 0
    n_skipped = 0
    n_failed = 0

    for batch_id in batch_ids:
        console.print(f"\n[bold cyan]{batch_id}[/bold cyan]")

        archive_dir = archive_base / batch_id
        existing_chunks = (
            [f for f in archive_dir.glob("*.json") if f.name != "manifest.json"]
            if archive_dir.exists() else []
        )

        if existing_chunks and not getattr(args, "force", False):
            console.print(
                f"  [dim]Already archived ({len(existing_chunks)} chunks) — "
                "skip (--force to re-download)[/dim]"
            )
            n_skipped += 1
            continue

        job_file = job_dir / f"{batch_id}.json"
        if not job_file.exists():
            console.print(f"  [red]Job file not found: {job_file}[/red]")
            n_failed += 1
            continue

        job = _json.loads(job_file.read_text())
        id_map: dict = job.get("id_map", {})
        council_full_name: str = job.get("council_name", COUNCILS[key]["short_name"])
        n_requests = job.get("request_count", len(id_map))

        console.print(
            f"  [dim]Downloading {n_requests} responses "
            f"({job.get('n_docs', '?')} docs, submitted {(job.get('submitted_at') or '?')[:10]})...[/dim]"
        )

        archive_dir.mkdir(parents=True, exist_ok=True)

        try:
            status, results = extractor.retrieve_batch_results(
                batch_id, archive_dir=archive_dir, id_map=id_map
            )
        except Exception as exc:
            console.print(f"  [red]API error: {exc}[/red]")
            n_failed += 1
            continue

        if status != "ended":
            console.print(
                f"  [yellow]Batch not yet complete (status: {status}) — skipping[/yellow]"
            )
            n_skipped += 1
            continue

        chunk_files = [f for f in archive_dir.glob("*.json") if f.name != "manifest.json"]
        n_ok = sum(1 for v in results.values() if not isinstance(v, Exception))
        n_err = len(results) - n_ok

        # Write manifest. imported=False: data is already in DB from original batch-collect;
        # this archive entry is for future re-import only.
        manifest = {
            "run_id": batch_id,
            "source": "batch",
            "council": key,
            "council_name": council_full_name,
            "model": job.get("model", extractor._model),
            "max_chars": job.get("max_chars"),
            "created_at": job.get("submitted_at"),
            "n_docs": job.get("n_docs", 0),
            "n_chunks": len(chunk_files),
            "imported": False,
            "imported_at": None,
            "retroactive_archive": True,
        }
        (archive_dir / "manifest.json").write_text(_json.dumps(manifest, indent=2))
        _update_archive_index(archive_base, manifest)

        console.print(
            f"  [green]✓[/green] {len(chunk_files)} chunks archived "
            f"({n_ok} ok, {n_err} errors) → {archive_dir}"
        )
        n_downloaded += 1

    console.print(
        f"\n[bold]Done:[/bold] {n_downloaded} downloaded, "
        f"{n_skipped} skipped, {n_failed} failed"
    )
    if n_downloaded:
        console.print(
            "[dim]Note: data is already in the DB from the original batch-collect. "
            "Use 'archive-import --force' only if you need to rebuild the DB from scratch.[/dim]"
        )
        console.print("[dim]View: council archive-status cambridge[/dim]")


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

    # ── Pre-filter: skip already-extracted PDFs (unless --force) ──────────
    # Done here so that dry-run and the cost estimate both reflect pending docs only.
    # The downstream filters in _cmd_batch_submit and the sync loop are safety nets.
    if pdfs and not getattr(args, "force", False):
        from src.models import Meeting as _Meeting
        from src.storage.database import init_db, make_session_factory
        _engine = init_db()
        _session = make_session_factory(_engine)()
        from src.models import Council as _Council
        _council_row = _session.query(_Council).filter_by(
            short_name=COUNCILS[key]["short_name"]
        ).first()
        _council_id = _council_row.id if _council_row else None

        _pending, _n_already = [], 0
        for _p in pdfs:
            # Primary check: exact path match
            if _session.query(_Meeting).filter_by(minutes_pdf_path=str(_p)).first():
                _n_already += 1
                continue
            # Secondary check: another PDF for the same meeting is already extracted.
            # Cambridge has multiple PDFs per meeting date (agenda + minutes); both map
            # to the same DB row. If the meeting row exists under any filename, skip.
            _meta = manifest.get(_p.name, {})
            _date = _meta.get("meeting_date")
            _mtype = _meta.get("meeting_type")
            if _date and _mtype and _council_id and _session.query(_Meeting).filter_by(
                council_id=_council_id,
                meeting_date=_date,
                meeting_type=_mtype,
            ).first():
                _n_already += 1
                continue
            _pending.append(_p)
        _session.close()
        if _n_already:
            console.print(f"[dim]{_n_already} already extracted — skipping (use --force to re-run)[/dim]")
        pdfs = _pending

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

    if getattr(args, "batch", False):
        _cmd_batch_submit(args, key, pdfs, max_chars, manifest)
        return

    console.print(Panel(f"Extracting [bold]{len(pdfs)}[/bold] PDFs for [bold]{key}[/bold]", style="blue"))

    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    council_full_name = council.name
    extractor = MinutesExtractor()

    # Create an archive run directory for this sync extraction batch
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    _archive_run_id = f"sync_{_dt.now(_tz.utc).strftime('%Y%m%d_%H%M%S')}"
    _archive_dir = Path("data/llm_archive") / _archive_run_id
    _archive_dir.mkdir(parents=True, exist_ok=True)
    _archive_start = _dt.now(_tz.utc).isoformat()

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
            doc_type = meta.get("document_type")
            try:
                extracted, raw_text = extractor.extract_from_pdf(
                    pdf,
                    council_name=council_full_name,
                    meeting_date_hint=meeting_date_hint,
                    max_chars=max_chars,
                    document_type=doc_type,
                    archive_dir=_archive_dir,
                )
                meeting_id = save_extraction(
                    session, council_id, extracted, pdf,
                    text=raw_text, pdf_url=meta.get("source_url"),
                    document_type=doc_type,
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

    # Write archive manifest and update index
    _archive_chunk_files = [f for f in _archive_dir.glob("*.json") if f.name != "manifest.json"]
    _archive_stems = {f.stem.split("__c")[0] for f in _archive_chunk_files if "__c" in f.stem}
    _archive_manifest = {
        "run_id": _archive_run_id,
        "source": "sync",
        "council": key,
        "council_name": council_full_name,
        "model": extractor._model,
        "max_chars": max_chars,
        "created_at": _archive_start,
        "n_docs": len(_archive_stems),
        "n_chunks": len(_archive_chunk_files),
        "imported": True,
        "imported_at": _dt.now(_tz.utc).isoformat(),
    }
    (_archive_dir / "manifest.json").write_text(_json.dumps(_archive_manifest, indent=2))
    _update_archive_index(Path("data/llm_archive"), _archive_manifest)
    if _archive_chunk_files:
        console.print(f"[dim]Archive: {len(_archive_chunk_files)} responses → {_archive_dir}[/dim]")

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




def _cmd_batch_submit(args, key: str, pdfs: list, max_chars: "int | None", manifest: dict) -> None:
    """Submit pdfs as an Anthropic batch job and save a job file for later collection."""
    import json as _json
    from datetime import datetime, timezone

    from src.extraction.extractor import MinutesExtractor
    from src.models import Meeting as _Meeting
    from src.storage.database import init_db, make_session_factory

    short_name = COUNCILS[key]["short_name"]
    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_full_name = council.name

    # Filter out already-extracted PDFs unless --force
    if not args.force:
        pending: list = []
        skipped = 0
        for pdf in pdfs:
            if session.query(_Meeting).filter_by(minutes_pdf_path=str(pdf)).first():
                skipped += 1
            else:
                pending.append(pdf)
        if skipped:
            console.print(f"[dim]Skipped {skipped} already-extracted PDFs (use --force to re-submit).[/dim]")
        pdfs = pending

    session.close()

    if not pdfs:
        console.print("[yellow]No pending PDFs to submit.[/yellow]")
        return

    console.print(Panel(
        f"Building batch for [bold]{len(pdfs)}[/bold] PDFs · [bold]{key}[/bold]",
        style="blue",
    ))

    extractor = MinutesExtractor()

    all_requests: list[dict] = []
    id_map: dict[str, dict] = {}
    build_errors: list[str] = []

    # fitz can infinite-loop on malformed content streams. Thread-level timeouts
    # cannot kill hanging threads, so each PDF is extracted in a child process
    # that can be SIGTERM'd / SIGKILL'd if it exceeds the timeout.
    _PDF_BUILD_TIMEOUT = 30  # seconds per PDF; pypdf reads even large docs in <15s

    import multiprocessing as _mp
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reading PDFs...", total=len(pdfs))
        for pdf in pdfs:
            progress.update(task, description=f"[cyan]{pdf.name}[/cyan]")
            q: "_mp.Queue[tuple]" = _mp.Queue()
            p = _mp.Process(
                target=_extract_pdf_text_worker,
                args=(str(pdf), q),
            )
            p.start()
            # Read from queue BEFORE joining — large payloads block q.put() in the
            # subprocess until the parent drains the pipe. If we join first, both sides
            # deadlock: subprocess waits on put(), parent waits on join().
            import queue as _queue
            try:
                status, *rest = q.get(timeout=_PDF_BUILD_TIMEOUT)
            except _queue.Empty:
                # Subprocess timed out or died without putting a result
                p.terminate()
                p.join(2)
                if p.is_alive():
                    p.kill()
                    p.join(1)
                build_errors.append(pdf.name)
                _log.warning(
                    "SKIP %s: PDF text extraction timed out after %ds (subprocess killed)",
                    pdf.name, _PDF_BUILD_TIMEOUT,
                )
                console.print(
                    f"  [red]✗[/red] {pdf.name}: skipped — timed out after "
                    f"{_PDF_BUILD_TIMEOUT}s (unreadable PDF)"
                )
                progress.advance(task)
                continue
            finally:
                p.join(5)
                if p.is_alive():
                    p.kill()
            if status == "ok":
                text = rest[0]
                reqs, mapping = extractor.build_requests_from_text(
                    pdf, text, max_chars, council_full_name, manifest
                )
                if reqs:
                    all_requests.extend(reqs)
                    id_map.update(mapping)
                else:
                    build_errors.append(pdf.name)
                    _log.warning("SKIP %s: no text extracted from PDF", pdf.name)
                    console.print(f"  [yellow]⚠[/yellow] {pdf.name}: no text extracted, skipping")
            else:
                build_errors.append(pdf.name)
                _log.warning("SKIP %s: %s", pdf.name, rest[0])
                console.print(f"  [yellow]⚠[/yellow] {pdf.name}: {rest[0]}")
            progress.advance(task)

    if build_errors:
        console.print(f"[yellow]Skipped {len(build_errors)} PDFs (no text / read error)[/yellow]")

    if not all_requests:
        console.print("[red]No requests built — all PDFs failed to read.[/red]")
        return

    n_docs = len({v["pdf_path"] for v in id_map.values()})
    console.print(f"[dim]Built {len(all_requests)} requests for {n_docs} PDFs[/dim]")
    console.print("[dim]Submitting to Anthropic batch API...[/dim]")

    batch_id = extractor.submit_batch(all_requests)

    job_dir = Path("data/batch_jobs")
    job_dir.mkdir(parents=True, exist_ok=True)
    job_file = job_dir / f"{batch_id}.json"
    job_file.write_text(_json.dumps({
        "batch_id": batch_id,
        "council": key,
        "council_name": council_full_name,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "model": extractor._model,
        "max_chars": max_chars,
        "n_docs": n_docs,
        "request_count": len(all_requests),
        "id_map": id_map,
    }, indent=2))

    console.print("\n[bold green]Batch submitted![/bold green]")
    console.print(f"  Batch ID:   [bold]{batch_id}[/bold]")
    console.print(f"  Requests:   {len(all_requests)} ({n_docs} documents)")
    console.print(f"  Job file:   {job_file}")
    console.print("\nRun when ready (up to 24 h):")
    console.print(f"  [bold]council batch-collect {key} {batch_id}[/bold]")


def cmd_batch_collect(args) -> None:
    import json as _json
    from collections import defaultdict
    from datetime import date, datetime, timezone

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    batch_id = args.batch_id
    job_file = Path("data/batch_jobs") / f"{batch_id}.json"
    if not job_file.exists():
        console.print(f"[red]Job file not found: {job_file}[/red]")
        console.print("[dim]Submit a batch first: council extract <council> --batch[/dim]")
        sys.exit(1)

    job = _json.loads(job_file.read_text())
    id_map: dict = job["id_map"]
    council_full_name: str = job.get("council_name", COUNCILS[key]["short_name"])

    from src.extraction.extractor import (
        MinutesExtractor, save_extraction, _merge_chunk_results,
        extract_text_from_pdf, _parse_date_from_text,
    )
    from src.storage.database import init_db, make_session_factory

    extractor = MinutesExtractor()

    # Prepare archive directory — responses are written per-chunk inside retrieve_batch_results
    _archive_dir = Path("data/llm_archive") / batch_id
    _archive_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Checking batch {batch_id}...[/dim]")
    status, chunk_results = extractor.retrieve_batch_results(
        batch_id, archive_dir=_archive_dir, id_map=id_map
    )

    if status != "ended":
        console.print(f"[yellow]Batch status: {status}[/yellow]")
        console.print(
            f"  Submitted:  {job.get('submitted_at', '?')}\n"
            f"  Requests:   {job['request_count']}  ·  {job['n_docs']} documents"
        )
        console.print("\n[dim]Run again when processing is complete (up to 24 h).[/dim]")
        return

    # Group chunk results by stem
    by_stem: dict[str, list] = defaultdict(list)
    for cid, result_or_exc in chunk_results.items():
        info = id_map.get(cid)
        if info is None:
            console.print(f"[yellow]Warning: unknown custom_id {cid} — not in job file, skipping[/yellow]")
            continue
        stem = Path(info["pdf_path"]).stem
        by_stem[stem].append((
            info["chunk_idx"],
            info["n_chunks"],
            Path(info["pdf_path"]),
            info.get("meeting_date_hint"),
            cid,
            result_or_exc,
        ))

    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, COUNCILS[key]["short_name"])
    council_id = council.id

    manifest_path = Path("data/raw") / key / "manifest.json"
    manifest = _json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    succeeded = 0
    failed = 0
    failures: list[dict] = []

    console.print(Panel(
        f"Saving [bold]{len(by_stem)}[/bold] extracted documents · [bold]{key}[/bold]",
        style="blue",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Saving...", total=len(by_stem))

        for stem, chunk_list in sorted(by_stem.items()):
            chunk_list.sort(key=lambda x: x[0])  # sort by chunk_idx
            pdf_path: Path = chunk_list[0][2]
            date_hint: "str | None" = chunk_list[0][3]

            progress.update(task, description=f"[cyan]{pdf_path.name}[/cyan]")

            # Any failed chunks abort the whole document
            chunk_errors = [
                (cid, exc) for _, _, _, _, cid, exc in chunk_list if isinstance(exc, Exception)
            ]
            if chunk_errors:
                for cid, exc in chunk_errors:
                    console.print(f"  [red]✗[/red] {pdf_path.name} [{cid}]: {exc}")
                    failures.append({
                        "filename": pdf_path.name,
                        "error_class": _classify_error(exc),
                        "error_type": type(exc).__qualname__,
                        "error_message": str(exc),
                        "raw_llm_response": getattr(exc, "raw_llm_response", None),
                    })
                failed += 1
                progress.advance(task)
                continue

            extracted_chunks = [r for _, _, _, _, _, r in chunk_list]

            # Apply chunk-0 metadata overrides (mirrors MinutesExtractor._extract_chunk)
            base = extracted_chunks[0]
            overrides: dict = {}
            if council_full_name and not base.council_name:
                overrides["council_name"] = council_full_name
            if not base.meeting_date and date_hint:
                try:
                    overrides["meeting_date"] = date.fromisoformat(date_hint)
                except ValueError:
                    pass
            if overrides:
                extracted_chunks[0] = base.model_copy(update=overrides)

            extracted = _merge_chunk_results(extracted_chunks) if len(extracted_chunks) > 1 else extracted_chunks[0]

            # Re-read PDF text for provenance; also supplies date fallback
            try:
                raw_text: "str | None" = extract_text_from_pdf(pdf_path)
            except Exception as exc:
                raw_text = None
                console.print(f"  [yellow]⚠[/yellow] {pdf_path.name}: could not re-read PDF ({exc}); provenance incomplete")

            if not extracted.meeting_date and not date_hint and raw_text:
                parsed_date = _parse_date_from_text(raw_text)
                if parsed_date:
                    extracted = extracted.model_copy(update={"meeting_date": parsed_date})

            meta = manifest.get(pdf_path.name, {})
            try:
                meeting_id = save_extraction(
                    session, council_id, extracted, pdf_path,
                    text=raw_text, pdf_url=meta.get("source_url"),
                    document_type=meta.get("document_type"),
                )
                console.print(
                    f"  [green]✓[/green] {pdf_path.name} → meeting {meeting_id} "
                    f"({extracted.meeting_date}, {len(extracted.motions)} motions)"
                )
                succeeded += 1
            except Exception as exc:
                session.rollback()
                console.print(f"  [red]✗[/red] {pdf_path.name}: {exc}")
                failures.append({
                    "filename": pdf_path.name,
                    "error_class": _classify_error(exc),
                    "error_type": type(exc).__qualname__,
                    "error_message": str(exc),
                    "raw_llm_response": None,
                })
                failed += 1
            finally:
                progress.advance(task)

    session.close()
    console.print(f"\n[bold]Done:[/bold] {succeeded} saved, {failed} failed")
    _log.info("batch-collect done: %d saved, %d failed", succeeded, failed)

    # Write archive manifest and update index
    _archive_chunk_files = [f for f in _archive_dir.glob("*.json") if f.name != "manifest.json"]
    _archive_manifest = {
        "run_id": batch_id,
        "source": "batch",
        "council": key,
        "council_name": council_full_name,
        "model": job.get("model", extractor._model),
        "max_chars": job.get("max_chars"),
        "created_at": job.get("submitted_at"),
        "n_docs": succeeded + failed,
        "n_chunks": len(_archive_chunk_files),
        "imported": True,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    (_archive_dir / "manifest.json").write_text(_json.dumps(_archive_manifest, indent=2))
    _update_archive_index(Path("data/llm_archive"), _archive_manifest)
    if _archive_chunk_files:
        console.print(f"[dim]Archive: {len(_archive_chunk_files)} responses → {_archive_dir}[/dim]")

    if failures:
        error_path = Path("data/extraction_errors.json")
        errors_by_class: dict = defaultdict(list)
        for entry in failures:
            errors_by_class[entry["error_class"]].append(entry)
        errors_by_class = dict(sorted(errors_by_class.items(), key=lambda kv: -len(kv[1])))
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "council": key,
            "batch_id": batch_id,
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

    console.print("[yellow]Note: extract-sample always re-extracts all docs (--force is implicit).[/yellow]")
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


def cmd_profile(args) -> None:
    """S2 corpus profile (docs/INFORMATION_ARCHITECTURE.md §3): a scripted,
    no-LLM pass over the already-extracted corpus — NULL rates, document/date
    spans, identity-resolution state, record-quality metrics — as one
    machine-readable document. Writes data/<council>_profile.json (gitignored,
    refreshed on every run, like census/typology) and prints a summary.
    """
    import json as _json
    from datetime import datetime, timezone

    from src.analysis.profile import compute_corpus_profile, profile_to_dict
    from src.analysis.queries import get_council_by_name
    from src.storage.database import init_db, make_session_factory

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)
    short_name = COUNCILS[key]["short_name"]

    engine = init_db()
    session = make_session_factory(engine)()
    council_obj = get_council_by_name(session, short_name)
    if not council_obj:
        console.print(f"[red]Council '{short_name}' not found in DB[/red]")
        sys.exit(1)

    generated_at = datetime.now(timezone.utc).isoformat()
    profile = compute_corpus_profile(session, council_obj.id, key, generated_at)
    session.close()

    output_path = Path("data") / f"{key}_profile.json"
    output_path.write_text(_json.dumps(profile_to_dict(profile), indent=2))

    console.print(Panel(f"Corpus profile → [bold]{output_path}[/bold]", style="blue"))

    span = profile.span
    console.print(
        f"[bold]{span.total_documents}[/bold] documents "
        f"{span.date_min} → {span.date_max}  ({span.by_document_type})"
    )
    if span.zero_meeting_months_in_span:
        console.print(
            f"[yellow]{len(span.zero_meeting_months_in_span)} zero-meeting month(s) in span "
            f"— candidate corpus gap(s)[/yellow]"
        )

    ec = profile.entity_counts
    console.print(
        f"councillors={ec.councillors}  motions={ec.motions}  votes={ec.votes}  "
        f"planning_applications={ec.planning_applications}  tenders={ec.tenders}"
    )

    ir = profile.identity_resolution
    if ir.with_neither:
        console.print(
            f"[yellow]{ir.with_neither} councillor row(s) with zero votes and zero terms "
            "— may not be real councillors[/yellow]"
        )
    if ir.duplicate_family_name_groups:
        console.print(
            f"[yellow]{ir.duplicate_family_name_groups} family name(s) shared by >1 councillor "
            "— worth checking for a split identity, not a confirmed one[/yellow]"
        )

    rq = profile.record_quality
    console.print(f"[dim]vote choice distribution: {rq.vote_choice_distribution}[/dim]")


def cmd_reply_packets(args) -> None:
    """S9 right of reply — packet assembly (docs/INFORMATION_ARCHITECTURE.md
    §3, src/reply_packets.py). Scripted: runs the battery fresh, groups every
    `individual`-unit claim with no reply on file by the person it names, and
    writes one packet per person to data/reply_packets/<council>/<run_id>/ for
    a human to send. Never sends anything itself. Today the battery is 100%
    institutional-unit, so a healthy run always produces zero packets — that's
    the correct, honest result, not a bug.
    """
    import json as _json
    from datetime import datetime, timezone

    from src.analysis.queries import get_council_by_name
    from src.analysis.tests import run_test_battery
    from src.reply_packets import assemble_reply_packets, load_response_window_days, render_packet_template
    from src.storage.database import init_db, make_session_factory

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)
    short_name = COUNCILS[key]["short_name"]

    engine = init_db()
    session = make_session_factory(engine)()
    council_obj = get_council_by_name(session, short_name)
    if not council_obj:
        console.print(f"[red]Council '{short_name}' not found in DB[/red]")
        sys.exit(1)

    battery = run_test_battery(session, council_obj.id)
    session.close()

    generated_at = datetime.now(timezone.utc).isoformat()
    packets = assemble_reply_packets(battery, load_response_window_days(), generated_at)

    run_id = f"reply_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    output_dir = Path("data/reply_packets") / key / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    for packet in packets:
        slug = packet.person.strip().lower().replace(" ", "-")
        (output_dir / f"{slug}.md").write_text(render_packet_template(packet))

    (output_dir / "manifest.json").write_text(_json.dumps({
        "run_id": run_id,
        "council": key,
        "generated_at": generated_at,
        "packets": [p.person for p in packets],
    }, indent=2))

    if packets:
        console.print(Panel(
            f"[green]✓[/green] {len(packets)} reply packet(s) → {output_dir}\n"
            "[dim]A human sends these — this command never does.[/dim]",
            style="green",
        ))
    else:
        console.print(Panel(
            f"0 reply packets — no `individual`-unit claim in this battery names anyone "
            f"(manifest written to {output_dir} regardless, for the record).",
            style="blue",
        ))


def cmd_analyse(args) -> None:
    from src.analysis.queries import (
        budget_by_year,
        co_mover_pairs,
        contestation_by_year,
        councillor_activity_ranges,
        councillor_vote_summary,
        contested_motions,
        interest_declarations_summary,
        list_councillors,
        motions_by_tag,
        planning_outcomes,
        public_engagement_by_year,
        topic_distribution_by_year,
        voting_alignment_matrix,
    )
    from src.models import Councillor, Meeting
    from src.storage.database import init_db, make_session_factory

    short_name = COUNCILS[args.council]["short_name"]
    engine = init_db()
    session = make_session_factory(engine)()
    council = _get_council(session, short_name)
    council_id = council.id
    q = args.query
    from_year = getattr(args, "from_year", None)
    to_year = getattr(args, "to_year", None)

    year_label = ""
    if from_year and to_year:
        year_label = f" {from_year}–{to_year}"
    elif from_year:
        year_label = f" {from_year}+"
    elif to_year:
        year_label = f" –{to_year}"

    if q == "councillors":
        rows = list_councillors(session, council_id, from_year=from_year, to_year=to_year)
        table = Table(title=f"{short_name} — Councillors{year_label} ({len(rows)})")
        table.add_column("Name")
        table.add_column("Votes", justify="right")
        for c, n in rows:
            table.add_row(f"{c.given_name} {c.family_name}".strip(), str(n))
        console.print(table)

    elif q == "alignment":
        pairs = voting_alignment_matrix(session, council_id, from_year=from_year, to_year=to_year)
        pairs = [p for p in pairs if p.total_shared_votes >= args.min_shared]
        table = Table(title=f"{short_name} — Voting Alignment{year_label} (≥{args.min_shared} shared votes)")
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
        motions = contested_motions(
            session, council_id, min_against=args.min_against,
            from_year=from_year, to_year=to_year,
        )
        table = Table(title=f"{short_name} — Contested Motions{year_label} (≥{args.min_against} against)")
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
        outcomes = planning_outcomes(session, council_id, from_year=from_year, to_year=to_year, limit=args.limit)
        console.print(f"\n[bold]{short_name} — Planning Applications{year_label}[/bold]")
        console.print(f"  Total: {outcomes.total} | Approved: {outcomes.approved} | "
                      f"Refused: {outcomes.refused} | Deferred: {outcomes.deferred} | "
                      f"Pending: {outcomes.pending}")
        decided = outcomes.approved + outcomes.refused
        if decided:
            console.print(f"  Approval rate: [green]{outcomes.approval_rate:.0%}[/green] "
                          f"({outcomes.approved}/{decided} decided)")
        if outcomes.top_sites:
            table = Table(title="Top Sites by Application Count")
            table.add_column("Address")
            table.add_column("Applications", justify="right")
            for addr, n in outcomes.top_sites:
                table.add_row(addr, str(n))
            console.print(table)
        if outcomes.top_applicants:
            table = Table(title="Top Applicants")
            table.add_column("Applicant")
            table.add_column("Applications", justify="right")
            for name, n in outcomes.top_applicants:
                table.add_row(name, str(n))
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
        summary = councillor_vote_summary(session, match.id, council_id, from_year=from_year, to_year=to_year)
        table = Table(
            title=f"{match.given_name} {match.family_name}".strip() + year_label,
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
        results = motions_by_tag(session, council_id, args.tag, from_year=from_year, to_year=to_year)
        showing = min(len(results), args.limit)
        table = Table(title=f"{short_name} — Motions tagged '{args.tag}'{year_label} ({len(results)} total, showing {showing})")
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

    elif q == "activity":
        rows = councillor_activity_ranges(
            session, council_id,
            from_year=from_year, to_year=to_year,
            min_votes=args.min_votes,
        )
        table = Table(title=f"{short_name} — Councillor Activity{year_label} (min {args.min_votes} votes)")
        table.add_column("Name")
        table.add_column("First vote")
        table.add_column("Last vote")
        table.add_column("Votes", justify="right")
        table.add_column("Active")
        table.add_column("Dissent", justify="right")
        for r in rows:
            name = f"{r.given_name} {r.family_name}".strip()
            active = "[green]Yes[/green]" if r.is_active else "[dim]No[/dim]"
            table.add_row(
                name,
                str(r.first_vote_date),
                str(r.last_vote_date),
                str(r.total_votes),
                active,
                f"{r.dissent_rate:.1%}",
            )
        console.print(table)

    elif q == "trends":
        contest = contestation_by_year(session, council_id, from_year=from_year, to_year=to_year)
        topics = topic_distribution_by_year(session, council_id, from_year=from_year, to_year=to_year)

        table = Table(title=f"{short_name} — Contestation by Year{year_label}")
        table.add_column("Year")
        table.add_column("Carried", justify="right")
        table.add_column("Contested", justify="right")
        table.add_column("Rate", justify="right")
        table.add_column("Most contested (top 1)")
        for s in contest:
            color = "red" if s.contestation_rate >= 0.15 else "yellow" if s.contestation_rate >= 0.05 else "dim"
            top = s.most_contested[0][0][:50] if s.most_contested else "—"
            table.add_row(
                str(s.year),
                str(s.total_carried),
                str(s.contested),
                f"[{color}]{s.contestation_rate:.0%}[/{color}]",
                top,
            )
        console.print(table)

        if topics:
            all_tags = sorted({t for yr_tags in topics.values() for t in yr_tags if t != "other"})
            table2 = Table(title=f"{short_name} — Topic Distribution by Year{year_label}")
            table2.add_column("Year")
            for tag in all_tags:
                table2.add_column(tag.capitalize(), justify="right")
            table2.add_column("other", justify="right")
            for yr, tag_counts in sorted(topics.items()):
                table2.add_row(
                    str(yr),
                    *[str(tag_counts.get(t, 0)) for t in all_tags],
                    str(tag_counts.get("other", 0)),
                )
            console.print(table2)

    elif q == "co-movers":
        pairs = co_mover_pairs(
            session, council_id,
            from_year=from_year, to_year=to_year,
            min_count=args.min_count,
            active_only=args.active_only,
        )
        active_label = " (active only)" if args.active_only else ""
        table = Table(title=f"{short_name} — Co-mover Pairs{year_label}{active_label} (≥{args.min_count})")
        table.add_column("Mover")
        table.add_column("Seconder")
        table.add_column("Count", justify="right")
        for p in pairs[:args.limit]:
            table.add_row(p.mover_name, p.seconder_name, str(p.count))
        console.print(table)

    elif q == "interests":
        rows = interest_declarations_summary(session, council_id, from_year=from_year, to_year=to_year)
        table = Table(title=f"{short_name} — Interest Declarations{year_label}")
        table.add_column("Councillor")
        table.add_column("Total", justify="right")
        table.add_column("Financial", justify="right")
        table.add_column("Impartiality", justify="right")
        table.add_column("Proximity", justify="right")
        table.add_column("Other", justify="right")
        table.add_column("Top topics")
        for r in rows[:args.limit]:
            fin = r.by_type.get("financial", 0)
            imp = r.by_type.get("impartiality", 0)
            prox = r.by_type.get("proximity", 0)
            oth = r.by_type.get("other", 0)
            fin_cell = f"[yellow]{fin}[/yellow]" if fin else str(fin)
            table.add_row(
                r.councillor_name,
                str(r.total),
                fin_cell,
                str(imp),
                str(prox),
                str(oth),
                ", ".join(r.top_topics[:3]),
            )
        console.print(table)

    elif q == "engagement":
        rows = public_engagement_by_year(session, council_id, from_year=from_year, to_year=to_year)
        table = Table(title=f"{short_name} — Public Engagement{year_label}")
        table.add_column("Year")
        table.add_column("Questions", justify="right")
        table.add_column("Deputations", justify="right")
        table.add_column("Petitions", justify="right")
        table.add_column("Total", justify="right")
        for r in rows:
            table.add_row(
                str(r.year),
                str(r.public_questions),
                str(r.deputations),
                str(r.petitions),
                str(r.total),
            )
        console.print(table)

    elif q == "budget":
        rows = budget_by_year(session, council_id, from_year=from_year, to_year=to_year, top_n=3)
        table = Table(title=f"{short_name} — Budget Items{year_label}")
        table.add_column("Year")
        table.add_column("Items", justify="right")
        table.add_column("With $", justify="right")
        table.add_column("Total $ (indicative)", justify="right")
        table.add_column("Largest item")
        for r in rows[:args.limit]:
            amt = f"${r.total_amount:,.0f}" if r.total_amount is not None else "—"
            top = f"{r.largest_items[0][0][:40]} (${r.largest_items[0][1]:,.0f})" if r.largest_items else "—"
            table.add_row(str(r.year), str(r.total_items), str(r.items_with_amount), amt, top)
        console.print(table)
        console.print("[dim]Note: total $ is the sum of extracted amounts and may double-count sub-items.[/dim]")

    elif q == "divergence":
        from src.analysis.divergence import officer_divergence
        results = officer_divergence(session, council_id, from_year=from_year, to_year=to_year)
        if not results:
            console.print("[yellow]No matched agenda+minutes pairs found for this period.[/yellow]")
        else:
            matched = len(results)
            diverged = sum(1 for r in results if r.diverged)
            console.print(
                f"\n[bold]{short_name} — Officer vs Council{year_label}[/bold]\n"
                f"  Matched pairs: {matched} | Diverged: {diverged} | "
                f"Rate: [{'red' if diverged/matched > 0.1 else 'green'}]{diverged/matched:.0%}[/]\n"
            )
            table = Table(title=f"Divergences (showing up to {args.limit})")
            table.add_column("Date")
            table.add_column("Item")
            table.add_column("Title")
            table.add_column("Outcome")
            table.add_column("Match")
            for r in [x for x in results if x.diverged][:args.limit]:
                table.add_row(
                    str(r.meeting_date),
                    r.item_number or "–",
                    (r.title or "")[:50],
                    r.council_outcome or "–",
                    f"{r.match_confidence:.0%}",
                )
            console.print(table)

    session.close()


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


# Every snapshot _generate_snapshots can write, tagged public vs. full-tier.
# Everything defaults to "full" (private) unless explicitly listed here as
# "public", or (for claim-bearing snapshots — see `_tier_of`) derived from
# the claims themselves — fail-safe direction either way, so an unlisted or
# newly-derived-full snapshot is never accidentally exposed. Static entries
# here are for snapshots with no claim-derivation path of their own; none
# exist yet, so this stays empty. See docs/TESTING.md.
SNAPSHOT_TIER: dict[str, str] = {}

# Snapshot name -> the battery/claim list that governs its tier, per §4/§7's
# tier-derivation rule (src/invariant_gate.py's derive_claim_tier). Only
# "scorecard" is built directly from TestResult claims today; every other
# snapshot is per-councillor profile data, out of scope for claim-level tier
# derivation until it's represented as claim objects too.
CLAIM_DERIVED_SNAPSHOTS = ("scorecard",)


def _tier_of(name: str, battery: list | None = None) -> str:
    if name in CLAIM_DERIVED_SNAPSHOTS and battery is not None:
        from src.invariant_gate import derive_claim_tier
        return derive_claim_tier(battery)
    return SNAPSHOT_TIER.get(name, "full")


def _generate_snapshots(
    session, council_id: int, output_dir: Path, generated_at: str
) -> tuple[list[str], list]:
    """Run the full analysis + standard test battery and write one JSON file
    per dashboard snapshot into output_dir. Returns the list of snapshot
    names written (in write order) and the battery itself (the claim objects
    the S7 invariant gate checks — src/invariant_gate.py).

    Pure generation — no knowledge of where output_dir sits (draft staging
    vs. a public directory) and no git/gate logic. Called by `council draft`;
    `council publish` never calls this directly (see src/publish_gate.py) —
    it only ever copies bytes a human has already reviewed.
    """
    import json as _json
    from dataclasses import asdict

    output_dir.mkdir(parents=True, exist_ok=True)

    def _dc(obj) -> dict:
        d = asdict(obj)
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        return d

    written: list[str] = []

    def _write(name: str, data) -> None:
        path = output_dir / f"{name}.json"
        path.write_text(_json.dumps({"published_at": generated_at, "data": data}, indent=2))
        console.print(f"  [green]✓[/green] {name}.json")
        written.append(name)

    from src.analysis.queries import (
        interest_declarations_summary, co_mover_pairs,
        voting_alignment_matrix, contestation_by_year,
        topic_distribution_by_year, public_engagement_by_year,
        planning_trend_by_year, planning_objection_stats,
        dissent_profiles, dissent_coalition_pairs, contestation_by_tag,
        conflict_recusal_stats, tender_concentration,
        objection_dose_response, transparency_by_year, councillor_tenure,
        mayoral_agenda_setting, voting_power, recusal_compliance_trend,
        sponsorship_network, public_question_responsiveness,
    )
    from src.analysis.divergence import officer_divergence

    # interests
    _write("interests", [_dc(s) for s in
        interest_declarations_summary(session, council_id, None, None)])

    # divergence
    pairs = officer_divergence(session, council_id, None, None)
    diverged = [p for p in pairs if p.diverged]
    total = len(pairs)
    years = [p.meeting_date.year for p in pairs if p.meeting_date]
    # fetch extraction_evidence quotes for the matched minutes motions
    div_motion_ids = [p.minutes_motion_id for p in diverged if p.minutes_motion_id]
    div_quote: dict[int, str] = {}
    if div_motion_ids:
        from src.models import ExtractionEvidence as _EE
        for mid, qt in session.query(_EE.entity_id, _EE.quote_text).filter(
            _EE.entity_table == "motions",
            _EE.entity_id.in_(div_motion_ids),
            _EE.quote_text.isnot(None),
        ):
            div_quote.setdefault(mid, qt)
    _write("divergence", {
        "total_matched": total,
        "diverged_count": len(diverged),
        "followed_count": total - len(diverged),
        "compliance_rate": round((total - len(diverged)) / total, 4) if total else None,
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "exceptions": [
            {
                "meeting_date": p.meeting_date.isoformat(),
                "item_number": p.item_number,
                "title": p.title,
                "officer_recommendation": p.officer_recommendation,
                "council_outcome": p.council_outcome,
                "match_confidence": round(p.match_confidence, 2),
                "motion_text": p.motion_text,
                "quote": div_quote.get(p.minutes_motion_id) if p.minutes_motion_id else None,
            }
            for p in diverged
        ],
    })

    # co-movers
    pairs_cm = co_mover_pairs(session, council_id, None, None, min_count=5, active_only=True)
    names: set[str] = set()
    for p in pairs_cm:
        names.add(p.mover_name)
        names.add(p.seconder_name)
    _write("co-movers", {
        "nodes": [{"id": n} for n in sorted(names)],
        "links": [{"source": p.mover_name, "target": p.seconder_name, "value": p.count} for p in pairs_cm],
        "pairs": [_dc(p) for p in pairs_cm],
    })

    # alignment
    ALLY, OPP = 0.85, 0.40
    rows = [r for r in voting_alignment_matrix(session, council_id, from_year=None, to_year=None)
            if r.total_shared_votes >= 10]
    _write("alignment", {"pairs": [
        {
            "name_a": r.councillor_a.strip(),
            "name_b": r.councillor_b.strip(),
            "agreement_rate": round(r.agreement_rate, 4),
            "shared_votes": r.total_shared_votes,
            "is_ally": r.agreement_rate >= ALLY,
            "is_opponent": r.agreement_rate <= OPP,
        }
        for r in rows
    ]})

    # trends
    contestation = contestation_by_year(session, council_id, None, None)
    topics = topic_distribution_by_year(session, council_id, None, None)
    _write("trends", {
        "contestation": [
            {
                "year": r.year,
                "total_carried": r.total_carried,
                "total_with_dissent": r.contested,
                "contestation_rate": round(r.contestation_rate, 4),
                "most_contested": [t for t, _ in (r.most_contested[:3] if r.most_contested else [])],
            }
            for r in contestation
        ],
        "topics": {str(k): v for k, v in topics.items()},
    })

    # engagement
    _write("engagement", [
        {"year": r.year, "public_questions": r.public_questions,
         "deputations": r.deputations, "petitions": r.petitions}
        for r in public_engagement_by_year(session, council_id, None, None)
    ])

    # planning: 30-year approval trend + objection effectiveness
    trend = planning_trend_by_year(session, council_id)
    obj_stats = planning_objection_stats(session, council_id)
    _write("planning", {
        "trend": [
            {
                "year": r.year,
                "n_applications": r.n_applications,
                "decided": r.decided,
                "approved": r.approved,
                "refused": r.refused,
                "approval_pct": r.approval_pct,
            }
            for r in trend
        ],
        "objections": {
            "with_objection": {
                "n": obj_stats.with_objection_n,
                "approved": obj_stats.with_objection_approved,
                "refused": obj_stats.with_objection_refused,
                "approval_pct": obj_stats.with_objection_pct,
            },
            "no_objection": {
                "n": obj_stats.no_objection_n,
                "approved": obj_stats.no_objection_approved,
                "refused": obj_stats.no_objection_refused,
                "approval_pct": obj_stats.no_objection_pct,
            },
        },
    })

    # dissent: councillor profiles + co-opposition pairs + contestation by topic
    profiles = dissent_profiles(session, council_id, min_votes=50)
    coalitions = dissent_coalition_pairs(session, council_id, min_count=10)
    by_tag = contestation_by_tag(session, council_id)
    _write("dissent", {
        "profiles": [
            {
                "name": p.name,
                "total_votes_on_carried": p.total_votes_on_carried,
                "against_count": p.against_count,
                "dissent_rate": p.dissent_rate,
                "is_active": p.is_active,
                "top_dissent_tags": p.top_dissent_tags,
            }
            for p in profiles
        ],
        "coalitions": [
            {
                "name_a": c.name_a,
                "name_b": c.name_b,
                "shared_dissent": c.shared_dissent,
            }
            for c in coalitions
        ],
        "by_tag": [
            {
                "tag": t.tag,
                "total_carried": t.total_carried,
                "contested": t.contested,
                "contestation_rate": t.contestation_rate,
            }
            for t in by_tag
        ],
    })

    # conflict of interest: recusal behaviour when an interest is declared
    recusal = conflict_recusal_stats(session, council_id, min_declared=8)
    _write("declared", {
        "declared_total": recusal.declared_total,
        "declared_recused": recusal.declared_recused,
        "declared_recusal_pct": recusal.declared_recusal_pct,
        "declared_against_pct": recusal.declared_against_pct,
        "baseline_total": recusal.baseline_total,
        "baseline_recusal_pct": recusal.baseline_recusal_pct,
        "baseline_against_pct": recusal.baseline_against_pct,
        "profiles": [
            {
                "name": p.name,
                "declared_votes": p.declared_votes,
                "recused": p.recused,
                "recusal_rate": p.recusal_rate,
                "is_active": p.is_active,
                # must-leave (financial/proximity) split of the blended rate above —
                # see BLOCKING #3, defamation_review_1.md: the blended recusal_rate
                # mixes legally-mandatory conflicts with lawful impartiality
                # declarations, which mis-colours councillors with zero mandatory
                # conflicts as if they'd ignored one. must_leave_recusal_rate is
                # None when the councillor has no must-leave declarations on record.
                "must_leave_declared": p.must_leave_declared,
                "must_leave_recused": p.must_leave_recused,
                "must_leave_recusal_rate": p.must_leave_recusal_rate,
                # inline drill-down detail — each declared-interest vote expanded
                "declarations": [_dc(d) for d in p.declarations],
            }
            for p in recusal.profiles
        ],
    })

    # tenders: concentration of $148M of awarded work among contractors
    tenders = tender_concentration(session, council_id, limit=15)
    _write("tenders", {
        "total_awards": tenders.total_awards,
        "total_amount": tenders.total_amount,
        "named_awards": tenders.named_awards,
        "named_amount": tenders.named_amount,
        "redacted_awards": tenders.redacted_awards,
        "redacted_amount": tenders.redacted_amount,
        "distinct_named": tenders.distinct_named,
        "top10_amount": tenders.top10_amount,
        "top10_share": tenders.top10_share,
        "contractors": [
            {
                "name": c.name,
                "n_awards": c.n_awards,
                "total_amount": c.total_amount,
                # inline drill-down detail — each award to this firm
                "awards": [_dc(a) for a in c.awards],
            }
            for c in tenders.contractors
        ],
    })

    # objection dose-response: does the NUMBER of objectors change the outcome?
    dose = objection_dose_response(session, council_id)
    # drill-down: per-bucket application lists (capped at 30 each, sorted by n_obj desc)
    from src.models import PlanningApplication as _PA, CommunitySubmission as _CS, Site as _Site, ApplicationStatus as _AS, ExtractionEvidence as _EE4, Motion as _Motion3, Meeting as _Meeting3
    from sqlalchemy import func as _func2
    _dose_rows = (
        session.query(
            _PA.id,
            _PA.reference_number,
            _PA.description,
            _PA.status,
            _func2.count(_CS.id).label("n_obj"),
            _Site.address,
        )
        .join(_Motion3, _PA.motion_id == _Motion3.id)
        .join(_Meeting3, _Motion3.meeting_id == _Meeting3.id)
        .outerjoin(_Site, _PA.site_id == _Site.id)
        .outerjoin(
            _CS,
            (_CS.application_id == _PA.id) & (_func2.lower(_CS.position) == "object"),
        )
        .filter(
            _Meeting3.council_id == council_id,
            _PA.status.in_([_AS.APPROVED, _AS.REFUSED]),
        )
        .group_by(_PA.id)
        .order_by(_func2.count(_CS.id).desc())
        .all()
    )
    def _dose_bucket(n: int) -> str:
        if n == 0:
            return "0"
        if n == 1:
            return "1"
        if n <= 4:
            return "2-4"
        return "5+"
    _apps_by_bucket: dict[str, list] = {"0": [], "1": [], "2-4": [], "5+": []}
    _app_ids_needed: list[int] = []
    for pid, ref, desc, status, n_obj, addr in _dose_rows:
        n_obj = int(n_obj or 0)
        bk = _dose_bucket(n_obj)
        if len(_apps_by_bucket[bk]) < 30:
            _apps_by_bucket[bk].append({
                "id": pid,
                "reference": ref,
                "description": (desc or "")[:200] or None,
                "address": addr,
                "n_objectors": n_obj,
                "outcome": status.value if status else None,
            })
            _app_ids_needed.append(pid)
    # fetch quotes
    _dose_quote: dict[int, str] = {}
    if _app_ids_needed:
        for pid, qt in session.query(_EE4.entity_id, _EE4.quote_text).filter(
            _EE4.entity_table == "planning_applications",
            _EE4.entity_id.in_(_app_ids_needed),
            _EE4.quote_text.isnot(None),
        ):
            _dose_quote.setdefault(pid, qt)
    for bk, apps in _apps_by_bucket.items():
        for app in apps:
            app["quote"] = _dose_quote.get(app.pop("id"))
    _write("dose", {
        "total_decided": dose.total_decided,
        "max_objections": dose.max_objections,
        "headline_examples": dose.headline_examples,
        "buckets": [
            {
                "label": b.label, "n": b.n, "refused": b.refused, "refusal_pct": b.refusal_pct,
                "n_shown": len(_apps_by_bucket.get(b.label, [])),
                "apps": _apps_by_bucket.get(b.label, []),
            }
            for b in dose.buckets
        ],
    })

    # transparency: share of council business decided behind closed doors over time
    trans = transparency_by_year(session, council_id)
    # drill-down detail: per-year confidential item lists (capped at 30)
    from sqlalchemy import text as sql_text
    _CONF_ITEMS_SQL = sql_text("""
        SELECT year, kind, entity_id, description, amount, meeting_date
        FROM (
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER) year,
                   'tender' kind, t.id entity_id,
                   t.description, t.amount, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM tenders t JOIN meetings m ON t.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND t.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'other_item', o.id,
                   o.description, NULL, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM other_items o JOIN meetings m ON o.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND o.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'delegated_decision', dd.id,
                   dd.description, NULL, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM delegated_decisions dd JOIN meetings m ON dd.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND dd.is_confidential = 1
            UNION ALL
            SELECT CAST(substr(m.meeting_date,1,4) AS INTEGER),
                   'budget_item', b.id,
                   b.description, b.amount, m.meeting_date,
                   ROW_NUMBER() OVER (PARTITION BY CAST(substr(m.meeting_date,1,4) AS INTEGER)
                                      ORDER BY m.meeting_date DESC) rn
              FROM budget_items b JOIN meetings m ON b.meeting_id = m.id
             WHERE m.council_id = :cid AND m.document_type = 'minutes' AND b.is_confidential = 1
        ) WHERE rn <= 30
        ORDER BY year, kind, meeting_date DESC
    """)
    conf_rows = session.execute(_CONF_ITEMS_SQL, {"cid": council_id}).fetchall()
    # fetch quotes for all entity ids
    from collections import defaultdict as _dd
    _entity_ids_by_table: dict[str, list[int]] = _dd(list)
    for _, kind, eid, *_ in conf_rows:
        table_name = {"tender": "tenders", "other_item": "other_items",
                      "delegated_decision": "delegated_decisions", "budget_item": "budget_items"}[kind]
        _entity_ids_by_table[table_name].append(eid)
    from src.models import ExtractionEvidence as _EE2
    _conf_quote: dict[tuple[str, int], str] = {}
    for table_name, ids in _entity_ids_by_table.items():
        for eid, qt in session.query(_EE2.entity_id, _EE2.quote_text).filter(
            _EE2.entity_table == table_name,
            _EE2.entity_id.in_(ids),
            _EE2.quote_text.isnot(None),
        ):
            _conf_quote.setdefault((table_name, eid), qt)
    _items_by_year: dict[int, list[dict]] = _dd(list)
    _year_item_counts: dict[int, int] = {}
    for year, kind, eid, desc, amount, mdate in conf_rows:
        table_name = {"tender": "tenders", "other_item": "other_items",
                      "delegated_decision": "delegated_decisions", "budget_item": "budget_items"}[kind]
        _items_by_year[year].append({
            "kind": kind,
            "description": (desc or "")[:200] or None,
            "amount": round(amount) if amount else None,
            "date": mdate if isinstance(mdate, str) else mdate.isoformat() if mdate else None,
            "quote": _conf_quote.get((table_name, eid)),
        })
    for yr, items in _items_by_year.items():
        _year_item_counts[yr] = len(items)
    _write("transparency", {
        "pre_era_pct": trans.pre_era_pct,
        "peak_year": trans.peak_year,
        "peak_pct": trans.peak_pct,
        "category_totals": trans.category_totals,
        "years": [
            {
                "year": y.year,
                "total": y.total,
                "confidential": y.confidential,
                "confidential_pct": y.confidential_pct,
                "n_shown": _year_item_counts.get(y.year, 0),
                "items": _items_by_year.get(y.year, []),
            }
            for y in trans.years
        ],
    })

    # tenure: career councillors vs one-term blow-ins
    tenure = councillor_tenure(session, council_id)
    _write("tenure", {
        "median_years": tenure.median_years,
        "n_councillors": tenure.n_councillors,
        "histogram": tenure.histogram,
        "profiles": [
            {"name": p.name, "years": p.years, "n_votes": p.n_votes,
             "first": p.first, "last": p.last, "is_active": p.is_active}
            for p in tenure.profiles
        ],
    })

    # mayoral agenda-setting: do motions moved by the Mayor draw more dissent?
    mayoral = mayoral_agenda_setting(session, council_id)
    # drill-down: per-mayor contested carried motion lists (capped at 30)
    from src.models import CouncillorTerm, Motion as _Motion2, Meeting as _Meeting2, Councillor as _Cllr2, MotionOutcome as _MO2, ExtractionEvidence as _EE3
    from datetime import date as _date
    _mayor_terms = session.query(
        CouncillorTerm.councillor_id,
        CouncillorTerm.term_start,
        CouncillorTerm.term_end,
        _Cllr2.given_name,
        _Cllr2.family_name,
    ).join(_Cllr2, CouncillorTerm.councillor_id == _Cllr2.id).filter(
        CouncillorTerm.role == "Mayor"
    ).all()
    # build: mayor_cid → name
    _mayor_name: dict[int, str] = {}
    for mc, ts, te, gn, fn in _mayor_terms:
        _mayor_name[mc] = f"{gn or ''} {fn or ''}".strip()
    # fetch all contested-carried motions by any mayor
    _contested_rows = (
        session.query(
            _Motion2.id,
            _Motion2.moved_by_id,
            _Motion2.title,
            _Meeting2.meeting_date,
            _Motion2.votes_for,
            _Motion2.votes_against,
        )
        .join(_Meeting2, _Motion2.meeting_id == _Meeting2.id)
        .filter(
            _Meeting2.council_id == council_id,
            _Motion2.moved_by_id.in_(list(_mayor_name.keys())),
            _Motion2.outcome == _MO2.CARRIED,
            _Motion2.votes_against > 0,
            _Meeting2.meeting_date.isnot(None),
        )
        .order_by(_Meeting2.meeting_date.desc())
        .all()
    )
    # filter to when they were actually serving as Mayor
    def _was_mayor(cid2: int, d: _date) -> bool:
        for mc, ts, te, *_ in _mayor_terms:
            if mc == cid2 and (ts is None or ts <= d) and (te is None or d <= te):
                return True
        return False
    _motions_by_mayor: dict[str, list] = {}
    _motion_ids_needed: list[int] = []
    for mid, mcid, title, mdate, vf, va in _contested_rows:
        md = mdate if isinstance(mdate, _date) else _date.fromisoformat(str(mdate))
        if not _was_mayor(mcid, md):
            continue
        name = _mayor_name[mcid]
        if name not in _motions_by_mayor:
            _motions_by_mayor[name] = []
        if len(_motions_by_mayor[name]) < 30:
            _motions_by_mayor[name].append({
                "id": mid, "title": title,
                "date": str(md),
                "votes_for": vf, "votes_against": va,
            })
            _motion_ids_needed.append(mid)
    # fetch quotes
    _mayoral_quote: dict[int, str] = {}
    if _motion_ids_needed:
        for mid, qt in session.query(_EE3.entity_id, _EE3.quote_text).filter(
            _EE3.entity_table == "motions",
            _EE3.entity_id.in_(_motion_ids_needed),
            _EE3.quote_text.isnot(None),
        ):
            _mayoral_quote.setdefault(mid, qt)
    # attach quotes and strip internal id
    for name, motions in _motions_by_mayor.items():
        for m in motions:
            m["quote"] = _mayoral_quote.get(m.pop("id"))
    _write("mayoral", {
        "mayor_moved": mayoral.mayor_moved,
        "mayor_carried_pct": mayoral.mayor_carried_pct,
        "mayor_contest_pct": mayoral.mayor_contest_pct,
        "other_moved": mayoral.other_moved,
        "other_carried_pct": mayoral.other_carried_pct,
        "other_contest_pct": mayoral.other_contest_pct,
        "contest_factor": mayoral.contest_factor,
        "per_mayor": [
            {
                "name": p.name, "carried": p.carried, "contested": p.contested,
                "contest_pct": p.contest_pct,
                "n_shown": len(_motions_by_mayor.get(p.name, [])),
                "motions": _motions_by_mayor.get(p.name, []),
            }
            for p in mayoral.per_mayor
        ],
    })

    # voting power: who wins on contested decisions, and whose dissent prevails?
    power = voting_power(session, council_id)
    _write("power", {
        "base_carry_rate": power.base_carry_rate,
        "base_fail_rate": power.base_fail_rate,
        "n_contested": power.n_contested,
        "profiles": [
            {"name": p.name, "n": p.n, "win_rate": p.win_rate,
             "dissent_rate": p.dissent_rate, "dissent_n": p.dissent_n,
             "dissent_effectiveness": p.dissent_effectiveness,
             "is_active": p.is_active,
             # inline drill-down detail — their contested votes (capped most-recent)
             "n_shown": p.n_shown,
             "votes": [_dc(v) for v in p.votes]}
            for p in power.profiles
        ],
        "over_time": [
            {"name": o.name,
             "points": [{"term": pt.term, "win_rate": pt.win_rate, "n": pt.n}
                        for pt in o.points]}
            for o in power.over_time
        ],
    })

    # recusal compliance over time: did "declare, then stay" become the norm,
    # and did it track the 2018–2021 Authorised Inquiry?
    rct = recusal_compliance_trend(session, council_id)
    _write("recusal", {
        "inquiry_window": rct.inquiry_window,
        "must_leave_pre_pct": rct.must_leave_pre_pct,
        "must_leave_pre_n": rct.must_leave_pre_n,
        "must_leave_inquiry_pct": rct.must_leave_inquiry_pct,
        "must_leave_inquiry_n": rct.must_leave_inquiry_n,
        "must_leave_post_pct": rct.must_leave_post_pct,
        "must_leave_post_n": rct.must_leave_post_n,
        "financial_inquiry_pct": rct.financial_inquiry_pct,
        "financial_inquiry_n": rct.financial_inquiry_n,
        "financial_post_pct": rct.financial_post_pct,
        "financial_post_n": rct.financial_post_n,
        "impartiality_post_declared": rct.impartiality_post_declared,
        "impartiality_post_recusal_pct": rct.impartiality_post_recusal_pct,
        "by_type_era": [
            {"interest_type": t.interest_type, "era": t.era,
             "declared": t.declared, "recused": t.recused, "recusal_pct": t.recusal_pct,
             # inline drill-down detail — the declarations behind this cell (capped)
             "n_shown": t.n_shown,
             "declarations": [_dc(d) for d in t.declarations]}
            for t in rct.by_type_era
        ],
        "by_year": [
            {"year": y.year, "must_leave_declared": y.must_leave_declared,
             "must_leave_recused": y.must_leave_recused, "must_leave_pct": y.must_leave_pct,
             "declared_share_pct": y.declared_share_pct}
            for y in rct.by_year
        ],
        "drivers": [
            {"name": d.name, "stayed": d.stayed, "total": d.total}
            for d in rct.drivers
        ],
        "ministerial_approved_post_n": rct.ministerial_approved_post_n,
    })

    # public-question responsiveness: are residents' questions answered in the
    # meeting, or increasingly "taken on notice"? Tracks the 2018–21 Inquiry shock.
    pqr = public_question_responsiveness(session, council_id)
    _write("question-responsiveness", {
        "inquiry_window": pqr.inquiry_window,
        "total": pqr.total,
        "answered": pqr.answered,
        "on_notice": pqr.on_notice,
        "blank": pqr.blank,
        "answered_pct": pqr.answered_pct,
        "on_notice_pct": pqr.on_notice_pct,
        "pre_pct": pqr.pre_pct, "pre_n": pqr.pre_n,
        "inquiry_pct": pqr.inquiry_pct, "inquiry_n": pqr.inquiry_n,
        "post_pct": pqr.post_pct, "post_n": pqr.post_n,
        "peak_year": pqr.peak_year, "peak_pct": pqr.peak_pct,
        "by_era": [
            {"era": e.era, "answered": e.answered, "on_notice": e.on_notice,
             "blank": e.blank, "on_notice_pct": e.on_notice_pct,
             "n_shown": e.n_shown,
             "questions": [_dc(q) for q in e.questions]}
            for e in pqr.by_era
        ],
        "by_year": [
            {"year": y.year, "answered": y.answered, "on_notice": y.on_notice,
             "n_nonblank": y.n_nonblank, "on_notice_pct": y.on_notice_pct}
            for y in pqr.by_year
        ],
    })

    # sponsorship network: who BACKED whose motions in a near-unanimous chamber —
    # validated alliances, the 2000s old-guard network, and the structural arc.
    spon = sponsorship_network(session, council_id)

    def _edge(e):
        return {
            "era_label": e.era_label, "name_a": e.name_a, "name_b": e.name_b,
            "sponsorships": e.sponsorships, "lift": e.lift,
            "agree_pct": e.agree_pct, "agree_n": e.agree_n, "kind": e.kind,
        }

    _write("sponsorship", {
        "alliances": [_edge(e) for e in spon.alliances],
        "procedural": [_edge(e) for e in spon.procedural],
        "convergence_high_agree": spon.convergence_high_agree,
        "convergence_low_agree": spon.convergence_low_agree,
        "oldguard_label": spon.oldguard_label,
        "oldguard_unanimous_pct": spon.oldguard_unanimous_pct,
        "oldguard_nodes": [
            {"name": n.name, "moved": n.moved, "seconded": n.seconded, "in_core": n.in_core}
            for n in spon.oldguard_nodes
        ],
        "oldguard_edges": [_edge(e) for e in spon.oldguard_edges],
        "eras": [
            {"label": r.label, "year_from": r.year_from, "year_to": r.year_to,
             "n_events": r.n_events, "n_active": r.n_active,
             "cluster_size": r.cluster_size, "core_names": r.core_names,
             "structure": r.structure}
            for r in spon.eras
        ],
    })

    # [36] confidentiality-by-topic credit numbers for the overview: the confidential
    # rate of the contentious "named development" theme vs the overall base rate.
    from src.analysis.tests import _CONF_THEMES as _CT
    from src.models import OtherItem as _OI36, DelegatedDecision as _DD36, Tender as _T36
    import re as _re36
    _descs36: list[tuple[str, bool]] = []
    for _model36 in (_T36, _OI36, _DD36):
        for _d36, _ic36 in (
            session.query(_model36.description, _model36.is_confidential)
            .join(_Meeting3, _model36.meeting_id == _Meeting3.id)
            .filter(_Meeting3.council_id == council_id, _Meeting3.document_type == "minutes")
        ):
            _descs36.append(((_d36 or "").lower(), bool(_ic36)))
    _tot36 = len(_descs36)
    _conf36 = sum(1 for _d, _ic in _descs36 if _ic)
    _conf_base_pct = round(_conf36 / _tot36 * 100, 1) if _tot36 else 0.0
    _dev_pat = _re36.compile(dict(_CT)["Named development"])
    _dev_items = [_ic for _d, _ic in _descs36 if _dev_pat.search(_d)]
    _conf_dev_pct = round(sum(1 for _ic in _dev_items if _ic) / len(_dev_items) * 100, 1) if _dev_items else 0.0

    # overview: cross-cutting synthesis numbers for the landing panel, assembled
    # from the already-computed query objects so the figures stay authoritative.
    win_rates = [p.win_rate for p in power.profiles]
    tenure_15plus = sum(1 for p in tenure.profiles if p.years >= 15)
    top_servant = max(tenure.profiles, key=lambda p: p.years) if tenure.profiles else None
    dose_by = {b.label: b.refusal_pct for b in dose.buckets}
    _write("overview", {
        "span": "1995–2026",
        "n_minutes": 506,
        "n_documents": 580,
        # 1 — the Inquiry hinge
        "confidential_pre_pct": trans.pre_era_pct,
        "confidential_peak_pct": trans.peak_pct,
        "confidential_peak_year": trans.peak_year,
        "recusal_inquiry_pct": rct.must_leave_inquiry_pct,
        "recusal_post_pct": rct.must_leave_post_pct,
        "financial_inquiry_pct": rct.financial_inquiry_pct,
        "financial_post_pct": rct.financial_post_pct,
        # 2 — consensus hides power
        "base_carry_pct": round(power.base_carry_rate * 100, 1),
        "n_contested": power.n_contested,
        "win_min_pct": round(min(win_rates) * 100) if win_rates else None,
        "win_max_pct": round(max(win_rates) * 100) if win_rates else None,
        "sponsor_conv_high": spon.convergence_high_agree,
        "sponsor_conv_low": spon.convergence_low_agree,
        "oldguard_unanimous_pct": spon.oldguard_unanimous_pct,
        # 3 — declaration as ritual
        "declared_stay_pct": round(100 - recusal.declared_recusal_pct, 1),
        "impartiality_post_declared": rct.impartiality_post_declared,
        "impartiality_post_recusal_pct": rct.impartiality_post_recusal_pct,
        # 4 — entrenchment
        "tenure_median_years": tenure.median_years,
        "tenure_15plus": tenure_15plus,
        "tenure_top_name": top_servant.name if top_servant else None,
        "tenure_top_years": top_servant.years if top_servant else None,
        # 5 — officer ratification
        "officer_matched": total,
        "officer_diverged": len(diverged),
        "officer_compliance_pct": round((total - len(diverged)) / total * 100, 1) if total else None,
        # 6 — residents move in numbers
        "dose_0_refusal_pct": dose_by.get("0"),
        "dose_5plus_refusal_pct": dose_by.get("5+"),
        # 7 — money concentrated, not captured
        "tender_total_m": round(tenders.total_amount / 1e6, 1),
        "tender_redacted_m": round(tenders.redacted_amount / 1e6, 1),
        "tender_top10_share_pct": round(tenders.top10_share * 100),
        # 8 — the record that earns credit (the promoter-lens balance)
        "mayor_contest_pct": mayoral.mayor_contest_pct,
        "other_contest_pct": mayoral.other_contest_pct,
        # [36] confidentiality tracks lawful grounds, not contentious topics (credit)
        "conf_dev_pct": _conf_dev_pct,
        "conf_base_pct": _conf_base_pct,
        # [37] public-question responsiveness — the 4th Inquiry-hinge panel;
        #      partially reverted (still above baseline), unlike recusal's full collapse
        "pq_pre_pct": pqr.pre_pct,
        "pq_inquiry_pct": pqr.inquiry_pct,
        "pq_post_pct": pqr.post_pct,
        "pq_peak_pct": pqr.peak_pct,
        "pq_peak_year": pqr.peak_year,
    })

    # scorecard: the standard, repeatable Test Battery — every test the corpus can
    # run, each flagged supportive / neutral / critical, including the ones the
    # council passes. Comparable across councils. Reuses the objects above.
    from src.analysis.tests import run_test_battery, battery_summary
    battery = run_test_battery(session, council_id, precomputed={
        "power": power, "recusal_trend": rct, "conflict": recusal,
        "tenders": tenders, "transparency": trans, "tenure": tenure,
        "mayoral": mayoral, "sponsorship": spon, "dose": dose, "divergence": pairs,
        "pq_responsiveness": pqr,
    })
    _write("scorecard", {
        "summary": battery_summary(battery),
        "tests": [_dc(t) for t in battery],
    })

    # councillors.json — unified cross-link profile keyed by full name; used by
    # CouncillorModal (opens whenever a councillor name is clicked in the UI).
    from src.models import (
        Councillor as _CllrX, CouncillorTerm as _CTX,
        Motion as _MotX, Meeting as _MeetX, Vote,
    )
    from sqlalchemy import func as _func_x

    _tenure_map   = {p.name: p for p in tenure.profiles}
    _power_map    = {p.name: p for p in power.profiles}
    _conflict_map = {p.name: p for p in recusal.profiles}

    # moved / seconded counts per councillor name
    _moved_x: dict[str, int] = {}
    for _gn, _fn, _cnt in (
        session.query(_CllrX.given_name, _CllrX.family_name, _func_x.count(_MotX.id))
        .join(_MotX, _CllrX.id == _MotX.moved_by_id)
        .join(_MeetX, _MotX.meeting_id == _MeetX.id)
        .filter(_MeetX.council_id == council_id)
        .group_by(_CllrX.id).all()
    ):
        _moved_x[f"{_gn or ''} {_fn or ''}".strip()] = _cnt
    _seconded_x: dict[str, int] = {}
    for _gn, _fn, _cnt in (
        session.query(_CllrX.given_name, _CllrX.family_name, _func_x.count(_MotX.id))
        .join(_MotX, _CllrX.id == _MotX.seconded_by_id)
        .join(_MeetX, _MotX.meeting_id == _MeetX.id)
        .filter(_MeetX.council_id == council_id)
        .group_by(_CllrX.id).all()
    ):
        _seconded_x[f"{_gn or ''} {_fn or ''}".strip()] = _cnt

    # top co-sponsorship partners per councillor (across all alliances + procedural edges)
    _partner_sums: dict[str, dict[str, int]] = {}
    for _e in (spon.alliances + spon.procedural):
        _partner_sums.setdefault(_e.name_a, {})
        _partner_sums[_e.name_a][_e.name_b] = _partner_sums[_e.name_a].get(_e.name_b, 0) + _e.sponsorships
        _partner_sums.setdefault(_e.name_b, {})
        _partner_sums[_e.name_b][_e.name_a] = _partner_sums[_e.name_b].get(_e.name_a, 0) + _e.sponsorships

    # roles (Mayor, Deputy Mayor, Councillor) per name
    _roles_x: dict[str, list[str]] = {}
    for _gn, _fn, _role in (
        session.query(_CllrX.given_name, _CllrX.family_name, _CTX.role)
        .join(_CTX, _CllrX.id == _CTX.councillor_id)
        .filter(_CTX.council_id == council_id, _CTX.role.isnot(None))
        .distinct().all()
    ):
        _n = f"{_gn or ''} {_fn or ''}".strip()
        _roles_x.setdefault(_n, [])
        if _role not in _roles_x[_n]:
            _roles_x[_n].append(_role)

    # Candidate names: the union of tenure/power/recusal profiles, not just
    # councillor_terms rows — councillor_terms (electoral-commission data) is
    # incomplete for 8 councillors with real vote/dissent/recusal history
    # (confirmed 2026-08-23, defamation review pass 1 BLOCKING flag 2: e.g.
    # Kate McKerracher, Ian Steele — both named in gated PowerPanel callouts
    # whose click-through silently failed because they had no by_name entry).
    # Slugs still come from a councillor_terms join where available, backed
    # by a votes-based fallback for names councillor_terms misses.
    _slug_map: dict[str, str] = {}
    for _gn, _fn, _slug in (
        session.query(_CllrX.given_name, _CllrX.family_name, _CllrX.slug)
        .join(_CTX, _CllrX.id == _CTX.councillor_id)
        .filter(_CTX.council_id == council_id)
        .distinct().all()
    ):
        _slug_map[f"{_gn or ''} {_fn or ''}".strip()] = _slug
    for _gn, _fn, _slug in (
        session.query(_CllrX.given_name, _CllrX.family_name, _CllrX.slug)
        .join(Vote, _CllrX.id == Vote.councillor_id)
        .join(_MotX, Vote.motion_id == _MotX.id)
        .join(_MeetX, _MotX.meeting_id == _MeetX.id)
        .filter(_MeetX.council_id == council_id)
        .distinct().all()
    ):
        _slug_map.setdefault(f"{_gn or ''} {_fn or ''}".strip(), _slug)

    # Also union in the alignment vote pool (`rows`, built above for
    # alignment.json) — confirmed 2026-08-23, defamation review pass 3
    # BLOCKING flag 1: five of the six individuals named in
    # AlignmentHeatmap.tsx's always-visible pairs note (Robert Powell, David
    # King, Erica MacRae, Kevin O'Connor, Rob Fredericks) had no by_name
    # entry, the same click-through-silently-fails failure mode already
    # fixed once for PowerPanel by this same eligibility widening. `rows` is
    # already filtered to the real-name/has-activity set (voting_alignment_
    # matrix excludes malformed extraction stubs), so no extra filtering is
    # needed here.
    _alignment_names = {n.strip() for r in rows for n in (r.councillor_a, r.councillor_b)}
    _cllr_names = set(_tenure_map) | set(_power_map) | set(_conflict_map) | _alignment_names
    _cllr_profiles: dict[str, dict] = {}
    for _name in _cllr_names:
        _slug = _slug_map.get(_name)
        _tp = _tenure_map.get(_name)
        _pp = _power_map.get(_name)
        _cp = _conflict_map.get(_name)
        # declarations newest-first, capped at 15
        _decls = sorted(
            _cp.declarations if _cp else [],
            key=lambda d: d.date or "", reverse=True,
        )[:15]
        # dissent examples: AGAINST votes from the power drill-down list, capped at 8
        _diss = [_dc(v) for v in (_pp.votes if _pp else []) if getattr(v, "choice", "") == "Against"][:8]
        # top co-sponsors by total count, capped at 3
        _top_p = sorted(
            [{"name": _pn, "count": _c} for _pn, _c in _partner_sums.get(_name, {}).items()],
            key=lambda x: -x["count"],
        )[:3]
        _cllr_profiles[_name] = {
            "name": _name,
            "slug": _slug,
            "is_active": _tp.is_active if _tp else (_pp.is_active if _pp else False),
            "tenure_years": _tp.years if _tp else None,
            "first_vote": _tp.first if _tp else None,
            "last_vote": _tp.last if _tp else None,
            "n_votes": _tp.n_votes if _tp else None,
            "roles": _roles_x.get(_name, []),
            "n_contested": _pp.n if _pp else None,
            "win_rate": round(_pp.win_rate, 3) if _pp else None,
            "dissent_rate": round(_pp.dissent_rate, 3) if _pp else None,
            "dissent_n": _pp.dissent_n if _pp else None,
            "dissent_effectiveness": (
                round(_pp.dissent_effectiveness, 3)
                if (_pp and _pp.dissent_effectiveness is not None) else None
            ),
            "n_declarations": _cp.declared_votes if _cp else 0,
            "n_recused": _cp.recused if _cp else 0,
            "recusal_rate": round(_cp.recusal_rate, 3) if _cp else None,
            "declarations": [_dc(d) for d in _decls],
            "dissent_votes": _diss,
            "moved": _moved_x.get(_name, 0),
            "seconded": _seconded_x.get(_name, 0),
            "top_partners": _top_p,
        }
    _write("councillors", {"by_name": _cllr_profiles})

    return written, battery


def cmd_draft(args) -> None:
    """Generate candidate snapshots for review — the stage before `council
    publish`. Writes to data/draft/<council>/<run_id>/, never to
    frontend/public/data/ and never committed to git. This is where the
    investigator agent and the defamation-auditor pass (built separately)
    review output before anything is eligible to be made public.
    """
    import hashlib
    import json as _json
    from datetime import datetime, timezone

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)
    short_name = COUNCILS[key]["short_name"]

    run_id = f"draft_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    output_dir = Path("data/draft") / key / run_id
    generated_at = datetime.now(timezone.utc).isoformat()

    console.print(Panel(f"Drafting [bold]{key}[/bold] → {output_dir}", style="blue"))

    from src.storage.database import init_db, make_session_factory
    from src.analysis.queries import get_council_by_name
    engine = init_db()
    session = make_session_factory(engine)()
    council_obj = get_council_by_name(session, short_name)
    if not council_obj:
        console.print(f"[red]Council '{short_name}' not found in DB[/red]")
        sys.exit(1)
    council_id = council_obj.id

    written, battery = _generate_snapshots(session, council_id, output_dir, generated_at)
    session.close()

    # S7 invariant gate (docs/INFORMATION_ARCHITECTURE.md §3, C2) — scripted,
    # runs on every draft, before a manifest exists. A failure blocks the
    # draft mechanically: no manifest.json means `council publish` cannot
    # find this run at all (see src/publish_gate.py), and no Editor call —
    # a gate failure is a blocked draft, not a review finding
    # (docs/AGENT_DESIGN.md §3 Q3).
    from dataclasses import asdict as _asdict

    from src.invariant_gate import load_min_n, run_invariant_gate
    gate = run_invariant_gate(battery, min_n=load_min_n())
    (output_dir / "gate_report.json").write_text(_json.dumps({
        "run_id": run_id,
        "council": key,
        "generated_at": generated_at,
        "passed": gate.passed,
        "violations": [_asdict(v) for v in gate.violations],
    }, indent=2))

    if not gate.passed:
        lines = "\n".join(
            f"  · [{v.test_id}] {v.check}: {v.detail}" for v in gate.violations
        )
        console.print(Panel(
            f"[red]✗ S7 invariant gate blocked this draft[/red]\n\n{lines}\n\n"
            f"[dim]Gate report: {output_dir / 'gate_report.json'}. No manifest.json was "
            "written, so `council publish` cannot find this run. Fix the generator that "
            "produced the violating claim and re-draft — this never reaches Editor or "
            "the review chain.[/dim]",
            style="red",
        ))
        sys.exit(1)

    file_hashes = {
        name: hashlib.sha256((output_dir / f"{name}.json").read_bytes()).hexdigest()
        for name in written
    }
    tiers = {name: _tier_of(name, battery) for name in written}

    (output_dir / "manifest.json").write_text(_json.dumps({
        "run_id": run_id,
        "council": key,
        "generated_at": generated_at,
        "snapshots": written,
        "file_hashes": file_hashes,
        "tiers": tiers,
    }, indent=2))

    n_public = sum(1 for t in tiers.values() if t == "public")
    n_full = len(tiers) - n_public
    console.print(Panel(
        f"[green]✓[/green] {len(written)} snapshots → {output_dir}\n"
        f"[dim]{n_public} public-tier, {n_full} full-tier[/dim]\n\n"
        f"Review this output (investigator + defamation-auditor), then run:\n"
        f"[bold]council publish {key} --from-draft {output_dir} --confirm \"<reviewer note>\"[/bold]",
        style="green",
    ))


def cmd_publish(args) -> None:
    """The publish gate: copy a reviewed draft's snapshots into
    frontend/public/data/ — the only command allowed to write there.

    Requires --from-draft (a directory produced by `council draft`) always,
    plus one of two authorization paths selected by --gate-profile:
    'interactive' (default) requires --confirm, an explicit human review
    note; 'auto' requires no --confirm, and instead independently
    re-validates a real Editor PASS record already in the draft directory
    (see src/publish_gate.py). There is no code path that publishes without
    clearing one of these. Copies bytes verbatim from the draft; never
    recomputes from the database, so what was reviewed is exactly what ships
    even if council.db has since changed. Public-tier snapshots go to
    frontend/public/data/; full-tier snapshots (paywall-pending — no serving
    layer exists yet) go to a private, gitignored data/published_full/
    instead.
    """
    import json as _json
    import shutil
    from datetime import datetime, timezone

    from src.publish_gate import load_draft_manifest, verify_draft_integrity, check_clearance

    key = args.council
    if key not in COUNCILS:
        console.print(f"[red]Unknown council: {key}[/red]")
        sys.exit(1)

    draft_dir = Path(args.from_draft)
    if not draft_dir.is_dir():
        console.print(f"[red]--from-draft directory not found: {draft_dir}[/red]")
        sys.exit(1)

    try:
        manifest = load_draft_manifest(draft_dir)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if manifest.council != key:
        console.print(
            f"[red]--from-draft is a '{manifest.council}' draft, not '{key}'[/red]"
        )
        sys.exit(1)

    drifted = verify_draft_integrity(draft_dir, manifest)
    if drifted:
        console.print(
            "[red]Refusing to publish: draft file(s) changed since review "
            f"(hash mismatch): {', '.join(drifted)}[/red]\n"
            "[dim]Re-run `council draft` and get a fresh review — publishing "
            "must reflect exactly what was reviewed.[/dim]"
        )
        sys.exit(1)

    if args.gate_profile == "interactive" and not (args.confirm or "").strip():
        console.print(
            "[red]--confirm is required in --gate-profile interactive "
            "(the default) — pass --gate-profile auto instead if this "
            "draft has a real Editor PASS record to clear it on.[/red]"
        )
        sys.exit(1)

    clearance = check_clearance(
        draft_dir, args.confirm, manifest.run_id, gate_profile=args.gate_profile,
    )
    if not clearance.cleared:
        console.print(f"[red]Not cleared to publish: {clearance.reason}[/red]")
        sys.exit(1)

    public_names = [n for n in manifest.snapshots if manifest.tiers.get(n, "full") == "public"]
    full_names = [n for n in manifest.snapshots if manifest.tiers.get(n, "full") != "public"]

    public_dir = Path("frontend/public/data")
    public_dir.mkdir(parents=True, exist_ok=True)
    for name in public_names:
        shutil.copyfile(draft_dir / f"{name}.json", public_dir / f"{name}.json")

    full_dir = None
    if full_names:
        full_dir = Path("data/published_full") / key / manifest.run_id
        full_dir.mkdir(parents=True, exist_ok=True)
        for name in full_names:
            shutil.copyfile(draft_dir / f"{name}.json", full_dir / f"{name}.json")

    published_at = datetime.now(timezone.utc).isoformat()
    (public_dir / "manifest.json").write_text(_json.dumps({
        "published_at": published_at,
        "council": key,
        "draft_run_id": manifest.run_id,
        "authorization": {
            "gate_profile": args.gate_profile,
            "confirm_note": args.confirm if args.gate_profile == "interactive" else None,
            "clearance_source": (
                clearance.reason if args.gate_profile == "auto" else None
            ),
            "reason": clearance.reason,
        },
        "snapshots": public_names,
    }, indent=2))

    summary = (
        f"[green]✓[/green] {len(public_names)} public snapshots → {public_dir}\n"
    )
    if full_dir:
        summary += (
            f"[dim]{len(full_names)} full-tier snapshots → {full_dir} "
            f"(private — no public serving layer yet)[/dim]\n"
        )
    summary += (
        f"[dim]Published at: {published_at}[/dim]\n"
        f"[dim]Cleared by: {clearance.reason}[/dim]"
    )
    console.print(Panel(summary, style="green"))


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
    p_extract.add_argument("--batch", action="store_true",
                           help="Submit as an async batch job (50%% off, up to 24 h). "
                                "Saves a job file; use 'council batch-collect' to retrieve results.")
    p_extract.set_defaults(func=cmd_extract, batch=False)

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
    p_extract_sample.add_argument("--batch", action="store_true",
                                  help="Submit as an async batch job (50%% off, up to 24 h). "
                                       "Use 'council batch-collect' to retrieve results.")
    p_extract_sample.set_defaults(func=cmd_extract_sample, batch=False)

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

    # profile (S2 corpus profile)
    p_profile = sub.add_parser(
        "profile",
        help="S2: corpus profile — NULL rates, spans, identity-resolution state, "
             "record-quality metrics as one machine-readable document (src/analysis/profile.py)",
    )
    p_profile.add_argument("council", choices=list(COUNCILS))
    p_profile.set_defaults(func=cmd_profile)

    # reply-packets (S9 right of reply — packet assembly)
    p_reply = sub.add_parser(
        "reply-packets",
        help="S9: assemble right-of-reply packets for every individual-unit claim "
             "with no reply on file (src/reply_packets.py) — never sends anything",
    )
    p_reply.add_argument("council", choices=list(COUNCILS))
    p_reply.set_defaults(func=cmd_reply_packets)

    # batch-collect
    p_batch_collect = sub.add_parser(
        "batch-collect",
        help="Collect results from a previously submitted batch job (council extract --batch)",
    )
    p_batch_collect.add_argument("council", choices=list(COUNCILS))
    p_batch_collect.add_argument(
        "batch_id", metavar="BATCH_ID",
        help="Batch ID returned when submitting (e.g. msgbatch_abc123)",
    )
    p_batch_collect.set_defaults(func=cmd_batch_collect)

    # analyse
    p_analyse = sub.add_parser("analyse", help="Run analysis queries against the DB")
    p_analyse.add_argument("council", choices=list(COUNCILS))
    p_analyse.add_argument(
        "query",
        choices=[
            "councillors", "alignment", "contested", "planning", "councillor", "motions",
            "activity", "trends", "co-movers", "interests", "engagement", "budget", "divergence",
        ],
        help=(
            "councillors: all councillors by vote count  |  "
            "alignment: pairwise voting agreement  |  "
            "contested: carried motions with opposition  |  "
            "planning: top sites + approval rate  |  "
            "councillor: one councillor's vote summary (--name)  |  "
            "motions: motions by tag (--tag)  |  "
            "activity: councillor date spans, active status, dissent rate  |  "
            "trends: contestation rate and topic distribution by year  |  "
            "co-movers: most frequent mover+seconder pairs  |  "
            "interests: interest declarations per councillor by type  |  "
            "engagement: public questions, deputations, petitions by year  |  "
            "budget: budget items and amounts by year  |  "
            "divergence: officer recommendations vs council outcomes"
        ),
    )
    p_analyse.add_argument("--from-year", type=int, metavar="YYYY", default=None,
                           dest="from_year", help="Filter to meetings from this year onwards")
    p_analyse.add_argument("--to-year", type=int, metavar="YYYY", default=None,
                           dest="to_year", help="Filter to meetings up to this year")
    p_analyse.add_argument("--min-against", type=int, default=2, dest="min_against",
                           help="Min against votes for 'contested' (default: 2)")
    p_analyse.add_argument("--min-shared", type=int, default=5, dest="min_shared",
                           help="Min shared votes for 'alignment' (default: 5)")
    p_analyse.add_argument("--min-votes", type=int, default=10, dest="min_votes",
                           help="Min vote count for 'activity' — suppresses AGM proxies (default: 10)")
    p_analyse.add_argument("--min-count", type=int, default=5, dest="min_count",
                           help="Min co-mover occurrences for 'co-movers' (default: 5)")
    p_analyse.add_argument("--active-only", action="store_true", dest="active_only",
                           help="Limit 'co-movers' to currently active councillors")
    p_analyse.add_argument("--limit", type=int, default=20,
                           help="Max rows to display (default: 20)")
    p_analyse.add_argument("--name", metavar="NAME",
                           help="Councillor family name for 'councillor' query (partial match)")
    p_analyse.add_argument("--tag", metavar="TAG",
                           help="Tag to filter by for 'motions' query")
    p_analyse.set_defaults(func=cmd_analyse)

    # build-relationships
    p_rel = sub.add_parser(
        "build-relationships",
        help="Dynamic layer: compute ALLY/OPPONENT edges from voting alignment and persist to DB (scripts/build_relationships.py)",
    )
    p_rel.add_argument("council", choices=list(COUNCILS))
    p_rel.add_argument("--min-shared", type=int, default=10, dest="min_shared",
                       help="Minimum shared votes to qualify a pair (default: 10)")
    p_rel.add_argument("--ally", type=float, default=0.85,
                       help="Agreement rate threshold for ALLY (default: 0.85)")
    p_rel.add_argument("--opponent", type=float, default=0.40,
                       help="Agreement rate threshold for OPPONENT (default: 0.40)")
    p_rel.add_argument("--from-year", type=int, default=None, dest="from_year",
                       help="Only include votes from this year onwards (default: all years)")
    p_rel.add_argument("--to-year", type=int, default=None, dest="to_year",
                       help="Only include votes up to this year (default: no limit)")
    p_rel.add_argument("--all-years", action="store_true", dest="all_years",
                       help="Include all years (overrides --from-year)")
    p_rel.add_argument("--dry-run", action="store_true", dest="dry_run",
                       help="Preview edges without writing to DB")
    def _cmd_build_relationships(a):
        from scripts.build_relationships import run as _run
        from_year = None if a.all_years else a.from_year
        _run(a.council, min_shared=a.min_shared, ally_threshold=a.ally,
             opponent_threshold=a.opponent, from_year=from_year, to_year=a.to_year,
             dry_run=a.dry_run)
    p_rel.set_defaults(func=_cmd_build_relationships)

    # audit
    p_audit = sub.add_parser(
        "audit",
        help="Level 6: generate a human-review audit report for a stratified sample of extracted docs",
    )
    p_audit.add_argument("council", help="Council key (e.g. cambridge)")
    p_audit.add_argument("--count", type=int, default=12,
                         help="Number of docs to sample (default: 12)")
    p_audit.add_argument("--from-year", type=int, default=None, dest="from_year",
                         help="Only include docs from this year onwards (default: all years)")
    p_audit.add_argument("--all-years", action="store_true", dest="all_years",
                         help="Include all extracted years (overrides --from-year)")
    p_audit.add_argument("--output", type=Path, default=None,
                         help="Output path (default: data/audit_report.md)")
    p_audit.add_argument("--seed", type=int, default=None,
                         help="Random seed for reproducible sampling")
    p_audit.add_argument("--list-only", action="store_true", dest="list_only",
                         help="List candidates without generating a report")

    def _cmd_audit(a):
        from scripts.audit_report import run as _run, DEFAULT_OUTPUT
        from_year = None if a.all_years else a.from_year
        output = a.output if a.output else DEFAULT_OUTPUT
        _run(a.council, count=a.count, from_year=from_year,
             output=output, seed=a.seed, list_only=a.list_only)

    p_audit.set_defaults(func=_cmd_audit)

    # scraper-audit
    p_saudit = sub.add_parser(
        "scraper-audit",
        help="Audit scraped corpus completeness; optionally clean manifest of noise docs",
    )
    p_saudit.add_argument("council", choices=list(COUNCILS))
    p_saudit.add_argument(
        "mode", nargs="?", default="report", choices=["report", "clean"],
        help="report (default) or clean",
    )
    p_saudit.add_argument(
        "--apply", action="store_true",
        help="With 'clean': write changes to manifest and delete noise files",
    )

    def _cmd_scraper_audit(a):
        from scripts.scraper_audit import clean as _clean, report as _report
        if a.mode == "clean":
            _clean(a.council, getattr(a, "apply", False))
        else:
            _report(a.council)

    p_saudit.set_defaults(func=_cmd_scraper_audit)

    # wayback-fill
    p_wbfill = sub.add_parser(
        "wayback-fill",
        help="Query Wayback Machine CDX for missing council minutes in given years/months",
    )
    p_wbfill.add_argument("council", choices=list(COUNCILS))
    p_wbfill.add_argument("years", nargs="+", type=int, metavar="YEAR",
                          help="Year(s) to check (e.g. 2022 2023)")
    p_wbfill.add_argument("--months", type=str, default=None, metavar="M-N",
                          help="Month range to check, e.g. 1-4 for Jan-Apr")
    p_wbfill.add_argument("--download", action="store_true",
                          help="Download newly found PDFs and update manifest")

    def _cmd_wayback_fill(a):
        from scripts.wayback_gap_fill import report_and_download
        months = None
        if a.months:
            parts = a.months.split("-")
            months = list(range(int(parts[0]), int(parts[1]) + 1)) if len(parts) == 2 else [int(parts[0])]
        report_and_download(a.council, a.years, months, a.download)

    p_wbfill.set_defaults(func=_cmd_wayback_fill)

    # geocode
    p_geocode = sub.add_parser("geocode", help="Geocode planning sites via Nominatim (E1)")
    p_geocode.add_argument("council", choices=list(COUNCILS))
    p_geocode.add_argument("--force", action="store_true",
                           help="Re-geocode sites that already have coordinates")
    p_geocode.add_argument("--dry-run", action="store_true", dest="dry_run",
                           help="Show what would be geocoded without making API calls")
    p_geocode.set_defaults(func=lambda a: __import__("scripts.geocode_sites", fromlist=["run"]).run(a))

    # merge-pdfs
    p_merge = sub.add_parser(
        "merge-pdfs",
        help="Concatenate all PDFs in a directory into a single file for OCR upload",
    )
    p_merge.add_argument("input_dir", type=Path, help="Directory containing PDFs to merge")
    p_merge.add_argument("output", type=Path, help="Output PDF path")
    p_merge.add_argument(
        "--exclude", nargs="*", default=[], metavar="PATTERN",
        help="Filename substrings to exclude (e.g. Survey Stakeholder)",
    )

    def _cmd_merge_pdfs(a):
        import fitz
        pdfs = sorted(p for p in Path(a.input_dir).glob("*.pdf")
                      if not any(x.lower() in p.name.lower() for x in a.exclude))
        if not pdfs:
            print("No PDFs found.")
            return
        out = fitz.open()
        for p in pdfs:
            print(f"  + {p.name}")
            with fitz.open(str(p)) as src:
                out.insert_pdf(src)
        out.save(str(a.output))
        size_mb = Path(a.output).stat().st_size / 1_048_576
        print(f"\nMerged {len(pdfs)} PDFs → {a.output}  ({size_mb:.1f} MB)")

    p_merge.set_defaults(func=_cmd_merge_pdfs)

    # derive-terms
    p_derive = sub.add_parser(
        "derive-terms",
        help="Generate a seed CSV of councillor term records from vote date spans (scripts/derive_terms.py)",
    )
    p_derive.add_argument("council", choices=list(COUNCILS))
    p_derive.add_argument(
        "--gap-years", type=int, default=2, dest="gap_years",
        help="Gap in calendar years that triggers a period split (default: 2)",
    )

    def _cmd_derive_terms(a):
        from scripts.derive_terms import run as _run
        _run(a.council, gap_years=a.gap_years)

    p_derive.set_defaults(func=_cmd_derive_terms)

    # import-terms
    p_import = sub.add_parser(
        "import-terms",
        help="Import a councillor terms CSV into councillor_terms (scripts/import_terms.py)",
    )
    p_import.add_argument("council", choices=list(COUNCILS))
    p_import.add_argument("csv", type=Path, help="Path to terms CSV")
    p_import.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")

    def _cmd_import_terms(a):
        from scripts.import_terms import run as _run
        _run(a.council, a.csv, apply=a.apply)

    p_import.set_defaults(func=_cmd_import_terms)

    # dedup
    p_dedup = sub.add_parser(
        "dedup",
        help="Deduplicate councillor records — merge title/placeholder/stub variants (scripts/dedup_councillors.py)",
    )
    p_dedup.add_argument("council", choices=list(COUNCILS), nargs="?",
                         help="Council (unused — dedup operates globally; kept for CLI consistency)")
    p_dedup.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    p_dedup.add_argument(
        "--use-terms", action="store_true", dest="use_terms",
        help="Annotate merges with councillor_terms coverage; with --apply only applies TERM ✓ merges",
    )

    def _cmd_dedup(a):
        from scripts.dedup_councillors import run as _run
        _run(apply=a.apply, use_terms=a.use_terms)

    p_dedup.set_defaults(func=_cmd_dedup)

    # archive-status
    p_archive_status = sub.add_parser(
        "archive-status",
        help="List archived LLM response runs for a council",
    )
    p_archive_status.add_argument("council", choices=list(COUNCILS))
    p_archive_status.set_defaults(func=cmd_archive_status)

    # archive-import
    p_archive_import = sub.add_parser(
        "archive-import",
        help="Re-import LLM responses from local archive into DB (no API calls)",
    )
    p_archive_import.add_argument("council", choices=list(COUNCILS))
    p_archive_import.add_argument(
        "run_id",
        help="Archive run ID shown by archive-status (sync_... or msgbatch_...)",
    )
    p_archive_import.add_argument(
        "--force", action="store_true",
        help="Re-import docs already in the DB (re-extraction from archive)",
    )
    p_archive_import.set_defaults(func=cmd_archive_import)

    # archive-download
    p_archive_dl = sub.add_parser(
        "archive-download",
        help="Download historical batch results from Anthropic API into local archive (no DB write)",
    )
    p_archive_dl.add_argument("council", choices=list(COUNCILS))
    p_archive_dl.add_argument(
        "batch_id", nargs="?",
        help="Batch ID to download (find IDs in data/batch_jobs/)",
    )
    p_archive_dl.add_argument(
        "--all", dest="all_batches", action="store_true",
        help="Download all batch IDs in data/batch_jobs/ for this council",
    )
    p_archive_dl.add_argument(
        "--force", action="store_true",
        help="Re-download even if already archived locally",
    )
    p_archive_dl.set_defaults(func=cmd_archive_download)

    # draft
    p_draft = sub.add_parser(
        "draft",
        help="Generate candidate dashboard snapshots to data/draft/ for review "
             "(investigator + defamation-auditor gate before publish)",
    )
    p_draft.add_argument("council", choices=list(COUNCILS))
    p_draft.set_defaults(func=cmd_draft)

    # publish
    p_publish = sub.add_parser(
        "publish",
        help="Gate: copy a reviewed draft's snapshots into frontend/public/data/ "
             "(requires --from-draft and --confirm; never recomputes)",
    )
    p_publish.add_argument("council", choices=list(COUNCILS))
    p_publish.add_argument(
        "--from-draft", required=True, metavar="PATH", dest="from_draft",
        help="Path to a data/draft/<council>/<run_id>/ directory produced by `council draft`",
    )
    p_publish.add_argument(
        "--confirm", required=False, metavar="NOTE", default=None,
        help="Explicit human confirmation that this draft has been reviewed "
             "(free-text note, e.g. reviewer name + date + summary). Required "
             "in the default --gate-profile interactive; ignored and not "
             "required in --gate-profile auto, where clearance instead comes "
             "from an on-disk Editor PASS record. There is no default-approve "
             "in interactive mode.",
    )
    p_publish.add_argument(
        "--gate-profile", choices=["interactive", "auto"], default="interactive",
        dest="gate_profile",
        help="How this publish is authorized. 'interactive' (default): "
             "requires --confirm, a human vouching directly. 'auto': requires "
             "no --confirm, instead independently re-validates a real Editor "
             "PASS record (defamation_review_<n>.json) already in the draft "
             "directory — see src/publish_gate.py and "
             "docs/review/CONDUCTOR.md's 'Gate profiles' section.",
    )
    p_publish.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    args.func(args)


if __name__ == "__main__":
    main()
