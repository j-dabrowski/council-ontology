"""
Level 6 audit report generator.

Selects N extracted meeting documents, stratified by era × size, and formats
them as a human-readable markdown report for manual quality review.

The report is designed to be read side-by-side with the source PDFs, with
AUDIT comment placeholders for the reviewer to fill in.

Excluded from selection: documents already in the Level 3 sample
(data/cambridge_sample.json).

CLI: council audit cambridge [--count N] [--from-year YYYY] [--output PATH]
     council audit cambridge --list-only
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
SAMPLE_FILE = ROOT / "data" / "cambridge_sample.json"
CENSUS_FILE = ROOT / "data" / "census.json"
DB_FILE = ROOT / "data" / "council.db"
VALIDATION_DIR = ROOT / "data" / "validation"
SELECTION_FILE = ROOT / "data" / "audit_selection.json"
DEFAULT_OUTPUT = ROOT / "data" / "audit_report.md"

CHOICE_ICON = {"for": "✓", "against": "✗", "abstain": "~", "absent": "—"}
STATUS_STYLE = {"PASS": "✅", "REVIEW": "⚠️", "FAIL": "❌"}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_excluded() -> set[str]:
    """Return stems excluded from audit (Level 3 sample)."""
    if not SAMPLE_FILE.exists():
        return set()
    data = json.loads(SAMPLE_FILE.read_text())
    return {Path(f).stem for f in data.get("files", [])}


def _load_census() -> dict[str, dict]:
    """Return stem → census entry mapping."""
    if not CENSUS_FILE.exists():
        return {}
    data = json.loads(CENSUS_FILE.read_text())
    return {Path(doc["filename"]).stem: doc for doc in data.get("documents", [])}


def _load_validation(stem: str) -> dict | None:
    path = VALIDATION_DIR / f"{stem}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------

def _pick_stratified(
    candidates: list[dict],
    n: int,
    seed: int | None = None,
) -> list[dict]:
    """
    Stratify by (decade, size_bucket) and sample up to n docs, balanced across strata.
    If a stratum has fewer docs than its quota, take all of them.
    """
    rng = random.Random(seed)
    buckets: dict[tuple, list[dict]] = {}
    for doc in candidates:
        key = (doc.get("decade", "unknown"), doc.get("size_bucket", "unknown"))
        buckets.setdefault(key, []).append(doc)

    result: list[dict] = []
    remaining = n
    # Sort keys for deterministic output
    sorted_keys = sorted(buckets.keys())
    for i, key in enumerate(sorted_keys):
        pool = buckets[key]
        # Distribute remaining quota evenly across remaining buckets
        quota = math.ceil(remaining / (len(sorted_keys) - i))
        chosen = rng.sample(pool, min(quota, len(pool)))
        result.extend(chosen)
        remaining -= len(chosen)
        if remaining <= 0:
            break

    rng.shuffle(result)
    return result[:n]


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------

def _query_candidates(conn: sqlite3.Connection, from_year: int | None) -> list[dict]:
    """Return all meetings that have at least one extracted motion."""
    sql = """
        SELECT m.id, m.meeting_date, m.meeting_type, m.document_type,
               m.minutes_pdf_path, m.minutes_pdf_url,
               COUNT(mo.id) AS motion_count
        FROM meetings m
        JOIN motions mo ON mo.meeting_id = m.id
        WHERE m.minutes_pdf_path IS NOT NULL
    """
    params: list = []
    if from_year:
        sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) >= ?"
        params.append(from_year)
    sql += " GROUP BY m.id ORDER BY m.meeting_date"

    rows = conn.execute(sql, params).fetchall()
    cols = ["id", "meeting_date", "meeting_type", "document_type",
            "minutes_pdf_path", "minutes_pdf_url", "motion_count"]
    return [dict(zip(cols, row)) for row in rows]


def _query_motions(conn: sqlite3.Connection, meeting_id: int) -> list[dict]:
    sql = """
        SELECT mo.id, mo.item_number, mo.title, mo.description,
               mo.motion_text, mo.outcome, mo.votes_for, mo.votes_against,
               mo.votes_abstain, mo.tags,
               cr_mov.given_name AS mover_given, cr_mov.family_name AS mover_family,
               cr_sec.given_name AS sec_given, cr_sec.family_name AS sec_family
        FROM motions mo
        LEFT JOIN councillors cr_mov ON cr_mov.id = mo.moved_by_id
        LEFT JOIN councillors cr_sec ON cr_sec.id = mo.seconded_by_id
        WHERE mo.meeting_id = ?
        ORDER BY mo.item_number, mo.id
    """
    rows = conn.execute(sql, [meeting_id]).fetchall()
    cols = ["id", "item_number", "title", "description", "motion_text",
            "outcome", "votes_for", "votes_against", "votes_abstain", "tags",
            "mover_given", "mover_family", "sec_given", "sec_family"]
    return [dict(zip(cols, r)) for r in rows]


def _query_votes(conn: sqlite3.Connection, motion_ids: list[int]) -> dict[int, list[dict]]:
    if not motion_ids:
        return {}
    placeholders = ",".join("?" * len(motion_ids))
    sql = f"""
        SELECT v.motion_id, c.given_name, c.family_name, v.choice, v.declared_interest
        FROM votes v
        JOIN councillors c ON c.id = v.councillor_id
        WHERE v.motion_id IN ({placeholders})
        ORDER BY v.motion_id, c.family_name, c.given_name
    """
    rows = conn.execute(sql, motion_ids).fetchall()
    result: dict[int, list[dict]] = {}
    for mid, given, family, choice, interest in rows:
        result.setdefault(mid, []).append({
            "given_name": given, "family_name": family,
            "choice": choice, "declared_interest": bool(interest),
        })
    return result


def _query_planning(conn: sqlite3.Connection, motion_ids: list[int]) -> dict[int, list[dict]]:
    if not motion_ids:
        return {}
    placeholders = ",".join("?" * len(motion_ids))
    sql = f"""
        SELECT pa.motion_id, pa.id, pa.reference_number, pa.applicant_name,
               pa.description, pa.status,
               s.address
        FROM planning_applications pa
        LEFT JOIN sites s ON s.id = pa.site_id
        WHERE pa.motion_id IN ({placeholders})
    """
    rows = conn.execute(sql, motion_ids).fetchall()
    cols = ["motion_id", "id", "reference_number", "applicant_name",
            "description", "status", "address"]
    result: dict[int, list[dict]] = {}
    for r in rows:
        d = dict(zip(cols, r))
        result.setdefault(d["motion_id"], []).append(d)
    return result


def _query_meeting_entities(conn: sqlite3.Connection, meeting_id: int) -> dict[str, list[dict]]:
    """Fetch all non-motion entity tables for a meeting."""
    entities: dict[str, list[dict]] = {}

    queries = {
        "public_questions": """
            SELECT id, questioner_name, question_summary, response_summary
            FROM public_questions WHERE meeting_id = ?""",
        "deputations": """
            SELECT id, presenter_name, topic, summary
            FROM deputations WHERE meeting_id = ?""",
        "petitions": """
            SELECT id, subject, presented_by, signatory_count
            FROM petitions WHERE meeting_id = ?""",
        "interest_declarations": """
            SELECT id, interest_type, description, item_reference
            FROM interest_declarations WHERE meeting_id = ?""",
        "tenders": """
            SELECT id, reference_number, description, awarded_to, amount, is_confidential
            FROM tenders WHERE meeting_id = ?""",
        "budget_items": """
            SELECT id, item_number, description, amount, is_confidential
            FROM budget_items WHERE meeting_id = ?""",
        "building_permits": """
            SELECT id, reference_number, site_address, description, estimated_value, status
            FROM building_permits WHERE meeting_id = ?""",
        "other_items": """
            SELECT id, item_number, item_type, description, is_confidential
            FROM other_items WHERE meeting_id = ?""",
    }
    for table, sql in queries.items():
        rows = conn.execute(sql, [meeting_id]).fetchall()
        if rows:
            cols = [d[0] for d in conn.execute(sql + " LIMIT 0", [meeting_id]).description]
            entities[table] = [dict(zip(cols, r)) for r in rows]

    return entities


def _query_evidence(conn: sqlite3.Connection, meeting_id: int) -> dict[tuple[str, int], list[str]]:
    """Return (table, entity_id) → list of quotes."""
    sql = """
        SELECT entity_table, entity_id, quote_text, char_offset
        FROM extraction_evidence
        WHERE meeting_id = ?
        ORDER BY entity_table, entity_id, id
    """
    rows = conn.execute(sql, [meeting_id]).fetchall()
    result: dict[tuple[str, int], list[str]] = {}
    for table, eid, quote, offset in rows:
        key = (table, eid)
        tag = "" if offset is not None else " *(unverified)*"
        result.setdefault(key, []).append(quote + tag)
    return result


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def _fmt_name(given: str | None, family: str | None) -> str:
    parts = [p for p in (given, family) if p]
    return " ".join(parts) if parts else "—"


def _fmt_money(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"${amount:,.0f}"


def _blockquote(text: str | None) -> str:
    if not text:
        return ""
    lines = text.strip().split("\n")
    return "\n".join(f"> {line}" for line in lines)


def _evidence_section(quotes: list[str]) -> str:
    if not quotes:
        return ""
    lines = ["**Source quote(s):**"]
    for q in quotes[:2]:  # cap at 2 quotes per entity to keep report readable
        # Truncate very long quotes
        display = q[:400] + "…" if len(q) > 400 else q
        lines.append(_blockquote(display))
    return "\n".join(lines)


def _fmt_motions(
    motions: list[dict],
    votes_by_motion: dict[int, list[dict]],
    planning_by_motion: dict[int, list[dict]],
    evidence: dict[tuple[str, int], list[str]],
) -> str:
    if not motions:
        return "*No motions extracted.*\n"
    lines: list[str] = []
    for i, m in enumerate(motions, 1):
        item_label = m["item_number"] or f"#{i}"
        outcome = m["outcome"] or "—"
        lines.append(f"#### M{i} · {item_label} — {m['title']} · *{outcome}*")

        mover = _fmt_name(m["mover_given"], m["mover_family"])
        seconder = _fmt_name(m["sec_given"], m["sec_family"])
        vote_tally = ""
        if m["votes_for"] is not None or m["votes_against"] is not None:
            vf = m["votes_for"] if m["votes_for"] is not None else "?"
            va = m["votes_against"] if m["votes_against"] is not None else "?"
            vote_tally = f" · For: {vf} · Against: {va}"
        lines.append(f"Moved by **{mover}** · Seconded by **{seconder}**{vote_tally}")

        if m["description"]:
            lines.append("")
            lines.append(_blockquote(m["description"]))

        if m["motion_text"] and m["motion_text"] != m["description"]:
            lines.append("")
            lines.append("**Motion text:**")
            lines.append(_blockquote(m["motion_text"]))

        votes = votes_by_motion.get(m["id"], [])
        if votes:
            lines.append("")
            lines.append("**Individual votes:**")
            for v in votes:
                choice = (v["choice"] or "").lower()
                icon = CHOICE_ICON.get(choice, "?")
                name = _fmt_name(v["given_name"], v["family_name"])
                interest_flag = " *(declared interest)*" if v["declared_interest"] else ""
                lines.append(f"- {name} — {v['choice']} {icon}{interest_flag}")

        # Planning applications linked to this motion
        apps = planning_by_motion.get(m["id"], [])
        for app in apps:
            lines.append("")
            lines.append(f"**Planning:** {app['reference_number'] or '—'}"
                         f" · {app['address'] or '—'}"
                         f" · status: *{app['status'] or '—'}*")
            if app["description"]:
                lines.append(f"  {app['description'][:200]}")

        ev = evidence.get(("motions", m["id"]), [])
        if ev:
            lines.append("")
            lines.append(_evidence_section(ev))

        if m["tags"]:
            lines.append(f"\n*Tags: {m['tags']}*")

        lines.append("")
        lines.append("<!-- AUDIT: [Y/N/PARTIAL] — notes: -->")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _fmt_entity_section(title: str, items: list[dict], evidence: dict, table: str) -> str:
    if not items:
        return ""
    lines = [f"### {title} ({len(items)})"]
    for i, item in enumerate(items, 1):
        eid = item.get("id")
        # Build a one-liner summary based on what fields are populated
        fields = {k: v for k, v in item.items()
                  if k not in ("id", "meeting_id") and v not in (None, False, "")}
        lines.append(f"#### {title[:-1] if title.endswith('s') else title} {i}")
        for k, v in fields.items():
            k_label = k.replace("_", " ").title()
            if isinstance(v, float):
                v_str = _fmt_money(v)
            elif isinstance(v, bool):
                v_str = "yes" if v else "no"
            else:
                v_str = str(v)[:300]
            lines.append(f"- **{k_label}:** {v_str}")
        ev = evidence.get((table, eid), [])
        if ev:
            lines.append("")
            lines.append(_evidence_section(ev))
        lines.append("")
        lines.append("<!-- AUDIT: [Y/N/PARTIAL] — notes: -->")
        lines.append("")
    return "\n".join(lines) + "\n"


def _fmt_validation(v: dict | None) -> str:
    if not v:
        return "*No validation data.*"
    status = v.get("status", "—")
    icon = STATUS_STYLE.get(status, "")
    qc = v.get("quote_completeness", {})
    qc_rate = qc.get("completeness_rate", None)
    qc_str = f"{qc_rate:.0%}" if isinstance(qc_rate, float) else "—"
    cov = v.get("coverage_ratio", None)
    cov_str = f"{cov:.1%}" if isinstance(cov, (int, float)) else "—"
    entity_counts = v.get("entity_counts", {})
    inv_data = v.get("inventory_agreement") or {}
    inv_agree = inv_data.get("agreed", None)
    ec_str = ", ".join(f"{t}: {n}" for t, n in entity_counts.items() if n) if entity_counts else "—"
    parts = [
        f"**Status:** {icon} {status}",
        f"**Quote completeness:** {qc_str}",
        f"**Coverage ratio:** {cov_str}",
        f"**Entities:** {ec_str}",
    ]
    if inv_agree is not None:
        parts.append(f"**Inventory agreement:** {'yes' if inv_agree else 'no'}")
    return " | ".join(parts)


def generate_report(
    docs: list[dict],
    conn: sqlite3.Connection,
    council_name: str,
    from_year: int | None,
    today: date,
) -> str:
    lines: list[str] = []
    lines.append(f"# Audit Report — {council_name.title()}")
    lines.append(f"Generated: {today}  ")
    yr_note = f"from_year: {from_year}" if from_year else "all years"
    lines.append(f"Docs: {len(docs)} | {yr_note} | Excludes Level 3 sample")
    lines.append("")
    lines.append("> **How to use:** Open each PDF alongside this report.")
    lines.append("> For each item, mark `[Y]` (correct), `[N]` (wrong), or `[PARTIAL]` in the AUDIT comment.")
    lines.append("> Add brief notes after the dash.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for doc_idx, doc in enumerate(docs, 1):
        meeting_id = doc["id"]
        stem = Path(doc["minutes_pdf_path"]).stem
        meeting_date = doc["meeting_date"]
        doc_type = doc.get("document_type") or "unknown"
        meeting_type = doc.get("meeting_type") or "—"
        motion_count = doc["motion_count"]
        size_bucket = doc.get("size_bucket", "?")
        decade = doc.get("decade", "?")
        pdf_path = doc["minutes_pdf_path"]
        pdf_url = doc.get("minutes_pdf_url") or "—"

        lines.append(f"## [{doc_idx}/{len(docs)}] {meeting_date} — {meeting_type} ({doc_type})")
        lines.append(f"**PDF:** `{pdf_path}`  ")
        lines.append(f"**URL:** {pdf_url}  ")
        lines.append(f"**Size:** {size_bucket} | **Era:** {decade}  ")
        lines.append(f"**Stem:** `{stem}`  ")

        val = _load_validation(stem)
        lines.append(_fmt_validation(val))
        lines.append("")

        motions = _query_motions(conn, meeting_id)
        motion_ids = [m["id"] for m in motions]
        votes_by_motion = _query_votes(conn, motion_ids)
        planning_by_motion = _query_planning(conn, motion_ids)
        evidence = _query_evidence(conn, meeting_id)
        other_entities = _query_meeting_entities(conn, meeting_id)

        lines.append(f"### Motions ({motion_count})")
        lines.append("")
        lines.append(_fmt_motions(motions, votes_by_motion, planning_by_motion, evidence))

        for table, items in other_entities.items():
            title = table.replace("_", " ").title()
            lines.append(_fmt_entity_section(title, items, evidence, table))

        lines.append("")
        lines.append("=" * 70)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    council_name: str,
    count: int = 12,
    from_year: int | None = 2024,
    output: Path = DEFAULT_OUTPUT,
    seed: int | None = None,
    list_only: bool = False,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    excluded = _load_excluded()
    census = _load_census()
    conn = sqlite3.connect(DB_FILE)

    candidates_raw = _query_candidates(conn, from_year)
    candidates: list[dict] = []
    for doc in candidates_raw:
        stem = Path(doc["minutes_pdf_path"]).stem
        if stem in excluded:
            continue
        # Enrich with census data
        cdata = census.get(stem, {})
        doc["size_bucket"] = cdata.get("size_bucket", "unknown")
        doc["decade"] = cdata.get("decade", "unknown")
        candidates.append(doc)

    yr_label = f"from {from_year}" if from_year else "all years"
    console.print(f"[bold]{len(candidates)}[/bold] candidate docs ({yr_label}, {len(excluded)} excluded)")

    if list_only:
        t = Table(title="Candidates")
        t.add_column("Date"); t.add_column("Type"); t.add_column("Decade"); t.add_column("Size"); t.add_column("Motions")
        for d in candidates:
            t.add_row(d["meeting_date"], d.get("meeting_type", ""), d.get("decade", "?"), d.get("size_bucket", "?"), str(d["motion_count"]))
        console.print(t)
        return

    selected = _pick_stratified(candidates, count, seed=seed)
    console.print(f"Selected [bold]{len(selected)}[/bold] docs")

    # Save selection
    selection_data = {
        "council": council_name,
        "generated_at": str(date.today()),
        "from_year": from_year,
        "count": len(selected),
        "files": [Path(d["minutes_pdf_path"]).stem + ".pdf" for d in selected],
    }
    SELECTION_FILE.write_text(json.dumps(selection_data, indent=2))
    console.print(f"Selection saved → [cyan]{SELECTION_FILE}[/cyan]")

    # Generate report
    report = generate_report(selected, conn, council_name, from_year, date.today())
    output = Path(output)
    output.write_text(report)
    console.print(f"Report written → [green]{output}[/green]  ({len(report):,} chars)")
    console.print(f"\n[dim]Open with: open {output}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Level 6 audit report generator")
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--count", type=int, default=12,
                        help="Number of docs to sample (default: 12)")
    parser.add_argument("--from-year", type=int, default=2024, dest="from_year",
                        help="Only include docs from this year onwards (default: 2024)")
    parser.add_argument("--all-years", action="store_true", dest="all_years",
                        help="Include all extracted years (overrides --from-year)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible sampling")
    parser.add_argument("--list-only", action="store_true", dest="list_only",
                        help="List candidates without generating report")
    args = parser.parse_args()

    from_year = None if args.all_years else args.from_year
    run(args.council, count=args.count, from_year=from_year,
        output=args.output, seed=args.seed, list_only=args.list_only)


if __name__ == "__main__":
    main()
