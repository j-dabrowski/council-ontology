"""
Extract Town of Cambridge election results from Elections WA PDFs (1999-2023).
Outputs a CSV suitable for: council import-terms cambridge <file> --apply
"""

import csv
import io
import re
import sys
import urllib.request

import pdfplumber

BASE = "https://www.elections.wa.gov.au"

# (year, url, [0-indexed result pages], election_date)
REPORTS = [
    (1999, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_1999.pdf",       [66],       "1999-05-01"),
    (2001, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2001_App.pdf",    [17],       "2001-05-05"),
    (2003, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2003_App.pdf",    [20],       "2003-05-03"),
    (2005, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2005_App.pdf",    [24],       "2005-05-07"),
    (2007, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2007.pdf",        [70],       "2007-10-20"),
    (2009, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2009.pdf",        [73],       "2009-10-17"),
    (2011, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2011.pdf",        [64],       "2011-10-15"),
    (2013, f"{BASE}/sites/default/files/content/documents/LG_Election_Report_2013.pdf",        [69],       "2013-10-19"),
    (2015, f"{BASE}/sites/default/files/content/2015%20Local%20Government%20Ordinary%20Elections%20Report.pdf", [73], "2015-10-17"),
    # 2017: Cambridge results page is absent from the statewide PDF — needs separate source
    (2019, f"{BASE}/sites/default/files/waec/lg_elections/Reports/2019_LG_Election_Report%20FINAL%20online.pdf", [47], "2019-10-19"),
    (2021, f"{BASE}/sites/default/files/2021_LG_Election_Report%20online%20vf.pdf",            [49],       "2021-10-16"),
    (2023, f"{BASE}/sites/default/files/LG%202023%20Statewide%20report%20-%20with%20appendices_0.pdf", [201], "2023-10-21"),
]


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
# Name splitting helpers
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
# Parsers for different era formats
# ---------------------------------------------------------------------------

def parse_standard(text: str, election_date: str) -> list[dict]:
    """
    Parse the 2003–2023 standard format:
      SURNAME, Firstname  votes (pct%)  [Expiry date]
    or
      SURNAME, Firstname  Elected Unopposed  [Expiry date]
    Sections headed by ward/role names in ALL CAPS.
    """
    rows = []
    current_ward = ""
    current_role = "Councillor"

    ward_aliases = {
        "MAYOR": ("Mayor", "Mayor"),
        "MAYORAL": ("Mayor", "Mayor"),
        "DEPUTY MAYOR": ("Mayor", "Deputy Mayor"),
        "COAST": ("Coast", "Councillor"),
        "WEMBLEY": ("Wembley", "Councillor"),
    }

    in_cambridge = False
    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Start capturing on Cambridge header
        if "TOWN OF CAMBRIDGE" in line.upper():
            in_cambridge = True
            continue

        # Stop at the next council
        if in_cambridge and re.match(r"^(CITY|SHIRE|TOWN|DISTRICT)\s+OF\s+", line.upper()):
            break

        if not in_cambridge:
            continue

        # Detect section headings
        upper = line.upper()
        matched_ward = False
        for key, (ward, role) in ward_aliases.items():
            if upper == key or upper.startswith(key + " "):
                current_ward = ward
                current_role = role
                matched_ward = True
                break
        if matched_ward:
            continue

        # Skip summary/header lines
        if any(line.startswith(s) for s in (
            "Candidate", "Total Valid", "Informal", "Total Votes",
            "TOWN OF CAMBRIDGE", "Contents", "Election Report",
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
            if name_raw.upper() not in (
                "COAST", "WEMBLEY", "MAYOR", "MAYORAL",
                "CANDIDATE", "TOTAL", "INFORMAL",
            ):
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


def parse_1999_2001(text: str, election_date: str) -> list[dict]:
    """
    Parse 1999/2001 format:
      SURNAME Firstname  votes  pct%  Elected / 4 Year Term
    or
      SURNAME Firstname  Elected Unopposed  4 Year Term
    """
    rows = []
    current_ward = ""
    current_role = "Councillor"

    ward_map = {
        "MAYORAL": ("Mayor", "Mayor"),
        "MAYOR": ("Mayor", "Mayor"),
        "COAST": ("Coast", "Councillor"),
        "WEMBLEY": ("Wembley", "Councillor"),
        "Coast": ("Coast", "Councillor"),
        "Wembley": ("Wembley", "Councillor"),
        "Mayoral": ("Mayor", "Mayor"),
    }

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Section heading
        for key, (ward, role) in ward_map.items():
            if line == key or line == key.upper():
                current_ward = ward
                current_role = role
                break
        else:
            # skip non-candidate lines
            if not current_ward:
                continue
            if any(line.startswith(s) for s in (
                "Candidate", "Total Valid", "Informal", "Total Votes",
                "TOWN OF CAMBRIDGE", "Votes", "Percentage", "Elected",
            )):
                continue

            # 1999/2001: "SURNAME Firstname  votes  pct%  [4 Year Term]"
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


def main(output_path: str = "data/cambridge_elections_raw.csv"):
    all_rows: list[dict] = []

    for year, url, page_indices, election_date in REPORTS:
        print(f"Fetching {year}...", end=" ", flush=True)
        try:
            pdf_bytes = fetch(url)
            text = extract_pages(pdf_bytes, page_indices)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        if year in (1999, 2001):
            rows = parse_1999_2001(text, election_date)
        else:
            rows = parse_standard(text, election_date)

        print(f"{len(rows)} candidates")
        all_rows.extend(rows)

    print(f"\nTotal: {len(all_rows)} rows across {len(set(r['election_date'] for r in all_rows))} elections")
    print("WARNING: 2017 results are absent from the statewide PDF — add manually.")

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/cambridge_elections_raw.csv"
    main(out)
