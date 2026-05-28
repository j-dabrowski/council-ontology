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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

INVENTORIES_DIR = Path("data/inventories")
OUTPUT_DIR = Path("data")
QUALITY_DIR = Path("data/inventory_quality")

# other_content rate at or below this → inventory is good enough; show extraction prompt
QUALITY_THRESHOLD = 0.20

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_inventories(limit: int | None = None) -> list[dict]:
    paths = [p for p in INVENTORIES_DIR.glob("*.json") if p.name != "summary.json"]
    if limit is not None:
        # Most recently modified first so --limit N matches the last --limit N inventory run
        paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    else:
        paths = sorted(paths)
    records = []
    for p in paths:
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

    n_docs = len(ok)

    out: list[str] = []
    out.append(f"Read {output_path}, then update the inventory prompt so that")
    out.append("recurring content types are captured in structured fields rather than")
    out.append("falling through to other_content.")
    out.append("")
    out.append("File to update:")
    out.append("  src/extraction/inventory_prompt.txt  — the Level 1 inventory prompt")
    out.append("  scripts/inventory.py                 — DocumentInventory Pydantic model")
    out.append("                                         (add matching fields + coerce validator)")
    out.append("")
    out.append("What to look for in the report:")
    out.append(f"  • other_content field: {sum(other_by_type.values())} docs across"
               f" {len(other_by_type)} meeting types have free-text content the inventory")
    out.append("    has no structured field for. The goal is to reduce this to a small")
    out.append("    residual of genuinely unclassifiable content.")
    out.append(f"  • Rare section headings: {n_rare} headings appear in 2–10 docs each.")
    out.append("    Check whether recurring content under those headings needs a new field.")
    out.append("")
    out.append("Decision rule — new inventory field vs leaving in other_content:")
    out.append("  Do NOT default to other_content to avoid adding fields — that defeats")
    out.append("  the purpose of this step.")
    out.append("")
    out.append(f"  Content type appears in >10% of corpus ({n_docs//10}+ docs):")
    out.append("    → MUST have a dedicated count field in the inventory prompt.")
    out.append(f"  Content type appears in 2–10% of corpus ({max(2, n_docs//50)}–{n_docs//10} docs):")
    out.append("    → Add a field if the content is countable and structurally consistent.")
    out.append("    → Leave in other_content only if genuinely free-form.")
    out.append("  Content type appears in <2% of corpus or is purely procedural:")
    out.append("    → other_content is appropriate.")
    out.append("")
    out.append("Instructions:")
    out.append("  1. Read the full report — all sections.")
    out.append("  2. Apply the decision rule to every content type in other_content.")
    out.append("  3. Add new count fields to the inventory prompt JSON schema and")
    out.append("     field descriptions. Keep the prompt concise — counts only, no")
    out.append("     structured sub-objects.")
    out.append("  4. Add matching fields to DocumentInventory in scripts/inventory.py.")
    out.append("     Include them in the _coerce_int validator.")
    out.append("  5. Bump PROMPT_VERSION in scripts/inventory.py (e.g. inventory-v2)")
    out.append("     so cached responses are invalidated and the re-run uses the new prompt.")
    out.append("  6. Run 'council inventory cambridge --force --limit 20' to test on a")
    out.append("     small sample before re-running the full corpus.")
    out.append("  7. If the sample looks good, run 'council inventory cambridge --force'")
    out.append("     to re-run all 537 docs (~$5, ~10 min).")
    out.append("  8. Run 'council typology cambridge' again to check that other_content")
    out.append("     is now minimal. Repeat from step 1 if significant content remains.")
    out.append("  9. When other_content is minimal, the inventory is complete. The")
    out.append("     extraction schema (src/extraction/schemas.py and system_prompt.txt)")
    out.append("     can now be updated with confidence to match the inventory fields.")
    out.append(" 10. Notify the user after step 8 — that is the commit point.")

    return "\n".join(out)


def _print_prompt_box(prompt_text: str, header: str = "PASTE INTO CLAUDE CODE") -> None:
    border = "═" * 72
    print(flush=True)
    print(border)
    print(f"  {header}")
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
# Quality scoring
# ---------------------------------------------------------------------------

def _compute_quality(ok: list[dict]) -> dict:
    """Compute inventory quality metrics from the current set of inventory records."""
    substantive = [
        r for r in ok
        if _inv(r).get("other_content") and len(_inv(r)["other_content"].strip()) > 30
    ]
    rate = len(substantive) / len(ok) if ok else 0.0
    word_counts = [len(_inv(r)["other_content"].split()) for r in substantive]
    avg_words = round(sum(word_counts) / len(word_counts), 1) if word_counts else 0.0
    return {
        "other_content_rate": round(rate, 4),
        "other_content_pct": round(rate * 100, 1),
        "substantive_docs": len(substantive),
        "total_docs": len(ok),
        "avg_other_content_words": avg_words,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _save_quality(quality: dict, council_key: str) -> None:
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    (QUALITY_DIR / f"quality_{council_key}_{ts}.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )
    (QUALITY_DIR / f"latest_{council_key}.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )


def _load_quality_history(council_key: str) -> list[dict]:
    if not QUALITY_DIR.exists():
        return []
    records = []
    for p in sorted(QUALITY_DIR.glob(f"quality_{council_key}_*.json")):
        try:
            records.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return records


def _print_quality_history(council_key: str) -> None:
    history = _load_quality_history(council_key)
    if not history:
        print(f"No quality history found for '{council_key}'.")
        return
    print(f"\n  Inventory quality history — {council_key}")
    print(f"  {'Timestamp':<22} {'Rate':>6}  {'Docs':>10}  {'Avg words':>10}")
    print(f"  {'-'*22} {'-'*6}  {'-'*10}  {'-'*10}")
    for q in history:
        raw_ts = q.get("timestamp", "?")
        try:
            ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            ts = raw_ts[:19].replace("T", " ")
        rate = f"{q.get('other_content_pct', '?')}%"
        docs = f"{q.get('substantive_docs', '?')}/{q.get('total_docs', '?')}"
        words = q.get("avg_other_content_words", "?")
        print(f"  {ts:<22} {rate:>6}  {docs:>10}  {words:>10}")
    print()


# ---------------------------------------------------------------------------
# Extraction schema prompt (shown when inventory quality is good)
# ---------------------------------------------------------------------------

def _generate_extraction_prompt(ok: list[dict], quality: dict, output_path: Path) -> str:
    """Prompt shown when other_content rate is below threshold — proceed to extraction schema."""
    n_docs = len(ok)

    # Collect inventory field names from the first ok record to tell Claude what was measured
    sample_inv = _inv(ok[0]) if ok else {}
    inv_fields = [k for k in sample_inv if k not in ("meeting_date", "meeting_type", "section_headings", "other_content")]

    heading_counts: Counter = Counter()
    for r in ok:
        for h in _inv(r).get("section_headings", []):
            heading_counts[h.strip()] += 1
    n_rare = sum(1 for c in heading_counts.values() if 2 <= c <= 10)

    out: list[str] = []
    out.append(f"Inventory quality is acceptable ({quality['other_content_pct']}% other_content rate,")
    out.append(f"threshold {int(QUALITY_THRESHOLD*100)}%). The inventory now covers the corpus well.")
    out.append(f"Read {output_path}, then update the extraction schema and prompt to match.")
    out.append("")
    out.append("Files to update:")
    out.append("  src/extraction/schemas.py        — Pydantic models for Claude output")
    out.append("  src/extraction/system_prompt.txt  — extraction prompt")
    out.append("  src/models/ontology.py            — only if a new DB table is needed")
    out.append("")
    out.append("The inventory now tracks these content types as structured fields:")
    for f in inv_fields:
        out.append(f"  {f}")
    out.append("")
    out.append("Decision rule — dedicated schema field vs other_items catch-all:")
    out.append("  Do NOT default to other_items to avoid schema changes.")
    out.append("")
    out.append(f"  Content type appears in >10% of corpus ({n_docs//10}+ docs):")
    out.append("    → MUST have a dedicated typed Pydantic model + list field on ExtractedMeeting.")
    out.append(f"  Content type appears in 2–10% of corpus ({max(2, n_docs//50)}–{n_docs//10} docs):")
    out.append("    → Add a dedicated field if structured and analytically useful.")
    out.append("    → other_items only if genuinely free-form narrative.")
    out.append("  Content type appears in <2% of corpus or is purely procedural:")
    out.append("    → other_items is appropriate.")
    out.append("")
    out.append(f"  Rare section headings: {n_rare} appear in 2–10 docs — check coverage.")
    out.append("")
    out.append("Instructions:")
    out.append("  1. Read the full typology report.")
    out.append("  2. Apply the decision rule to every inventory field and other_content residual.")
    out.append("  3. For each type getting a dedicated field: add a Pydantic sub-model in")
    out.append("     schemas.py with lenient validators; add a list field on ExtractedMeeting.")
    out.append("  4. Add the new fields to the OUTPUT SCHEMA block in system_prompt.txt and")
    out.append("     write extraction rules explaining when/how to populate each.")
    out.append("  5. Remove promoted types from the other_items item_type list in the prompt.")
    out.append("  6. Only touch ontology.py if a new DB table is genuinely required.")
    out.append("  7. Do not touch extractor.py or database.py.")
    out.append("  8. Run 'council eval --compare' to verify no regression.")
    out.append("     Runs against 4 benchmark PDFs only (~2 min, safe to run).")
    out.append("     Drop of ≤3 points overall is normal variance.")
    out.append("     Drop of >5 points on any single PDF warrants investigation.")
    out.append("  9. Notify the user — this is a commit point.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args) -> None:
    council_key: str = args.council
    quiet: bool = getattr(args, "quiet", False)
    history: bool = getattr(args, "history", False)
    limit: int | None = getattr(args, "limit", None)

    if history:
        _print_quality_history(council_key)
        return

    records = load_inventories(limit=limit)
    ok = [r for r in records if r.get("status") == "ok"]
    errors = [r for r in records if r.get("status") != "ok"]

    if not ok:
        print(f"No inventory data found in {INVENTORIES_DIR}. Run 'council inventory {council_key}' first.")
        return

    output_path = OUTPUT_DIR / f"{council_key}_typology_review.txt"

    quality = _compute_quality(ok)
    _save_quality(quality, council_key)

    needs_improvement = quality["other_content_rate"] > QUALITY_THRESHOLD
    prompt_text = (
        _generate_schema_prompt(ok, output_path)
        if needs_improvement
        else _generate_extraction_prompt(ok, quality, output_path)
    )
    prompt_header = (
        "PASTE INTO CLAUDE CODE  ▶  Inventory needs improvement"
        if needs_improvement
        else "PASTE INTO CLAUDE CODE  ▶  Inventory complete — update extraction schema"
    )

    header = [
        "=" * 72,
        f"  LEVEL 1 INVENTORY TYPOLOGY REVIEW — {council_key.upper()}",
        f"  {len(ok)} documents OK  |  {len(errors)} errors  |  {len(records)} total",
        "=" * 72,
        "",
    ]

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

    # Console: status + quality score + next steps + prompt box
    if not quiet:
        threshold_pct = int(QUALITY_THRESHOLD * 100)
        status = "needs improvement" if needs_improvement else "acceptable ✓"
        scope = f"  (sample: {limit} most-recently-updated docs)" if limit else ""
        print(f"Analysed {len(ok)} inventories  |  {len(errors)} errors{scope}")
        print(f"other_content rate: {quality['other_content_pct']}%  "
              f"({quality['substantive_docs']}/{quality['total_docs']} docs)  "
              f"threshold {threshold_pct}%  →  {status}")
        print(f"Report written to {output_path}")
        print()
        if needs_improvement:
            print("Your next steps:")
            print("  1. Paste the prompt below into Claude Code — it will update the inventory prompt")
            print("     and Pydantic model. You don't need to do anything else until it notifies you.")
            print(f"  2. Test on a sample:  council inventory cambridge --force --limit {limit or 20}")
            print(f"  3. Check the sample:  council typology cambridge --limit {limit or 20}")
            print(f"  4. If looking good, full re-run:  council inventory cambridge --force")
            print(f"  5. Check full corpus: council typology cambridge")
        else:
            print("Your next steps:")
            print("  1. Paste the prompt below into Claude Code — it will update the extraction schema.")
            print("     You don't need to do anything else until it notifies you.")
            print("  2. Verify: council eval --compare")
        print()

    _print_prompt_box(prompt_text, header=prompt_header)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse Level 1 inventory typology for Level 2 schema review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Write to file only, suppress stdout")
    parser.add_argument("--history", action="store_true",
                        help="Show inventory quality score history and exit")
    parser.add_argument("--limit", "-n", type=int, default=None, metavar="N",
                        help="Analyse only the N most-recently-updated inventory files")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
