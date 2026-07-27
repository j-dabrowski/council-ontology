"""
Level 3c: Validate sample extractions.

Reads data/{council}_sample.json, then for each doc computes:
  - Quote completeness: fraction of entities with ≥1 source quote in extraction_evidence.
  - Paraphrase rate: quotes that cannot be matched in the normalised source text.
  - Coverage ratio: fraction of the extraction window covered by matched quotes.
  - Inventory agreement: extracted entity counts vs L1 inventory counts.
  - Keyword gap rate: high-signal keywords in normalised source text not covered
    by any matched quote span (potential missed entities).

All matching is done at query time against the live PDF text — the DB column
char_offset is not used here (it is a best-effort convenience for UI only).

Writes:
  data/sample_validation/{stem}.json  per-doc JSON report
  data/sample_validation/report.txt   human-readable summary + interpretation
  data/sample_validation/paraphrase_report.txt  per-quote paraphrase detail

Prints a rich table to stdout.

Usage:
    council validate-sample cambridge
    python scripts/validate_sample.py cambridge
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

VALIDATION_DIR = DATA_DIR / "sample_validation"

STATUS_STYLE = {"PASS": "green", "REVIEW": "yellow", "FAIL": "red"}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_table(results: list[dict]) -> None:
    table = Table(title="Level 3c Sample Validation", show_lines=True)
    table.add_column("File", style="dim", width=14)
    table.add_column("Date", width=10)
    table.add_column("Type", width=20)
    table.add_column("Quot", justify="right", width=5)
    table.add_column("Cmpl%", justify="right", width=6)
    table.add_column("Para%", justify="right", width=6)
    table.add_column("Cov%", justify="right", width=6)
    table.add_column("InvAgr", justify="right", width=7)
    table.add_column("KwGap%", justify="right", width=7)
    table.add_column("Status", width=7)

    for r in results:
        if "error" in r:
            table.add_row(r["filename"][:14], "—", r["error"], "—", "—", "—", "—", "—", "—", "[red]FAIL[/red]")
            continue

        q = r["quotes"]
        para_rate = q["paraphrase_rate"]
        cov = r["coverage_ratio"]
        gap_rate = r["keyword_gap"]["gap_rate"]
        cmpl = r.get("quote_completeness", {}).get("completeness_rate", 1.0)

        inv = r.get("inventory_agreement") or {}
        meaningful = [
            min(v["ratio"], 2.5)
            for v in inv.values()
            if v["ratio"] != float("inf") and (v["l1"] > 0 or v["extracted"] > 0)
        ]
        avg_inv = sum(meaningful) / len(meaningful) if meaningful else None

        para_style = "red" if para_rate >= 0.70 else ("yellow" if para_rate >= 0.40 else "green")
        cov_style = "red" if cov < 0.02 else ("yellow" if cov < 0.05 else "green")
        gap_style = "red" if gap_rate >= 0.50 else ("yellow" if gap_rate >= 0.25 else "green")
        cmpl_style = "red" if cmpl < 0.50 else ("yellow" if cmpl < 0.80 else "green")

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
            f"{avg_inv:.2f}" if avg_inv is not None else "—",
            f"[{gap_style}]{gap_rate*100:.0f}%[/{gap_style}]",
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


def _write_report(results: list[dict], council: str, sample: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "Level 3c Sample Validation Report",
        f"Council: {council}  |  Sample: {sample['count']} docs  |  Generated: {ts}",
        "",
        "METRICS",
        "-------",
        "  Quote completeness  — fraction of extracted entities that have ≥1 source quote in",
        "                        extraction_evidence. Paraphrase rate only measures quality of",
        "                        quotes that were produced; this metric catches entities where",
        "                        source_quotes=[] was returned (no evidence rows at all).",
        "                        Target: >80%. FAIL if <50%.",
        "  Paraphrase rate     — quotes not found in whitespace-normalised source text.",
        "                        Both PDF text and quote are normalised before matching.",
        "                        Only genuine content differences count. Target: <30%.",
        "  Coverage ratio      — fraction of the extraction window (first max_chars chars) covered",
        "                        by matched quotes. Denominator is capped at the extraction window",
        "                        so large documents are not penalised for truncated content.",
        "                        Target: >5%.",
        "  Inventory agreement — average of (extracted count / L1 count) across entity types.",
        "                        Values near 1.0 = good. Flagged if <0.4 or >2.5.",
        "  Keyword gap rate    — MOVED/CARRIED/DA/DECLARATION etc. in normalised source text",
        "                        not covered by any matched quote span. Target: <25%.",
        "",
        "RESULTS",
        "-------",
    ]

    hdr = f"{'File':<16} {'Date':<12} {'Para%':>5} {'Cov%':>5} {'KwGap%':>7} {'Status'}"
    lines.append(hdr)
    lines.append("-" * (len(hdr) + 4))

    for r in results:
        if "error" in r:
            lines.append(f"{r['filename']:<16} {'—':<12} {'—':>5} {'—':>5} {'—':>7} FAIL  ({r['error']})")
            continue
        q = r["quotes"]
        lines.append(
            f"{r['filename']:<16} {str(r['meeting_date']):<12}"
            f" {q['paraphrase_rate']*100:>4.0f}%"
            f" {r['coverage_ratio']*100:>4.1f}%"
            f" {r['keyword_gap']['gap_rate']*100:>6.0f}%"
            f" {r['status']}"
        )

    lines.append("")

    valid = [r for r in results if "error" not in r]
    if valid:
        avg_para = sum(r["quotes"]["paraphrase_rate"] for r in valid) / len(valid)
        avg_cov = sum(r["coverage_ratio"] for r in valid) / len(valid)
        avg_gap = sum(r["keyword_gap"]["gap_rate"] for r in valid) / len(valid)
        avg_cmpl = sum(r.get("quote_completeness", {}).get("completeness_rate", 1.0) for r in valid) / len(valid)
        passes = sum(1 for r in valid if r["status"] == "PASS")
        reviews = sum(1 for r in valid if r["status"] == "REVIEW")
        fails = sum(1 for r in valid if r["status"] == "FAIL")

        lines += [
            f"AGGREGATE (n={len(valid)})",
            "---------",
            f"  Quote completeness: {avg_cmpl*100:.1f}%  (target >80%)",
            f"  Paraphrase rate:    {avg_para*100:.1f}%  (target <30%)",
            f"  Coverage ratio:     {avg_cov*100:.2f}%  (target >5%)",
            f"  Keyword gap rate:   {avg_gap*100:.1f}%  (target <25%)",
            f"  Status:             {passes} PASS / {reviews} REVIEW / {fails} FAIL",
            "",
        ]

        issues: list[str] = []
        if avg_cmpl < 0.50:
            issues.append(
                f"LOW QUOTE COMPLETENESS ({avg_cmpl*100:.0f}%)\n"
                "  More than half the extracted entities have no source quote in extraction_evidence.\n"
                "  This means the model is extracting content but silently dropping the PROVENANCE RULE.\n"
                "  Check missing_by_table in per-doc JSON to see which entity types are worst.\n"
                "  Fix: strengthen the PROVENANCE RULE in system_prompt.txt; ensure source_quotes\n"
                "  appears in the OUTPUT SCHEMA block for every entity type."
            )
        elif avg_cmpl < 0.80:
            issues.append(
                f"MODERATE QUOTE COMPLETENESS ({avg_cmpl*100:.0f}%)\n"
                "  Some extracted entities have no source quote. Check missing_by_table in per-doc\n"
                "  JSON to identify which entity types are missing provenance most often."
            )
        if avg_para >= 0.50:
            issues.append(
                f"HIGH PARAPHRASE RATE ({avg_para*100:.0f}%)\n"
                "  More than half the model's source quotes cannot be found in the source text\n"
                "  even after whitespace normalisation. The model is paraphrasing or condensing\n"
                "  rather than quoting. Fix: strengthen the PROVENANCE RULE in system_prompt.txt."
            )
        if avg_cov < 0.03:
            issues.append(
                f"LOW COVERAGE RATIO ({avg_cov*100:.2f}%)\n"
                "  Very little of the source text is spanned by matched quotes. This is usually\n"
                "  a downstream effect of a high paraphrase rate: unmatched quotes contribute\n"
                "  nothing to coverage. Reducing the paraphrase rate should raise coverage."
            )
        if avg_gap >= 0.40:
            issues.append(
                f"HIGH KEYWORD GAP RATE ({avg_gap*100:.0f}%)\n"
                "  Many entity-signalling keywords (MOVED, CARRIED, DA, etc.) appear in source\n"
                "  text but are not spanned by any matched quote. This means either:\n"
                "  (a) entities are being missed entirely (extraction gap), or\n"
                "  (b) they are extracted but with paraphrased quotes (covered by paraphrase fix).\n"
                "  Check per-doc gap_examples in sample_validation/*.json to distinguish."
            )

        if issues:
            lines.append("INTERPRETATION")
            lines.append("--------------")
            for issue in issues:
                lines.append(issue)
                lines.append("")
            lines.append("NEXT STEPS")
            lines.append("----------")
            lines.append("  1. Fix the identified issues in system_prompt.txt (and/or schemas.py).")
            lines.append("  2. Re-run: council extract-sample cambridge")
            lines.append("  3. Re-run: council validate-sample cambridge")
            lines.append("  Repeat until paraphrase <30%, coverage >5%, keyword gap <25%.")
            lines.append("  Then proceed to Level 4: confidence metrics and full batch extraction.")
        else:
            lines += [
                "NEXT STEPS",
                "----------",
                "  Metrics are within targets. Proceed to Level 4:",
                "  Implement scripts/validate_extraction.py (per-doc confidence scorer).",
                "  Then run: council batch cambridge --limit 20",
            ]

        flagged_fields: dict[str, list[str]] = {}
        for r in valid:
            if not r.get("inventory_agreement"):
                continue
            for field, info in r["inventory_agreement"].items():
                if info.get("flag"):
                    flagged_fields.setdefault(field, []).append(
                        f"  {r['filename']} (L1={info['l1']}, extracted={info['extracted']}, ratio={info['ratio']})"
                    )
        if flagged_fields:
            lines += ["", "INVENTORY AGREEMENT FLAGS", "-------------------------"]
            for field, cases in sorted(flagged_fields.items()):
                lines.append(f"  {field}: {len(cases)} doc(s) flagged")
                for case in cases[:5]:
                    lines.append(case)

    (VALIDATION_DIR / "report.txt").write_text("\n".join(lines) + "\n")


def _write_paraphrase_report(results: list[dict], council: str, sample: dict) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "Paraphrase Analysis Report",
        f"Council: {council}  |  Sample: {sample['count']} docs  |  Generated: {ts}",
        "",
        "HOW TO READ THIS REPORT",
        "-----------------------",
        "Each entry is a quote the model produced that could not be matched in the",
        "normalised source text (whitespace collapsed to single spaces).",
        "",
        "  partial_match: longest prefix of the quote found verbatim in the source.",
        "    matched_words/total_words — how much of the quote's start was found.",
        "    source_context — what the source text actually says from that position.",
        "    If source_context ≈ quote: the normaliser needs improvement.",
        "    If source_context diverges early: the model paraphrased the content.",
        "  no_partial_match: even the first 4 words weren't found — likely fabricated",
        "    structure or a heavily reworded passage.",
        "",
        "=" * 72,
        "",
    ]

    valid = [r for r in results if "error" not in r]
    for r in valid:
        examples = r.get("quotes", {}).get("paraphrase_examples", [])
        if not examples:
            continue

        q_info = r["quotes"]
        header = (
            f"{r['filename']}  |  {r['meeting_type']}  |  {r['meeting_date']}"
            f"  |  {q_info['paraphrased']}/{q_info['total']} quotes paraphrased"
            f"  ({q_info['paraphrase_rate']*100:.0f}%)"
        )
        lines.append(header)
        lines.append("-" * min(len(header), 72))

        for ex in examples:
            lines.append(f"  [{ex['entity_table']}]")
            quote_lines = _wrap(ex["quote"], 68)
            lines.append(f"    QUOTE:  {quote_lines[0]}")
            for ql in quote_lines[1:]:
                lines.append(f"            {ql}")

            pm = ex.get("partial_match")
            if pm:
                matched = pm["matched_words"]
                total = pm["total_words"]
                ctx_lines = _wrap(pm["source_context"], 68)
                lines.append(f"    SOURCE: {ctx_lines[0]}  [{matched}/{total} words matched]")
                for cl in ctx_lines[1:]:
                    lines.append(f"            {cl}")
            else:
                lines.append("    SOURCE: [no partial match — first 4 words not found in source]")
            lines.append("")

        lines.append("")

    (VALIDATION_DIR / "paraphrase_report.txt").write_text("\n".join(lines) + "\n")


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    line = ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip() if line else w
    if line:
        out.append(line)
    return out or [""]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(args) -> None:
    from src.extraction.extractor import DEFAULT_MAX_CHARS
    council = args.council
    max_chars: int | None = getattr(args, "max_chars", DEFAULT_MAX_CHARS)

    sample_path = DATA_DIR / f"{council}_sample.json"
    if not sample_path.exists():
        console.print(f"[red]No sample file at {sample_path}. Run 'council sample {council}' first.[/red]")
        sys.exit(1)

    sample = json.loads(sample_path.read_text())
    files: list[str] = sample["files"]

    console.print(f"\n[bold]Level 3c: validating {len(files)} sample docs for council '{council}'[/bold]")

    census = load_census()
    conn = sqlite3.connect(str(DATA_DIR / "council.db"))
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for filename in files:
        console.print(f"  {filename} ...", end="", highlight=False)
        result = validate_doc(conn, council, filename, census, max_chars=max_chars)
        results.append(result)
        stem = Path(filename).stem
        (VALIDATION_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2))
        status = result.get("status", "?")
        style = STATUS_STYLE.get(status, "white")
        console.print(f" [{style}]{status}[/{style}]")

    conn.close()

    console.print()
    _print_table(results)
    _write_report(results, council, sample)
    _write_paraphrase_report(results, council, sample)

    console.print(f"\n[dim]Per-doc JSON:        {VALIDATION_DIR}/*.json[/dim]")
    console.print(f"[dim]Summary:             {VALIDATION_DIR}/report.txt[/dim]")
    console.print(f"[dim]Paraphrase detail:   {VALIDATION_DIR}/paraphrase_report.txt[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
