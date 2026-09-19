"""
Scraper for the City of South Perth (WA) council minutes.

Discovery strategy (confirmed 2026-09-19):

  southperth.wa.gov.au runs on Progress Sitefinity CMS (robots.txt
  disallows /Sitefinity/, /Mvc/, /ResourcePackages/Cosp/MVC; the page's own
  <meta name="Generator" content="Sitefinity 14.4.8153.0 DX">) — a third
  CMS/hosting stack, distinct from both Cambridge (OpenCities/ASP.NET
  WebForms) and Perth (Sitecore behind Cloudflare). Unlike Perth, there is
  no bot-protection challenge here: a plain httpx GET with no browser
  fingerprint returns real rendered content — no Playwright dependency for
  this scraper.

  The single council-meetings page
  (https://southperth.wa.gov.au/about-us/council/council-meetings) renders
  two tables: a "SCHEDULED MEETINGS TABLE" (upcoming; usually undocumented)
  and a "PAST MEETINGS TABLE", paginated **by year** via `?year=YYYY` — a
  whole year's meetings render on one page load regardless of count, no
  within-year pagination to walk. Both tables share one row shape: either a
  bare <tr> (a single meeting) or a <tr><td class="sp-meetings__linked-data">
  wrapping a nested <table> of several meetings held together (typically an
  Agenda Briefing paired with the Ordinary Council Meeting it precedes).
  Every real meeting row — nested or not — has the same four <td>s: date,
  time, meeting-type ("desc"), and a "documents" cell of
  <a class="sp-meetings__doc-link"> items (or "Not yet published", no <a>
  tags at all). Some "desc" cells — confirmed for a Special Council Meeting
  called on a confidential matter — append a free-text purpose statement
  after a <br/>; `_parse_page()` reads only the <strong> text, the actual
  meeting-type name. `_parse_page()` walks every such row uniformly by selecting
  `td.sp-meetings__date` and reading its own parent <tr>'s sibling <td>s,
  rather than distinguishing the two row shapes structurally — a nested
  row's <tr> never contains a further nested table of its own, so
  `tr.find(...)` can't cross into an unrelated meeting's cells.

  Document typing reads the link's VISIBLE LABEL, not the PDF filename —
  the opposite of Perth's and Cambridge's approach, and deliberately so:
  sampling 2007–2026 found PDF filenames on this site are inconsistent
  slugified free text, often missing "minutes"/"agenda" entirely (e.g.
  "2018-annual-electors'-meeting.pdf" is in fact that year's Electors
  Meeting minutes) — but every real minutes/agenda link's RENDERED label
  reliably contains "Minutes" or "Agenda" as a whole word ("Minutes (PDF
  0.6Mb)", "SCM Public Agenda 20260814 (PDF 0.6Mb)", "Agenda OCM (PDF
  0.7Mb)"). Supplementary material — attachment packs (often 100MB+ of
  scanned plans), "Notes and Responses to Questions Taken on Notice",
  informal briefing notes, single-item RAR planning reports — is labelled
  distinctly ("Attachments...", "Minutes Attachment", "Notes...") and is
  deliberately excluded (`_classify_doc_label()`), same intent as Perth's
  Details-list filtering: this project extracts minutes/agenda/addendum
  content, not report attachments.

  Because `document_type` (derived at manifest-write time by
  `BaseCouncilScraper.classify_document_type()`, which reads the PDF
  *filename*, not our label) is load-bearing throughout the downstream
  pipeline (`Meeting.document_type == 'minutes'` gates census counting,
  extraction routing and every confidentiality query), a filename-only
  classification would silently disagree with the label-based type this
  scraper actually determined — exactly the class of silent-wrong-output
  this project has been burned by before. `_tagged_url()` appends a URL
  fragment spelling the label-determined type into what
  classify_document_type() reads as the filename — fragments are never
  sent over HTTP (confirmed: the same technique is already load-bearing in
  `perth.py`'s `_discover_documentdb_legacy()`), so this changes nothing
  about what bytes get downloaded, only what the manifest records.

  Year floor: the live site's per-year archive returns real historical
  content from 2006 onward; every year 2001–2005 queried returns only the
  always-present "scheduled meetings" table (the current year's own
  upcoming-meeting links, not that year's data) — confirmed by hand,
  `_EARLIEST_YEAR = 2006`. The City of South Perth has been a local
  government since 1901; whether earlier records exist anywhere (Wayback,
  a dead pre-Sitefinity CMS, physical archives) is UNRESEARCHED, not
  verified absent — flag as an open gap in `pipeline/PIPELINE.md`, the
  same treatment Perth's pre-2015 stretch got, rather than assumed closed.
"""

import logging
import re
import time
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseCouncilScraper, MinutesDocument

logger = logging.getLogger(__name__)

BASE_URL = "https://southperth.wa.gov.au"
LISTING_PATH = "/about-us/council/council-meetings"
# Earliest year the live site's per-year archive returns real content —
# confirmed by hand 2026-09-19 (see module docstring "Year floor").
_EARLIEST_YEAR = 2006

_ATTACHMENT_LABEL_RE = re.compile(r"\battachment", re.IGNORECASE)
_MINUTES_LABEL_RE = re.compile(r"\bminutes\b", re.IGNORECASE)
_AGENDA_LABEL_RE = re.compile(r"\bagenda\b", re.IGNORECASE)
_ADDENDUM_LABEL_RE = re.compile(r"\baddendum\b", re.IGNORECASE)


def _classify_doc_label(label: str) -> str:
    """Classify a document link's rendered label — see module docstring
    "Document typing". Labels containing "attachment" anywhere, or starting
    with "notes" (informal briefing notes / Q&A responses, not a formal
    agenda), are excluded before the minutes/agenda check even runs, so
    e.g. "Minutes Attachment" and "Notes Council Agenda Briefing" — both
    real labels seen on this site — are correctly dropped despite
    containing "minutes"/"agenda" as substrings.
    """
    stripped = label.strip()
    if _ATTACHMENT_LABEL_RE.search(stripped):
        return "unknown"
    if stripped.lower().startswith("notes"):
        return "unknown"
    if _ADDENDUM_LABEL_RE.search(stripped):
        return "addendum"
    if _MINUTES_LABEL_RE.search(stripped):
        return "minutes"
    if _AGENDA_LABEL_RE.search(stripped):
        return "agenda"
    return "unknown"


def _tagged_url(url: str, doc_type: str, meeting_date: date) -> str:
    """Append a URL fragment spelling *doc_type* — see module docstring
    "Because `document_type`...". Never sent over HTTP; only changes what
    `classify_document_type()` reads as the "filename" at manifest-write
    time.
    """
    return f"{url}#{doc_type}_{meeting_date.isoformat()}.pdf"


def _parse_row_date(text: str) -> date | None:
    # Row dates render as "DD Month YYYY", e.g. "22 September 2026".
    try:
        return datetime.strptime(text.strip(), "%d %B %Y").date()
    except ValueError:
        return None


class SouthPerthScraper(BaseCouncilScraper):
    """
    Discovers and downloads City of South Perth council minutes/agenda PDFs.

    No Playwright needed (module docstring) — `discover()` uses the plain
    httpx `client` `run()` already provides, one GET per year requested.

    Args:
        since_year: Only include meetings from this year onward. `None`
            includes all archived years back to `_EARLIEST_YEAR`.
        request_delay: Seconds to sleep between per-year page fetches.
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
        return "south_perth"

    def discover(self, client: httpx.Client) -> list[MinutesDocument]:
        current_year = date.today().year
        since_year = self.since_year or _EARLIEST_YEAR
        floor = max(since_year, _EARLIEST_YEAR)

        docs: list[MinutesDocument] = []
        seen: set[str] = set()

        for i, year in enumerate(range(current_year, floor - 1, -1)):
            if self.request_delay and i:
                time.sleep(self.request_delay)
            url = f"{BASE_URL}{LISTING_PATH}?year={year}&TopicsSelected="
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Could not fetch %s: %s", url, exc)
                continue
            year_docs = self._parse_page(resp.text)
            for d in year_docs:
                if d.source_url not in seen:
                    seen.add(d.source_url)
                    docs.append(d)

        logger.info("Discovered %d minutes/agenda PDFs total", len(docs))
        return docs

    def _parse_page(self, html: str) -> list[MinutesDocument]:
        soup = BeautifulSoup(html, "html.parser")
        docs: list[MinutesDocument] = []

        for date_td in soup.select("td.sp-meetings__date"):
            tr = date_td.find_parent("tr")
            if tr is None:
                continue
            desc_td = tr.find("td", class_="sp-meetings__desc")
            docs_td = tr.find("td", class_="sp-meetings__documents")
            if not isinstance(desc_td, Tag) or not isinstance(docs_td, Tag):
                continue

            meeting_date = _parse_row_date(date_td.get_text(strip=True))
            if meeting_date is None:
                continue
            # Some rows (Special Council Meetings called for a confidential
            # matter) append a free-text purpose statement after a <br/> —
            # e.g. "Special Council Meeting<br/>The purpose of the meeting
            # is to consider Chief Executive Officer arrangements..."
            # (confirmed 2026-09-19, 10 Aug/16 Apr 2026 rows). Only the
            # <strong> holds the actual meeting-type name.
            desc_strong = desc_td.find("strong")
            meeting_type = (
                desc_strong.get_text(" ", strip=True)
                if desc_strong is not None
                else desc_td.get_text(" ", strip=True)
            )

            for a in docs_td.find_all("a", class_="sp-meetings__doc-link", href=True):
                label = a.get_text(" ", strip=True)
                doc_type = _classify_doc_label(label)
                if doc_type == "unknown":
                    continue
                href = a["href"]
                url = href if href.startswith("http") else BASE_URL + href
                docs.append(
                    MinutesDocument(
                        council_short_name=self.council_short_name,
                        meeting_date=meeting_date,
                        meeting_type=meeting_type,
                        source_url=_tagged_url(url, doc_type, meeting_date),
                    )
                )
        return docs
