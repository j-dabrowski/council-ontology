"""
One-time deduplication migration for the councillors table.

The extraction pipeline historically created duplicate records when the LLM outputs
names in different formats ("Cr Barlow", "Kate Barlow", "Barlow", "null Barlow",
"Barlow Cr" etc.).  This script finds, reports, and merges those duplicates.

Three passes:
  Pass 1 — Bad records: given_name is a title, placeholder, self-repeat, or the
            fields are swapped (family_name is the title).  These are unambiguously
            wrong and are merged into the canonical for their family name.
  Pass 2 — Family-only stubs: given_name is empty/null but a real-name canonical
            exists for the same family name.  Merged when unambiguous.
  Pass 3 — Fuzzy family-name stubs: family name is a near-misspelling of a real
            councillor's name (e.g. "Timmermans" → "Timmermanis", "Pelcar" →
            "Pelczar").  Resolved using term overlap; reported for review otherwise.

Merge target selection (in order):
  1. Exact normalised-slug match (e.g. "Cr Gavin Foley" → "gavin-foley").
  2. Single real-name canonical for this family name.
  3. Terms-match: stub's vote date span overlaps a candidate's known term window.
  4. Canonical with the most 2024+ votes (clear winner = ≥2× runner-up).
  5. Otherwise: normalise in place (just fix the slug/given_name), flag in report.

Term annotation:
  councillor_terms data is always loaded and used for disambiguation (step 3 above).
  Every planned merge is annotated:
    TERM ✓  — stub votes fall within a known candidate term (confirmed)
    TERM ✗  — stub votes fall entirely outside all candidate terms (conflict)
    TERM ?  — candidate has no term records (falls back to vote-date heuristic)

  With --use-terms, only TERM ✓ merges are applied automatically; TERM ✗ and
  TERM ? merges are moved to the held list for manual review.

Usage:
    python scripts/dedup_councillors.py            # dry run — print report only
    python scripts/dedup_councillors.py --apply    # write changes to DB
    python scripts/dedup_councillors.py --use-terms --apply  # only apply TERM ✓ merges
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "council.db"

HONORIFICS = frozenset({
    "cr", "cr.", "councillor", "mayor", "deputy", "deputy mayor",
})
PLACEHOLDERS = frozenset({
    "null", "name", "unknown", "none", "n/a",
})
# Patterns that look like given names but are LLM placeholders or OCR artifacts
_PLACEHOLDER_RE = re.compile(
    r"^(not[\s_]named?|unnamed|unspecified|name[\s_]unknown|given[_\s]?name"
    r"|unrecorded|not\s+provided|first\s+name)$",
    re.IGNORECASE,
)

# Minimum SequenceMatcher ratio for fuzzy family-name matching in Pass 3
_FUZZY_THRESHOLD = 0.82

# All tables with a FK column that points at councillors.id
FK_COLUMNS: list[tuple[str, str]] = [
    ("votes", "councillor_id"),
    ("motions", "moved_by_id"),
    ("motions", "seconded_by_id"),
    ("appointments", "councillor_id"),
    ("interest_declarations", "councillor_id"),
]


# ---------------------------------------------------------------------------
# Name helpers (mirrors extractor._normalise_councillor_name)
# ---------------------------------------------------------------------------

def normalise_name(given: str | None, family: str | None) -> tuple[str, str]:
    given = (given or "").strip()
    family = (family or "").strip()

    if family.lower().rstrip(".") in HONORIFICS:
        given, family = family, given

    parts = given.split()
    while parts:
        two = " ".join(parts[:2]).lower() if len(parts) >= 2 else ""
        one = parts[0].lower().rstrip(".")
        if two in HONORIFICS:
            parts = parts[2:]
        elif one in HONORIFICS:
            parts = parts[1:]
        else:
            break
    given = " ".join(parts)

    # Rejoin compound surname particles split across fields ("Le"+"Page" → "Le Page")
    _PARTICLES = frozenset({"le", "van", "de", "du", "von", "la", "di", "der", "den"})
    if given.lower() in _PARTICLES and family:
        family = f"{given} {family}"
        given = ""

    if given.lower() in PLACEHOLDERS or (family and given.lower() == family.lower()):
        given = ""

    return given, family


def make_slug(given: str, family: str) -> str:
    name = f"{given} {family}".strip() if given else family
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def is_real_given(given: str | None) -> bool:
    g = (given or "").strip().lower().rstrip(".")
    return bool(g) and g not in HONORIFICS and g not in PLACEHOLDERS and not _PLACEHOLDER_RE.match(g)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def load_councillors(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, given_name, family_name, slug FROM councillors ORDER BY id"
    ).fetchall()
    councillors = []
    for r in rows:
        c = dict(zip(["id", "given_name", "family_name", "slug"], r))
        ng, nf = normalise_name(c["given_name"], c["family_name"])
        c["norm_given"] = ng
        c["norm_family"] = nf
        c["norm_slug"] = make_slug(ng, nf)
        # "bad" = normalisation changes something meaningful
        orig_g = (c["given_name"] or "").strip()
        orig_f = (c["family_name"] or "").strip()
        c["is_bad"] = (ng != orig_g) or (nf != orig_f and nf != orig_f)
        councillors.append(c)
    return councillors


def load_vote_stats(conn: sqlite3.Connection) -> tuple[dict[int, int], dict[int, int]]:
    """Return (votes_total, votes_2024) keyed by councillor_id."""
    total: dict[int, int] = {}
    y2024: dict[int, int] = {}

    rows = conn.execute("""
        SELECT v.councillor_id,
               COUNT(v.id),
               SUM(CASE WHEN strftime('%Y', m.meeting_date) >= '2024' THEN 1 ELSE 0 END)
        FROM votes v
        JOIN motions mo ON v.motion_id = mo.id
        JOIN meetings m  ON mo.meeting_id = m.id
        GROUP BY v.councillor_id
    """).fetchall()
    for cid, tot, y24 in rows:
        total[cid] = tot or 0
        y2024[cid] = y24 or 0
    return total, y2024


def load_terms(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    """Return councillor_terms keyed by councillor_id."""
    # source/notes columns may not exist in older DBs
    cols = {row[1] for row in conn.execute("PRAGMA table_info(councillor_terms)")}
    extra = ", source, notes" if "source" in cols else ""
    rows = conn.execute(
        f"SELECT councillor_id, term_start, term_end{extra} FROM councillor_terms"
    ).fetchall()
    out: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        cid = row[0]
        out[cid].append({"term_start": row[1], "term_end": row[2]})
    return dict(out)


def load_vote_dates(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """Return (first_vote_date, last_vote_date) keyed by councillor_id."""
    rows = conn.execute("""
        SELECT v.councillor_id, MIN(m.meeting_date), MAX(m.meeting_date)
        FROM votes v
        JOIN motions mo ON v.motion_id = mo.id
        JOIN meetings m ON mo.meeting_id = m.id
        GROUP BY v.councillor_id
    """).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def check_term_coverage(
    stub_first: str | None,
    stub_last: str | None,
    candidate_terms: list[dict],
) -> str:
    """
    Return 'confirmed', 'conflict', or 'no_terms'.

    'confirmed'  — stub's vote span overlaps with at least one candidate term.
    'conflict'   — stub's vote span falls entirely outside all candidate terms.
    'no_terms'   — candidate has no term records; can't evaluate.

    A 6-month buffer is applied to term boundaries to account for the
    approximation in dates derived from vote records.
    """
    if not candidate_terms:
        return "no_terms"
    if not stub_first or not stub_last:
        return "no_terms"

    try:
        s_start = date.fromisoformat(stub_first)
        s_end = date.fromisoformat(stub_last)
    except ValueError:
        return "no_terms"

    buffer = timedelta(days=183)  # ~6 months

    for term in candidate_terms:
        ts_raw = term.get("term_start")
        te_raw = term.get("term_end")

        ts = (date.fromisoformat(ts_raw) - buffer) if ts_raw else date(1900, 1, 1)
        te = (date.fromisoformat(te_raw) + buffer) if te_raw else date.today()

        # Overlap: stub span intersects term span
        if s_start <= te and s_end >= ts:
            return "confirmed"

    return "conflict"


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def find_target(
    c: dict,
    by_family: dict[str, list[dict]],
    votes_2024: dict[int, int],
    already_merging: set[int],
    terms: dict[int, list[dict]] | None = None,
    vote_dates: dict[int, tuple[str, str]] | None = None,
) -> tuple[dict | None, str]:
    """Return (target_record, reason) for merging c into, or (None, reason) to skip/in-place."""
    family_key = c["norm_family"].lower()
    norm_given = c["norm_given"]
    norm_slug = c["norm_slug"]

    # Treat placeholder given names (e.g. "Not named", "unspecified", "Given_name")
    # as family-only — normalise_name() keeps them intact but they're not real names.
    if norm_given and not is_real_given(norm_given):
        norm_given = ""
        norm_slug = make_slug("", c["norm_family"])

    group = [
        x for x in by_family.get(family_key, [])
        if x["id"] != c["id"] and x["id"] not in already_merging
    ]

    # 1. If normalization produced a real given name, look for exact slug match.
    if norm_given:
        for x in group:
            if x["slug"] == norm_slug:
                return x, f"norm-slug-match → '{x['given_name']} {x['family_name']}'"
        return None, f"normalize-in-place (no '{norm_slug}' record exists yet)"

    # Normalized to family-only.  Find real-name candidates.
    real = [x for x in group if is_real_given(x["norm_given"] or x["given_name"])]

    if not real:
        return None, "no-real-candidate — normalize in place"

    if len(real) == 1:
        t = real[0]
        return t, f"single-canonical → '{t['given_name']} {t['family_name']}'"

    # Multiple candidates — prefer those with confirmed term records (electoral
    # commission data) to narrow ambiguity before falling through to vote tiebreak.
    # Terms are the authoritative provenance source; vote counts are NOT used here
    # because pre-2024 councillors may have 0 extracted votes yet be entirely real.
    if terms is not None and len(real) > 1:
        term_backed = [x for x in real if terms.get(x["id"])]
        if 0 < len(term_backed) < len(real):
            real = term_backed

    if len(real) == 1:
        t = real[0]
        return t, f"single-term-backed → '{t['given_name']} {t['family_name']}'"

    # Multiple real names — try to narrow using term overlap before vote tiebreak.
    if terms is not None and vote_dates is not None:
        stub_dates = vote_dates.get(c["id"])
        if stub_dates:
            term_confirmed = [
                x for x in real
                if check_term_coverage(stub_dates[0], stub_dates[1], terms.get(x["id"], [])) == "confirmed"
            ]
            if len(term_confirmed) == 1:
                t = term_confirmed[0]
                return t, f"term-match → '{t['given_name']} {t['family_name']}'"
            elif len(term_confirmed) > 1:
                real = term_confirmed  # narrowed set; fall through to vote tiebreak

    # Multiple candidates remaining — pick the one with most 2024+ votes.
    scored = sorted(real, key=lambda x: -votes_2024.get(x["id"], 0))
    top_count = votes_2024.get(scored[0]["id"], 0)
    runner_up = votes_2024.get(scored[1]["id"], 0) if len(scored) > 1 else 0

    if top_count > 0 and top_count >= runner_up * 2:
        t = scored[0]
        return t, (
            f"2024-votes-winner ({top_count} vs {runner_up}) → "
            f"'{t['given_name']} {t['family_name']}'"
        )

    names = ", ".join(f"'{x['given_name']} {x['family_name']}' ({votes_2024.get(x['id'],0)}v)"
                      for x in scored[:4])
    return None, f"ambiguous — {names}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(apply: bool = False, use_terms: bool = False) -> None:
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL")

    councillors = load_councillors(conn)
    votes_total, votes_2024 = load_vote_stats(conn)
    # Always load terms — used for disambiguation in all passes, not just annotation
    terms = load_terms(conn)
    vote_dates = load_vote_dates(conn)

    # Group by normalised family name
    by_family: dict[str, list[dict]] = defaultdict(list)
    for c in councillors:
        fk = (c["norm_family"] or c["family_name"] or "").lower()
        if fk:
            by_family[fk].append(c)

    # -------------------------------------------------------------------
    # Pass 1: bad records (title/placeholder/swapped/self-repeat given names)
    # -------------------------------------------------------------------
    merges: list[tuple[dict, dict, str]] = []   # (bad, target, reason)
    in_place: list[tuple[dict, str, str, str]] = []  # (c, new_given, new_family, new_slug)
    skipped: list[tuple[dict, str]] = []

    merging_ids: set[int] = set()

    bad_records = [c for c in councillors if c["is_bad"]]
    for c in bad_records:
        target, reason = find_target(c, by_family, votes_2024, merging_ids, terms, vote_dates)
        if target:
            merges.append((c, target, reason))
            merging_ids.add(c["id"])
        elif "normalize-in-place" in reason or "no-real-candidate" in reason:
            new_slug = c["norm_slug"]
            # Check if the normalised slug already exists (another record)
            existing = next(
                (x for x in councillors
                 if x["slug"] == new_slug and x["id"] != c["id"] and x["id"] not in merging_ids),
                None,
            )
            if existing:
                merges.append((c, existing, f"norm-slug-exists → '{existing['given_name']} {existing['family_name']}'"))
                merging_ids.add(c["id"])
            else:
                in_place.append((c, c["norm_given"], c["norm_family"], new_slug))
        else:
            skipped.append((c, reason))

    # -------------------------------------------------------------------
    # Pass 2: family-only stubs (not themselves "bad", but empty given_name)
    # -------------------------------------------------------------------
    family_only = [
        c for c in councillors
        if not c["is_bad"] and not is_real_given(c["given_name"]) and c["id"] not in merging_ids
    ]
    for c in family_only:
        target, reason = find_target(c, by_family, votes_2024, merging_ids, terms, vote_dates)
        if target:
            merges.append((c, target, f"[stub] {reason}"))
            merging_ids.add(c["id"])
        else:
            skipped.append((c, f"[stub] {reason}"))

    # -------------------------------------------------------------------
    # Pass 3: fuzzy family-name stubs (misspellings like "Timmermans" →
    # "Timmermanis", "Pelcar" → "Pelczar").  Only attempts stubs that
    # landed in "no-real-candidate" — i.e. exact family-name lookup found
    # nothing — and uses term overlap to confirm the match.
    # -------------------------------------------------------------------
    still_skipped: list[tuple[dict, str]] = []
    for c, reason in skipped:
        if "no-real-candidate" not in reason:
            still_skipped.append((c, reason))
            continue
        fk = (c["norm_family"] or "").lower()
        if not fk:
            still_skipped.append((c, reason))
            continue

        # Find real-name councillors whose family name is similar.
        # Prefer evidenced candidates (has term records or non-zero total votes)
        # to filter out LLM-hallucinated names.
        candidates: list[tuple[dict, float]] = []
        for other_fk, group in by_family.items():
            if other_fk == fk:
                continue
            sim = SequenceMatcher(None, fk, other_fk).ratio()
            if sim < _FUZZY_THRESHOLD:
                continue
            for x in group:
                if x["id"] in merging_ids:
                    continue
                if is_real_given(x["norm_given"] or x["given_name"]):
                    candidates.append((x, sim))

        # Prefer candidates with confirmed term records (authoritative provenance)
        if candidates:
            term_backed_cands = [
                (x, sim) for x, sim in candidates if terms.get(x["id"])
            ]
            if 0 < len(term_backed_cands) < len(candidates):
                candidates = term_backed_cands

        if not candidates:
            still_skipped.append((c, reason))
            continue

        # Among candidates, prefer term-confirmed match
        stub_dates = vote_dates.get(c["id"])
        confirmed = [
            (x, sim) for x, sim in candidates
            if stub_dates and check_term_coverage(
                stub_dates[0], stub_dates[1], terms.get(x["id"], [])
            ) == "confirmed"
        ]

        if len(confirmed) == 1:
            t, sim = confirmed[0]
            merges.append((
                c, t,
                f"[stub] fuzzy-family ({fk}→{t['norm_family']}, {sim:.0%}) + term-match"
                f" → '{t['given_name']} {t['family_name']}'",
            ))
            merging_ids.add(c["id"])
        elif len(candidates) == 1:
            t, sim = candidates[0]
            if terms.get(t["id"]):
                # Single term-backed candidate — authoritative enough to merge
                merges.append((
                    c, t,
                    f"[stub] fuzzy-family ({fk}→{t['norm_family']}, {sim:.0%}) + term-backed"
                    f" → '{t['given_name']} {t['family_name']}'",
                ))
                merging_ids.add(c["id"])
            else:
                still_skipped.append((
                    c,
                    f"[stub] fuzzy-family ({fk}→{t['norm_family']}, {sim:.0%})"
                    f" → '{t['given_name']} {t['family_name']}' [no term data to confirm]",
                ))
        else:
            names = ", ".join(
                f"'{x['given_name']} {x['family_name']}' ({sim:.0%})"
                for x, sim in candidates[:4]
            )
            still_skipped.append((c, f"[stub] fuzzy-family ambiguous — {names}"))

    skipped = still_skipped

    # -------------------------------------------------------------------
    # Term annotation — always computed; affects --apply behaviour only
    # when --use-terms is set
    # -------------------------------------------------------------------
    TERM_SYMBOLS = {"confirmed": "TERM ✓", "conflict": "TERM ✗", "no_terms": "TERM ?"}

    annotated: list[tuple[dict, dict, str, str]] = []
    for bad, tgt, reason in merges:
        stub_dates = vote_dates.get(bad["id"])
        coverage = check_term_coverage(
            stub_dates[0] if stub_dates else None,
            stub_dates[1] if stub_dates else None,
            terms.get(tgt["id"], []),
        )
        annotated.append((bad, tgt, reason, coverage))

    # With --use-terms --apply: only TERM ✓ merges run automatically; others held
    # Without --use-terms: all planned merges run (annotation is informational only)
    if use_terms:
        auto = [(b, t, r, s) for b, t, r, s in annotated if s == "confirmed"]
        held = [(b, t, r, s) for b, t, r, s in annotated if s != "confirmed"]
    else:
        auto = annotated
        held = []

    # -------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------
    def _label(c: dict) -> str:
        g = c["given_name"] or ""
        f = c["family_name"] or ""
        v = votes_total.get(c["id"], 0)
        v24 = votes_2024.get(c["id"], 0)
        return f"'{g} {f}'.strip() [id={c['id']}, votes={v}, 2024+={v24}]"

    mode = "DRY RUN" if not apply else "APPLYING"
    conservative_note = " (conservative: TERM ✓ only)" if use_terms else ""
    print(f"\n{'='*70}")
    print(f"Councillor Dedup Report  ({mode}{conservative_note})")
    print(f"{'='*70}")
    print(f"Total councillors : {len(councillors)}")
    print(f"Bad records       : {len(bad_records)}")
    print(f"Family-only stubs : {len(family_only)}")
    print(f"Merges planned    : {len(auto)}")
    if held:
        print(f"Held for review   : {len(held)}")
    print(f"In-place fixes    : {len(in_place)}")
    print(f"Skipped/ambiguous : {len(skipped)}")
    n_terms = sum(1 for v in terms.values() if v)
    print(f"Term records      : {sum(len(v) for v in terms.values())} terms / {n_terms} councillors")

    print(f"\n--- Merges ({len(auto)}) ---")
    for bad, tgt, reason, term_status in auto:
        print(f"  [{bad['id']}→{tgt['id']}]  {_label(bad)}  →  {_label(tgt)}")
        suffix = f"  [{TERM_SYMBOLS[term_status]}]" if use_terms else ""
        print(f"           reason: {reason}{suffix}")

    if held:
        print(f"\n--- Held — term validation needed ({len(held)}) ---")
        for bad, tgt, reason, term_status in held:
            print(f"  [{bad['id']}→{tgt['id']}]  {_label(bad)}  →  {_label(tgt)}")
            stub_dates = vote_dates.get(bad["id"])
            date_span = f"{stub_dates[0]} → {stub_dates[1]}" if stub_dates else "unknown"
            cand_terms = terms.get(tgt["id"], [])
            term_spans = (
                ", ".join(f"{t['term_start'] or '?'} → {t['term_end'] or 'present'}"
                          for t in cand_terms)
                if cand_terms else "no term records"
            )
            print(f"           reason: {reason}  [{TERM_SYMBOLS[term_status]}]")
            print(f"           stub votes: {date_span}  |  candidate terms: {term_spans}")

    if in_place:
        print(f"\n--- In-place normalisations ({len(in_place)}) ---")
        for c, ng, nf, ns in in_place:
            print(f"  [{c['id']}]  '{c['given_name']} {c['family_name']}'  →  '{ng} {nf}'  (slug: {ns})")

    if skipped:
        print(f"\n--- Skipped / ambiguous ({len(skipped)}) ---")
        for c, reason in skipped:
            print(f"  [{c['id']}]  {_label(c)}  —  {reason}")

    if not apply:
        print(f"\n[DRY RUN]  Pass --apply to write changes.\n")
        return

    # -------------------------------------------------------------------
    # Apply — only auto-confirmed merges when --use-terms is active
    # -------------------------------------------------------------------
    merges_to_apply = [(b, t, r) for b, t, r, _ in auto]
    print(f"\nApplying {len(merges_to_apply)} merges + {len(in_place)} in-place fixes …")

    for bad, tgt, _ in merges_to_apply:
        bad_id = tgt_id = bad["id"], tgt["id"]
        bad_id, tgt_id = bad["id"], tgt["id"]

        for table, col in FK_COLUMNS:
            if table == "votes" and col == "councillor_id":
                # Delete duplicate votes before remapping to avoid UNIQUE(motion_id, councillor_id)
                conn.execute(f"""
                    DELETE FROM votes
                    WHERE councillor_id = ?
                      AND motion_id IN (
                          SELECT motion_id FROM votes WHERE councillor_id = ?
                      )
                """, (bad_id, tgt_id))
                conn.execute(
                    "UPDATE votes SET councillor_id = ? WHERE councillor_id = ?",
                    (tgt_id, bad_id),
                )
            else:
                conn.execute(
                    f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                    (tgt_id, bad_id),
                )

        conn.execute("DELETE FROM councillors WHERE id = ?", (bad_id,))

    for c, ng, nf, ns in in_place:
        # If the target slug already exists (race condition), merge instead
        existing = conn.execute(
            "SELECT id FROM councillors WHERE slug = ? AND id != ?", (ns, c["id"])
        ).fetchone()
        if existing:
            tgt_id = existing[0]
            for table, col in FK_COLUMNS:
                if table == "votes" and col == "councillor_id":
                    conn.execute(f"""
                        DELETE FROM votes
                        WHERE councillor_id = ?
                          AND motion_id IN (SELECT motion_id FROM votes WHERE councillor_id = ?)
                    """, (c["id"], tgt_id))
                    conn.execute(
                        "UPDATE votes SET councillor_id = ? WHERE councillor_id = ?",
                        (tgt_id, c["id"]),
                    )
                else:
                    conn.execute(
                        f"UPDATE {table} SET {col} = ? WHERE {col} = ?",
                        (tgt_id, c["id"]),
                    )
            conn.execute("DELETE FROM councillors WHERE id = ?", (c["id"],))
        else:
            conn.execute(
                "UPDATE councillors SET given_name = ?, family_name = ?, slug = ? WHERE id = ?",
                (ng, nf, ns, c["id"]),
            )

    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM councillors").fetchone()[0]
    print(f"Done.  Councillors: {len(councillors)} → {after}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate councillor records in council.db")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument(
        "--use-terms",
        action="store_true",
        dest="use_terms",
        help="Annotate merges with councillor_terms coverage; with --apply, only apply TERM ✓ merges",
    )
    args = parser.parse_args()
    run(apply=args.apply, use_terms=args.use_terms)


if __name__ == "__main__":
    main()
