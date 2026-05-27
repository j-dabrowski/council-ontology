#!/usr/bin/env python3
"""
Estimate Anthropic API cost for extracting pending council meeting documents.

Mirrors the logic in src/extraction/extractor.py exactly:
  - text extracted via pypdf (same as extract_text_from_pdf)
  - truncated to first 80,000 chars (same as _chunk_text)
  - prompt overhead matches the actual user/system prompts
  - max_tokens=64,000 used for output token estimate

Saves a JSON report to data/cost_estimates/ for later reference.

Usage:
    python estimate_costs.py
    python estimate_costs.py --from-year 2020
    python estimate_costs.py --from-year 2020 --to-year 2023
    python estimate_costs.py --quiet           # suppress per-doc lines
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve imports from project root
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from pypdf import PdfReader

from src.models import Council, Meeting
from src.storage.database import init_db, make_session_factory
from src.extraction.extractor import _SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Pipeline constants — keep in sync with src/extraction/extractor.py
# ---------------------------------------------------------------------------

MAX_CHARS = 80_000          # _chunk_text default; only first chunk is used
MAX_OUTPUT_TOKENS = 64_000  # max_tokens passed to the API
CHARS_PER_TOKEN = 4

# User-prompt overhead (everything except the document text itself)
_USER_PROMPT_TEMPLATE_OVERHEAD = (
    "Council: City of Cambridge\n\n"
    "Extract all entities from the following council meeting minutes:\n\n"
    "---\n\n---"
)

PROMPT_OVERHEAD_TOKENS = (
    len(_SYSTEM_PROMPT) + len(_USER_PROMPT_TEMPLATE_OVERHEAD)
) // CHARS_PER_TOKEN

# ---------------------------------------------------------------------------
# Model pricing: (label, input $/MTok, output $/MTok)
# ---------------------------------------------------------------------------

MODELS = [
    ("Opus 4.6",          5.00, 25.00),
    ("Opus 4.6 batch",    2.50, 12.50),
    ("Sonnet 4.6",        3.00, 15.00),
    ("Sonnet 4.6 batch",  1.50,  7.50),
    ("Haiku 4.5",         1.00,  5.00),
    ("Haiku 4.5 batch",   0.50,  2.50),
]

REPORT_DIR = Path("data/cost_estimates")
COL_W = 22


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from a PDF — identical to extractor.py."""
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def get_pending_pdfs(session, council: Council, raw_dir: Path, manifest: dict) -> list[Path]:
    """
    Return PDFs that have not yet been processed.

    A PDF is considered done if either:
    - its basename is the canonical minutes_pdf_path of a meeting, OR
    - its manifest date already has a meeting row in the DB (sibling PDF for
      the same date was already extracted).
    """
    if not raw_dir.exists():
        return []
    all_pdfs = sorted(raw_dir.glob("*.pdf"))
    if not all_pdfs:
        return []

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


def filter_pdfs_by_year(
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args) -> None:
    """Core logic — callable from the CLI or run standalone via main()."""
    # Resolve truncation limit: None means no cap (full document)
    if args.max_chars.lower() == "full":
        trunc_limit: int | None = None
        trunc_label = "full (no truncation)"
    else:
        try:
            trunc_limit = int(args.max_chars)
        except ValueError:
            print(f"--max-chars must be an integer or 'full', got: {args.max_chars!r}")
            raise SystemExit(1)
        trunc_label = f"{trunc_limit:,} chars" + (" (pipeline default)" if trunc_limit == MAX_CHARS else "")

    if args.show:
        if not (REPORT_DIR / "latest.json").exists():
            print("No saved report found. Run without --show first.")
            raise SystemExit(1)
        report = json.loads((REPORT_DIR / "latest.json").read_text())
        print(f"Generated: {report['generated_at']}")
        print(report["summary_text"])
        return

    engine = init_db()
    session = make_session_factory(engine)()

    councils = session.query(Council).all()
    if not councils:
        print("No councils in database.")
        return

    # Track across all councils for the report
    all_doc_records: list[dict] = []
    grand_total_docs = 0
    grand_total_input_tokens = 0
    run_ts = datetime.now(timezone.utc)

    for council in councils:
        key = council.short_name.lower()
        raw_dir = Path("data/raw") / key

        manifest_path = raw_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

        pending = get_pending_pdfs(session, council, raw_dir, manifest)

        pending, n_no_date = filter_pdfs_by_year(
            pending, manifest, args.from_year, args.to_year
        )

        yr_range = ""
        if args.from_year or args.to_year:
            yr_range = f" [{args.from_year or '∞'}–{args.to_year or '∞'}]"

        print(f"\n{'─'*60}")
        print(f"  {council.name}  —  {len(pending)} pending PDFs{yr_range}")
        if n_no_date:
            print(f"  ({n_no_date} excluded — no manifest date)")
        print(f"{'─'*60}")

        if not pending:
            print("  (nothing to estimate)")
            continue

        doc_input_tokens: list[int] = []
        n_missing = 0
        n_errors = 0

        for i, pdf_path in enumerate(pending, 1):
            label = f"[{i:3d}/{len(pending)}] {pdf_path.name}"
            meta = manifest.get(pdf_path.name, {})
            meeting_date = meta.get("meeting_date", "")
            try:
                text = extract_text_from_pdf(pdf_path)
                if not text.strip():
                    if not args.quiet:
                        print(f"  {label}  →  (no extractable text, skipped)")
                    n_missing += 1
                    continue
                raw_chars = len(text)
                effective_chars = raw_chars if trunc_limit is None else min(raw_chars, trunc_limit)
                text_tokens = effective_chars // CHARS_PER_TOKEN
                total_input = text_tokens + PROMPT_OVERHEAD_TOKENS
                doc_input_tokens.append(total_input)
                is_truncated = trunc_limit is not None and raw_chars > trunc_limit
                all_doc_records.append({
                    "council": key,
                    "filename": pdf_path.name,
                    "meeting_date": meeting_date,
                    "raw_chars": raw_chars,
                    "effective_chars": effective_chars,
                    "truncated": is_truncated,
                    "input_tokens": total_input,
                    "output_tokens": MAX_OUTPUT_TOKENS,
                })
                if not args.quiet:
                    truncated = " [truncated]" if is_truncated else ""
                    print(
                        f"  {label}  →  {raw_chars:>7,} chars"
                        f"{truncated}  ≈ {total_input:>6,} input tokens"
                    )
            except Exception as exc:
                if not args.quiet:
                    print(f"  {label}  →  ERROR: {exc}")
                n_errors += 1

        if n_missing:
            print(f"\n  Skipped {n_missing} PDF(s) with no extractable text.")
        if n_errors:
            print(f"  Skipped {n_errors} PDF(s) due to read errors.")

        council_docs = len(doc_input_tokens)
        council_input_tokens = sum(doc_input_tokens)
        grand_total_docs += council_docs
        grand_total_input_tokens += council_input_tokens

    # -------------------------------------------------------------------------
    # Summary table
    # -------------------------------------------------------------------------
    if grand_total_docs == 0:
        print("\nNo pending documents with extractable text — nothing to estimate.")
        return

    grand_total_output_tokens = grand_total_docs * MAX_OUTPUT_TOKENS

    # Build summary text so it can be both printed and stored in the report
    hr = "=" * 68
    lines = []
    lines.append(hr)
    lines.append("  COST ESTIMATE SUMMARY")
    if args.from_year or args.to_year:
        lines.append(f"  Date range: {args.from_year or '∞'} – {args.to_year or '∞'}")
    lines.append(f"  Truncation: {trunc_label}")
    lines.append(hr)
    lines.append(f"  {'Total pending documents':<30} {grand_total_docs:>10,}")
    lines.append(f"  {'Total input tokens':<30} {grand_total_input_tokens:>10,}")
    lines.append(f"  {'Output tokens per doc (max)':<30} {MAX_OUTPUT_TOKENS:>10,}")
    lines.append(f"  {'Total output tokens':<30} {grand_total_output_tokens:>10,}")
    lines.append("")
    lines.append("  NOTE: adaptive thinking tokens not included — actual costs may be")
    lines.append("  significantly higher, especially with Opus.")
    lines.append("")
    lines.append(hr)
    lines.append(
        f"  {'Model':<{COL_W}} {'In $/MTok':>10} {'Out $/MTok':>11} {'Est. Cost':>12}"
    )
    lines.append(f"  {'-'*COL_W} {'-'*10} {'-'*11} {'-'*12}")

    cost_rows = []
    for label, in_rate, out_rate in MODELS:
        cost = (
            grand_total_input_tokens / 1_000_000 * in_rate
            + grand_total_output_tokens / 1_000_000 * out_rate
        )
        cost_rows.append({
            "model": label,
            "input_per_mtok": in_rate,
            "output_per_mtok": out_rate,
            "estimated_cost_usd": round(cost, 2),
        })
        lines.append(
            f"  {label:<{COL_W}} ${in_rate:>8.2f}   ${out_rate:>9.2f}   ${cost:>10.2f}"
        )

    lines.append(hr)
    summary_text = "\n".join(lines)
    print(f"\n{summary_text}")

    # -------------------------------------------------------------------------
    # Save report
    # -------------------------------------------------------------------------
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    ts_str = run_ts.strftime("%Y%m%d_%H%M%S")
    range_tag = ""
    if args.from_year:
        range_tag += f"_from{args.from_year}"
    if args.to_year:
        range_tag += f"_to{args.to_year}"
    if trunc_limit is None:
        range_tag += "_full"
    elif trunc_limit != MAX_CHARS:
        range_tag += f"_cap{trunc_limit}"
    report_filename = f"estimate_{ts_str}{range_tag}.json"
    report_path = REPORT_DIR / report_filename
    latest_path = REPORT_DIR / "latest.json"

    report = {
        "generated_at": run_ts.isoformat(),
        "from_year": args.from_year,
        "to_year": args.to_year,
        "truncation_chars": trunc_limit,
        "summary_text": summary_text,
        "totals": {
            "documents": grand_total_docs,
            "input_tokens": grand_total_input_tokens,
            "output_tokens_per_doc": MAX_OUTPUT_TOKENS,
            "total_output_tokens": grand_total_output_tokens,
        },
        "cost_estimates": cost_rows,
        "documents": all_doc_records,
    }

    report_json = json.dumps(report, indent=2)
    report_path.write_text(report_json, encoding="utf-8")
    latest_path.write_text(report_json, encoding="utf-8")

    print(f"\n  Report saved → {report_path}")
    print(f"             → {latest_path} (always latest)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate extraction API costs for pending council PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--from-year", type=int, metavar="YYYY", dest="from_year",
        help="Only include meetings from this year onward",
    )
    parser.add_argument(
        "--to-year", type=int, metavar="YYYY", dest="to_year",
        help="Only include meetings up to and including this year",
    )
    parser.add_argument(
        "--max-chars", default=str(MAX_CHARS), metavar="N|full", dest="max_chars",
        help=f"Truncation limit in chars, or 'full' for no truncation "
             f"(default: {MAX_CHARS:,} — matches the extraction pipeline)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress per-document output lines",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Print the summary from the saved report without regenerating",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
