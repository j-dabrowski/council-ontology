#!/usr/bin/env python3
"""
Iterative batch extraction runner for debugging and quality control.

Processes N pending council meeting PDFs, saves successes to the database,
and writes a structured error report to data/extraction_errors.json.

Idempotent: already-extracted documents (those with a Meeting row in the DB)
are skipped automatically, so it's safe to re-run at any point.

Usage:
    python scripts/batch_extract.py                     # 5 docs, haiku
    python scripts/batch_extract.py --limit 20
    python scripts/batch_extract.py --model claude-sonnet-4-6 --limit 10
    python scripts/batch_extract.py --limit 370         # full run
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Make project root importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pydantic

from src.extraction.extractor import MinutesExtractor, save_extraction
from src.models import Council, Meeting
from src.storage.database import init_db, make_session_factory

_log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_LIMIT = 5
ERROR_REPORT_PATH = Path("data/extraction_errors.json")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False) -> None:
    """Mirror the logging configuration from src/cli.py main()."""
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler("council.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)

    # Keep third-party libraries quiet
    for noisy in ("anthropic", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_pending_pdfs(session, council: Council, raw_dir: Path, manifest: dict) -> list[Path]:
    """
    Return sorted list of PDFs that have not yet been processed.

    A PDF is considered done if either:
    - its basename is the canonical minutes_pdf_path of a meeting, OR
    - its manifest date already has a meeting row in the DB (meaning a sibling
      PDF for the same date was already extracted — common when the scraper
      downloads multiple document types per meeting).
    """
    if not raw_dir.exists():
        return []
    all_pdfs = sorted(raw_dir.glob("*.pdf"))

    rows = (
        session.query(Meeting)
        .filter(Meeting.council_id == council.id)
        .all()
    )
    ingested_names: set[str] = {
        Path(row.minutes_pdf_path).name
        for row in rows
        if row.minutes_pdf_path
    }
    ingested_dates: set[str] = {str(row.meeting_date) for row in rows}

    result = []
    for p in all_pdfs:
        if p.name in ingested_names:
            continue
        manifest_date = manifest.get(p.name, {}).get("meeting_date", "")
        if manifest_date and manifest_date in ingested_dates:
            continue
        result.append(p)
    return result


def _filter_pdfs_by_year(
    pdfs: list[Path],
    manifest: dict,
    from_year: int | None,
    to_year: int | None,
) -> tuple[list[Path], int]:
    """
    Filter PDFs to those whose manifest date falls within [from_year, to_year].
    PDFs with no manifest date are excluded when any filter is active.
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


def _classify_error(exc: Exception) -> str:
    """
    Return a short, groupable key describing this error.

    Pydantic ValidationErrors are decomposed to their first field + error type
    so a single fix can address the entire class:
      ValidationError:missing@motions.0.outcome
      ValidationError:literal_error@motions.0.individual_votes.0.choice
    """
    if isinstance(exc, pydantic.ValidationError):
        errs = exc.errors(include_url=False)
        if errs:
            e = errs[0]
            loc = ".".join(
                # Collapse list indices to [] to group across different list positions
                "[]" if isinstance(part, int) else str(part)
                for part in e["loc"]
            ) if e["loc"] else "(root)"
            return f"ValidationError:{e['type']}@{loc}"
        return "ValidationError:unknown"
    if isinstance(exc, (json.JSONDecodeError, ValueError)) and "JSON" in str(exc):
        return "JSONDecodeError"
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------

def run_batch(
    council_key: str,
    model: str,
    limit: int,
    from_year: int | None = None,
    to_year: int | None = None,
    files: list[str] | None = None,
    force: bool = False,
) -> dict:
    """
    Process up to `limit` pending PDFs and return a result dict for the report.

    When `files` is given, processes exactly those PDFs regardless of pending
    status, date filters, or limit. Use `force=True` to re-run files that are
    already in the DB.
    """
    engine = init_db()
    session = make_session_factory(engine)()

    council = session.query(Council).filter_by(
        short_name=council_key.capitalize()
    ).first()
    if council is None:
        raise SystemExit(f"Council '{council_key}' not found in database.")

    raw_dir = Path("data/raw") / council_key
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    targeted_mode = bool(files)

    if targeted_mode:
        # Resolve specified filenames to paths in raw_dir
        batch: list[Path] = []
        for f in files:  # type: ignore[union-attr]
            pdf_path = raw_dir / Path(f).name
            if pdf_path.exists():
                batch.append(pdf_path)
            else:
                print(f"  WARNING: {Path(f).name} not found in {raw_dir}, skipping")
        if not batch:
            raise SystemExit("No valid PDF files found.")
        total_pending = len(batch)
        in_range = len(batch)
        _log.info(
            "batch_extract start: targeted %d file(s), model=%s, force=%s",
            len(batch), model, force,
        )
        print(f"Targeted: {len(batch)} file(s)  |  Model: {model}  |  Force: {force}\n")
    else:
        # Normal mode: pending detection → date filter → limit
        pending = _get_pending_pdfs(session, council, raw_dir, manifest)
        total_pending = len(pending)

        pending, n_no_date = _filter_pdfs_by_year(pending, manifest, from_year, to_year)
        if from_year or to_year:
            yr_range = f"{from_year or '∞'}–{to_year or '∞'}"
            note = f" ({n_no_date} excluded — no manifest date)" if n_no_date else ""
            print(f"Date filter {yr_range}: {len(pending)} of {total_pending} PDFs match{note}")

        batch = pending[:limit]
        in_range = len(pending)
        _log.info(
            "batch_extract start: %d pending (%d in range), processing %d, model=%s",
            total_pending, in_range, len(batch), model,
        )
        print(f"In range: {in_range}  |  This batch: {len(batch)}  |  Model: {model}\n")

    # Build a lookup of already-extracted basenames for fast skip checks
    extracted_names: dict[str, int] = {
        Path(row.minutes_pdf_path).name: row.id
        for row in session.query(Meeting)
        .filter(Meeting.council_id == council.id, Meeting.minutes_pdf_path.isnot(None))
        .all()
    }

    extractor = MinutesExtractor(model=model)

    successes: list[dict] = []
    failures: list[dict] = []
    skipped: list[dict] = []

    for i, pdf in enumerate(batch, 1):
        meta = manifest.get(pdf.name, {})
        meeting_date_hint = meta.get("meeting_date")
        prefix = f"[{i:3d}/{len(batch)}] {pdf.name}"
        print(f"{prefix} ...", end=" ", flush=True)

        # Skip already-extracted unless --force
        if not force and pdf.name in extracted_names:
            meeting_id = extracted_names[pdf.name]
            print(f"SKIP  (meeting {meeting_id}, already extracted — use --force to re-run)")
            _log.info("SKIP: %s (meeting %d)", pdf.name, meeting_id)
            skipped.append({"filename": pdf.name, "meeting_id": meeting_id})
            continue

        try:
            extracted, raw_text = extractor.extract_from_pdf(
                pdf,
                council_name=council.name,
                meeting_date_hint=meeting_date_hint,
            )
            meeting_id = save_extraction(session, council.id, extracted, pdf, text=raw_text)
            detail = (
                f"meeting {meeting_id} "
                f"({extracted.meeting_date}, {len(extracted.motions)} motions)"
            )
            print(f"OK  → {detail}")
            _log.info("OK: %s → %s", pdf.name, detail)
            successes.append({"filename": pdf.name, "meeting_id": meeting_id, "detail": detail})

        except Exception as exc:  # noqa: BLE001
            raw_response: str | None = getattr(exc, "raw_llm_response", None)
            error_class = _classify_error(exc)
            print(f"FAIL  [{error_class}]")
            _log.error("FAIL: %s: %s", pdf.name, exc)
            failures.append({
                "filename": pdf.name,
                "error_class": error_class,
                "error_type": type(exc).__qualname__,
                "error_message": str(exc),
                "raw_llm_response": raw_response,
            })

    session.close()
    _log.info(
        "batch_extract done: %d ok, %d failed, %d skipped",
        len(successes), len(failures), len(skipped),
    )

    # Group failures by error class, sorted by frequency desc
    errors_by_class: dict[str, list[dict]] = defaultdict(list)
    for entry in failures:
        errors_by_class[entry["error_class"]].append(entry)
    errors_by_class = dict(
        sorted(errors_by_class.items(), key=lambda kv: -len(kv[1]))
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "council": council_key,
        "targeted_files": files,
        "force": force,
        "from_year": from_year,
        "to_year": to_year,
        "total_pending_before_run": total_pending,
        "in_date_range": in_range,
        "limit": limit if not targeted_mode else None,
        "attempted": len(batch),
        "succeeded": len(successes),
        "failed": len(failures),
        "skipped": len(skipped),
        "successes": successes,
        "errors_by_class": errors_by_class,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(args) -> None:
    """Core logic — callable from the CLI or run standalone via main()."""
    report = run_batch(
        council_key=args.council,
        model=args.model,
        limit=args.limit,
        from_year=args.from_year,
        to_year=args.to_year,
        files=args.files,
        force=args.force,
    )

    ERROR_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERROR_REPORT_PATH.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )

    n_ok = report["succeeded"]
    n_fail = report["failed"]
    n_skip = report["skipped"]
    n_total = report["attempted"]
    remaining = report["total_pending_before_run"] - n_ok

    hr = "─" * 52
    print(f"\n{hr}")
    print(f"  Attempted : {n_total}")
    print(f"  Succeeded : {n_ok}")
    print(f"  Failed    : {n_fail}")
    if n_skip:
        print(f"  Skipped   : {n_skip}  (already extracted, use --force to re-run)")

    if report["errors_by_class"]:
        print(f"\n  Error breakdown:")
        for cls, entries in report["errors_by_class"].items():
            print(f"    {len(entries):3d}×  {cls}")
        print(f"\n  Full report → {ERROR_REPORT_PATH}")
    else:
        print("\n  No errors.")

    if not report["targeted_files"]:
        print(f"\n  Docs still pending: {remaining}")
    print(hr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Iterative batch extraction runner. Safe to re-run — skips already-extracted docs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Typical workflow:
  1.  python scripts/batch_extract.py --limit 5       # first pass, haiku
  2.  review data/extraction_errors.json
  3.  fix the error class (schema / prompt / coercion)
  4.  re-run same command to verify fix
  5.  python scripts/batch_extract.py --limit 50      # wider pass
  6.  python scripts/batch_extract.py --limit 370     # full haiku run
  7.  python scripts/batch_extract.py --model claude-sonnet-4-6 --limit 10
  8.  final: council extract cambridge (or batch API)
        """,
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=DEFAULT_LIMIT, metavar="N",
        help=f"Max pending docs to process in this run (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--council", default="cambridge", choices=["cambridge"],
        help="Council key (default: cambridge)",
    )
    parser.add_argument(
        "--from-year", type=int, metavar="YYYY", dest="from_year",
        help="Only process meetings from this year onward (uses manifest date)",
    )
    parser.add_argument(
        "--to-year", type=int, metavar="YYYY", dest="to_year",
        help="Only process meetings up to and including this year",
    )
    parser.add_argument(
        "--files", nargs="+", metavar="PDF",
        help="Process only these specific PDFs (basenames); ignores --limit and date filters",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-extract already-extracted PDFs (default: skip them)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Emit DEBUG logs to stderr in addition to council.log",
    )
    args = parser.parse_args()

    _setup_logging(verbose=args.verbose)
    run(args)


if __name__ == "__main__":
    main()
