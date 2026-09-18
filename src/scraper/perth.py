"""
Scraper for the City of Perth (WA) council minutes.

Discovery strategy (confirmed 2026-09-18, SECOND_COUNCIL_PLAN.md 5.2):

  The City of Perth site runs on Sitecore (robots.txt disallows /sitecore,
  /sitecore_files, /sitecore modules) behind Cloudflare's managed JS
  challenge. Every HTML page — including /sitemap.xml — returns
  Cloudflare's "Just a moment..." interstitial (HTTP 403) to a plain HTTP
  client with no browser fingerprint (httpx, curl). This is a different
  CMS (Sitecore, not OpenCities/ASP.NET WebForms) and a different
  bot-protection product (Cloudflare, not Akamai) than Cambridge, so this
  scraper does NOT subclass CambridgeScraper — see base.py's module
  docstring on not forcing reuse that doesn't fit.

  A headless Chromium session (Playwright) passes the challenge — but only
  on a browser context's *first* navigation. Empirically (tested
  2026-09-18): a second `page.goto()` in the same browser context is
  challenged every time regardless of the delay between requests (12s
  still failed), while a brand-new `browser.launch()` + `new_context()`
  per request passes reliably, back-to-back, with no delay needed. So
  discovery here launches one throwaway browser per HTML page fetched,
  rather than reusing a single page/context across the whole crawl the
  way CambridgeScraper's Playwright source does. Slower (a few seconds of
  browser-launch overhead per page) but the only strategy found that
  actually works against this site's protection.

  PDF media assets themselves (under /-/media/...) are NOT behind the
  challenge — a plain httpx GET succeeds (confirmed: curl -I returns 200
  with no browser UA tricks needed) — so only *discovery* (HTML pages)
  needs Playwright; BaseCouncilScraper.download() / run()'s httpx-based
  download loop is unchanged and used as-is. Fair warning for the actual
  extraction session: some of these PDFs are enormous (a single OCM
  agenda or minutes pack was observed at 200-230MB, evidently full-
  resolution scanned attachments) — worth a note in PIPELINE.md's gaps
  when full scraping starts.

  Two listing shapes:

  1. Current year — https://www.perth.wa.gov.au/council/council-meetings
     lists the current year's meetings across two tables ("upcoming" and
     "past this year"), but its Details column only links back to the
     meeting's own subpage (.../council-meetings/<slug>), not the PDFs
     directly — each subpage must be fetched to get the real Agenda/
     Minutes hrefs.
  2. Prior (archived) years — https://www.perth.wa.gov.au/council/
     council-meetings/<year>-meetings (2015-2017) or
     <year>-council-meetings (2018+), paginated via a `?Meetings=N` query
     param (Sitecore SXA pagination) — these DO embed the real PDF hrefs
     directly in the Details column, so no subpage visit is needed once a
     year has been archived off the main listing.

  Filenames already spell "Agenda"/"Minutes" as literal words in the vast
  majority of cases (e.g. "Agenda---OCM---24-February-2026.pdf",
  "20240229---minutes---no-130---city-of-perth.pdf") — base.py's generic
  classify_document_type() already matches these; no MINUTES_SHORTHAND_RE /
  AGENDA_SHORTHAND_RE override is needed.

  Each meeting's Details list also carries non-meeting support docs (audio
  recordings, presentations, registration forms, "Table of Report
  Changes", agenda-briefing-session "Notes" which are workshop notes, not
  formal minutes) labelled distinctly from "Agenda"/"Minutes" in the same
  list. Rather than Cambridge's NOISE_PATTERNS_RE approach (needed because
  its accordion mixes meeting and non-meeting PDFs with no structural
  label), discovery here simply keeps only hrefs classify_document_type()
  resolves to a real type (minutes/agenda/addendum/briefing_notes) and
  drops "unknown" outright — the structured Details list makes the
  keyword/date fallback in is_meeting_document() unnecessary.
"""

import logging
import time
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseCouncilScraper, MinutesDocument

logger = logging.getLogger(__name__)

BASE_URL = "https://www.perth.wa.gov.au"
LISTING_PATH = "/council/council-meetings"
# Earliest year-archive page confirmed to exist (found via the main
# listing page's own "past years" links, 2026-09-18).
_EARLIEST_ARCHIVE_YEAR = 2015

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _year_archive_slug(year: int) -> str:
    # 2015-2017 use "<year>-meetings"; 2018+ use "<year>-council-meetings"
    # — confirmed by hand from the year-archive links on the main listing
    # page; no documented reason for the split, just a CMS-authoring
    # inconsistency that predates this scraper.
    return f"{year}-meetings" if year <= 2017 else f"{year}-council-meetings"


def _parse_row_date(text: str) -> date | None:
    # Row dates render as "DD Mon YY", e.g. "24 Feb 26".
    try:
        return datetime.strptime(text.strip(), "%d %b %y").date()
    except ValueError:
        return None


def _fetch_html(pw, url: str, attempts: int = 3, wait_s: float = 4.0) -> tuple[str | None, str | None]:
    """Fetch *url*'s rendered HTML past Cloudflare's managed challenge.

    Launches a fresh browser + context for every attempt — see module
    docstring: reusing one context across navigations gets challenged on
    the second request every time, but a brand-new context passes
    reliably. Returns (html, title); (None, None) if every attempt was
    challenged or errored.
    """
    for attempt in range(attempts):
        browser = None
        try:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_BROWSER_UA,
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(wait_s)
            title = page.title()
            if "Just a moment" in title:
                logger.info("Cloudflare challenge on %s, retrying (%d/%d)", url, attempt + 1, attempts)
            else:
                html = page.content()
                return html, title
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch failed (%s), attempt %d/%d: %s", url, attempt + 1, attempts, exc)
        finally:
            if browser is not None:
                browser.close()
        time.sleep(2)
    return None, None


def _extract_rows(html: str) -> list[tuple[date, str, str, Tag | None]]:
    """Parse every meeting row out of a listing page's `.page-table`
    component(s). Returns (meeting_date, meeting_type, meeting_page_url,
    details_cell) — `details_cell` is the row's 4th <td> (may or may not
    contain direct PDF links depending on which listing shape this is).
    """
    soup = BeautifulSoup(html, "html.parser")
    rows_out: list[tuple[date, str, str, Tag | None]] = []
    for table in soup.select(".page-table"):
        for tr in table.select("tbody tr"):
            date_cells = tr.select("td.field-meetingdate .tablesaw-cell-content")
            if not date_cells:
                continue
            meeting_date = _parse_row_date(date_cells[0].get_text())
            if meeting_date is None:
                continue
            meeting_link = tr.select_one("td:nth-of-type(3) a[href]")
            if meeting_link is None:
                continue
            meeting_type = meeting_link.get_text(strip=True)
            meeting_page_url = meeting_link["href"]
            if not meeting_page_url.startswith("http"):
                meeting_page_url = BASE_URL + meeting_page_url
            details_cell = tr.select_one("td:nth-of-type(4)")
            rows_out.append((meeting_date, meeting_type, meeting_page_url, details_cell))
    return rows_out


def _pdf_docs_from(
    container: Tag,
    meeting_date: date,
    meeting_type: str,
    classify,
) -> list[MinutesDocument]:
    """Collect MinutesDocuments from every classifiable PDF link under
    *container* (a row's Details cell, or a whole meeting-subpage soup).
    Drops anything classify_document_type() can't positively identify —
    see module docstring on why that's sufficient noise filtering here.
    """
    docs = []
    for a in container.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        url = href if href.startswith("http") else BASE_URL + href
        if classify(url) == "unknown":
            continue
        docs.append(
            MinutesDocument(
                council_short_name="perth",
                meeting_date=meeting_date,
                meeting_type=meeting_type,
                source_url=url,
            )
        )
    return docs


class PerthScraper(BaseCouncilScraper):
    """
    Discovers and downloads City of Perth council minutes/agenda PDFs.

    Every HTML page on perth.wa.gov.au is behind Cloudflare's managed
    challenge, so discover() drives its own headless-Chromium fetches
    (one throwaway browser per page — see module docstring) rather than
    the httpx `client` argument `run()` passes in. That client is still
    used, unmodified, for the actual PDF downloads afterward — those are
    not challenge-protected.

    Args:
        since_year: Only include meetings from this year onward. `None`
            includes all archived years back to `_EARLIEST_ARCHIVE_YEAR`.
        request_delay: Seconds to sleep between page fetches. Not needed
            to dodge the Cloudflare challenge itself (a fresh browser
            context handles that), but kept as a polite pacing knob.
    """

    BASE_URL = BASE_URL

    def __init__(
        self,
        since_year: int | None = None,
        request_delay: float = 0.5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.since_year = since_year
        self.request_delay = request_delay

    @property
    def council_short_name(self) -> str:
        return "perth"

    def discover(self, client: httpx.Client) -> list[MinutesDocument]:  # noqa: C901
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "The Perth scraper requires Playwright "
                "(pip install '.[browser]' && playwright install chromium) — "
                "every HTML page on this site is behind a Cloudflare JS "
                "challenge that a plain HTTP client cannot pass."
            ) from exc

        current_year = date.today().year
        since_year = self.since_year or _EARLIEST_ARCHIVE_YEAR

        docs: list[MinutesDocument] = []
        seen: set[str] = set()

        with sync_playwright() as pw:
            for year in range(current_year, since_year - 1, -1):
                if year == current_year:
                    year_docs = self._discover_current_year(pw)
                else:
                    year_docs = self._discover_archive_year(pw, year)
                for d in year_docs:
                    if d.source_url not in seen:
                        seen.add(d.source_url)
                        docs.append(d)

        logger.info("Discovered %d minutes/agenda PDFs total", len(docs))
        return docs

    def _discover_current_year(self, pw) -> list[MinutesDocument]:
        """The current year has no archive page yet — its listing page only
        links to each meeting's own subpage, which must be visited to find
        the real PDF hrefs (the listing's own Details column just repeats
        a link back to that subpage, labelled "Agenda & Minutes")."""
        url = BASE_URL + LISTING_PATH
        html, _title = _fetch_html(pw, url)
        if html is None:
            logger.warning("Could not load %s past the Cloudflare challenge", url)
            return []
        rows = _extract_rows(html)
        logger.info("Current-year listing (%d): %d meeting rows", date.today().year, len(rows))

        docs: list[MinutesDocument] = []
        for i, (meeting_date, meeting_type, meeting_page_url, _details) in enumerate(rows):
            if self.request_delay and i:
                time.sleep(self.request_delay)
            sub_html, sub_title = _fetch_html(pw, meeting_page_url)
            if sub_html is None:
                logger.warning("Could not load meeting page %s", meeting_page_url)
                continue
            sub_rows = _extract_rows(sub_html)
            # Meeting subpages don't reuse the listing's .page-table
            # wrapper — their Details list lives under .meeting-wrapper /
            # .meeting-detail-list instead — so fall back to scanning the
            # whole page for classifiable PDF links when no table row
            # shape is found.
            container: Tag = (
                sub_rows[0][3] if (sub_rows and sub_rows[0][3] is not None)
                else BeautifulSoup(sub_html, "html.parser")
            )
            docs.extend(
                _pdf_docs_from(container, meeting_date, meeting_type, self.classify_document_type)
            )
        return docs

    def _discover_archive_year(self, pw, year: int) -> list[MinutesDocument]:
        slug = _year_archive_slug(year)
        url = f"{BASE_URL}{LISTING_PATH}/{slug}"
        html, title = _fetch_html(pw, url)
        if html is None:
            logger.warning("Could not load %s past the Cloudflare challenge", url)
            return []
        if title and "Page not found" in title:
            logger.info("No archive page for %d (%s) — skipping", year, slug)
            return []

        docs: list[MinutesDocument] = list(self._docs_from_year_html(html, year))

        # Pagination: Sitecore SXA numbers pages via ?Meetings=N.
        soup = BeautifulSoup(html, "html.parser")
        page_nums = [
            int(a.get_text(strip=True))
            for a in soup.select("a.sxa-paginationnumber")
            if a.get_text(strip=True).isdigit()
        ]
        max_page = max(page_nums) if page_nums else 1

        for n in range(2, max_page + 1):
            if self.request_delay:
                time.sleep(self.request_delay)
            page_url = f"{url}?Meetings={n}"
            page_html, _t = _fetch_html(pw, page_url)
            if page_html is None:
                logger.warning("Could not load %s", page_url)
                continue
            docs.extend(self._docs_from_year_html(page_html, year))

        return docs

    def _docs_from_year_html(self, html: str, year: int) -> list[MinutesDocument]:
        docs = []
        for meeting_date, meeting_type, _page_url, details_cell in _extract_rows(html):
            if meeting_date.year != year or details_cell is None:
                continue
            docs.extend(
                _pdf_docs_from(details_cell, meeting_date, meeting_type, self.classify_document_type)
            )
        return docs
