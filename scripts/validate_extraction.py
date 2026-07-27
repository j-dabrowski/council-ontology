"""
Level 4: Per-document confidence scoring for all extracted meetings.

Extends Level 3c (validate_sample) with two additional metrics:
  - Entity density: motions per 10k source chars. Flags meetings with suspiciously
    few motions relative to document size (possible extraction gap).
  - Schema completeness: structural checks — Ordinary meetings must have ≥1 motion;
    all extracted motions must have a non-null outcome.

All five Level 3c metrics are inherited from src/validation/core.py:
  quote_completeness, paraphrase_rate, coverage_ratio,
  inventory_agreement, keyword_gap_rate.

Runs against all extracted meetings in the DB by default, or a specified subset
via --files, --limit, --from-year, --to-year. Use --force to re-validate docs
that already have a data/validation/*.json report.

This script is called automatically by 'council batch' after each extraction run.

Usage:
    council validate cambridge
    council validate cambridge --limit 20
    council validate cambridge --from-year 2010 --to-year 2020
    council validate cambridge --files a.pdf b.pdf
    python scripts/validate_extraction.py cambridge
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table

from src.validation.core import (
    DATA_DIR,
    load_census,
    validate_doc,
)

console = Console()

VALIDATION_DIR = DATA_DIR / "validation"

STATUS_STYLE = {"PASS": "green", "REVIEW": "yellow", "FAIL": "red"}

# Calibrated from Level 3c sample (Cambridge, 2026-05-31, 18 docs).
# Ordinary meetings with density below LOW_DENSITY_THRESHOLD flag as REVIEW.
LOW_DENSITY_THRESHOLD = 0.3   # motions per 10k chars — well below sample avg
ZERO_DENSITY_TYPES = {"ordinary council meeting", "ordinary meeting", "council meeting"}


# ---------------------------------------------------------------------------
# New Level 4 metrics
# ---------------------------------------------------------------------------

def compute_entity_density(motion_count: int, char_count: int) -> dict:
    """Motions per 10k source chars. Low density on large Ordinary meetings = extraction gap."""
    density = motion_count / (char_count / 10_000) if char_count > 0 else 0.0
    return {
        "motions_per_10k": round(density, 2),
        "motion_count": motion_count,
        "char_count": char_count,
    }


def compute_schema_completeness(
    conn: sqlite3.Connection,
    meeting_id: int,
    meeting_type: str,
    document_type: str | None = None,
) -> dict:
    """Structural checks: Ordinary meetings need ≥1 motion; all motions need outcomes.

    For agenda documents the outcome check is skipped (outcomes are null by design).
    """
    is_agenda = document_type == "agenda"
    motion_count = conn.execute(
        "SELECT COUNT(*) FROM motions WHERE meeting_id = ?", (meeting_id,)
    ).fetchone()[0]
    null_outcome_count = conn.execute(
        "SELECT COUNT(*) FROM motions WHERE meeting_id = ? "
        "AND (outcome IS NULL OR outcome = '')",
        (meeting_id,),
    ).fetchone()[0]

    flags: list[str] = []
    mtype_lower = (meeting_type or "").lower()
    # Agendas don't have voted outcomes — skip both vote-related flags.
    if not is_agenda:
        if any(t in mtype_lower for t in ZERO_DENSITY_TYPES) and motion_count == 0:
            flags.append("ordinary_meeting_no_motions")
        if null_outcome_count > 0:
            flags.append(f"{null_outcome_count}_motions_null_outcome")

    return {
        "flags": flags,
        "motion_count": motion_count,
        "null_outcome_count": null_outcome_count,
    }


def determine_status_l4(
    base_status: str,
    entity_density: dict,
    schema_completeness: dict,
    meeting_type: str,
    document_type: str | None = None,
) -> str:
    """Extend Level 3c status with entity density and schema completeness checks."""
    if base_status == "FAIL":
        return "FAIL"
    is_agenda = document_type == "agenda"
    mtype_lower = (meeting_type or "").lower()
    is_ordinary = mtype_lower in ZERO_DENSITY_TYPES
    # Agendas don't have votes so density check (motions = proposed resolutions) is
    # still meaningful, but the threshold calibrated for minutes doesn't apply.
    density_flag = (
        not is_agenda
        and is_ordinary
        and entity_density["char_count"] > 50_000
        and entity_density["motions_per_10k"] < LOW_DENSITY_THRESHOLD
    )
    if schema_completeness["flags"] or density_flag:
        return "REVIEW" if base_status == "PASS" else base_status
    return base_status


# ---------------------------------------------------------------------------
# Per-document L4 validation (wraps core validate_doc)
# ---------------------------------------------------------------------------

def _add_l4_metrics(
    conn: sqlite3.Connection, result: dict, census: dict, filename: str
) -> dict:
    meeting_id = result["meeting_id"]
    meeting_type = result.get("meeting_type", "")
    document_type = result.get("document_type")
    char_count = census.get(filename, {}).get("char_count", 0)
    motion_count = result["entity_counts"].get("motion_count", 0)

    result["entity_density"] = compute_entity_density(motion_count, char_count)
    result["schema_completeness"] = compute_schema_completeness(
        conn, meeting_id, meeting_type, document_type=document_type
    )
    result["status"] = determine_status_l4(
        result["status"], result["entity_density"], result["schema_completeness"],
        meeting_type, document_type=document_type,
    )
    return result


def validate_doc_l4(
    conn: sqlite3.Connection,
    council: str,
    filename: str,
    census: dict,
    max_chars: int | None = None,
) -> dict:
    result = validate_doc(conn, council, filename, census, max_chars=max_chars)
    if "error" not in result:
        result = _add_l4_metrics(conn, result, census, filename)
    return result


# ---------------------------------------------------------------------------
# Batch API (used by batch_extract.py and run() below)
# ---------------------------------------------------------------------------

def validate_files(
    council_key: str,
    filenames: list[str],
    max_chars: int | None = None,
    force: bool = False,
    quiet: bool = False,
) -> tuple[list[dict], dict[str, int]]:
    """Validate a list of extracted PDFs. Returns (results, status_counts).

    Writes per-doc JSON to data/validation/{stem}.json.
    Skips docs that already have a report unless force=True.
    """
    census = load_census()
    conn = sqlite3.connect(str(DATA_DIR / "council.db"))
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    counts: dict[str, int] = {"PASS": 0, "REVIEW": 0, "FAIL": 0}

    for filename in filenames:
        stem = Path(filename).stem
        out_path = VALIDATION_DIR / f"{stem}.json"

        if not force and out_path.exists():
            result = json.loads(out_path.read_text())
        else:
            result = validate_doc_l4(conn, council_key, filename, census, max_chars=max_chars)
            out_path.write_text(json.dumps(result, indent=2))

        results.append(result)
        status = result.get("status", "FAIL")
        counts[status] = counts.get(status, 0) + 1

        if not quiet:
            style = STATUS_STYLE.get(status, "white")
            console.print(f"  {filename} ... [{style}]{status}[/{style}]", highlight=False)

    conn.close()
    return results, counts


# ---------------------------------------------------------------------------
# DB helpers — find all extracted filenames for a council
# ---------------------------------------------------------------------------

def get_extracted_filenames(
    council_key: str,
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[str]:
    conn = sqlite3.connect(str(DATA_DIR / "council.db"))
    rows = conn.execute(
        "SELECT m.minutes_pdf_path FROM meetings m "
        "JOIN councils c ON c.id = m.council_id "
        "WHERE c.short_name = ? AND m.minutes_pdf_path IS NOT NULL",
        (council_key.capitalize(),),
    ).fetchall()
    conn.close()
    filenames = [Path(r[0]).name for r in rows if r[0]]

    if from_year or to_year:
        manifest_path = DATA_DIR / "raw" / council_key / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        filtered = []
        for f in filenames:
            date_str = manifest.get(f, {}).get("meeting_date", "")
            try:
                year = int(date_str[:4])
            except (ValueError, TypeError):
                continue
            if from_year and year < from_year:
                continue
            if to_year and year > to_year:
                continue
            filtered.append(f)
        filenames = filtered

    return filenames


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_table(results: list[dict]) -> None:
    table = Table(title="Level 4 Extraction Validation", show_lines=True)
    table.add_column("File", style="dim", width=14)
    table.add_column("Date", width=10)
    table.add_column("Type", width=20)
    table.add_column("Quot", justify="right", width=5)
    table.add_column("Cmpl%", justify="right", width=6)
    table.add_column("Para%", justify="right", width=6)
    table.add_column("Cov%", justify="right", width=6)
    table.add_column("KwGap%", justify="right", width=7)
    table.add_column("Dens", justify="right", width=5)
    table.add_column("Schm", justify="right", width=5)
    table.add_column("Status", width=7)

    for r in results:
        if "error" in r:
            table.add_row(
                r["filename"][:14], "—", r["error"],
                "—", "—", "—", "—", "—", "—", "—", "[red]FAIL[/red]",
            )
            continue

        q = r["quotes"]
        para_rate = q["paraphrase_rate"]
        cov = r["coverage_ratio"]
        gap_rate = r["keyword_gap"]["gap_rate"]
        cmpl = r.get("quote_completeness", {}).get("completeness_rate", 1.0)
        density = r.get("entity_density", {}).get("motions_per_10k", 0.0)
        schema_flags = len(r.get("schema_completeness", {}).get("flags", []))

        para_style = "red" if para_rate >= 0.70 else ("yellow" if para_rate >= 0.40 else "green")
        cov_style = "red" if cov < 0.02 else ("yellow" if cov < 0.05 else "green")
        gap_style = "red" if gap_rate >= 0.50 else ("yellow" if gap_rate >= 0.25 else "green")
        cmpl_style = "red" if cmpl < 0.50 else ("yellow" if cmpl < 0.80 else "green")
        dens_style = "yellow" if density < LOW_DENSITY_THRESHOLD else "green"
        schm_style = "yellow" if schema_flags > 0 else "green"

        mtype = r.get("meeting_type", "")[:20]
        status = r.get("status", "?")

        table.add_row(
            r["filename"][:14],
            str(r.get("meeting_date", ""))[:10],
            mtype,
            str(q["total"]),
            f"[{cmpl_style}]{cmpl*100:.0f}%[/{cmpl_style}]",
            f"[{para_style}]{para_rate*100:.0f}%[/{para_style}]",
            f"[{cov_style}]{cov*100:.1f}%[/{cov_style}]",
            f"[{gap_style}]{gap_rate*100:.0f}%[/{gap_style}]",
            f"[{dens_style}]{density:.1f}[/{dens_style}]",
            f"[{schm_style}]{schema_flags}[/{schm_style}]",
            f"[{STATUS_STYLE.get(status, 'white')}]{status}[/{STATUS_STYLE.get(status, 'white')}]",
        )

    console.print(table)

    valid = [r for r in results if "error" not in r]
    if not valid:
        return

    avg_para = sum(r["quotes"]["paraphrase_rate"] for r in valid) / len(valid)
    avg_cov = sum(r["coverage_ratio"] for r in valid) / len(valid)
    avg_gap = sum(r["keyword_gap"]["gap_rate"] for r in valid) / len(valid)
    avg_cmpl = sum(r.get("quote_completeness", {}).get("completeness_rate", 1.0) for r in valid) / len(valid)
    passes = sum(1 for r in valid if r["status"] == "PASS")
    reviews = sum(1 for r in valid if r["status"] == "REVIEW")
    fails = sum(1 for r in valid if r["status"] == "FAIL")

    console.print(f"\n[bold]Aggregate (n={len(valid)}):[/bold]")
    cmpl_col = "red" if avg_cmpl < 0.50 else ("yellow" if avg_cmpl < 0.80 else "green")
    para_col = "red" if avg_para >= 0.50 else "green"
    cov_col = "red" if avg_cov < 0.03 else "green"
    gap_col = "red" if avg_gap >= 0.40 else "green"
    console.print(f"  Quote completeness: [{cmpl_col}]{avg_cmpl*100:.1f}%[/{cmpl_col}]  (target >80%)")
    console.print(f"  Paraphrase rate:    [{para_col}]{avg_para*100:.1f}%[/{para_col}]  (target <30%)")
    console.print(f"  Coverage ratio:     [{cov_col}]{avg_cov*100:.2f}%[/{cov_col}]  (target >5%)")
    console.print(f"  Keyword gap rate:   [{gap_col}]{avg_gap*100:.1f}%[/{gap_col}]  (target <25%)")
    console.print(f"  Status: [green]{passes} PASS[/green]  [yellow]{reviews} REVIEW[/yellow]  [red]{fails} FAIL[/red]")


def _write_summary(results: list[dict], council: str) -> None:
    valid = [r for r in results if "error" not in r]
    ts = datetime.now(timezone.utc).isoformat()
    summary: dict = {
        "generated_at": ts,
        "council": council,
        "total_validated": len(results),
        "errors": len(results) - len(valid),
        "pass": sum(1 for r in valid if r["status"] == "PASS"),
        "review": sum(1 for r in valid if r["status"] == "REVIEW"),
        "fail": sum(1 for r in valid if r["status"] == "FAIL"),
    }
    if valid:
        summary["avg_quote_completeness"] = round(
            sum(r.get("quote_completeness", {}).get("completeness_rate", 1.0) for r in valid) / len(valid), 4
        )
        summary["avg_paraphrase_rate"] = round(
            sum(r["quotes"]["paraphrase_rate"] for r in valid) / len(valid), 4
        )
        summary["avg_coverage_ratio"] = round(
            sum(r["coverage_ratio"] for r in valid) / len(valid), 4
        )
        summary["avg_keyword_gap_rate"] = round(
            sum(r["keyword_gap"]["gap_rate"] for r in valid) / len(valid), 4
        )
        schema_flagged = [r for r in valid if r.get("schema_completeness", {}).get("flags")]
        summary["schema_flags_count"] = len(schema_flagged)
        summary["schema_flagged_files"] = [r["filename"] for r in schema_flagged]
    (VALIDATION_DIR / "summary.json").write_text(json.dumps(summary, indent=2))


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(args) -> None:
    from src.extraction.extractor import DEFAULT_MAX_CHARS
    council = args.council
    max_chars: int | None = getattr(args, "max_chars", DEFAULT_MAX_CHARS)
    force: bool = getattr(args, "force", False)
    limit: int | None = getattr(args, "limit", None)
    from_year: int | None = getattr(args, "from_year", None)
    to_year: int | None = getattr(args, "to_year", None)
    files: list[str] | None = getattr(args, "files", None)

    if files:
        filenames = [Path(f).name for f in files]
    else:
        filenames = get_extracted_filenames(council, from_year=from_year, to_year=to_year)
        if limit:
            filenames = filenames[:limit]

    if not filenames:
        console.print(f"[yellow]No extracted documents found for council '{council}'.[/yellow]")
        sys.exit(0)

    console.print(f"\n[bold]Level 4: validating {len(filenames)} extracted docs for council '{council}'[/bold]")
    if force:
        console.print("[yellow]  --force: re-validating all docs regardless of existing reports[/yellow]")

    results, counts = validate_files(council, filenames, max_chars=max_chars, force=force)

    console.print()
    _print_table(results)
    _write_summary(results, council)

    console.print(f"\n[dim]Per-doc JSON: {VALIDATION_DIR}/*.json[/dim]")
    console.print(f"[dim]Summary:      {VALIDATION_DIR}/summary.json[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument("--limit", "-n", type=int, metavar="N",
                        help="Validate only the first N extracted docs")
    parser.add_argument("--files", nargs="+", metavar="PDF",
                        help="Validate only these specific PDFs (basenames)")
    parser.add_argument("--from-year", type=int, metavar="YYYY", dest="from_year",
                        help="Only validate meetings from this year onward")
    parser.add_argument("--to-year", type=int, metavar="YYYY", dest="to_year",
                        help="Only validate meetings up to and including this year")
    parser.add_argument("--force", action="store_true",
                        help="Re-validate even if data/validation/{stem}.json already exists")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
