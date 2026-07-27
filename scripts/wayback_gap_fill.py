"""
Wayback Machine CDX gap-filler for Cambridge council minutes.

Queries the Wayback Machine CDX API for meeting documents in year/month ranges
that are absent from the local manifest. Two query strategies:

  pages  — search for meeting INDEX PAGE URLs archived by Wayback, then fetch
            each page (from the live site) and extract the PDF link.  Best for
            periods where the council published static meeting pages (pre-CMS).

  pdfs   — search directly for archived PDF files matching the Cambridge asset
            path. Best when the meeting page structure has changed or been lost.

Usage:
  python scripts/wayback_gap_fill.py cambridge 2022        # gaps in 2022
  python scripts/wayback_gap_fill.py cambridge 2022 2023   # gaps in both years
  python scripts/wayback_gap_fill.py cambridge 2022 --months 1-4  # Jan-Apr only
  python scripts/wayback_gap_fill.py cambridge 2022 --download    # actually download
  council wayback-fill cambridge 2022 2023 [--months M-N] [--download]
"""

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.base import classify_document_type, is_meeting_document
from src.scraper.cambridge import (
    _parse_slug, _parse_pdf_url,
    _extract_minutes_pdf_url, BASE_URL,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = ROOT / "data" / "raw"
CDX_API = "https://web.archive.org/cdx/search/cdx"

CAMBRIDGE_ASSET_PATHS = [
    "www.cambridge.wa.gov.au/files/assets/public/*/documents-and-files/aaa-agenda-and-minutes",
    "www.cambridge.wa.gov.au/files/assets/public/v/1/documents-and-files/aaa-agenda-and-minutes",
]
CAMBRIDGE_PAGES_PATH = "www.cambridge.wa.gov.au/About/Town-Council/Agendas-Minutes"

# Scraper instance used for hashing URLs → local filenames and downloading.
_SCRAPER = None


def _get_scraper():
    global _SCRAPER
    if _SCRAPER is None:
        from src.scraper.cambridge import CambridgeScraper
        _SCRAPER = CambridgeScraper(since_year=None)
    return _SCRAPER


def load_manifest(council: str) -> dict:
    path = RAW_DIR / council / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_manifest(council: str, manifest: dict) -> None:
    (RAW_DIR / council / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _cdx_query(client: httpx.Client, url_pattern: str, from_ts: str, to_ts: str,
                extra: dict | None = None) -> list[str]:
    """Return a deduplicated list of original URLs matching the CDX query."""
    params = {
        "url": url_pattern,
        "output": "json",
        "fl": "original",
        "collapse": "urlkey",
        "from": from_ts,
        "to": to_ts,
        "limit": "1000",
    }
    if extra:
        params.update(extra)
    try:
        resp = client.get(CDX_API, params=params, timeout=60)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        logger.warning("CDX query failed for %s: %s", url_pattern, exc)
        return []
    data = rows[1:] if rows and rows[0] == ["original"] else rows
    seen: set[str] = set()
    out: list[str] = []
    for row in data:
        url = (row[0] if isinstance(row, list) else row).replace("http://", "https://")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _year_month_ts(year: int, month: int | None = None, end: bool = False) -> str:
    """Return a 14-digit CDX timestamp for the start or end of a year/month."""
    if month is None:
        return f"{year}1231235959" if end else f"{year}0101000000"
    days = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and year % 4 == 0:
        days[2] = 29
    return f"{year}{month:02d}{days[month]:02d}235959" if end else f"{year}{month:02d}01000000"


def search_pages(client: httpx.Client, year: int, months: list[int]) -> list[tuple[str, date, str]]:
    """
    Search Wayback for archived Cambridge meeting page URLs for the given year/months.
    Returns (pdf_url, meeting_date, meeting_type) tuples.
    """
    from_ts = _year_month_ts(year, min(months))
    to_ts = _year_month_ts(year, max(months), end=True)
    pattern = f"{CAMBRIDGE_PAGES_PATH}/{year}/*"

    page_urls = _cdx_query(client, pattern, from_ts, to_ts)
    logger.info("CDX pages: %d archived meeting page URLs for %d months %s",
                len(page_urls), year, months)

    results: list[tuple[str, date, str]] = []
    seen_pdf: set[str] = set()

    for page_url in page_urls:
        slug = page_url.rstrip("/").rsplit("/", 1)[-1]
        parsed = _parse_slug(slug)
        if parsed is None:
            continue
        meeting_date, meeting_type = parsed
        if meeting_date.month not in months:
            continue

        logger.debug("Fetching live meeting page: %s", page_url)
        try:
            resp = client.get(page_url, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("Live page fetch failed %s: %s", page_url, exc)
            # Try Wayback-proxied version
            wb_url = f"https://web.archive.org/web/{from_ts}/{page_url}"
            try:
                resp = client.get(wb_url, timeout=30)
                resp.raise_for_status()
            except Exception:
                logger.warning("Wayback proxy also failed: %s", page_url)
                continue

        pdf_href = _extract_minutes_pdf_url(resp.text)
        if not pdf_href:
            continue
        pdf_url = pdf_href if pdf_href.startswith("http") else BASE_URL + pdf_href
        if pdf_url not in seen_pdf and is_meeting_document(pdf_url):
            seen_pdf.add(pdf_url)
            results.append((pdf_url, meeting_date, meeting_type))
        time.sleep(0.5)

    return results


def search_pdfs(client: httpx.Client, year: int, months: list[int]) -> list[tuple[str, date, str]]:
    """
    Search Wayback for archived PDF files in Cambridge's asset paths for year/months.
    Returns (pdf_url, meeting_date, meeting_type) tuples.
    """
    from_ts = _year_month_ts(year, min(months))
    to_ts = _year_month_ts(year, max(months), end=True)

    results: list[tuple[str, date, str]] = []
    seen_pdf: set[str] = set()

    for asset_pattern in CAMBRIDGE_ASSET_PATHS:
        pdfs = _cdx_query(
            client,
            f"{asset_pattern}/{year}/*",
            from_ts, to_ts,
            extra={"filter": "mimetype:application/pdf"},
        )
        logger.info("CDX pdfs (%s): %d entries for %d", asset_pattern.split("/")[-3], len(pdfs), year)
        for url in pdfs:
            if not is_meeting_document(url):
                continue
            parsed = _parse_pdf_url(url)
            if parsed is None:
                continue
            meeting_date, meeting_type = parsed
            if meeting_date.month not in months:
                continue
            if url not in seen_pdf:
                seen_pdf.add(url)
                results.append((url, meeting_date, meeting_type))

    return results


def _url_to_local_name(url: str, council: str) -> str:
    scraper = _get_scraper()
    return scraper._url_to_filename(url)


def report_and_download(
    council: str,
    years: list[int],
    months: list[int] | None,
    download: bool,
) -> None:
    manifest = load_manifest(council)
    existing_urls: set[str] = {info.get("source_url", "") for info in manifest.values()}

    dest_dir = RAW_DIR / council
    dest_dir.mkdir(parents=True, exist_ok=True)

    new_docs: list[tuple[str, date, str]] = []

    with httpx.Client(
        headers={"User-Agent": "council-ontology-bot/0.1 (research; contact: research@example.com)"},
        follow_redirects=True,
        timeout=30,
    ) as client:
        for year in years:
            target_months = months or list(range(1, 13))
            logger.info("=== Year %d, checking months %s ===", year, target_months)

            # Strategy 1: meeting page URLs
            page_results = search_pages(client, year, target_months)
            for pdf_url, meeting_date, meeting_type in page_results:
                if pdf_url not in existing_urls:
                    logger.info("NEW (pages): %s  %s  %s", meeting_date, meeting_type, pdf_url.split("/")[-1])
                    new_docs.append((pdf_url, meeting_date, meeting_type))
                    existing_urls.add(pdf_url)

            # Strategy 2: PDF asset search
            pdf_results = search_pdfs(client, year, target_months)
            for pdf_url, meeting_date, meeting_type in pdf_results:
                if pdf_url not in existing_urls:
                    logger.info("NEW (pdfs): %s  %s  %s", meeting_date, meeting_type, pdf_url.split("/")[-1])
                    new_docs.append((pdf_url, meeting_date, meeting_type))
                    existing_urls.add(pdf_url)
            time.sleep(1)

    if not new_docs:
        print(f"\nNo new documents found for years {years}, months {months or 'all'}.")
        return

    print(f"\nFound {len(new_docs)} new document(s):")
    for pdf_url, meeting_date, meeting_type in sorted(new_docs, key=lambda x: x[1]):
        print(f"  {meeting_date}  {meeting_type:<30}  {pdf_url.split('/')[-1]}")

    if not download:
        print("\nRe-run with --download to fetch these PDFs.")
        return

    print("\nDownloading...")
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for pdf_url, meeting_date, meeting_type in new_docs:
            fname = _url_to_local_name(pdf_url, council)
            dest = dest_dir / fname
            if dest.exists():
                logger.debug("Already exists: %s", fname)
            else:
                try:
                    resp = client.get(pdf_url)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
                    print(f"  Downloaded: {fname}  ({pdf_url.split('/')[-1]})")
                except Exception as exc:
                    print(f"  FAILED: {pdf_url.split('/')[-1]}: {exc}")
                    continue
                time.sleep(0.5)

            manifest[fname] = {
                "meeting_date": meeting_date.isoformat(),
                "meeting_type": meeting_type,
                "source_url": pdf_url,
                "document_type": classify_document_type(pdf_url),
            }

    save_manifest(council, manifest)
    print(f"\nManifest updated: {len(manifest)} entries.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Wayback CDX gap-filler for council minutes")
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument("years", nargs="+", type=int, help="Year(s) to check (e.g. 2022 2023)")
    parser.add_argument(
        "--months", type=str, default=None, metavar="M-N",
        help="Month range to check, e.g. 1-4 for Jan–Apr (default: all months)",
    )
    parser.add_argument(
        "--download", action="store_true",
        help="Download newly found PDFs and update manifest",
    )
    args = parser.parse_args(argv)

    months: list[int] | None = None
    if args.months:
        parts = args.months.split("-")
        if len(parts) == 2:
            months = list(range(int(parts[0]), int(parts[1]) + 1))
        else:
            months = [int(parts[0])]

    report_and_download(args.council, args.years, months, args.download)


if __name__ == "__main__":
    main()
