"""
One-time deduplication migration for the councillors table.

The extraction pipeline historically created duplicate records when the LLM outputs
names in different formats ("Cr Barlow", "Kate Barlow", "Barlow", "null Barlow",
"Barlow Cr" etc.).  This script finds, reports, and merges those duplicates.

Five passes:
  Pass 1 — Bad records: given_name is a title, placeholder, self-repeat, or the
            fields are swapped with a TITLE (family_name is the title).  These
            are unambiguously wrong and are merged into the canonical for their
            family name.
  Pass 2 — Family-only stubs: given_name is empty/null but a real-name canonical
            exists for the same family name.  Merged when unambiguous.
  Pass 3 — Fuzzy family-name stubs: family name is a near-misspelling of a real
            councillor's name (e.g. "Timmermans" → "Timmermanis", "Pelcar" →
            "Pelczar").  Resolved using term overlap; reported for review otherwise.
  Pass 4 — Given/family field swap between TWO records (e.g. "Colin Walker" vs
            "Walker Colin" — two REAL name tokens transposed across two distinct
            rows, not one bad record with a title in the wrong field, which Pass 1
            already handles). Detected by exact transposition; auto-merged only
            when one side has zero rows in every other councillor-keyed table
            (a confirmed phantom), else held for review. See
            docs/pipeline/PIPELINE.md "Known dedup gaps" for the incident (Colin
            Walker/Walker Colin, found 2026-08-22 during a Refiner session) this
            pass was written to generalise and catch automatically next time.
  Pass 5 — Orphan single-token stubs (given_name empty AND family_name matches
            no known family, e.g. a bare "Gary" with no last name captured at
            all — not even a swap candidate, since Pass 4 requires both fields
            populated). Resolved system-wide (not scoped to a family group) by
            requiring a real-named candidate's interest_declarations to cover
            EVERY one of the stub's (meeting, item_reference) keys, not just
            one — a single shared key is common on a busy agenda item where
            several councillors independently declare on the same item, but
            covering the stub's entire declaration set is not. Also requires
            the stub's fragment to be a literal name token of the candidate
            (catches the case where full coverage is coincidental — e.g. a
            council staff member's declaration text sharing an agenda item
            with an unrelated councillor, not the same declaration extracted
            twice). Auto-merged only when exactly one candidate qualifies and
            the stub itself has zero votes/terms (no competing identity
            evidence); else held. See
            docs/pipeline/PIPELINE.md "Known dedup gaps" for the incident
            (councillor_id=173 "Gary" → Gary Mack, found 2026-08-23 during a
            live Conductor-loop Editor pass) this pass generalises.

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


def load_motion_sets(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """Return the set of motion_ids each councillor cast a vote on, keyed by id.

    Used as a gold-standard identity signal: a real person can cast at most one
    vote per motion, so two records that *never* share a motion can be the same
    person, whereas any shared motion proves they are distinct people.
    """
    out: dict[int, set[int]] = defaultdict(set)
    for cid, mid in conn.execute("SELECT councillor_id, motion_id FROM votes"):
        out[cid].add(mid)
    return dict(out)


def vote_spans_overlap(
    a_dates: tuple[str, str] | None,
    b_dates: tuple[str, str] | None,
) -> bool:
    """True if two (first, last) vote-date spans overlap (6-month buffer)."""
    if not a_dates or not b_dates:
        return False
    try:
        a0, a1 = date.fromisoformat(a_dates[0]), date.fromisoformat(a_dates[1])
        b0, b1 = date.fromisoformat(b_dates[0]), date.fromisoformat(b_dates[1])
    except (ValueError, TypeError):
        return False
    buf = timedelta(days=183)
    return a0 - buf <= b1 and a1 + buf >= b0


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
    motion_sets: dict[int, set[int]] | None = None,
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

    # Vote-evidence disambiguation (gold standard).  A real person casts at most
    # one vote per motion, so the true match is a candidate who (a) actually
    # appears in the vote record, (b) never shares a motion with the stub, and
    # (c) has an overlapping vote-date span.  This separates an active councillor
    # (e.g. "Ian Everett", 97 votes) from phantom same-surname records that have
    # no votes and no terms (e.g. "Julian/Graham/Rod Everett") — cases the term
    # and 2024-vote tiebreaks below cannot resolve.
    if motion_sets is not None and vote_dates is not None and len(real) > 1:
        stub_motions = motion_sets.get(c["id"], set())
        stub_dates = vote_dates.get(c["id"])
        evidenced = [
            x for x in real
            if motion_sets.get(x["id"])  # candidate has real votes
            and not (motion_sets.get(x["id"], set()) & stub_motions)  # no collision
            and vote_spans_overlap(stub_dates, vote_dates.get(x["id"]))
        ]
        if len(evidenced) == 1:
            t = evidenced[0]
            return t, f"vote-evidence (no shared motion, span overlap) → '{t['given_name']} {t['family_name']}'"
        if len(evidenced) > 1:
            # Several vote-bearing candidates pass (often the same real person split
            # again, e.g. "Julian"/"Graham" Everett = stray motions of Ian Everett).
            # Merge into the dominant one only when it clearly outweighs the rest
            # (>=2x runner-up); genuinely co-serving namesakes have comparable
            # histories and stay ambiguous.
            ev = sorted(evidenced, key=lambda x: -len(motion_sets.get(x["id"], set())))
            top = len(motion_sets.get(ev[0]["id"], set()))
            runner = len(motion_sets.get(ev[1]["id"], set()))
            if top >= 2 * max(runner, 1):
                t = ev[0]
                return t, (f"vote-evidence dominant ({top} vs {runner} votes, no shared motion) "
                           f"→ '{t['given_name']} {t['family_name']}'")

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
    motion_sets = load_motion_sets(conn)

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
        target, reason = find_target(c, by_family, votes_2024, merging_ids, terms, vote_dates, motion_sets)
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
        target, reason = find_target(c, by_family, votes_2024, merging_ids, terms, vote_dates, motion_sets)
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
    # Pass 4: given/family-name field swap between two distinct records
    # (e.g. "Colin Walker" id=246 vs "Walker Colin" id=385) — a structural
    # blind spot Passes 1-3 above cannot catch: no title/placeholder is
    # involved (Pass 1's trigger), both fields are populated with real
    # tokens (Pass 2 needs an empty given_name), and the family names
    # aren't a fuzzy misspelling of each other (Pass 3's threshold).
    # Detected by exact transposition — cheap, one hash-map pass, no fuzzy
    # matching, near-zero false-positive risk on an exact swap.
    #
    # Three independent ways to confirm which side is the phantom, tried
    # in order, ANY of which auto-merges — not a single all-or-nothing
    # threshold:
    #   Tier 1 — one side has zero rows in every OTHER councillor-keyed
    #     table. The original check.
    #   Tier 2 — neither side is zero, but they never share a motion (the
    #     same gold-standard, no-fan-out disambiguation signal Passes 1-3
    #     already trust elsewhere in this script — votes carries
    #     UNIQUE(motion_id, councillor_id), so two records that ever
    #     BOTH voted on the same motion cannot be the same real person,
    #     making "no shared motion" a genuine, checkable fact, not an
    #     assumption) AND one side's activity is small in absolute terms
    #     AND dominated by a wide margin. Added 2026-08-23 after a live
    #     Conductor-loop run found this exact evidence (no shared motion,
    #     overlapping vote-date spans) already being gathered by hand,
    #     for pairs the original zero-only check couldn't resolve because
    #     the "phantom" side had 1-3 stray rows, not exactly zero.
    #   Tier 3 — neither side is zero and Tier 2's dominance margin isn't
    #     met (this is what a 1-vs-1 pair like a duplicate-declaration
    #     case looks like — dominance is meaningless when both sides are
    #     equally small), but both sides declared an interest on the
    #     *same* meeting + item_reference — direct evidence of one real
    #     declaration extracted twice under two swapped-name records, not
    #     an identity inference at all.
    # If NONE of the three fire, held for review exactly as before —
    # these tiers only ADD auto-merge paths, they never remove the
    # existing safety net.
    # -------------------------------------------------------------------
    _DOMINANCE_MIN_RATIO = 20  # smaller side's activity times this <= larger side's
    _DOMINANCE_MAX_ABSOLUTE = 10  # smaller side's raw activity count must also be small

    def _raw_key(c: dict) -> tuple[str, str]:
        return (
            (c["given_name"] or "").strip().lower(),
            (c["family_name"] or "").strip().lower(),
        )

    def _identity_activity(cid: int) -> int:
        """Rows in tables that confirm a real, independent identity.
        Excludes `appointments`, which Pass 4 treats as cleanly
        reassignable and never lets block an auto-merge on its own."""
        n = votes_total.get(cid, 0) + len(terms.get(cid, []))
        n += conn.execute(
            "SELECT COUNT(*) FROM motions WHERE moved_by_id=? OR seconded_by_id=?",
            (cid, cid),
        ).fetchone()[0]
        n += conn.execute(
            "SELECT COUNT(*) FROM interest_declarations WHERE councillor_id=?",
            (cid,),
        ).fetchone()[0]
        return n

    def _shares_motion(a_id: int, b_id: int) -> bool:
        """True if the two ever BOTH voted on the same motion — if so,
        they cannot be the same real person (UNIQUE(motion_id,
        councillor_id) on votes), so this is a hard disqualifier for
        Tiers 2 and 3, checked before either regardless of how strong
        the other evidence looks."""
        a_motions = motion_sets.get(a_id, set())
        b_motions = motion_sets.get(b_id, set())
        return bool(a_motions & b_motions)

    def _duplicate_declaration(a_id: int, b_id: int) -> bool:
        """True if the two share an interest_declarations row on the
        same meeting + item_reference — the same real declaration,
        extracted twice under two swapped-name records. Queried per side
        so a shared key requires BOTH ids present, not just two
        declarations from one side landing in the same bucket."""
        a_keys = {
            (m, i) for m, i in conn.execute(
                "SELECT meeting_id, item_reference FROM interest_declarations "
                "WHERE councillor_id=? AND item_reference IS NOT NULL", (a_id,)
            ).fetchall()
        }
        b_keys = {
            (m, i) for m, i in conn.execute(
                "SELECT meeting_id, item_reference FROM interest_declarations "
                "WHERE councillor_id=? AND item_reference IS NOT NULL", (b_id,)
            ).fetchall()
        }
        return bool(a_keys & b_keys)

    by_raw_key: dict[tuple[str, str], dict] = {}
    for c in councillors:
        if c["id"] in merging_ids:
            continue
        g, f = _raw_key(c)
        if g and f and g != f and is_real_given(g) and is_real_given(f):
            by_raw_key.setdefault((g, f), c)  # first record wins any exact dup

    swap_merges: list[tuple[dict, dict, str]] = []
    swap_held: list[tuple[dict, dict, str]] = []
    seen_pairs: set[frozenset] = set()

    for (g, f), c in by_raw_key.items():
        swapped = by_raw_key.get((f, g))
        if not swapped or swapped["id"] == c["id"]:
            continue
        pair_key = frozenset({c["id"], swapped["id"]})
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        a_activity = _identity_activity(c["id"])
        b_activity = _identity_activity(swapped["id"])
        phantom = canonical = None
        tier_reason = ""

        if a_activity == 0 and b_activity > 0:
            phantom, canonical = c, swapped
            tier_reason = "phantom had 0 identity rows"
        elif b_activity == 0 and a_activity > 0:
            phantom, canonical = swapped, c
            tier_reason = "phantom had 0 identity rows"
        elif _shares_motion(c["id"], swapped["id"]):
            # Hard disqualifier: they voted on the same motion at least
            # once, so they are provably two different real people
            # regardless of any other evidence. Never merge; say why.
            swap_held.append((
                c, swapped,
                f"field-swap, but both sides voted on at least one SHARED motion "
                f"({a_activity} vs {b_activity} activity rows) — provably two "
                f"different people despite the swapped-looking names, do not merge",
            ))
            continue
        else:
            lo, hi = sorted((a_activity, b_activity))
            if lo > 0 and lo <= _DOMINANCE_MAX_ABSOLUTE and hi >= lo * _DOMINANCE_MIN_RATIO:
                phantom, canonical = (c, swapped) if a_activity < b_activity else (swapped, c)
                tier_reason = (
                    f"no shared motion, dominance {hi}:{lo} "
                    f"(>= {_DOMINANCE_MIN_RATIO}:1, phantom side <= {_DOMINANCE_MAX_ABSOLUTE} rows)"
                )
            elif _duplicate_declaration(c["id"], swapped["id"]):
                # Dominance alone can't pick a direction when both sides
                # are equally small (e.g. 1 vs 1) -- the duplicate
                # declaration doesn't imply one either, so default to the
                # lower-id record as canonical (arbitrary but stable) and
                # say so plainly rather than pretend it's evidence-based.
                phantom, canonical = (swapped, c) if c["id"] < swapped["id"] else (c, swapped)
                tier_reason = (
                    "no shared motion, matching interest_declarations on the same "
                    "meeting+item_reference (duplicate declaration, not an identity "
                    "inference) — direction chosen arbitrarily (lower id kept), not by evidence"
                )
            else:
                swap_held.append((
                    c, swapped,
                    f"field-swap, both sides have identity activity ({a_activity} vs "
                    f"{b_activity} rows), no shared motion but neither dominance nor a "
                    f"duplicate declaration confirms a direction — needs manual review",
                ))
                continue

        swap_merges.append((
            phantom, canonical,
            f"field-swap (given↔family of '{canonical['given_name']} {canonical['family_name']}') "
            f"→ '{canonical['given_name']} {canonical['family_name']}' [{tier_reason}]",
        ))
        merging_ids.add(phantom["id"])

    # -------------------------------------------------------------------
    # Pass 5: orphan single-token stubs — given_name empty AND family_name
    # doesn't match any real-named candidate's family (so Pass 2 already
    # tried and failed via "no-real-candidate", and Pass 4 never considered
    # it since a field swap needs both fields populated). The only
    # remaining evidence is interest_declarations content: if a real-named
    # candidate's declarations cover the stub's ENTIRE key set (every
    # (meeting_id, item_reference) pair the stub declared on, not just
    # one — a lone shared key is unremarkable on a busy agenda item with
    # several independent declarants), that's strong evidence the stub is
    # the same declaration extracted twice under a fragment name. Scoped
    # to stubs with zero votes/terms so this only fires when no other
    # identity signal exists to contradict or confirm it.
    # -------------------------------------------------------------------
    def _declaration_keys(cid: int) -> set[tuple[int, str]]:
        return {
            (m, i) for m, i in conn.execute(
                "SELECT meeting_id, item_reference FROM interest_declarations "
                "WHERE councillor_id=? AND item_reference IS NOT NULL", (cid,)
            ).fetchall()
        }

    dup_decl_merges: list[tuple[dict, dict, str]] = []
    dup_decl_held: list[tuple[dict, str]] = []

    still_skipped2: list[tuple[dict, str]] = []
    for c, reason in skipped:
        is_orphan = (
            "no-real-candidate" in reason
            and not is_real_given(c["given_name"])
            and c["id"] not in merging_ids
            and votes_total.get(c["id"], 0) == 0
            and not terms.get(c["id"])
        )
        if not is_orphan:
            still_skipped2.append((c, reason))
            continue

        stub_keys = _declaration_keys(c["id"])
        if not stub_keys:
            still_skipped2.append((c, reason))
            continue

        stub_token = (c["norm_family"] or c["family_name"] or "").strip().lower()

        def _name_tokens(x: dict) -> set[str]:
            return {
                t.lower() for t in
                f"{x['given_name'] or ''} {x['family_name'] or ''}".split()
            }

        covering = [
            x for x in councillors
            if x["id"] != c["id"]
            and x["id"] not in merging_ids
            and is_real_given(x["norm_given"] or x["given_name"])
            and stub_token in _name_tokens(x)
            and stub_keys <= _declaration_keys(x["id"])
        ]

        if len(covering) == 1:
            t = covering[0]
            dup_decl_merges.append((
                c, t,
                f"[Pass 5] orphan stub, candidate's declarations cover all "
                f"{len(stub_keys)} of the stub's (meeting, item) keys "
                f"→ '{t['given_name']} {t['family_name']}'",
            ))
            merging_ids.add(c["id"])
        elif len(covering) > 1:
            names = ", ".join(f"'{x['given_name']} {x['family_name']}'" for x in covering[:4])
            dup_decl_held.append((c, f"[Pass 5] multiple candidates cover all declaration keys — {names}"))
        else:
            key_only = [
                x for x in councillors
                if x["id"] != c["id"]
                and x["id"] not in merging_ids
                and is_real_given(x["norm_given"] or x["given_name"])
                and stub_keys <= _declaration_keys(x["id"])
            ]
            if key_only:
                names = ", ".join(f"'{x['given_name']} {x['family_name']}'" for x in key_only[:4])
                dup_decl_held.append((
                    c,
                    f"[Pass 5] key coverage found but not lexically plausible "
                    f"(fragment '{stub_token}' isn't a name token of the candidate) — {names}",
                ))
            else:
                dup_decl_held.append((c, "[Pass 5] no candidate covers the full declaration key set"))

    skipped = still_skipped2

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
    print(f"Field-swap pairs  : {len(swap_merges) + len(swap_held)}")
    print(f"Orphan stubs      : {len(dup_decl_merges) + len(dup_decl_held)}")
    print(f"Merges planned    : {len(auto) + len(swap_merges) + len(dup_decl_merges)}")
    if held:
        print(f"Held for review   : {len(held)}")
    if swap_held:
        print(f"Held (field-swap) : {len(swap_held)}")
    if dup_decl_held:
        print(f"Held (orphan)     : {len(dup_decl_held)}")
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

    if swap_merges:
        print(f"\n--- Field-swap merges, Pass 4 ({len(swap_merges)}) ---")
        for bad, tgt, reason in swap_merges:
            print(f"  [{bad['id']}→{tgt['id']}]  {_label(bad)}  →  {_label(tgt)}")
            print(f"           reason: {reason}")

    if swap_held:
        print(f"\n--- Held — field-swap, needs review ({len(swap_held)}) ---")
        for a, b, reason in swap_held:
            print(f"  [{a['id']} ↔ {b['id']}]  {_label(a)}  ↔  {_label(b)}")
            print(f"           reason: {reason}")

    if dup_decl_merges:
        print(f"\n--- Orphan-stub merges, Pass 5 ({len(dup_decl_merges)}) ---")
        for bad, tgt, reason in dup_decl_merges:
            print(f"  [{bad['id']}→{tgt['id']}]  {_label(bad)}  →  {_label(tgt)}")
            print(f"           reason: {reason}")

    if dup_decl_held:
        print(f"\n--- Held — orphan stub, needs review ({len(dup_decl_held)}) ---")
        for c, reason in dup_decl_held:
            print(f"  [{c['id']}]  {_label(c)}  —  {reason}")

    if in_place:
        print(f"\n--- In-place normalisations ({len(in_place)}) ---")
        for c, ng, nf, ns in in_place:
            print(f"  [{c['id']}]  '{c['given_name']} {c['family_name']}'  →  '{ng} {nf}'  (slug: {ns})")

    if skipped:
        print(f"\n--- Skipped / ambiguous ({len(skipped)}) ---")
        for c, reason in skipped:
            print(f"  [{c['id']}]  {_label(c)}  —  {reason}")

    if not apply:
        print("\n[DRY RUN]  Pass --apply to write changes.\n")
        return

    # -------------------------------------------------------------------
    # Apply — only auto-confirmed merges when --use-terms is active
    # -------------------------------------------------------------------
    merges_to_apply = [(b, t, r) for b, t, r, _ in auto] + swap_merges + dup_decl_merges
    print(f"\nApplying {len(merges_to_apply)} merges + {len(in_place)} in-place fixes …")

    for bad, tgt, _ in merges_to_apply:
        bad_id = tgt_id = bad["id"], tgt["id"]
        bad_id, tgt_id = bad["id"], tgt["id"]

        for table, col in FK_COLUMNS:
            if table == "votes" and col == "councillor_id":
                # Delete duplicate votes before remapping to avoid UNIQUE(motion_id, councillor_id)
                conn.execute("""
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
                    conn.execute("""
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
