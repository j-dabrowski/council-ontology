#!/usr/bin/env python3
"""
Compare extraction output across Opus 4.6, Sonnet 4.6, and Haiku 4.5 for a single PDF.

Runs all three models in parallel. Does NOT write to the database.
Results are printed as a side-by-side comparison and saved to
data/model_comparison/<pdf_stem>_<timestamp>.json for further inspection.

Usage:
    python scripts/compare_models.py <pdf_basename>
    python scripts/compare_models.py bde23c99.pdf
    python scripts/compare_models.py bde23c99.pdf --council cambridge
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich import box

from src.extraction.extractor import MinutesExtractor, extract_text_from_pdf
from src.extraction.schemas import ExtractedMeeting

console = Console()

MODELS = [
    ("Haiku 4.5",  "claude-haiku-4-5-20251001"),
    ("Sonnet 4.6", "claude-sonnet-4-6"),
    ("Opus 4.6",   "claude-opus-4-6"),
]

OUTPUT_DIR = Path("data/model_comparison")


# ---------------------------------------------------------------------------
# Extraction (no DB writes)
# ---------------------------------------------------------------------------

def _run_one(
    label: str,
    model_id: str,
    text: str,
    pdf_name: str,
    council_name: str,
    meeting_date_hint: str | None,
) -> tuple[str, str, ExtractedMeeting | None, Exception | None]:
    try:
        extractor = MinutesExtractor(model=model_id)
        result = extractor.extract(
            text,
            source_hint=f"{pdf_name} [{label}]",
            council_name=council_name,
            meeting_date_hint=meeting_date_hint,
        )
        return label, model_id, result, None
    except Exception as exc:  # noqa: BLE001
        return label, model_id, None, exc


def run_all_models(
    pdf_path: Path,
    council_name: str,
    meeting_date_hint: str | None,
) -> dict[str, ExtractedMeeting | None]:
    """Extract with all three models in parallel. Returns {label: result}."""
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        raise ValueError(f"No text extracted from {pdf_path}")

    console.print(
        f"\n[dim]Extracted {len(text):,} chars from {pdf_path.name}"
        f" (effective: {min(len(text), 80_000):,})[/dim]\n"
    )

    results: dict[str, ExtractedMeeting | None] = {}
    order = [label for label, _ in MODELS]

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(
                _run_one, label, model_id, text,
                pdf_path.name, council_name, meeting_date_hint,
            ): label
            for label, model_id in MODELS
        }
        for fut in as_completed(futures):
            label, model_id, result, exc = fut.result()
            if exc:
                console.print(f"[red]✗ {label}[/red]: {exc}")
                results[label] = None
            else:
                console.print(f"[green]✓ {label}[/green]: {len(result.motions)} motions")
                results[label] = result

    # Return in consistent order
    return {lbl: results.get(lbl) for lbl in order}


# ---------------------------------------------------------------------------
# Comparison display
# ---------------------------------------------------------------------------

def _val(v, fmt=str, fallback="–") -> str:
    return fmt(v) if v is not None else fallback


def _councillor_name(c) -> str:
    if c is None:
        return "–"
    parts = [c.given_name, c.family_name]
    return " ".join(p for p in parts if p) or "–"


def _highlight(values: list[str]) -> list[str]:
    """Mark cells that differ from the others with an asterisk."""
    unique = set(values)
    if len(unique) == 1:
        return values
    return [f"[yellow]{v}[/yellow]" if v != "–" else v for v in values]


def print_comparison(pdf_name: str, results: dict[str, ExtractedMeeting | None]) -> None:
    labels = list(results.keys())
    meetings = list(results.values())

    # ── Header ──────────────────────────────────────────────────────────────
    console.rule(f"[bold]Model comparison — {pdf_name}[/bold]")

    # ── Top-level stats ──────────────────────────────────────────────────────
    stats = Table(box=box.SIMPLE, pad_edge=False, show_header=True)
    stats.add_column("", style="dim", min_width=26)
    for lbl in labels:
        stats.add_column(lbl, justify="right", min_width=14)

    def stat_row(name: str, values: list[str]) -> None:
        stats.add_row(name, *_highlight(values))

    stat_row("Meeting date",        [_val(m and m.meeting_date) for m in meetings])
    stat_row("Meeting type",        [_val(m and m.meeting_type) for m in meetings])
    stat_row("Location",            [_val(m and m.location) for m in meetings])
    stat_row("Councillors present", [str(len(m.councillors_present)) if m else "–" for m in meetings])
    stat_row("Councillors apology", [str(len(m.councillors_apology)) if m else "–" for m in meetings])
    stat_row("Motions",             [str(len(m.motions)) if m else "–" for m in meetings])
    stat_row("Individual votes",    [str(sum(len(mo.individual_votes) for mo in m.motions)) if m else "–" for m in meetings])
    stat_row("Planning apps",       [str(sum(1 for mo in m.motions if mo.planning_application)) if m else "–" for m in meetings])

    console.print(stats)

    # ── Per-motion comparison ─────────────────────────────────────────────────
    # Build a unified list of item keys across all models
    all_items: list[str] = []
    seen: set[str] = set()
    for m in meetings:
        if not m:
            continue
        for mo in m.motions:
            key = mo.item_number or mo.title or f"motion_{len(seen)+1}"
            if key not in seen:
                all_items.append(key)
                seen.add(key)

    if not all_items:
        console.print("[dim]No motions to compare.[/dim]")
        return

    console.rule("[bold]Motions[/bold]")

    for item_key in all_items:
        # Find the motion from each model matching this key
        motions_by_model: list = []
        for m in meetings:
            if not m:
                motions_by_model.append(None)
                continue
            match = next(
                (mo for mo in m.motions if (mo.item_number or mo.title or "") == item_key),
                None,
            )
            motions_by_model.append(match)

        tbl = Table(
            title=f"Item {item_key}",
            box=box.SIMPLE,
            pad_edge=False,
            title_style="bold cyan",
            show_header=True,
        )
        tbl.add_column("", style="dim", min_width=20)
        for lbl in labels:
            tbl.add_column(lbl, min_width=22)

        def motion_row(name: str, vals: list[str]) -> None:
            tbl.add_row(name, *_highlight(vals))

        motion_row("Title",      [_val(mo and (mo.title or "")[:50]) for mo in motions_by_model])
        motion_row("Outcome",    [_val(mo and mo.outcome) for mo in motions_by_model])
        motion_row("Votes for",  [_val(mo and mo.votes_for) for mo in motions_by_model])
        motion_row("Votes against", [_val(mo and mo.votes_against) for mo in motions_by_model])
        motion_row("Moved by",   [_councillor_name(mo and mo.moved_by) for mo in motions_by_model])
        motion_row("Seconded by",[_councillor_name(mo and mo.seconded_by) for mo in motions_by_model])
        motion_row("Indiv. votes", [str(len(mo.individual_votes)) if mo else "–" for mo in motions_by_model])
        motion_row("Planning app", ["yes" if (mo and mo.planning_application) else "no" for mo in motions_by_model])
        motion_row("Tags",       [", ".join(mo.tags) if (mo and mo.tags) else "–" for mo in motions_by_model])

        console.print(tbl)

    # ── Councillors present ───────────────────────────────────────────────────
    console.rule("[bold]Councillors present[/bold]")
    coun_tbl = Table(box=box.SIMPLE, pad_edge=False, show_header=True)
    coun_tbl.add_column("#", style="dim", justify="right")
    for lbl in labels:
        coun_tbl.add_column(lbl, min_width=24)

    max_rows = max((len(m.councillors_present) for m in meetings if m), default=0)
    for i in range(max_rows):
        row_vals = []
        for m in meetings:
            if m and i < len(m.councillors_present):
                c = m.councillors_present[i]
                row_vals.append(f"{c.given_name} {c.family_name}".strip())
            else:
                row_vals.append("–")
        coun_tbl.add_row(str(i + 1), *_highlight(row_vals))

    console.print(coun_tbl)


# ---------------------------------------------------------------------------
# Save report
# ---------------------------------------------------------------------------

def save_report(
    pdf_name: str,
    results: dict[str, ExtractedMeeting | None],
    errors: dict[str, str],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = Path(pdf_name).stem
    out_path = OUTPUT_DIR / f"{stem}_{ts}.json"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf": pdf_name,
        "models": {},
    }
    for label, result in results.items():
        if result is not None:
            report["models"][label] = json.loads(result.model_dump_json())
        else:
            report["models"][label] = {"error": errors.get(label, "unknown error")}

    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_COUNCIL_NAMES = {"cambridge": "City of Cambridge"}


def run(args) -> None:
    """Core logic — callable from the CLI or run standalone via main()."""
    raw_dir = Path("data/raw") / args.council
    pdf_path = raw_dir / Path(args.pdf).name
    if not pdf_path.exists():
        console.print(f"[red]File not found: {pdf_path}[/red]")
        raise SystemExit(1)

    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    meta = manifest.get(pdf_path.name, {})
    meeting_date_hint = meta.get("meeting_date")
    council_name = _COUNCIL_NAMES.get(args.council, "City of Cambridge")

    if meeting_date_hint:
        console.print(f"[dim]Manifest date hint: {meeting_date_hint}[/dim]")

    console.print(f"\nRunning [bold]3 models in parallel[/bold] on [cyan]{pdf_path.name}[/cyan] …\n")

    results = run_all_models(pdf_path, council_name, meeting_date_hint)

    print_comparison(pdf_path.name, results)

    if not args.no_save:
        errors = {lbl: "extraction failed" for lbl, res in results.items() if res is None}
        out = save_report(pdf_path.name, results, errors)
        console.print(f"\n[dim]Full JSON saved → {out}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare extraction output across Opus, Sonnet, and Haiku for one PDF.",
    )
    parser.add_argument("pdf", metavar="PDF", help="PDF basename (e.g. bde23c99.pdf)")
    parser.add_argument("--council", default="cambridge", choices=["cambridge"])
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't save the JSON report to data/model_comparison/",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
