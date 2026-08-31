"""
Scraper audit: measure completeness of the scraped corpus and clean up the manifest.

Two modes:
  report   — print per-year completeness table and quota check (default)
  clean    — re-classify 'unknown' entries and remove confirmed noise documents
             from the manifest.  Use --apply to write changes.

Usage:
  python scripts/scraper_audit.py cambridge
  python scripts/scraper_audit.py cambridge clean
  python scripts/scraper_audit.py cambridge clean --apply
  council scraper-audit cambridge [clean] [--apply]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.base import classify_document_type, is_meeting_document

RAW_DIR = ROOT / "data" / "raw"

# Cambridge is required to hold ≥1 ordinary council meeting per month.
# January is traditionally skipped. So the floor is 11 months × 1 meeting
# = 11 ordinary meetings.  Add special meetings, AGMs, committees ≈ 14–20/year.
# We use a conservative floor to catch genuine gaps without false alarms.
QUOTA_MEETING_DATES = 10    # distinct meeting dates with any minutes/agenda per year
QUOTA_MAX_GAP_MONTHS = 2    # most consecutive non-January months allowed with no meetings

MONTH_NAMES = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def load_manifest(council: str) -> dict:
    path = RAW_DIR / council / "manifest.json"
    if not path.exists():
        sys.exit(f"Manifest not found: {path}")
    return json.loads(path.read_text())


def save_manifest(council: str, manifest: dict) -> None:
    path = RAW_DIR / council / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))


def _max_consecutive_gap(months_present: set[str]) -> int:
    """Return the longest run of consecutive non-January months absent from the set."""
    non_jan = [m for m in ("%02d" % i for i in range(2, 13)) if m not in months_present]
    if not non_jan:
        return 0
    max_gap = 0
    run = 0
    for m in ("%02d" % i for i in range(2, 13)):
        if m in months_present:
            run = 0
        else:
            run += 1
            max_gap = max(max_gap, run)
    return max_gap


_CAMBRIDGE_GAP_NOTES: dict[str, str] = {
    # year → plain-text explanation of why this gap exists and what to try
    "2022": (
        "Cambridge migrated from static HTML pages (sitemap-indexed, reliable to 2021) "
        "to a JS-rendered OpenCities CMS around May 2022. Meetings before the migration "
        "were published on the old system but were not carried into the new CMS. "
        "Wayback Machine has no crawl of the old pages for Jan–Apr 2022, and the new "
        "CMS year-filter returns nothing for those months. June 2022 is also absent."
    ),
    "2023": (
        "Similar to 2022: the CMS transition effects appear to have extended into H1 2023. "
        "The Playwright scraper (which reads the live CMS accordion) finds no meetings for "
        "Jan–Apr 2023 or June–July 2023. Wayback has no archived records for those months."
    ),
}

_RECOVERY_STEPS = """
Recovery options (in order of effort):
  1. Manual browser check
     Open https://www.cambridge.wa.gov.au/About/Town-Council/Agendas-Minutes in a
     browser, select the failing year from the dropdown, and count meetings shown.
     If the site shows meetings for the missing months, the scraper's year-filter
     selector may have changed — re-inspect the form element names via DevTools.

  2. Council website search
     Use the site's own search: search for "council meeting minutes [month] [year]"
     or browse any separate "archive" or "past meetings" section that may exist
     outside the main accordion page.

  3. Contact the council directly
     Under WA Local Government Act 1995 s.5.22, councils must make minutes available
     for public inspection. The Town Clerk / Records Officer can provide digital copies
     or direct you to where they are published.
       Phone:  (08) 9347 6000
       Email:  admin@cambridge.wa.gov.au
       Post:   Town of Cambridge, PO Box 32, Wembley WA 6913
     Request: "Digital copies of Ordinary Council Meeting minutes for [months/year]
     that do not appear to be published on the council website."

  4. Freedom of Information (FOI)
     If the council does not respond or claims the records are not publicly available,
     lodge a FOI request under the WA Freedom of Information Act 1992.
     FOI applications can be submitted via foi@cambridge.wa.gov.au.
"""


def _print_gap_guidance(council: str, by_year: dict) -> None:
    all_months = set("%02d" % i for i in range(2, 13))
    failing: list[tuple[str, list[str]]] = []
    for yr in sorted(by_year.keys()):
        if yr < "1995" or yr > "2023":
            continue
        info2 = by_year[yr]
        ndates = len(info2["dates"])
        months = info2["months"]
        missing = sorted(all_months - months)
        max_gap = _max_consecutive_gap(months)
        if ndates < QUOTA_MEETING_DATES or max_gap > QUOTA_MAX_GAP_MONTHS:
            failing.append((yr, [MONTH_NAMES[m] for m in missing]))

    print("The following years fail the completeness quota:\n")
    for yr, missing in failing:
        missing_str = ", ".join(missing) if missing else "(low total count)"
        print(f"  {yr}  missing: {missing_str}")
        note = _CAMBRIDGE_GAP_NOTES.get(yr) if council == "cambridge" else None
        if note:
            for line in _wrap(note, width=72, indent="    "):
                print(line)
        print()

    print(_RECOVERY_STEPS)


def _wrap(text: str, width: int = 72, indent: str = "") -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent)


def report(council: str) -> None:
    manifest = load_manifest(council)

    by_year: dict[str, dict] = defaultdict(lambda: {
        "dates": set(),
        "months": set(),
        "doctypes": defaultdict(int),
    })

    for fname, info in manifest.items():
        d = info.get("meeting_date") or ""
        if not d:
            continue
        yr, mo = d[:4], d[5:7]
        dt = info.get("document_type", "unknown")
        by_year[yr]["dates"].add(d)
        by_year[yr]["months"].add(mo)
        by_year[yr]["doctypes"][dt] += 1

    total = len(manifest)
    unknowns = sum(1 for i in manifest.values() if i.get("document_type") == "unknown")
    noise = sum(
        1 for i in manifest.values()
        if not is_meeting_document(i.get("source_url", ""))
    )

    print(f"Manifest: {total} entries  ({unknowns} unknown doc_type, {noise} noise docs)\n")

    hdr = f"{'Year':4}  {'Dates':5}  {'Months covered':40}  {'Missing (non-Jan)':25}  {'Quota'}"
    print(hdr)
    print("-" * len(hdr))

    all_pass = True
    for yr in sorted(by_year.keys()):
        if yr < "1995" or yr > "2023":
            continue
        info2 = by_year[yr]
        ndates = len(info2["dates"])
        months = info2["months"]
        all_months = set("%02d" % i for i in range(2, 13))
        missing = sorted(all_months - months)
        max_gap = _max_consecutive_gap(months)
        pass_quota = ndates >= QUOTA_MEETING_DATES and max_gap <= QUOTA_MAX_GAP_MONTHS
        if not pass_quota:
            all_pass = False
        months_str = ",".join(MONTH_NAMES[m] for m in sorted(months) if m != "01")
        missing_str = ",".join(MONTH_NAMES[m] for m in missing) if missing else "none"
        flag = "✓" if pass_quota else "✗ FAIL"
        print(f"{yr}  {ndates:5}  {months_str:40}  {missing_str:25}  {flag}")

    print()
    if all_pass:
        print("All years 1995-2023 pass quota.")
    else:
        _print_gap_guidance(council, by_year)

    # Show unknown breakdown
    if unknowns:
        print(f"\nUnknown document_type breakdown ({unknowns} entries):")
        patterns: dict[str, int] = defaultdict(int)
        for fname, info in manifest.items():
            if info.get("document_type") != "unknown":
                continue
            url = info.get("source_url", "")
            urlname = url.split("/")[-1].lower()
            if re.match(r"dv\d{2}_", urlname):
                p = "dv##_* (individual DA report)"
            elif "attachment" in urlname:
                p = "*attachment* (support doc)"
            elif "cr-item" in urlname:
                p = "cr-item-* (committee report attachment)"
            elif "dva.pdf" in urlname:
                p = "*dva.pdf (DA variance doc)"
            elif re.search(r"\d{4}_\d{2}_\d{2}[a-z]*m\.pdf$", urlname):
                p = "YYYY_MM_DDm.pdf (minutes — needs reclassify)"
            elif re.search(r"\d{4}_\d{2}_\d{2}[a-z]*a\.pdf$", urlname):
                p = "YYYY_MM_DDa.pdf (agenda — needs reclassify)"
            else:
                p = f"other: {urlname[:50]}"
            patterns[p] += 1
        for k, v in sorted(patterns.items(), key=lambda x: -x[1]):
            print(f"  {v:3}  {k}")


def clean(council: str, apply: bool) -> None:
    manifest = load_manifest(council)
    original_count = len(manifest)
    reclassified = 0
    removed = 0
    new_manifest: dict = {}

    for fname, info in manifest.items():
        url = info.get("source_url", "")
        current_type = info.get("document_type", "unknown")

        # Remove confirmed noise documents.
        if not is_meeting_document(url):
            removed += 1
            path = RAW_DIR / council / fname
            if apply and path.exists():
                path.unlink()
                print(f"  Deleted file: {fname}")
            else:
                print(f"  Would remove: {fname}  ({url.split('/')[-1]})")
            continue

        # Re-classify unknowns with the updated classifier.
        if current_type == "unknown":
            new_type = classify_document_type(url)
            if new_type != "unknown":
                info = {**info, "document_type": new_type}
                reclassified += 1
                print(f"  Reclassify: {fname} → {new_type}  ({url.split('/')[-1]})")

        new_manifest[fname] = info

    print(
        f"\n{'Applied' if apply else 'Dry run'}:  "
        f"{removed} noise entries removed, "
        f"{reclassified} entries reclassified, "
        f"{len(new_manifest)} entries remain (was {original_count})."
    )

    if apply:
        save_manifest(council, new_manifest)
        print("Manifest saved.")
    else:
        print("Run with --apply to write changes.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scraper audit for council corpus")
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument(
        "mode",
        nargs="?",
        default="report",
        choices=["report", "clean"],
        help="report (default) or clean",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With 'clean': actually write changes to manifest and delete files",
    )
    args = parser.parse_args(argv)

    if args.mode == "clean":
        clean(args.council, args.apply)
    else:
        report(args.council)


def run(args: argparse.Namespace) -> None:
    if getattr(args, "clean", False):
        clean(args.council, getattr(args, "apply", False))
    else:
        report(args.council)


if __name__ == "__main__":
    main()
