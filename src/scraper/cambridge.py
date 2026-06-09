"""
Scraper for the City of Cambridge (WA) council minutes.

Discovery strategy (confirmed 2026-04-14):

  Source 1 — Sitemap (/sitemap.xml)
    Public, comprehensive for 1994–2021. Gives per-meeting page URLs with
    dates embedded in the slug.

  Source 2 — Playwright headless browser  [primary for 2022+]
    The agendas page is an ASP.NET WebForms / OpenCities CMS app.
    Year-filtered results are loaded by submitting a dropdown form; each
    meeting item is an accordion whose body is fetched via AJAX from
    OCServiceHandler.axd.  A real Chromium session handles the Akamai
    protection and JS rendering.  We:
      1. Navigate to /About/Town-Council/Agendas-Minutes
      2. Select each year in the dropdown and click Search
      3. For every .ajax-trigger element (data-cvid GUID), click it and
         intercept the OCServiceHandler.axd AJAX response to get the PDF link
      4. Paginate with the Next button
    Requires `pip install ".[browser]"` and `playwright install chromium`.

  Source 3 — Wayback Machine CDX API  [fallback when Playwright not installed]
    Queries web.archive.org/cdx for PDF assets at Cambridge's known static
    document path.  Covers whatever Wayback has indexed (partial coverage —
    the CDN version numbers vary and not all files are archived).

  Source 4 — Site search  [live tail]
    The site's own search endpoint returns the ~10 most recent meetings
    regardless of query — catches newly published meetings before Wayback
    indexes them.

Flow:
  Path A — meeting-page probing (sitemap + search → fetch HTML → PDF):
    1. Sitemap → meeting page URLs for since_year–2021
    2. Site search → live tail of most recent meetings
    3. For each unique page URL: fetch HTML, extract minutes PDF href

  Source 2 — Playwright returns MinutesDocument list directly (PDF URLs
    already resolved via AJAX), merged with Path A results.

  Path B — CDX direct PDF (only when Playwright found nothing):
    CDX API → PDF asset URLs; parse date/type from URL directly

  All sources share a seen-URL set so there are no duplicate downloads.
"""

import json
import logging
import re
import time
from datetime import date
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from .base import BaseCouncilScraper, MinutesDocument

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cambridge.wa.gov.au"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
AGENDAS_PATH_PREFIX = "/About/Town-Council/Agendas-Minutes"
_SITEMAP_MAX_YEAR = 2021  # sitemap is reliable up to and including this year

_CDX_API = "https://web.archive.org/cdx/search/cdx"
_PDF_ASSET_PATH = "documents-and-files/aaa-agenda-and-minutes"

# Sitemap slug format:  "19-Oct-2021-Special-Council-Meeting"
_SLUG_OLD_RE = re.compile(r"^(\d{1,2})-([A-Za-z]+)-(\d{4})-(.+)$")
# New slug format:      "Ordinary-Council-Meeting-16-December-2025"
_SLUG_NEW_RE = re.compile(r"^(.+?)-(\d{1,2})-([A-Za-z]+)-(\d{4})$")

_MONTH_MAP = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}

# Site-search URL — returns ~10 most recent meetings regardless of keyword
_SEARCH_URL = (
    f"{BASE_URL}/About/Town-Council/Agendas-Minutes"
    "?dlv_OC+CL+Public+Site+Search=(keyword=council+meeting)"
)
_MEETING_URL_RE = re.compile(
    r"https://www\.cambridge\.wa\.gov\.au"
    r"/About/Town-Council/Agendas-Minutes/(\d{4})/([^\"\s<>]+)"
)


def _parse_slug(slug: str) -> tuple[date, str] | None:
    """
    Parse a meeting slug into (date, meeting_type).
    Handles both old format (DD-Mon-YYYY-Type) and new format (Type-DD-Month-YYYY).
    """
    # Old format: "19-Oct-2021-Special-Council-Meeting"
    m = _SLUG_OLD_RE.match(slug)
    if m:
        day_s, mon_s, year_s, type_slug = m.groups()
        month = _MONTH_MAP.get(mon_s[:3].lower())
        if month:
            try:
                return (
                    date(int(year_s), month, int(day_s)),
                    type_slug.replace("-", " ").title(),
                )
            except ValueError:
                pass

    # New format: "Ordinary-Council-Meeting-16-December-2025"
    m = _SLUG_NEW_RE.match(slug)
    if m:
        type_slug, day_s, mon_s, year_s = m.groups()
        month = _MONTH_MAP.get(mon_s[:3].lower())
        if month:
            try:
                return (
                    date(int(year_s), month, int(day_s)),
                    type_slug.replace("-", " ").title(),
                )
            except ValueError:
                pass

    return None


def _collect_from_sitemap(
    client: httpx.Client, since_year: int | None
) -> dict[str, tuple[date, str]]:
    """
    Parse the sitemap and return {page_url: (date, type)} for every meeting page,
    optionally filtered to >= since_year.
    """
    logger.info("Fetching sitemap: %s", SITEMAP_URL)
    resp = client.get(SITEMAP_URL)
    resp.raise_for_status()

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    try:
        root = ElementTree.fromstring(resp.text)
    except ElementTree.ParseError as exc:
        raise RuntimeError(f"Failed to parse sitemap XML: {exc}") from exc

    results: dict[str, tuple[date, str]] = {}
    for loc_el in root.findall(".//sm:loc", ns):
        url = (loc_el.text or "").strip()
        if AGENDAS_PATH_PREFIX not in url:
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        parsed = _parse_slug(slug)
        if parsed is None:
            logger.debug("Could not parse sitemap slug: %s", slug)
            continue
        meeting_date, meeting_type = parsed
        if since_year and meeting_date.year < since_year:
            continue
        results[url] = (meeting_date, meeting_type)

    logger.info(
        "Sitemap: %d meeting pages%s",
        len(results),
        f" (since {since_year})" if since_year else "",
    )
    return results


def _collect_from_search(client: httpx.Client) -> dict[str, tuple[date, str]]:
    """
    Hit the site-search endpoint and collect the ~10 most recent meeting URLs.
    Used as a live tail to catch meetings not yet indexed by the Wayback Machine.
    """
    logger.info("Fetching recent meetings via site search")
    try:
        resp = client.get(_SEARCH_URL)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Site search failed: %s", exc)
        return {}

    results: dict[str, tuple[date, str]] = {}
    for m in _MEETING_URL_RE.finditer(resp.text):
        year_s, slug = m.group(1), m.group(2)
        url = f"{BASE_URL}/About/Town-Council/Agendas-Minutes/{year_s}/{slug}"
        slug_clean = slug.rstrip("/")
        parsed = _parse_slug(slug_clean)
        if parsed:
            results[url] = parsed
        else:
            logger.debug("Could not parse search slug: %s", slug_clean)

    logger.info("Search: %d recent meeting pages", len(results))
    return results


def _collect_from_playwright(
    since_year: int,
    until_year: int,
    request_delay: float = 0.5,
) -> list[MinutesDocument]:
    """
    Use a headless Chromium browser to collect Cambridge council minutes
    PDFs for the given year range.

    Strategy (confirmed working 2026-04):
      1. For each year: navigate fresh to the main agendas page (resets
         ASP.NET ViewState so pagination always starts at page 1), select
         the year in the dropdown, and click Search
      2. For every .ajax-trigger[data-cvid] accordion: click it via
         page.click() (full Chromium stack, needed for Akamai) and capture
         the OCServiceHandler.axd AJAX response via expect_response
      3. Paginate via the Next button until no more pages

    Returns MinutesDocument objects with source_url already pointing to the
    PDF — callers do NOT need to fetch meeting pages separately.

    Requires `playwright` (`pip install ".[browser]"` then
    `playwright install chromium`).  Returns [] when unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.info(
            "playwright not installed — skipping headless browser source "
            "(run: pip install '.[browser]' && playwright install chromium)"
        )
        return []

    docs: list[MinutesDocument] = []
    seen: set[str] = set()
    main_url = f"{BASE_URL}{AGENDAS_PATH_PREFIX}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for year in range(until_year, since_year - 1, -1):
            logger.info("Playwright: filtering year %d", year)

            # Navigate fresh each year — resets ASP.NET ViewState and pagination
            # so we always start at page 1 of the new year's results.
            try:
                page.goto(main_url, wait_until="networkidle", timeout=60_000)
                page.select_option(
                    'select[name="ctl11$ctl00$ctl18$ctl00$ctl00"]',
                    str(year),
                    timeout=10_000,
                )
                page.click('input[name="ctl11$ctl00$ctl19"]', timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Playwright: error loading year %d: %s", year, exc)
                continue

            year_docs = 0
            page_num = 1

            while True:
                soup = BeautifulSoup(page.content(), "html.parser")
                triggers = soup.select(".ajax-trigger[data-cvid]")
                logger.info(
                    "Playwright %d page %d: %d accordion items",
                    year, page_num, len(triggers),
                )
                if not triggers:
                    break

                for trigger in triggers:
                    cvid: str = trigger["data-cvid"]
                    heading = trigger.get_text(" ", strip=True)
                    parsed = _parse_meeting_heading(heading)
                    if parsed is None:
                        logger.debug("Cannot parse heading: %r", heading)
                        continue
                    meeting_date, meeting_type = parsed

                    # Click the accordion trigger and intercept the AJAX
                    # response.  We use page.click() (full Chromium stack) so
                    # the request carries the real browser fingerprint — needed
                    # to pass Akamai bot protection.  The expect_response
                    # context-manager sets up the listener BEFORE the click so
                    # there is no race condition.
                    pdf_href: str | None = None
                    try:
                        with page.expect_response(
                            # Default-arg captures cvid at definition time,
                            # avoiding late-binding in the loop.
                            lambda r, _c=cvid: (
                                "OCServiceHandler" in r.url
                                and _c.lower() in r.url.lower()
                            ),
                            timeout=15_000,
                        ) as resp_info:
                            page.click(f'[data-cvid="{cvid}"]', timeout=10_000)

                        # The OCServiceHandler response is JSON with an
                        # "html" field — parse the JSON first, then the HTML.
                        raw = resp_info.value.text()
                        try:
                            inner_html = json.loads(raw).get("html", raw)
                        except json.JSONDecodeError:
                            inner_html = raw  # fallback: treat as plain HTML

                        ajax_soup = BeautifulSoup(inner_html, "html.parser")

                        # Collect ALL PDF links from the accordion response.
                        # Emitting each PDF separately ensures minutes are
                        # never missed when both agenda and minutes are listed.
                        pdf_hrefs: list[str] = [
                            link["href"]
                            for link in ajax_soup.find_all("a", href=True)
                            if link["href"].lower().endswith(".pdf")
                        ]

                    except PWTimeout:
                        logger.debug("Playwright: AJAX timeout cvid=%s", cvid)
                        pdf_hrefs = []
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Playwright: error on cvid=%s: %s", cvid, exc)
                        pdf_hrefs = []

                    if not pdf_hrefs:
                        logger.debug("No PDF in AJAX response cvid=%s", cvid)
                        continue

                    if request_delay:
                        time.sleep(request_delay)

                    for pdf_href in pdf_hrefs:
                        pdf_url = (
                            pdf_href if pdf_href.startswith("http") else BASE_URL + pdf_href
                        )
                        if pdf_url in seen:
                            continue
                        seen.add(pdf_url)

                        docs.append(
                            MinutesDocument(
                                council_short_name="cambridge",
                                meeting_date=meeting_date,
                                meeting_type=meeting_type,
                                source_url=pdf_url,
                            )
                        )
                        year_docs += 1

                # Advance to next page if the Next button is enabled
                try:
                    next_btn = page.query_selector('input[name="ctl11$ctl00$ctl10"]')
                    if next_btn and next_btn.get_attribute("disabled") is None:
                        next_btn.click()
                        page.wait_for_load_state("networkidle", timeout=30_000)
                        page_num += 1
                        continue
                except Exception:  # noqa: BLE001
                    pass
                break  # no Next button → last page for this year

            logger.info("Playwright year %d: %d minutes PDFs", year, year_docs)

        browser.close()

    logger.info("Playwright total: %d minutes PDFs", len(docs))
    return docs


def _infer_type_from_pdf_url(url: str) -> str:
    """Infer meeting type from a PDF URL / filename."""
    s = url.lower()
    if "public-art" in s or "/pac" in s:
        return "Public Art Committee"
    if "audit" in s:
        return "Audit Committee"
    if "agm" in s or "electors" in s:
        return "Annual General Meeting Of Electors"
    if "special" in s or "scm" in s or re.search(r"[_-]sc[_.\-]", s) or s.endswith("sc.pdf"):
        return "Special Council Meeting"
    return "Ordinary Council Meeting"


def _parse_pdf_url(url: str) -> tuple[date, str] | None:
    """
    Extract (meeting_date, meeting_type) from a Cambridge minutes PDF URL.

    Handles the two naming eras:
      Old: YYYY_MM_DD*.pdf  (e.g. 2022_03_22scm-minutes.pdf)
      New: minutes-{type}-DD-Month-YYYY.pdf
    Falls back to year+month from the path component when only that is available.
    """
    filename = url.rstrip("/").rsplit("/", 1)[-1].lower().removesuffix(".pdf")
    meeting_type = _infer_type_from_pdf_url(url)

    # Old format: YYYY_MM_DD…
    m = re.match(r"(\d{4})_(\d{1,2})_(\d{1,2})", filename)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), meeting_type
        except ValueError:
            pass

    # New format: minutes-{type}-DD-monthname-YYYY
    m = re.search(r"(\d{1,2})-([a-z]+)-(\d{4})$", filename)
    if m:
        day_s, mon_s, year_s = m.groups()
        month = _MONTH_MAP.get(mon_s[:3])
        if month:
            try:
                return date(int(year_s), month, int(day_s)), meeting_type
            except ValueError:
                pass

    # Fall back: extract year + month from path (e.g. /2022/3.-march/)
    year_m = re.search(r"/(\d{4})/", url)
    month_m = re.search(r"/(\d{1,2})\.-[a-z]+/", url)
    if year_m and month_m:
        try:
            return date(int(year_m.group(1)), int(month_m.group(1)), 1), meeting_type
        except ValueError:
            pass

    return None


def _parse_meeting_heading(text: str) -> tuple[date, str] | None:
    """
    Parse a meeting accordion heading like
      "20 December 2022 Ordinary Council Meeting (show below)"
    into (meeting_date, meeting_type).

    The "(show below)" suffix is accordion UI chrome — strip it before parsing.
    """
    # Strip accordion UI suffix "(show below)" in any capitalisation
    clean = re.sub(r"\s*\(show below\)\s*$", "", text.strip(), flags=re.IGNORECASE)

    date_m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", clean)
    if not date_m:
        return None

    day_s, mon_s, year_s = date_m.groups()
    month = _MONTH_MAP.get(mon_s[:3].lower())
    if not month:
        return None
    try:
        meeting_date = date(int(year_s), month, int(day_s))
    except ValueError:
        return None

    type_m = re.search(
        r"(Ordinary Council Meeting|Special Council Meeting"
        r"|Public Art Committee|Audit Committee"
        r"|Annual General Meeting[^(]*)",
        clean,
        re.IGNORECASE,
    )
    meeting_type = type_m.group(1).strip().title() if type_m else "Ordinary Council Meeting"
    return meeting_date, meeting_type


def _collect_from_wayback_pdfs(
    client: httpx.Client,
    since_year: int,
    until_year: int,
) -> list[MinutesDocument]:
    """
    Query the Wayback Machine CDX API for minutes PDF files at Cambridge's
    known static document path for each year in [since_year, until_year].

    Targets PDF assets directly rather than JS-rendered meeting index pages —
    static PDF files are reliably indexed by the Wayback Machine crawler even
    when the HTML navigation around them requires JavaScript.

    Returns MinutesDocument objects ready for download (source_url is the PDF).
    """
    docs: list[MinutesDocument] = []
    seen: set[str] = set()

    for year in range(since_year, until_year + 1):
        try:
            resp = client.get(
                _CDX_API,
                params={
                    "url": (
                        f"www.cambridge.wa.gov.au/files/assets/public/v/1"
                        f"/{_PDF_ASSET_PATH}/{year}/*"
                    ),
                    "output": "json",
                    "fl": "original",
                    "collapse": "urlkey",
                    "filter": "mimetype:application/pdf",
                    "limit": "500",
                },
                timeout=60,
            )
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wayback CDX PDF query failed for %d: %s", year, exc)
            continue

        data_rows = rows[1:] if rows and rows[0] == ["original"] else rows

        found = 0
        for row in data_rows:
            url = (row[0] if isinstance(row, list) else row).replace("http://", "https://")
            filename = url.rstrip("/").rsplit("/", 1)[-1].lower()

            # Skip agendas; keep minutes and council-minutes path entries
            is_minutes_file = "minutes" in filename
            is_minutes_folder = "council-minutes" in url or re.search(r"/\d+\.-[a-z]+/", url)
            if not (is_minutes_file or is_minutes_folder):
                continue

            if url in seen:
                continue
            seen.add(url)

            parsed = _parse_pdf_url(url)
            if parsed:
                meeting_date, meeting_type = parsed
                docs.append(MinutesDocument(
                    council_short_name="cambridge",
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    source_url=url,
                ))
                found += 1

        logger.info("Wayback CDX PDF %d: %d minutes PDFs", year, found)

    return docs


def _extract_minutes_pdf_url(html: str) -> str | None:
    """Extract the minutes PDF href from a meeting page's .meeting-container div."""
    soup = BeautifulSoup(html, "html.parser")

    for container in soup.select(".meeting-document"):
        heading = container.find("h2")
        if heading and heading.get_text(strip=True).lower() == "minutes":
            link = container.select_one("a[href$='.pdf']")
            if link:
                return link["href"]

    # Fallback: any PDF link whose path contains "minutes"
    for link in soup.find_all("a", href=re.compile(r"minutes.*\.pdf$", re.IGNORECASE)):
        return link["href"]

    return None


class CambridgeScraper(BaseCouncilScraper):
    """
    Discovers and downloads City of Cambridge council minutes PDFs.

    Sources:
      - Sitemap (1994–2021, comprehensive)
      - Wayback Machine CDX API (2022–present, fills the JS-rendered gap)
      - Site search (most recent ~10 meetings, live tail)

    Args:
        since_year: Only include meetings from this year onward (default: 2020).
                    The Wayback and site-search sources are always fetched from
                    max(since_year, 2022) and the live tail respectively.
                    Pass None to include all history.
        request_delay: Seconds to sleep between meeting-page requests.
    """

    BASE_URL = BASE_URL

    def __init__(
        self,
        since_year: int | None = 2020,
        request_delay: float = 0.3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.since_year = since_year
        self.request_delay = request_delay

    @property
    def council_short_name(self) -> str:
        return "cambridge"

    def discover(self, client: httpx.Client) -> list[MinutesDocument]:  # noqa: C901
        docs: list[MinutesDocument] = []
        seen_pdf_urls: set[str] = set()

        post_start = max(self.since_year or 0, _SITEMAP_MAX_YEAR + 1)
        post_end = date.today().year

        # ------------------------------------------------------------------
        # Source 2: Playwright for 2022+ (returns MinutesDocuments directly
        # with PDF URLs already resolved — no HTTP page-fetch needed).
        # ------------------------------------------------------------------
        playwright_docs: list[MinutesDocument] = []
        if post_start <= post_end:
            playwright_docs = _collect_from_playwright(
                post_start, post_end, self.request_delay
            )
            if playwright_docs:
                logger.info(
                    "Playwright found %d post-2021 minutes PDFs", len(playwright_docs)
                )
            else:
                logger.info(
                    "Playwright found no docs; will fall back to Wayback CDX"
                )

        # ------------------------------------------------------------------
        # Collect meeting page URLs for Path A (sitemap + live search).
        # Playwright already handles 2022+ so sitemap covers up to 2021.
        # Site-search catches the very latest meetings as a live tail.
        # ------------------------------------------------------------------
        all_pages: dict[str, tuple[date, str]] = {}
        all_pages.update(_collect_from_sitemap(client, self.since_year))
        all_pages.update(_collect_from_search(client))

        # ------------------------------------------------------------------
        # Path A: fetch each meeting page via httpx and extract the PDF link.
        # ------------------------------------------------------------------
        ordered = sorted(all_pages.items(), key=lambda kv: kv[1][0], reverse=True)
        logger.info("Meeting pages to probe: %d", len(ordered))

        for i, (page_url, (meeting_date, meeting_type)) in enumerate(ordered):
            logger.debug("Fetching meeting page: %s", page_url)
            try:
                resp = client.get(page_url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                level = logging.DEBUG if exc.response.status_code == 404 else logging.WARNING
                logger.log(
                    level,
                    "Skipping %s: %s",
                    page_url.rsplit("/", 1)[-1],
                    exc.response.status_code,
                )
                continue
            except httpx.HTTPError as exc:
                logger.warning("Could not fetch %s: %s", page_url, exc)
                continue

            pdf_href = _extract_minutes_pdf_url(resp.text)
            if not pdf_href:
                logger.debug("No minutes PDF on %s", page_url)
                continue

            pdf_url = pdf_href if pdf_href.startswith("http") else self.BASE_URL + pdf_href
            if pdf_url in seen_pdf_urls:
                continue
            seen_pdf_urls.add(pdf_url)

            docs.append(
                MinutesDocument(
                    council_short_name=self.council_short_name,
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    source_url=pdf_url,
                )
            )

            if self.request_delay and i < len(ordered) - 1:
                time.sleep(self.request_delay)

        # ------------------------------------------------------------------
        # Merge Playwright docs (deduplicating against Path A results).
        # ------------------------------------------------------------------
        for doc in playwright_docs:
            if doc.source_url not in seen_pdf_urls:
                docs.append(doc)
                seen_pdf_urls.add(doc.source_url)

        # ------------------------------------------------------------------
        # Path B: Wayback CDX direct PDF fallback (only when Playwright
        # found nothing — partial coverage is better than nothing).
        # ------------------------------------------------------------------
        if post_start <= post_end and not playwright_docs:
            for doc in _collect_from_wayback_pdfs(client, post_start, post_end):
                if doc.source_url not in seen_pdf_urls:
                    docs.append(doc)
                    seen_pdf_urls.add(doc.source_url)

        logger.info("Discovered %d minutes PDFs total", len(docs))
        return docs
