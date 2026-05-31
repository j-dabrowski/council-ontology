#!/usr/bin/env python3
"""
Estimate Anthropic API cost for all LLM stages of the pipeline.

Stages covered:
  inventory   Level 1: one Haiku call per document (30k char window)
  extract     Level 5 (and 3b): one call per document (default 80k chars)

Uses census.json char counts — no PDF re-reads needed (~1s vs ~4 min).

Usage:
    council costs [--from-year YYYY] [--to-year YYYY] [--max-chars N|full]
    council costs --show          # reprint last saved report
    python estimate_costs.py      # standalone
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.models import Council, Meeting
from src.storage.database import init_db, make_session_factory
from src.cost_estimator import (
    MODELS,
    CostEstimate,
    estimate_extraction,
    estimate_inventory,
    load_census,
    model_key_from_string,
)
from src.extraction.extractor import DEFAULT_MAX_CHARS, _MODEL as _EXTRACT_MODEL
from scripts.inventory import INVENTORY_MODEL

REPORT_DIR = Path("data/cost_estimates")
COL_W = 24

_ACTIVE_EXTRACT_KEY = model_key_from_string(_EXTRACT_MODEL)
_ACTIVE_INVENTORY_KEY = model_key_from_string(INVENTORY_MODEL)


# ---------------------------------------------------------------------------
# Pending-doc helpers (unchanged logic, no PDF reads)
# ---------------------------------------------------------------------------


def get_pending_pdfs(session, council: Council, raw_dir: Path, manifest: dict) -> list[Path]:
    """Return PDFs not yet extracted (not in meetings table)."""
    if not raw_dir.exists():
        return []
    all_pdfs = sorted(raw_dir.glob("*.pdf"))
    if not all_pdfs:
        return []
    rows = session.query(Meeting).filter(Meeting.council_id == council.id).all()
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


def get_uninventoried_pdfs(raw_dir: Path, force: bool = False) -> list[Path]:
    """Return PDFs without an existing ok-status inventory file."""
    inv_dir = Path("data/inventories")
    result = []
    for p in sorted(raw_dir.glob("*.pdf")):
        inv_path = inv_dir / f"{p.stem}.json"
        if not force and inv_path.exists():
            try:
                if json.loads(inv_path.read_text(encoding="utf-8")).get("status") == "ok":
                    continue
            except Exception:
                pass
        result.append(p)
    return result


def filter_pdfs_by_year(
    pdfs: list[Path],
    manifest: dict,
    from_year: int | None,
    to_year: int | None,
) -> tuple[list[Path], int]:
    if not from_year and not to_year:
        return pdfs, 0
    filtered, n_no_date = [], 0
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
# Summary table builder
# ---------------------------------------------------------------------------


def _build_cost_table(
    label: str,
    estimate: CostEstimate,
    active_key: str,
    lines: list[str],
) -> None:
    hr = "-" * 68
    lines.append(f"\n  {label}")
    lines.append(f"  {hr}")
    lines.append(
        f"  {'Documents':<32} {estimate.n_docs:>10,}"
    )
    lines.append(
        f"  {'Input tokens (est.)':<32} {estimate.input_tokens:>10,}"
    )
    lines.append(
        f"  {'Output tokens (est.)':<32} {estimate.output_tokens:>10,}"
    )
    lines.append("")
    lines.append(
        f"  {'Model':<{COL_W}} {'In $/MTok':>10} {'Out $/MTok':>11} {'Est. Cost':>12}"
    )
    lines.append(f"  {'-'*COL_W} {'-'*10} {'-'*11} {'-'*12}")
    for key, pricing in MODELS.items():
        cost = (
            estimate.input_tokens  / 1_000_000 * pricing.input_per_mtok
            + estimate.output_tokens / 1_000_000 * pricing.output_per_mtok
        )
        active_marker = " *" if key == active_key else "  "
        lines.append(
            f"  {pricing.label:<{COL_W}}"
            f" ${pricing.input_per_mtok:>8.2f}"
            f"   ${pricing.output_per_mtok:>9.2f}"
            f"   ${cost:>10.2f}{active_marker}"
        )
    lines.append(f"  {'-'*COL_W} {'-'*10} {'-'*11} {'-'*12}")
    lines.append(f"  * = currently configured model")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(args) -> None:
    if args.max_chars.lower() == "full":
        trunc_limit: int | None = None
        trunc_label = "full (no truncation)"
    else:
        try:
            trunc_limit = int(args.max_chars)
        except ValueError:
            print(f"--max-chars must be an integer or 'full', got: {args.max_chars!r}")
            raise SystemExit(1)
        trunc_label = (
            f"{trunc_limit:,} chars"
            + (" (pipeline default)" if trunc_limit == DEFAULT_MAX_CHARS else "")
        )

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

    run_ts = datetime.now(timezone.utc)
    all_lines: list[str] = []
    report_data: dict = {
        "generated_at": run_ts.isoformat(),
        "from_year": args.from_year,
        "to_year": args.to_year,
        "truncation_chars": trunc_limit,
        "stages": {},
    }

    for council in councils:
        key = council.short_name.lower()
        raw_dir = Path("data/raw") / key
        manifest_path = raw_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

        census = load_census()

        force: bool = getattr(args, "force", False)
        inv_all = sorted(raw_dir.glob("*.pdf")) if raw_dir.exists() else []

        # ── Inventory stage ────────────────────────────────────────────────
        if force:
            inv_docs = inv_all
        else:
            inv_docs = get_uninventoried_pdfs(raw_dir)
        inv_docs, _ = filter_pdfs_by_year(inv_docs, manifest, args.from_year, args.to_year)
        inv_estimate = estimate_inventory(inv_docs, census)

        # ── Extraction stage ───────────────────────────────────────────────
        if force:
            ext_docs = inv_all
        else:
            ext_docs = get_pending_pdfs(session, council, raw_dir, manifest)
        ext_docs, n_no_date = filter_pdfs_by_year(ext_docs, manifest, args.from_year, args.to_year)
        ext_estimate = estimate_extraction(ext_docs, trunc_limit, _ACTIVE_EXTRACT_KEY, census)

        yr_range = ""
        if args.from_year or args.to_year:
            yr_range = f" [{args.from_year or '∞'}–{args.to_year or '∞'}]"
        force_note = "  [--force: all docs]" if force else ""

        hr = "=" * 68
        all_lines.append(f"\n{hr}")
        all_lines.append(f"  {council.name}{yr_range}{force_note}")
        all_lines.append(f"  Extraction window: {trunc_label}")
        all_lines.append(hr)

        if inv_docs:
            inv_label = (
                f"INVENTORY  ({len(inv_docs)} of {len(inv_all)} docs — full re-run)"
                if force else
                f"INVENTORY  ({len(inv_docs)} without inventory / {len(inv_all)} total)"
            )
            _build_cost_table(inv_label, inv_estimate, _ACTIVE_INVENTORY_KEY, all_lines)
        else:
            all_lines.append("\n  INVENTORY  all docs already inventoried")

        if ext_docs:
            ext_label = (
                f"EXTRACTION  ({len(ext_docs)} docs — full re-run"
                + (f", {n_no_date} skipped — no date" if n_no_date else "")
                + ")"
                if force else
                f"EXTRACTION  ({len(ext_docs)} pending"
                + (f", {n_no_date} skipped — no date" if n_no_date else "")
                + ")"
            )
            _build_cost_table(ext_label, ext_estimate, _ACTIVE_EXTRACT_KEY, all_lines)
        else:
            all_lines.append("\n  EXTRACTION  no pending documents")

        all_lines.append(f"\n  NOTE: output tokens are estimates (size-bucket heuristic).")
        all_lines.append("  Adaptive thinking tokens not included — Sonnet/Opus actual costs")
        all_lines.append("  may be higher.")
        all_lines.append(hr)

        report_data["stages"][key] = {
            "inventory": {
                "n_docs": inv_estimate.n_docs,
                "input_tokens": inv_estimate.input_tokens,
                "output_tokens": inv_estimate.output_tokens,
            },
            "extraction": {
                "n_docs": ext_estimate.n_docs,
                "input_tokens": ext_estimate.input_tokens,
                "output_tokens": ext_estimate.output_tokens,
            },
        }

    session.close()

    summary_text = "\n".join(all_lines)
    print(summary_text)

    # ── Save report ────────────────────────────────────────────────────────
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts_str = run_ts.strftime("%Y%m%d_%H%M%S")
    range_tag = ""
    if args.from_year:
        range_tag += f"_from{args.from_year}"
    if args.to_year:
        range_tag += f"_to{args.to_year}"
    if trunc_limit is None:
        range_tag += "_full"
    elif trunc_limit != DEFAULT_MAX_CHARS:
        range_tag += f"_cap{trunc_limit}"
    report_path = REPORT_DIR / f"estimate_{ts_str}{range_tag}.json"
    latest_path = REPORT_DIR / "latest.json"
    report_data["summary_text"] = summary_text
    report_json = json.dumps(report_data, indent=2)
    report_path.write_text(report_json, encoding="utf-8")
    latest_path.write_text(report_json, encoding="utf-8")
    print(f"\n  Report saved → {report_path}")
    print(f"             → {latest_path} (always latest)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate API costs for pending council pipeline stages.",
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
        "--max-chars", default=str(DEFAULT_MAX_CHARS), metavar="N|full", dest="max_chars",
        help=f"Extraction truncation limit or 'full' (default: {DEFAULT_MAX_CHARS:,})",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="(no-op; kept for CLI compatibility)",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Print the summary from the last saved report without regenerating",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
