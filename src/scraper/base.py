"""
Abstract base scraper. Each council gets a concrete subclass.
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


import re as _re

# Filename patterns that confirm a PDF is a meeting minute.
# Cambridge shorthand: YYYY_MM_DD followed by optional suffix letter(s) then 'm'.
_MINUTES_SHORTHAND = _re.compile(r"\d{4}_\d{2}_\d{2}[a-z]*m\.pdf$")
# Agenda shorthand: ends in 'a' (but not 'dva' which is a DA-variance attachment).
# Explicit list of safe suffixes to avoid false-positives:
#   a   = agenda
#   cra = committee-report agenda
#   scma = special council meeting agenda
_AGENDA_SHORTHAND = _re.compile(r"\d{4}_\d{2}_\d{2}(cra|scma?|a)\.pdf$")

# Filename patterns that identify known non-meeting support documents.
# These are downloaded alongside the main meeting PDFs but are individual DA
# reports, item attachments, or public notices — not meeting records.
_NOISE_PATTERNS = _re.compile(
    r"^dv\d{2}_"               # individual development-application reports
    r"|attachment.to.item"      # item attachment PDFs
    r"|cr-item-attachment"      # committee-report item attachments
    r"|-dva\.pdf$"              # development-variance agenda (standalone DA doc)
    r"|_dva\.pdf$"
    r"|public.notice"           # public notices (not meeting minutes)
    r"|question.register"       # public question registers
)


def classify_document_type(url: str) -> str:
    """
    Infer document type from the PDF filename portion of a URL.

    Checks only the filename (last path segment), not the directory path,
    to avoid false matches from folder names like 'aaa-agenda-and-minutes'.

    Returns one of: 'minutes', 'agenda', 'addendum', 'briefing_notes', 'unknown'.
    """
    fname = url.rstrip("/").rsplit("/", 1)[-1].lower()
    if "minutes" in fname:
        return "minutes"
    if "agenda" in fname:
        return "agenda"
    if "addendum" in fname:
        return "addendum"
    if "briefing-forum" in fname or "briefing-notes" in fname or \
       "briefing_forum" in fname or "briefing_notes" in fname:
        return "briefing_notes"
    # Shorthand filename conventions used by Cambridge before the CMS migration.
    if _MINUTES_SHORTHAND.search(fname):
        return "minutes"
    if _AGENDA_SHORTHAND.search(fname):
        return "agenda"
    return "unknown"


_MEETING_KEYWORD_RE = _re.compile(
    r"\b(council|ordinary|special|electors?|agm|committee|briefing|scm|sca|scma)\b"
)

def is_meeting_document(url: str) -> bool:
    """
    Return True if the PDF URL looks like a meeting document (minutes, agenda,
    addendum, briefing notes) rather than a support attachment.

    Used by scrapers to filter out individual DA reports, item attachments,
    and other non-meeting PDFs that are linked from the same accordion.
    """
    fname = url.rstrip("/").rsplit("/", 1)[-1].lower()
    if _NOISE_PATTERNS.search(fname):
        return False
    doc_type = classify_document_type(url)
    # Accept anything the classifier can positively identify.
    if doc_type != "unknown":
        return True
    # For unknown filenames: accept if the name contains council/meeting keywords
    # or a date-like component in any of the naming conventions Cambridge has used.
    # Only reject files with no such signal — those are purely descriptive support docs.
    has_keyword = bool(_MEETING_KEYWORD_RE.search(fname))
    has_date = bool(
        _re.search(r"\d{4}[_-]\d{1,2}[_-]\d{1,2}", fname)   # YYYY-M-D or YYYY-MM-DD
        or _re.search(r"\d{1,2}[_-]\d{1,2}[_-]\d{4}", fname)  # D-M-YYYY or DD-MM-YYYY
        or _re.search(r"\d{1,2}[_-][a-z]{3,}[_-]\d{2,4}", fname)  # D-Month-YY or D-Month-YYYY
    )
    return has_keyword or has_date

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


@dataclass
class MinutesDocument:
    """Represents a discovered minutes PDF before or after download."""

    council_short_name: str
    meeting_date: date
    meeting_type: str
    source_url: str
    local_path: Path | None = None
    # Populated after text extraction
    text: str | None = None


@dataclass
class ScraperResult:
    documents: list[MinutesDocument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseCouncilScraper(ABC):
    """
    Skeleton for a council minutes scraper.

    Subclasses must implement:
      - `discover()` — return a list of MinutesDocument (URLs found on the minutes page)
      - `council_short_name` property

    The `run()` method calls discover() then downloads each PDF.
    """

    def __init__(
        self,
        raw_dir: Path = RAW_DIR,
        timeout: float = 30.0,
        headers: dict | None = None,
    ) -> None:
        self.raw_dir = raw_dir
        self.timeout = timeout
        self.headers = headers or {
            "User-Agent": (
                "council-ontology-bot/0.1 "
                "(research; contact: research@example.com)"
            )
        }
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def council_short_name(self) -> str: ...

    @abstractmethod
    def discover(self, client: httpx.Client) -> list[MinutesDocument]:
        """
        Fetch the council's minutes index page and return a list of
        MinutesDocument objects, one per PDF link found.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def _dest_dir(self) -> Path:
        d = self.raw_dir / self.council_short_name.lower().replace(" ", "_")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _url_to_filename(self, url: str) -> str:
        digest = hashlib.md5(url.encode()).hexdigest()[:8]
        suffix = url.split("?")[0].rsplit(".", 1)[-1]
        suffix = suffix if suffix.lower() in {"pdf", "docx", "html"} else "pdf"
        return f"{digest}.{suffix}"

    def _manifest_path(self) -> Path:
        return self._dest_dir() / "manifest.json"

    def _load_manifest(self) -> dict:
        p = self._manifest_path()
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        self._manifest_path().write_text(json.dumps(manifest, indent=2))

    def download(
        self,
        doc: MinutesDocument,
        client: httpx.Client,
        manifest: dict | None = None,
    ) -> MinutesDocument:
        """Download a PDF to disk; set doc.local_path. Skips if already present.

        If *manifest* is provided (a dict loaded by the caller), it is updated
        in-place but NOT written to disk — the caller is responsible for saving
        it once after all downloads complete.  If *manifest* is None the legacy
        per-call read/write behaviour is used (kept for callers that invoke
        download() directly).
        """
        dest = self._dest_dir() / self._url_to_filename(doc.source_url)
        if dest.exists():
            logger.debug("Already downloaded: %s", dest)
            doc.local_path = dest
        else:
            logger.info("Downloading %s → %s", doc.source_url, dest.name)
            try:
                resp = client.get(doc.source_url, follow_redirects=True)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                doc.local_path = dest
            except httpx.HTTPError as exc:
                logger.warning("Failed to download %s: %s", doc.source_url, exc)

        if doc.local_path:
            entry = {
                "meeting_date": doc.meeting_date.isoformat(),
                "meeting_type": doc.meeting_type,
                "source_url": doc.source_url,
                "document_type": classify_document_type(doc.source_url),
            }
            if manifest is not None:
                manifest[dest.name] = entry
            else:
                m = self._load_manifest()
                m[dest.name] = entry
                self._save_manifest(m)

        return doc

    def run(self, download_pdfs: bool = True) -> ScraperResult:
        result = ScraperResult()
        with httpx.Client(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        ) as client:
            try:
                docs = self.discover(client)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"discover() failed: {exc}")
                logger.exception("discover() failed")
                return result

            result.documents = docs
            logger.info("Discovered %d document(s)", len(docs))

            if download_pdfs:
                # Load manifest once; update in memory; save once at the end.
                manifest = self._load_manifest()
                for doc in docs:
                    try:
                        self.download(doc, client, manifest=manifest)
                    except Exception as exc:  # noqa: BLE001
                        result.errors.append(f"download failed for {doc.source_url}: {exc}")
                self._save_manifest(manifest)

        return result
