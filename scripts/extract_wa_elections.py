"""
Extract WA council election results from Elections WA statewide PDFs.
Outputs a CSV suitable for: council import-terms <council> <file> --apply

Usage: python scripts/extract_wa_elections.py <council-key> [output_csv]
  council-key must be a key in COUNCIL_CONFIGS below.

Generalised from the original Cambridge-only extract_cambridge_elections.py
(SECOND_COUNCIL_PLAN.md 5.3 — the point flagged for parameterising rather
than copy-pasting a third per-council script). Adding a new WA council is:
find its section in each statewide PDF (search "COUNCIL NAME" in caps
across pages, per PIPELINE.md's "Council Setup: Terms Seeding"), work out
its ward/role heading names, and add one COUNCIL_CONFIGS entry — no new
parsing code.
"""

import csv
import io
import re
import sys
import urllib.request

import pdfplumber

BASE = "https://www.elections.wa.gov.au"

# ---------------------------------------------------------------------------
# Per-council configuration
# ---------------------------------------------------------------------------
#
# "header": the literal ALL-CAPS line that opens the council's own section
#   in a statewide report (e.g. "TOWN OF CAMBRIDGE") — parsing starts after
#   this line and stops at the next "CITY|SHIRE|TOWN|DISTRICT OF ..." line,
#   so a report page that also carries other councils' results (common —
#   sections don't reliably start on a fresh page) doesn't leak into this
#   council's rows.
# "ward_aliases": {heading text: (ward_label, role_label)} for every
#   section-heading string found in that council's own results across all
#   years. Matching is case-sensitive against the given form AND its
#   upper() form (`line == key or line == key.upper()`) — so one mixed-case
#   entry like "Lord Mayor" also matches an all-caps "LORD MAYOR" heading in
#   a later year's report; only add a second entry when a heading appears
#   in a form key.upper() doesn't cover.
# "reports": (year, statewide-PDF url, [0-indexed result pages], election
#   date) — found by hand per PIPELINE.md's "Council Setup: Terms Seeding"
#   (pdfplumber, search "COUNCIL NAME" in caps across pages). Almost always
#   one page; use a list when the section spans a page break (confirmed by
#   checking whether the *next* page continues the same council's own
#   headings before any other "... OF ..." line appears).
# "old_era_years": years using the 1999/2001 report's older column layout
#   ("SURNAME Firstname  votes  pct%  [4 Year Term]", no comma/parens) —
#   everything else uses the 2003+ layout ("SURNAME, Firstname  votes
#   (pct%)  [expiry date]").

COUNCIL_CONFIGS = {
    "cambridge": {
        "header": "TOWN OF CAMBRIDGE",
        "ward_aliases": {
            "MAYOR": ("Mayor", "Mayor"),
            "MAYORAL": ("Mayor", "Mayor"),
            "DEPUTY MAYOR": ("Mayor", "Deputy Mayor"),
            "COAST": ("Coast", "Councillor"),
            "WEMBLEY": ("Wembley", "Councillor"),
            "Coast": ("Coast", "Councillor"),
            "Wembley": ("Wembley", "Councillor"),
            "Mayoral": ("Mayor", "Mayor"),
        },
        "reports": [
            (1999, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_1999.pdf", [66], "1999-05-01"),
            (2001, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2001_App.pdf", [17], "2001-05-05"),
            (2003, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2003_App.pdf", [20], "2003-05-03"),
            (2005, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2005_App.pdf", [24], "2005-05-07"),
            (2007, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2007.pdf", [70], "2007-10-20"),
            (2009, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2009.pdf", [73], "2009-10-17"),
            (2011, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2011.pdf", [64], "2011-10-15"),
            (2013, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2013.pdf", [69], "2013-10-19"),
            (2015, f"{BASE}/sites/default/files/content/2015%20Local%20Government%20Ordinary%20Elections%20Report.pdf", [73], "2015-10-17"),
            # 2017: Cambridge's results page is absent from the statewide PDF — needs a separate source.
            (2019, f"{BASE}/sites/default/files/waec/lg_elections/Reports/2019_LG_Election_Report%20FINAL%20online.pdf", [47], "2019-10-19"),
            (2021, f"{BASE}/sites/default/files/2021_LG_Election_Report%20online%20vf.pdf", [49], "2021-10-16"),
            (2023, f"{BASE}/sites/default/files/LG%202023%20Statewide%20report%20-%20with%20appendices_0.pdf", [201], "2023-10-21"),
        ],
        "old_era_years": {1999, 2001},
        "output_csv": "data/cambridge_elections_raw.csv",
    },
    "perth": {
        "header": "CITY OF PERTH",
        # No sub-wards — Perth elects a Lord Mayor plus an at-large Council.
        # The presiding-member heading is "Lord Mayor"/"LORD MAYOR" in most
        # years and just "MAYOR" in the 2007 report only; both map to the
        # same role — "Lord Mayor" is the formal WA title, unique to Perth
        # among WA local governments (confirmed 2026-09-18 against the 2023
        # report, which elects Basil Zempilas "LORD MAYOR"). The at-large
        # councillor race is headed "Council"/"Councillors" (1999-2001),
        # "PERTH" (2003+), or "DISTRICT" (2007's report only).
        "ward_aliases": {
            "Lord Mayor": ("Perth", "Lord Mayor"),
            "MAYOR": ("Perth", "Lord Mayor"),
            # "MAYORAL" is the 2003 report's own heading for the same race
            # (confirmed 2026-09-18 against that report's page 47 — every
            # other year uses "Lord Mayor"/"LORD MAYOR"/"MAYOR").
            "MAYORAL": ("Perth", "Lord Mayor"),
            "Council": ("Perth", "Councillor"),
            "Councillors": ("Perth", "Councillor"),
            "PERTH": ("Perth", "Councillor"),
            "DISTRICT": ("Perth", "Councillor"),
        },
        # 2005's report repeats "CITY OF PERTH" as the section's own
        # ward-position heading instead of a distinct ward name (confirmed
        # 2026-09-18, page 54) — default_ward means that quirk still lands
        # candidates under "Perth" instead of a blank ward, since Perth has
        # no true wards to fall back on. Left unset for Cambridge (None) so
        # its behaviour is unchanged from the original script — every one
        # of its own headings is a real, recognised ward.
        "default_ward": "Perth",
        "reports": [
            # 1999's own section spans two pages (77-78) — "Lord Mayor" on
            # the first, "Councillors" starting only on the second, unlike
            # every later year where the whole section fits one page.
            (1999, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_1999.pdf", [77, 78], "1999-05-01"),
            (2001, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2001_App.pdf", [38], "2001-05-05"),
            (2003, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2003_App.pdf", [47], "2003-05-03"),
            (2005, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2005_App.pdf", [54], "2005-05-07"),
            (2007, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2007.pdf", [116], "2007-10-20"),
            (2009, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2009.pdf", [122], "2009-10-17"),
            (2011, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2011.pdf", [114], "2011-10-15"),
            (2013, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2013.pdf", [121], "2013-10-19"),
            (2015, f"{BASE}/sites/default/files/content/2015%20Local%20Government%20Ordinary%20Elections%20Report.pdf", [133], "2015-10-17"),
            (2017, f"{BASE}/sites/default/files/2017_LG_Election_Report.pdf", [98], "2017-10-21"),
            # 2019: no ordinary election — the City of Perth was governed by
            # WA state-appointed commissioners from March 2018 to October
            # 2021 (the elected council was dismissed following a state
            # government intervention), so the 2019 statewide report has no
            # City of Perth section at all — confirmed 2026-09-18 (searched
            # every page of the 2019 report for "PERTH"; only "City of
            # South Perth" appears).
            (2021, f"{BASE}/sites/default/files/2021_LG_Election_Report%20online%20vf.pdf", [101], "2021-10-16"),
            (2023, f"{BASE}/sites/default/files/LG%202023%20Statewide%20report%20-%20with%20appendices_0.pdf", [159], "2023-10-21"),
        ],
        "old_era_years": {1999, 2001},
        "output_csv": "data/perth_elections_raw.csv",
    },
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def extract_pages(pdf_bytes: bytes, page_indices: list[int]) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        parts = []
        for i in page_indices:
            text = pdf.pages[i].extract_text() or ""
            parts.append(text)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Name splitting helpers (council-agnostic)
# ---------------------------------------------------------------------------

def _fix_case(s: str) -> str:
    """Title-case a name, preserving Mc/Mac prefixes and hyphens."""
    s = s.strip().title()
    # Fix Mc/Mac prefixes: e.g. Mcaulay → McAulay, Macrae → MacRae
    # Require 2+ chars after prefix to avoid Mack → MacK false positives
    s = re.sub(r"\bMc([a-z])([a-z])", lambda m: "Mc" + m.group(1).upper() + m.group(2), s)
    s = re.sub(r"\bMac([a-z])([a-z])", lambda m: "Mac" + m.group(1).upper() + m.group(2), s)
    # Fix O' prefix: e.g. O'connor → O'Connor
    s = re.sub(r"\bO'([a-z])", lambda m: "O'" + m.group(1).upper(), s)
    return s


def split_name(raw: str) -> tuple[str, str]:
    """Split 'SURNAME, Firstname' or 'SURNAME Firstname' into (given, family)."""
    # Strip any "Elected Unopposed" or trailing date artefacts
    raw = re.split(r"\s+Elected\s+Unopposed", raw, maxsplit=1)[0]
    raw = re.split(r"\s+\d{1,2}\s+\w+\s+\d{4}", raw, maxsplit=1)[0]
    raw = raw.strip()
    if "," in raw:
        parts = raw.split(",", 1)
        family = _fix_case(parts[0].strip())
        given = _fix_case(parts[1].strip())
    else:
        tokens = raw.split()
        if len(tokens) >= 2:
            given = _fix_case(tokens[-1])
            family = _fix_case(" ".join(tokens[:-1]))
        else:
            family = _fix_case(raw)
            given = ""
    return given, family


# ---------------------------------------------------------------------------
# Parsers for different era formats — both take the target council's own
# header text and ward_aliases so no parsing code is per-council.
# ---------------------------------------------------------------------------

def parse_standard(
    text: str, election_date: str, header: str, ward_aliases: dict, default_ward: str = ""
) -> list[dict]:
    """
    Parse the 2003–2023 standard format:
      SURNAME, Firstname  votes (pct%)  [Expiry date]
    or
      SURNAME, Firstname  Elected Unopposed  [Expiry date]
    Sections headed by ward/role names in ALL CAPS (or, some years, mixed
    case — see ward_aliases).
    """
    rows = []
    current_ward = default_ward
    current_role = "Councillor"

    in_target = False
    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Start capturing on the council's own header line. Reset
        # current_ward to default_ward here too, not just at function
        # entry — some reports repeat the council's own name as a stray
        # section heading instead of a real ward name (Perth's 2005 report
        # does this), which would otherwise leave current_ward stuck empty
        # for every candidate line that follows.
        if header in line.upper():
            in_target = True
            current_ward = default_ward
            continue

        # Stop at the next council
        if in_target and re.match(r"^(CITY|SHIRE|TOWN|DISTRICT)\s+OF\s+", line.upper()):
            break

        if not in_target:
            continue

        # Detect section headings. Comparing against key.upper() (not the
        # key as-given) makes this case-insensitive to how a given year's
        # report renders the heading — Cambridge's own keys are already
        # uppercase so this is unchanged for Cambridge; Perth's ward_aliases
        # mixes "Lord Mayor" (1999-era mixed case) and "LORD MAYOR"
        # (2023-era caps) under one entry rather than needing both as
        # separate dict keys.
        upper = line.upper()
        matched_ward = False
        for key, (ward, role) in ward_aliases.items():
            key_upper = key.upper()
            if upper == key_upper or upper.startswith(key_upper + " "):
                current_ward = ward
                current_role = role
                matched_ward = True
                break
        if matched_ward:
            continue

        # Skip summary/header lines
        if any(line.startswith(s) for s in (
            "Candidate", "Total Valid", "Informal", "Total Votes",
            header, "Contents", "Election Report",
            "Be a vocal", "Western Australian", "ELECTION REPORT",
            "continued", "Appendix", "Number of Electors", "Turnout",
            "Valid Votes", "Quota",
        )):
            continue

        # Try to match a candidate line
        # Patterns:
        #   SURNAME, Firstname  1234 (56.78%)  [date]
        #   SURNAME, Firstname  Elected Unopposed  [date]
        #   SURNAME Firstname  1234  56.78%  Elected/4 Year Term  (1999/2001 style)

        # Detect "Elected Unopposed"
        if re.search(r"Elected\s+Unopposed", line, re.IGNORECASE):
            name_part = re.split(r"\s+Elected\s+Unopposed", line, maxsplit=1)[0].strip()
            given, family = split_name(name_part)
            if family:
                rows.append({
                    "election_date": election_date,
                    "ward": current_ward,
                    "role": current_role,
                    "given_name": given,
                    "family_name": family,
                    "elected": "TRUE",
                    "votes": "",
                })
            continue

        # Standard vote line: NAME  NNNN (PP.PP%)  [date]
        m = re.match(
            r"^([A-Z][A-Z\s\-']+(?:,\s*[A-Za-z][A-Za-z\s\-'\.]+)?)"
            r"\s+(\d[\d,]+)\s*\([\d.]+%\)"
            r"(?:\s+([\d]+\s+\w+\s+\d{4}))?",
            line,
        )
        if m:
            name_raw = m.group(1).strip()
            votes = m.group(2).replace(",", "")
            expiry = m.group(3)
            elected = "TRUE" if expiry else "FALSE"
            given, family = split_name(name_raw)
            if family:
                rows.append({
                    "election_date": election_date,
                    "ward": current_ward,
                    "role": current_role,
                    "given_name": given,
                    "family_name": family,
                    "elected": elected,
                    "votes": votes,
                })
            continue

        # 2007-style: NAME  Elected Nth  [date]  — no vote counts
        m2 = re.match(
            r"^([A-Z][A-Z\s\-']+(?:,\s*[A-Za-z][A-Za-z\s\-'\.]+)?)"
            r"\s+Elected\s+\d",
            line,
        )
        if m2:
            name_raw = m2.group(1).strip()
            given, family = split_name(name_raw)
            if family:
                rows.append({
                    "election_date": election_date,
                    "ward": current_ward,
                    "role": current_role,
                    "given_name": given,
                    "family_name": family,
                    "elected": "TRUE",
                    "votes": "",
                })
            continue

        # 2007-style: NAME only (not elected, no expiry)
        m3 = re.match(r"^([A-Z][A-Z\s\-']+(?:,\s*[A-Za-z][A-Za-z\s\-'\.]+)?)$", line)
        if m3 and current_ward:
            name_raw = m3.group(1).strip()
            # filter out section headings that slipped through
            if name_raw.upper() not in {k.upper() for k in ward_aliases} | {
                "CANDIDATE", "TOTAL", "INFORMAL",
            }:
                given, family = split_name(name_raw)
                if family and len(family) > 1:
                    rows.append({
                        "election_date": election_date,
                        "ward": current_ward,
                        "role": current_role,
                        "given_name": given,
                        "family_name": family,
                        "elected": "FALSE",
                        "votes": "",
                    })

    return rows


def parse_old_era(
    text: str, election_date: str, header: str, ward_aliases: dict, default_ward: str = ""
) -> list[dict]:
    """
    Parse 1999/2001 format:
      SURNAME Firstname  votes  pct%  Elected / 4 Year Term
    or
      SURNAME Firstname  Elected Unopposed  4 Year Term

    Gated by the same header-anchor / next-council-stop rule as
    parse_standard() — required so a page whose *tail* runs into the next
    council's own wards (seen in Perth's 1999 two-page section, where
    Perth's own results end mid-page and Shire of Plantagenet's wards
    follow immediately after) doesn't get misattributed to the last ward
    matched here. Cambridge's own 1999/2001 pages happen to end cleanly at
    the council boundary already, so this doesn't change Cambridge's output
    — confirmed by direct comparison against the original script.
    """
    rows = []
    current_ward = default_ward
    current_role = "Councillor"
    in_target = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if header in line.upper():
            in_target = True
            current_ward = default_ward
            continue

        if in_target and re.match(r"^(CITY|SHIRE|TOWN|DISTRICT)\s+OF\s+", line.upper()):
            break

        if not in_target:
            continue

        # Section heading
        matched_ward = False
        for key, (ward, role) in ward_aliases.items():
            if line == key or line == key.upper():
                current_ward = ward
                current_role = role
                matched_ward = True
                break
        if matched_ward:
            continue

        # skip non-candidate lines
        if not current_ward:
            continue
        if any(line.startswith(s) for s in (
            "Candidate", "Total Valid", "Informal", "Total Votes",
            header, "Votes", "Percentage", "Elected",
        )):
            continue

        # "SURNAME Firstname  votes  pct%  [4 Year Term]"
        m = re.match(
            r"^([A-Z][A-Za-z\s\-']+)\s+"
            r"(\d[\d,]+)\s+"
            r"[\d.]+%\s*"
            r"(4 Year Term)?",
            line,
        )
        if m:
            name_raw = m.group(1).strip()
            votes = m.group(2).replace(",", "")
            elected = "TRUE" if m.group(3) else "FALSE"
            given, family = split_name(name_raw)
            if family:
                rows.append({
                    "election_date": election_date,
                    "ward": current_ward,
                    "role": current_role,
                    "given_name": given,
                    "family_name": family,
                    "elected": elected,
                    "votes": votes,
                })
            continue

        # Unopposed
        if "Elected Unopposed" in line:
            name_raw = line.split("Elected")[0].strip()
            given, family = split_name(name_raw)
            if family:
                rows.append({
                    "election_date": election_date,
                    "ward": current_ward,
                    "role": current_role,
                    "given_name": given,
                    "family_name": family,
                    "elected": "TRUE",
                    "votes": "",
                })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FIELDNAMES = ["election_date", "ward", "role", "given_name", "family_name", "elected", "votes"]


def main(council_key: str, output_path: str | None = None):
    if council_key not in COUNCIL_CONFIGS:
        print(f"Unknown council '{council_key}'. Available: {', '.join(COUNCIL_CONFIGS)}")
        sys.exit(1)
    cfg = COUNCIL_CONFIGS[council_key]
    output_path = output_path or cfg["output_csv"]
    default_ward = cfg.get("default_ward", "")

    all_rows: list[dict] = []

    for year, url, page_indices, election_date in cfg["reports"]:
        print(f"Fetching {year}...", end=" ", flush=True)
        try:
            pdf_bytes = fetch(url)
            text = extract_pages(pdf_bytes, page_indices)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        if year in cfg["old_era_years"]:
            rows = parse_old_era(text, election_date, cfg["header"], cfg["ward_aliases"], default_ward)
        else:
            rows = parse_standard(text, election_date, cfg["header"], cfg["ward_aliases"], default_ward)

        print(f"{len(rows)} candidates")
        all_rows.extend(rows)

    print(f"\nTotal: {len(all_rows)} rows across {len(set(r['election_date'] for r in all_rows))} elections")

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <council-key> [output_csv]")
        print(f"Available council keys: {', '.join(COUNCIL_CONFIGS)}")
        sys.exit(1)
    council_arg = sys.argv[1].strip().lower()
    out_arg = sys.argv[2] if len(sys.argv) > 2 else None
    main(council_arg, out_arg)
