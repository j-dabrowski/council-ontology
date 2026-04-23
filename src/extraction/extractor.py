"""
LLM extraction pipeline: PDF text → structured ExtractedMeeting.

Uses claude-opus-4-6 with structured outputs (messages.parse) to extract
entities from council meeting minutes text.
"""

import logging
import re
from datetime import date
from pathlib import Path

import anthropic
from pypdf import PdfReader
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .schemas import ExtractedMeeting

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

#_MODEL = "claude-opus-4-6"
#_MODEL = "claude-sonnet-4-6"
_MODEL = "claude-haiku-4-5-20251001"

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august"
    r"|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b",
    re.IGNORECASE,
)


def _parse_date_from_text(text: str) -> "date | None":
    """Best-effort: extract the first plausible meeting date from raw text."""
    m = _DATE_RE.search(text[:3000])
    if not m:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None

_SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8").strip()


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from a PDF file using pypdf."""
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _chunk_text(text: str, max_chars: int = 80_000) -> list[str]:
    """
    Split text into chunks small enough for a single API call.
    Tries to break at paragraph boundaries.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Find a paragraph break before the limit
        split_pos = text.rfind("\n\n", 0, max_chars)
        if split_pos == -1:
            split_pos = max_chars
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    return chunks


class MinutesExtractor:
    """
    Extracts structured entities from council minutes text using Claude.

    Usage::

        extractor = MinutesExtractor()
        result = extractor.extract(minutes_text)
        # result is an ExtractedMeeting Pydantic model
    """

    def __init__(self, api_key: str | None = None, model: str = _MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def extract(self, text: str, source_hint: str = "", council_name: str | None = None, meeting_date_hint: str | None = None) -> ExtractedMeeting:
        """
        Extract structured data from minutes text.

        For very long documents the text is chunked and the first chunk is used
        (future: merge multi-chunk results).

        Args:
            text: Full text of the meeting minutes.
            source_hint: Optional label for logging (e.g. filename).
            council_name: Known council name to include as a hint for the model.

        Returns:
            ExtractedMeeting Pydantic model.
        """
        chunks = _chunk_text(text)
        if len(chunks) > 1:
            logger.warning(
                "%s: text truncated to first chunk (%d/%d chars)",
                source_hint or "document",
                len(chunks[0]),
                len(text),
            )

        hints = []
        if council_name:
            hints.append(f"Council: {council_name}")
        if meeting_date_hint:
            hints.append(f"Meeting date: {meeting_date_hint}")
        hint = ("\n".join(hints) + "\n\n") if hints else ""
        user_content = (
            f"{hint}Extract all entities from the following council meeting minutes:\n\n"
            f"---\n{chunks[0]}\n---"
        )

        logger.info(
            "Calling Claude (%s) for extraction%s",
            self._model,
            f" [{source_hint}]" if source_hint else "",
        )

        # Stream with a high token limit to avoid truncated JSON.
        # messages.parse() is avoided: our nested schema exceeds the API's
        # compiled-grammar size limit for strict structured output.
        # Adaptive thinking is only supported on Opus and Sonnet, not Haiku.
        _supports_thinking = "haiku" not in self._model.lower()

        @retry(
            retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.APIStatusError)),
            wait=wait_exponential(multiplier=1, min=4, max=30),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        def _call_api() -> str:
            kwargs: dict = dict(
                model=self._model,
                max_tokens=64_000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            if _supports_thinking:
                kwargs["thinking"] = {"type": "adaptive"}
            with self._client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
            return next(b.text for b in msg.content if b.type == "text")

        raw = _call_api()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
        try:
            result = ExtractedMeeting.model_validate_json(raw)
        except Exception as exc:
            logger.error(
                "PARSE_FAIL[%s]: %.4000s",
                source_hint or "unknown",
                raw,
            )
            exc.raw_llm_response = raw  # type: ignore[attr-defined]
            raise
        # Override with known context if Claude omitted these fields
        overrides: dict = {}
        if council_name and not result.council_name:
            overrides["council_name"] = council_name
        if not result.meeting_date:
            if meeting_date_hint:
                overrides["meeting_date"] = date.fromisoformat(meeting_date_hint)
            else:
                parsed = _parse_date_from_text(chunks[0])
                if parsed:
                    overrides["meeting_date"] = parsed
        if overrides:
            result = result.model_copy(update=overrides)
        logger.info(
            "Extracted: %d motions, %d councillors present",
            len(result.motions),
            len(result.councillors_present),
        )
        return result

    def extract_from_pdf(self, pdf_path: Path, council_name: str | None = None, meeting_date_hint: str | None = None) -> ExtractedMeeting:
        """Convenience method: extract text from PDF then run extraction."""
        logger.info("Reading PDF: %s", pdf_path)
        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            raise ValueError(f"No text extracted from {pdf_path}")
        return self.extract(text, source_hint=pdf_path.name, council_name=council_name, meeting_date_hint=meeting_date_hint)


# ---------------------------------------------------------------------------
# Persistence helpers: write extraction results into the database
# ---------------------------------------------------------------------------


def _get_or_create_councillor(session, given_name: str, family_name: str):
    from src.models import Councillor

    slug = re.sub(r"[^a-z0-9]+", "-", f"{given_name}-{family_name}".lower()).strip("-")
    obj = session.query(Councillor).filter_by(slug=slug).first()
    if obj:
        return obj
    obj = Councillor(given_name=given_name, family_name=family_name, slug=slug)
    session.add(obj)
    session.flush()
    return obj


def save_extraction(session, council_id: int, extracted: ExtractedMeeting, pdf_path: Path | None = None) -> int:
    """
    Persist an ExtractedMeeting into the database.

    Returns the Meeting.id of the created record.
    """
    if not extracted.meeting_date:
        raise ValueError("meeting_date is required but could not be determined")
    from src.models import (
        ApplicationStatus,
        CommunitySubmission,
        Meeting,
        Motion,
        MotionOutcome,
        PlanningApplication,
        Site,
        Vote,
        VoteChoice,
    )

    # Upsert meeting
    meeting = (
        session.query(Meeting)
        .filter_by(council_id=council_id, meeting_date=extracted.meeting_date)
        .first()
    )
    if not meeting:
        meeting = Meeting(
            council_id=council_id,
            meeting_date=extracted.meeting_date,
            meeting_type=extracted.meeting_type,
            location=extracted.location,
        )
        session.add(meeting)

    if pdf_path and not meeting.minutes_pdf_path:
        meeting.minutes_pdf_path = str(pdf_path)

    session.flush()

    for em in extracted.motions:
        motion = Motion(
            meeting_id=meeting.id,
            item_number=em.item_number,
            title=em.title or em.item_number or "",
            description=em.description,
            motion_text=em.motion_text,
            outcome=MotionOutcome(em.outcome) if em.outcome else None,
            votes_for=em.votes_for,
            votes_against=em.votes_against,
            votes_abstain=em.votes_abstain,
            tags=",".join(em.tags) if em.tags else None,
        )

        if em.moved_by:
            motion.moved_by = _get_or_create_councillor(
                session, em.moved_by.given_name, em.moved_by.family_name
            )
        if em.seconded_by:
            motion.seconded_by = _get_or_create_councillor(
                session, em.seconded_by.given_name, em.seconded_by.family_name
            )

        session.add(motion)
        session.flush()

        # Individual votes
        for ev in em.individual_votes:
            councillor = _get_or_create_councillor(
                session, ev.councillor_given_name, ev.councillor_family_name
            )
            vote = Vote(
                motion_id=motion.id,
                councillor_id=councillor.id,
                choice=VoteChoice(ev.choice),
                declared_interest=ev.declared_interest,
                interest_description=ev.interest_description,
            )
            session.add(vote)

        # Planning application
        if em.planning_application:
            ep = em.planning_application

            site = None
            if ep.site_address:
                site = session.query(Site).filter_by(
                    council_id=council_id, address=ep.site_address
                ).first()
                if not site:
                    site = Site(council_id=council_id, address=ep.site_address)
                    session.add(site)
                    session.flush()

            app = PlanningApplication(
                motion_id=motion.id,
                site_id=site.id if site else None,
                reference_number=ep.reference_number,
                applicant_name=ep.applicant_name,
                description=ep.description,
                status=ApplicationStatus(ep.status) if ep.status else None,
                estimated_value=ep.estimated_value,
            )
            session.add(app)
            session.flush()

            for es in ep.community_submissions:
                submission = CommunitySubmission(
                    application_id=app.id,
                    submitter_name=es.submitter_name,
                    submitter_type=es.submitter_type,
                    position=es.position,
                    summary=es.summary,
                )
                session.add(submission)

    session.commit()
    logger.info("Saved meeting id=%d with %d motions", meeting.id, len(extracted.motions))
    return meeting.id
