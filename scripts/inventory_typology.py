#!/usr/bin/env python3
"""
Analyse Level 1 inventory data to surface corpus typology for Level 2 schema review.

Should be run after Level 1 inventory is complete, before making Level 2 schema
decisions. Surfaces what the corpus actually contains so schema gaps are identified
before committing to a prompt revision and full extraction run.

Reads all data/inventories/*.json files and produces a report covering:
  - Meeting type distribution and average entity counts per type
  - Entity counts by decade
  - Prevalence and content of the other_content free-text field
  - Section heading patterns (common + rare — rare ones are potential schema gaps)
  - Docs with cross-reference flags from census comparison

Output: printed to stdout and written to data/typology_review.txt

Usage:
    python scripts/inventory_typology.py cambridge
    python scripts/inventory_typology.py cambridge --quiet   # file only, no stdout
    council typology cambridge
    council typology cambridge --quiet
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

INVENTORIES_DIR = Path("data/inventories")
OUTPUT_DIR = Path("data")

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_inventories() -> list[dict]:
    records = []
    for p in sorted(INVENTORIES_DIR.glob("*.json")):
        if p.name == "summary.json":
            continue
        try:
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return records


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _meeting_type(r: dict) -> str:
    return r.get("inventory", {}).get("meeting_type") or "unknown"


def _short_type(mt: str) -> str:
    """Abbreviate for table display."""
    return (mt
        .replace("Ordinary Council Meeting", "Ordinary")
        .replace("Special Council Meeting", "Special Council")
        .replace("Annual General Meeting of Electors", "AGM Electors")
        .replace("Annual General Meeting", "AGM")
        .replace("Special Meeting of Electors", "Special Electors")
        .replace("Development Committee Meeting", "Dev Committee")
        .replace("Committee Meeting", "Committee")
        .replace("Special Meeting", "Special")
        .replace("Agenda Briefing Forum", "Briefing Forum")
        .replace("Meeting Agenda Briefing Forum", "Briefing Forum")
    )


def _inv(r: dict) -> dict:
    return r.get("inventory", {})


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def _section_meeting_types(ok: list[dict]) -> list[str]:
    lines = ["=" * 72, "  MEETING TYPE DISTRIBUTION AND ENTITY AVERAGES", "=" * 72, ""]

    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        by_type[_meeting_type(r)].append(r)

    # Header
    lines.append(f"  {'Meeting type':<32} {'N':>4}  {'Motions':>7}  {'Planning':>8}  {'Interests':>9}  {'Budget':>6}")
    lines.append(f"  {'-'*32} {'-'*4}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}")

    for mt, recs in sorted(by_type.items(), key=lambda x: -len(x[1])):
        n = len(recs)
        def avg(key):
            vals = [_inv(r).get(key, 0) or 0 for r in recs]
            return sum(vals) / n

        lines.append(
            f"  {_short_type(mt):<32} {n:>4}  "
            f"{avg('motion_count'):>7.1f}  "
            f"{avg('planning_count'):>8.1f}  "
            f"{avg('interest_count'):>9.1f}  "
            f"{avg('budget_item_count'):>6.1f}"
        )

    lines.append("")
    return lines


def _section_other_content(ok: list[dict], brief: bool = False) -> list[str]:
    """
    brief=True  — console view: word frequency + 2 examples per meeting type.
    brief=False — file view: full per-document listing.
    """
    lines = ["=" * 72, "  OTHER_CONTENT FIELD — CORPUS TYPOLOGY", "=" * 72, ""]

    with_content = [r for r in ok if _inv(r).get("other_content")]
    null_count = len(ok) - len(with_content)

    lines.append(f"  Non-null: {len(with_content)} / {len(ok)}  ({len(with_content)*100//len(ok)}%)")
    lines.append(f"  Null:     {null_count}")
    lines.append("")

    # Word frequency across all other_content values
    word_counts: Counter = Counter()
    for r in with_content:
        text = _inv(r)["other_content"].lower()
        words = re.findall(r"\b[a-z]{4,}\b", text)
        word_counts.update(words)

    _STOP = {
        "that", "this", "with", "from", "have", "been", "also", "which", "their",
        "there", "about", "items", "item", "meeting", "council", "document",
        "contains", "including", "such", "other", "various", "number", "general",
        "matters", "related", "information", "reports", "report", "noted", "agenda",
        "section", "sections", "discussed", "provided", "received", "considered",
        "approval", "under", "within", "presented", "relating", "details",
    }
    significant = [(w, c) for w, c in word_counts.most_common(60) if w not in _STOP]

    lines.append("  Most frequent terms in other_content (after stopwords):")
    row = []
    for w, c in significant[:40]:
        row.append(f"{w}({c})")
        if len(row) == 8:
            lines.append("    " + "  ".join(row))
            row = []
    if row:
        lines.append("    " + "  ".join(row))
    lines.append("")

    # Group by meeting type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in with_content:
        by_type[_meeting_type(r)].append(r)

    sample_n = 2 if brief else None  # None = show all
    lines.append(
        f"  Sample content by meeting type (2 per type — see full report for all):"
        if brief else
        "  Content grouped by meeting type:"
    )
    lines.append("")

    for mt, recs in sorted(by_type.items(), key=lambda x: -len(x[1])):
        shown = recs[:sample_n] if sample_n else recs
        lines.append(f"  ── {_short_type(mt)} ({len(recs)} docs) " + "─" * max(0, 56 - len(mt)))
        for r in shown:
            inv = _inv(r)
            date = inv.get("meeting_date") or "unknown date"
            text = inv["other_content"].strip()
            lines.append(f"    {r['filename']}  {date}")
            if brief:
                # One truncated line only
                truncated = (text[:100] + "…") if len(text) > 100 else text
                lines.append(f"      {truncated}")
            else:
                # Full word-wrap
                words = text.split()
                line_buf, cur_len = [], 0
                for word in words:
                    if cur_len + len(word) + 1 > 64:
                        lines.append("      " + " ".join(line_buf))
                        line_buf, cur_len = [word], len(word)
                    else:
                        line_buf.append(word)
                        cur_len += len(word) + 1
                if line_buf:
                    lines.append("      " + " ".join(line_buf))
            lines.append("")
        if sample_n and len(recs) > sample_n:
            lines.append(f"      … {len(recs) - sample_n} more in full report")
            lines.append("")

    return lines


def _section_headings(ok: list[dict]) -> list[str]:
    lines = ["=" * 72, "  SECTION HEADING PATTERNS", "=" * 72, ""]

    heading_counts: Counter = Counter()
    for r in ok:
        for h in _inv(r).get("section_headings", []):
            heading_counts[h.strip()] += 1

    lines.append("  Most common section headings across all documents (top 40):")
    lines.append("")
    for heading, count in heading_counts.most_common(40):
        lines.append(f"  {count:>4}  {heading}")
    lines.append("")

    # Headings that appear rarely — potential schema coverage gaps
    rare = [(h, c) for h, c in heading_counts.items() if 2 <= c <= 10]
    rare.sort(key=lambda x: -x[1])
    lines.append(f"  Uncommon headings (2–10 occurrences, {len(rare)} total) — potential schema gaps:")
    lines.append("")
    for heading, count in rare[:30]:
        lines.append(f"  {count:>4}  {heading}")
    if len(rare) > 30:
        lines.append(f"       ... and {len(rare)-30} more")
    lines.append("")

    return lines


def _section_flags(ok: list[dict]) -> list[str]:
    lines = ["=" * 72, "  CENSUS CROSS-REFERENCE FLAGS", "=" * 72, ""]

    flagged = [
        r for r in ok
        if r.get("census_comparison", {}).get("flags")
    ]

    if not flagged:
        lines.append("  No flagged documents.")
    else:
        lines.append(f"  {len(flagged)} document(s) flagged:")
        lines.append("")
        for r in flagged:
            flags = r["census_comparison"]["flags"]
            inv = _inv(r)
            cc = r["census_comparison"]
            lines.append(f"  {r['filename']}  {inv.get('meeting_date', '?')}  {_short_type(_meeting_type(r))}")
            lines.append(f"    Flags: {', '.join(flags)}")
            lines.append(f"    L1 motion_count={inv.get('motion_count')}  L0 est={cc.get('census_estimated_motions')}  truncated={r.get('window_truncated')}")
    lines.append("")
    return lines


def _section_era_breakdown(ok: list[dict]) -> list[str]:
    lines = ["=" * 72, "  ENTITY COUNTS BY DECADE", "=" * 72, ""]

    by_decade: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        date = _inv(r).get("meeting_date") or ""
        year = int(date[:4]) if date and len(date) >= 4 else 0
        if year < 2000:
            decade = "1990s"
        elif year < 2010:
            decade = "2000s"
        elif year < 2020:
            decade = "2010s"
        elif year >= 2020:
            decade = "2020s"
        else:
            decade = "unknown"
        by_decade[decade].append(r)

    lines.append(f"  {'Decade':<10} {'N':>4}  {'Motions':>7}  {'Planning':>8}  {'Budget':>6}  {'Interests':>9}")
    lines.append(f"  {'-'*10} {'-'*4}  {'-'*7}  {'-'*8}  {'-'*6}  {'-'*9}")
    for decade in ["1990s", "2000s", "2010s", "2020s", "unknown"]:
        recs = by_decade.get(decade, [])
        if not recs:
            continue
        n = len(recs)
        def avg(key):
            vals = [_inv(r).get(key, 0) or 0 for r in recs]
            return sum(vals) / n
        lines.append(
            f"  {decade:<10} {n:>4}  "
            f"{avg('motion_count'):>7.1f}  "
            f"{avg('planning_count'):>8.1f}  "
            f"{avg('budget_item_count'):>6.1f}  "
            f"{avg('interest_count'):>9.1f}"
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Schema update prompt generator
# ---------------------------------------------------------------------------

def _generate_schema_prompt(ok: list[dict], output_path: Path) -> str:
    """Build a directive prompt for Claude Code to act on the typology report."""

    # Collect high-level gap signals (counts only — Claude reads the file for detail)
    other_by_type: dict[str, int] = {}
    for r in ok:
        if _inv(r).get("other_content", "").strip():
            mt = _short_type(_meeting_type(r))
            other_by_type[mt] = other_by_type.get(mt, 0) + 1

    heading_counts: Counter = Counter()
    for r in ok:
        for h in _inv(r).get("section_headings", []):
            heading_counts[h.strip()] += 1
    n_rare = sum(1 for c in heading_counts.values() if 2 <= c <= 10)

    out: list[str] = []
    out.append(f"Read {output_path}, then update the extraction schema and prompt")
    out.append("to close the gaps it identifies.")
    out.append("")
    out.append("Files to update:")
    out.append("  src/extraction/schemas.py        — Pydantic models for Claude output")
    out.append("  src/extraction/system_prompt.txt  — extraction prompt")
    out.append("  src/models/ontology.py            — only if a new DB table is needed")
    out.append("")
    out.append("What to look for in the report:")
    out.append(f"  • other_content field: {sum(other_by_type.values())} docs across"
               f" {len(other_by_type)} meeting types have free-text content the schema")
    out.append("    has no slot for. For each pattern: new field or other_items catch-all?")
    out.append(f"  • Rare section headings: {n_rare} headings appear in 2–10 docs each.")
    out.append("    Check whether content under those headings is captured or discarded.")
    out.append("")
    out.append("Instructions:")
    out.append("  1. Read the full report — all sections.")
    out.append("  2. Update schemas.py: add missing fields; keep validators lenient.")
    out.append("  3. Update system_prompt.txt: instruct Claude to populate new fields.")
    out.append("  4. Only touch ontology.py if a new DB table is genuinely required.")
    out.append("  5. Do not touch extractor.py or database.py.")
    out.append("  6. Run 'council eval --compare' after changes.")
    out.append("  7. Notify the user — this is a commit point.")

    return "\n".join(out)


def _print_prompt_box(prompt_text: str) -> None:
    border = "═" * 72
    print(flush=True)
    print(border)
    print("  PASTE INTO CLAUDE CODE  ▶  Level 2: Schema Update")
    print(border)
    print()
    for line in prompt_text.split("\n"):
        print(("  " + line) if line.strip() else "")
    print()
    print(border)
    print()


def _section_schema_prompt(prompt_text: str) -> list[str]:
    lines: list[str] = [
        "=" * 72,
        "  SCHEMA UPDATE PROMPT — Claude Code instructions for Level 2",
        "=" * 72,
        "",
    ]
    for line in prompt_text.split("\n"):
        lines.append(("  " + line) if line.strip() else "")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args) -> None:
    council_key: str = args.council
    quiet: bool = getattr(args, "quiet", False)

    records = load_inventories()
    ok = [r for r in records if r.get("status") == "ok"]
    errors = [r for r in records if r.get("status") != "ok"]

    if not ok:
        print(f"No inventory data found in {INVENTORIES_DIR}. Run 'council inventory {council_key}' first.")
        return

    output_path = OUTPUT_DIR / f"{council_key}_typology_review.txt"

    header = [
        "=" * 72,
        f"  LEVEL 1 INVENTORY TYPOLOGY REVIEW — {council_key.upper()}",
        f"  {len(ok)} documents OK  |  {len(errors)} errors  |  {len(records)} total",
        "=" * 72,
        "",
    ]

    prompt_text = _generate_schema_prompt(ok, output_path)

    common_sections = (
        _section_meeting_types(ok)
        + _section_era_breakdown(ok)
        + _section_headings(ok)
        + _section_flags(ok)
    )

    # File gets the full report
    file_sections = header + common_sections + _section_other_content(ok, brief=False) + _section_schema_prompt(prompt_text)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(file_sections), encoding="utf-8")

    # Console: status line + prompt box only
    if not quiet:
        print(f"Analysed {len(ok)} inventories  |  {len(errors)} errors")
        print(f"Report written to {output_path}")

    _print_prompt_box(prompt_text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse Level 1 inventory typology for Level 2 schema review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Write to file only, suppress stdout")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
