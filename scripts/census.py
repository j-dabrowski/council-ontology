#!/usr/bin/env python3
"""
Level 0 census: text extraction + keyword/section scan across all council PDFs.

Produces:
  data/census.json         — per-document metadata, keyword counts, flags
  data/census_summary.txt  — aggregate stats and outlier list

Incremental by default: existing census entries are preserved and only new
or changed PDFs are scanned. Use --force to rescan everything.

Usage:
    python scripts/census.py cambridge
    python scripts/census.py cambridge --force
    python scripts/census.py cambridge --quiet
    council census cambridge [--force] [--quiet]
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pypdf import PdfReader
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

console = Console()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CENSUS_DIR = Path("data")
CENSUS_PATH = CENSUS_DIR / "census.json"
SUMMARY_PATH = CENSUS_DIR / "census_summary.txt"

# ---------------------------------------------------------------------------
# Keyword groups: {group: {display_name: regex_pattern}}
# ---------------------------------------------------------------------------

KEYWORD_GROUPS: dict[str, dict[str, str]] = {
    "agenda": {
        "OFFICER RECOMMENDATION": r"OFFICER RECOMMENDATION",
        "RECOMMENDED THAT":       r"RECOMMENDED THAT",
        "PROPOSED RESOLUTION":    r"PROPOSED RESOLUTION",
    },
    "motions": {
        "MOVED":      r"\bMOVED\b",
        "SECONDED":   r"\bSECONDED\b",
        "RESOLVED":   r"\bRESOLVED\b",
        "AMENDMENT":  r"\bAMENDMENT\b",
        "MOTION":     r"\bMOTION\b",
    },
    "votes": {
        "CARRIED":    r"\bCARRIED\b",
        "LOST":       r"\bLOST\b",
        "WITHDRAWN":  r"\bWITHDRAWN\b",
        "DEFERRED":   r"\bDEFERRED\b",
        "LAPSED":     r"\bLAPSED\b",
        "DIVISION":   r"\bDIVISION\b",
        "FOR:":       r"\bFOR\s*:",
        "AGAINST:":   r"\bAGAINST\s*:",
    },
    "planning": {
        "DEVELOPMENT APPLICATION": r"DEVELOPMENT APPLICATION",
        "PLANNING APPLICATION":    r"PLANNING APPLICATION",
        "DA":                      r"\bDA\b",
        "DV":                      r"\bDV\b",
        "LOT":                     r"\bLOT\b",
        "SITE ADDRESS":            r"SITE ADDRESS",
    },
    "interests": {
        "DECLARATION OF INTEREST": r"DECLARATION OF INTEREST",
        "FINANCIAL INTEREST":      r"FINANCIAL INTEREST",
        "IMPARTIALITY INTEREST":   r"IMPARTIALITY INTEREST",
        "CONFLICT OF INTEREST":    r"CONFLICT OF INTEREST",
    },
    "community": {
        "PETITION":       r"\bPETITION\b",
        "SUBMISSION":     r"\bSUBMISSION\b",
        "OBJECTION":      r"\bOBJECTION\b",
        "DEPUTATION":     r"\bDEPUTATION\b",
        "PUBLIC QUESTION": r"PUBLIC QUESTION",
    },
    "budget": {
        "BUDGET":      r"\bBUDGET\b",
        "EXPENDITURE": r"\bEXPENDITURE\b",
        "REVENUE":     r"\bREVENUE\b",
        "RATES":       r"\bRATES\b",
        "LEVY":        r"\bLEVY\b",
    },
    "procedural": {
        "MINUTES CONFIRMED": r"MINUTES CONFIRMED",
        "APOLOGIES":         r"\bAPOLOGIES\b",
        "LEAVE OF ABSENCE":  r"LEAVE OF ABSENCE",
        "PRESIDING MEMBER":  r"PRESIDING MEMBER",
    },
}

# Pre-compiled regex cache: group → {name: compiled_pattern}
_COMPILED: dict[str, dict[str, re.Pattern]] = {
    group: {name: re.compile(pattern, re.IGNORECASE) for name, pattern in kws.items()}
    for group, kws in KEYWORD_GROUPS.items()
}

# Section header patterns — numbered items like "9.1", "12.3.4", uppercase titles
_SECTION_PATTERN = re.compile(
    r"^\s*(?:\d+\.)+\d*\s+[A-Z]|^\s*[A-Z]{4,}(?:\s+[A-Z]+)*\s*$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Size buckets
# ---------------------------------------------------------------------------

def _size_bucket(char_count: int | None) -> str:
    if char_count is None:
        return "failed"
    if char_count < 10_000:
        return "tiny"
    if char_count < 50_000:
        return "small"
    if char_count < 200_000:
        return "medium"
    return "large"


def _decade(meeting_date: str | None) -> str:
    if not meeting_date or len(meeting_date) < 4:
        return "unknown"
    try:
        year = int(meeting_date[:4])
    except ValueError:
        return "unknown"
    if year < 2000:
        return "1990s"
    if year < 2010:
        return "2000s"
    if year < 2020:
        return "2010s"
    return "2020s"


# ---------------------------------------------------------------------------
# Per-document scan
# ---------------------------------------------------------------------------

def _extract_text(pdf_path: Path) -> tuple[str | None, str | None]:
    """Return (text, error_message). text is None on failure."""
    try:
        reader = PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n\n".join(parts)
        return text, None
    except Exception as exc:
        return None, str(exc)


def scan_document(pdf_path: Path, manifest: dict) -> dict:
    """Produce a census record for a single PDF."""
    meta = manifest.get(pdf_path.name, {})
    meeting_date: str | None = meta.get("meeting_date") or None
    meeting_type: str | None = meta.get("meeting_type") or None
    document_type: str = meta.get("document_type") or "unknown"

    text, error_msg = _extract_text(pdf_path)

    if text is None:
        return {
            "filename": pdf_path.name,
            "meeting_date": meeting_date,
            "meeting_type": meeting_type,
            "document_type": document_type,
            "char_count": None,
            "size_bucket": "failed",
            "decade": _decade(meeting_date),
            "extraction_status": "error",
            "error_message": error_msg,
            "keyword_counts": {g: {k: 0 for k in kws} for g, kws in KEYWORD_GROUPS.items()},
            "section_count": 0,
            "estimated_motions": 0,
            "estimated_planning_items": 0,
            "estimated_interest_declarations": 0,
            "estimated_officer_recommendations": 0,
            "flags": ["extraction_error"],
        }

    char_count = len(text)

    if not text.strip():
        return {
            "filename": pdf_path.name,
            "meeting_date": meeting_date,
            "meeting_type": meeting_type,
            "document_type": document_type,
            "char_count": char_count,
            "size_bucket": "failed",
            "decade": _decade(meeting_date),
            "extraction_status": "empty",
            "error_message": None,
            "keyword_counts": {g: {k: 0 for k in kws} for g, kws in KEYWORD_GROUPS.items()},
            "section_count": 0,
            "estimated_motions": 0,
            "estimated_planning_items": 0,
            "estimated_interest_declarations": 0,
            "estimated_officer_recommendations": 0,
            "flags": ["extraction_empty"],
        }

    # Keyword counts
    keyword_counts: dict[str, dict[str, int]] = {}
    for group, patterns in _COMPILED.items():
        keyword_counts[group] = {name: len(pat.findall(text)) for name, pat in patterns.items()}

    # Section headers
    section_count = len(_SECTION_PATTERN.findall(text))

    # Derived entity estimates
    kc = keyword_counts
    moved = kc["motions"].get("MOVED", 0)
    outcome_sum = sum([
        kc["votes"].get("CARRIED", 0),
        kc["votes"].get("LOST", 0),
        kc["votes"].get("WITHDRAWN", 0),
        kc["votes"].get("DEFERRED", 0),
        kc["votes"].get("LAPSED", 0),
    ])
    estimated_motions = max(moved, outcome_sum)

    da_count = kc["planning"].get("DA", 0)
    dev_app = kc["planning"].get("DEVELOPMENT APPLICATION", 0)
    estimated_planning_items = max(da_count, dev_app)

    decl = kc["interests"].get("DECLARATION OF INTEREST", 0)
    fin = kc["interests"].get("FINANCIAL INTEREST", 0)
    imp = kc["interests"].get("IMPARTIALITY INTEREST", 0)
    estimated_interest_declarations = max(decl, fin + imp)

    # Officer recommendation estimate (agendas)
    rec_hits = keyword_counts.get("agenda", {})
    estimated_officer_recommendations = max(
        rec_hits.get("OFFICER RECOMMENDATION", 0),
        rec_hits.get("RECOMMENDED THAT", 0),
    )

    # Flags
    flags: list[str] = []
    total_keyword_hits = sum(n for g in keyword_counts.values() for n in g.values())
    if total_keyword_hits == 0:
        flags.append("zero_keyword_hits")
    # no_motion_keywords is only meaningful for documents expected to have votes
    if moved == 0 and outcome_sum == 0 and document_type not in ("agenda", "addendum", "briefing_notes", "unknown"):
        flags.append("no_motion_keywords")
    bucket = _size_bucket(char_count)
    if bucket == "tiny":
        flags.append("tiny_document")
    if bucket == "large":
        flags.append("large_document")
    if da_count > 20:
        flags.append("high_da_count")

    return {
        "filename": pdf_path.name,
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
        "document_type": document_type,
        "char_count": char_count,
        "size_bucket": bucket,
        "decade": _decade(meeting_date),
        "extraction_status": "ok",
        "error_message": None,
        "keyword_counts": keyword_counts,
        "section_count": section_count,
        "estimated_motions": estimated_motions,
        "estimated_planning_items": estimated_planning_items,
        "estimated_interest_declarations": estimated_interest_declarations,
        "estimated_officer_recommendations": estimated_officer_recommendations,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def _build_summary(records: list[dict]) -> str:
    total = len(records)
    if total == 0:
        return "No documents in census."

    status_counts: Counter = Counter(r["extraction_status"] for r in records)
    bucket_counts: Counter = Counter(r["size_bucket"] for r in records)
    decade_counts: Counter = Counter(r["decade"] for r in records)

    total_chars = sum(r["char_count"] or 0 for r in records)
    avg_chars = total_chars // total if total else 0

    # Aggregate keyword totals
    group_totals: dict[str, int] = {}
    for group in KEYWORD_GROUPS:
        group_totals[group] = sum(
            sum(r["keyword_counts"].get(group, {}).values())
            for r in records
        )

    # Estimated entity totals
    total_motions = sum(r["estimated_motions"] for r in records)
    total_planning = sum(r["estimated_planning_items"] for r in records)
    total_interests = sum(r["estimated_interest_declarations"] for r in records)

    # Outliers
    flagged: dict[str, list[str]] = {}
    for r in records:
        for flag in r["flags"]:
            flagged.setdefault(flag, []).append(r["filename"])

    lines = [
        "=" * 68,
        "  CENSUS SUMMARY",
        f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 68,
        "",
        f"  Total documents:      {total:>6,}",
        f"  Total chars:          {total_chars:>12,}",
        f"  Average chars/doc:    {avg_chars:>12,}",
        "",
        "  Extraction status:",
        f"    OK:                 {status_counts.get('ok', 0):>6,}",
        f"    Empty:              {status_counts.get('empty', 0):>6,}",
        f"    Error:              {status_counts.get('error', 0):>6,}",
        "",
        "  Size buckets:",
        f"    tiny   (<10k):      {bucket_counts.get('tiny', 0):>6,}",
        f"    small  (10-50k):    {bucket_counts.get('small', 0):>6,}",
        f"    medium (50-200k):   {bucket_counts.get('medium', 0):>6,}",
        f"    large  (200k+):     {bucket_counts.get('large', 0):>6,}",
        f"    failed:             {bucket_counts.get('failed', 0):>6,}",
        "",
        "  By decade:",
        *[f"    {d}:              {n:>6,}" for d, n in sorted(decade_counts.items())],
        "",
        "  Estimated entity totals (across OK documents):",
        f"    Motions:            {total_motions:>6,}",
        f"    Planning items:     {total_planning:>6,}",
        f"    Interest decls:     {total_interests:>6,}",
        "",
        "  Keyword group hit counts:",
        *[f"    {g:<22} {n:>8,}" for g, n in sorted(group_totals.items(), key=lambda x: -x[1])],
        "",
    ]

    if flagged:
        lines.append("  Flagged documents:")
        for flag, filenames in sorted(flagged.items()):
            lines.append(f"    {flag} ({len(filenames)}):")
            for fn in filenames[:5]:
                lines.append(f"      {fn}")
            if len(filenames) > 5:
                lines.append(f"      ... and {len(filenames) - 5} more")
    else:
        lines.append("  No flagged documents.")

    lines.append("=" * 68)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def _scan_worker(args_tuple: tuple) -> dict:
    """Top-level function for ProcessPoolExecutor (must be picklable)."""
    pdf_path, manifest = args_tuple
    return scan_document(Path(pdf_path), manifest)


def run(args) -> None:
    council_key: str = args.council
    force: bool = getattr(args, "force", False)
    quiet: bool = getattr(args, "quiet", False)
    workers: int = getattr(args, "workers", None) or min(8, os.cpu_count() or 4)

    raw_dir = Path("data/raw") / council_key
    manifest_path = raw_dir / "manifest.json"

    if not raw_dir.exists():
        console.print(f"[red]No raw directory for '{council_key}'. Run scrape first.[/red]")
        raise SystemExit(1)

    manifest: dict = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    all_pdfs = sorted(raw_dir.glob("*.pdf"))
    if not all_pdfs:
        console.print(f"[yellow]No PDFs found in {raw_dir}.[/yellow]")
        return

    # Load existing census
    existing: dict[str, dict] = {}
    if CENSUS_PATH.exists() and not force:
        try:
            raw = json.loads(CENSUS_PATH.read_text())
            for record in raw.get("documents", []):
                existing[record["filename"]] = record
        except Exception:
            pass

    # Decide which PDFs need scanning
    to_scan = [p for p in all_pdfs if force or p.name not in existing]
    already_done = len(all_pdfs) - len(to_scan)

    if not force and already_done:
        console.print(
            f"[dim]Incremental mode: {already_done} cached, {len(to_scan)} to scan[/dim]"
        )

    if not to_scan:
        console.print("[green]Census is up-to-date. Use --force to rescan.[/green]")
        records = list(existing.values())
        _write_outputs(records, quiet)
        return

    # Scan PDFs in parallel
    new_records: dict[str, dict] = {}
    n_errors = 0
    # Pass str paths to workers (Path objects aren't always picklable across platforms)
    work_items = [(str(p), manifest) for p in to_scan]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        disable=quiet,
    ) as progress:
        task = progress.add_task(
            f"Scanning {len(to_scan)} PDFs ({workers} workers)…", total=len(to_scan)
        )
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_scan_worker, item): item[0] for item in work_items}
            for fut in as_completed(futures):
                record = fut.result()
                new_records[record["filename"]] = record
                if record["extraction_status"] != "ok":
                    n_errors += 1
                    if not quiet:
                        status = record["extraction_status"]
                        msg = record.get("error_message") or status
                        console.print(f"  [yellow]⚠[/yellow]  {record['filename']}: {msg}")
                progress.advance(task)

    # Merge: existing + new (new overwrites if --force)
    merged = {**existing, **new_records}
    # Sort by filename for deterministic output
    records = [merged[p.name] for p in all_pdfs if p.name in merged]

    console.print(
        f"[bold]Scanned {len(to_scan)} PDFs[/bold] "
        f"({'0' if not n_errors else str(n_errors)} errors)"
    )

    _write_outputs(records, quiet)


def _write_outputs(records: list[dict], quiet: bool) -> None:
    CENSUS_DIR.mkdir(parents=True, exist_ok=True)

    # census.json
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(records),
        "documents": records,
    }
    CENSUS_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # census_summary.txt
    summary = _build_summary(records)
    SUMMARY_PATH.write_text(summary, encoding="utf-8")

    if not quiet:
        console.print(f"\n{summary}")
        console.print(f"\n[dim]→ {CENSUS_PATH}[/dim]")
        console.print(f"[dim]→ {SUMMARY_PATH}[/dim]")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Level 0 census: keyword scan across all council PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--force", action="store_true",
                        help="Rescan all PDFs, ignoring cached results")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress per-document output and summary")
    parser.add_argument("--workers", type=int, default=None, metavar="N",
                        help=f"Parallel worker processes (default: min(8, cpu_count))")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
