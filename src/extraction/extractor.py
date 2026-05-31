"""
LLM extraction pipeline: PDF text → structured ExtractedMeeting.

Uses claude-opus-4-6 with structured outputs (messages.parse) to extract
entities from council meeting minutes text.
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path

import anthropic
from pypdf import PdfReader
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .schemas import ExtractedMeeting

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 80_000

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


def _chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
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


# Entity list fields on ExtractedMeeting that are concatenated across chunks.
# Scalar fields (council_name, meeting_date, meeting_type, location, councillors_*)
# are taken from chunk 0 only.
_ENTITY_LISTS = [
    "motions", "public_questions", "deputations", "petitions", "appointments",
    "committee_reports", "budget_items", "interest_declarations", "tenders",
    "delegated_decisions", "building_permits", "other_items",
]


def _merge_chunk_results(results: list[ExtractedMeeting]) -> ExtractedMeeting:
    """Merge per-chunk extractions: metadata from chunk 0, entity lists concatenated."""
    base = results[0]
    for subsequent in results[1:]:
        update = {f: getattr(base, f) + getattr(subsequent, f) for f in _ENTITY_LISTS}
        base = base.model_copy(update=update)
    return base


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

    def extract(
        self,
        text: str,
        source_hint: str = "",
        council_name: str | None = None,
        meeting_date_hint: str | None = None,
        max_chars: "int | None" = DEFAULT_MAX_CHARS,
    ) -> ExtractedMeeting:
        """
        Extract structured data from minutes text.

        max_chars controls how much of the document is extracted:
          - int (default DEFAULT_MAX_CHARS): truncate to the first max_chars chars
            (single API call, existing behaviour).
          - None: extract the full document in chunks of DEFAULT_MAX_CHARS each,
            merging results (multi-chunk mode, more expensive).

        Args:
            text: Full text of the meeting minutes.
            source_hint: Optional label for logging (e.g. filename).
            council_name: Known council name to include as a hint for the model.
            meeting_date_hint: ISO date string passed as a hint for chunk 0.
            max_chars: Extraction limit. None means full document (multi-chunk).

        Returns:
            ExtractedMeeting Pydantic model.
        """
        if max_chars is not None:
            # Truncated single-chunk mode
            chunk = _chunk_text(text, max_chars)[0]
            if len(text) > len(chunk):
                logger.warning(
                    "%s: truncated to first chunk (%d/%d chars)",
                    source_hint or "document",
                    len(chunk),
                    len(text),
                )
            return self._extract_chunk(
                chunk,
                source_hint=source_hint,
                council_name=council_name,
                meeting_date_hint=meeting_date_hint,
            )

        # Unlimited multi-chunk mode
        chunks = _chunk_text(text, DEFAULT_MAX_CHARS)

        if len(chunks) == 1:
            return self._extract_chunk(
                chunks[0],
                source_hint=source_hint,
                council_name=council_name,
                meeting_date_hint=meeting_date_hint,
            )

        logger.info(
            "%s: %d chunks (%d total chars) — running multi-chunk extraction",
            source_hint or "document",
            len(chunks),
            len(text),
        )
        results: list[ExtractedMeeting] = []
        for i, chunk in enumerate(chunks):
            chunk_hint = f"{source_hint} [{i + 1}/{len(chunks)}]" if source_hint else f"chunk {i + 1}/{len(chunks)}"
            result = self._extract_chunk(
                chunk,
                source_hint=chunk_hint,
                council_name=council_name,
                meeting_date_hint=meeting_date_hint if i == 0 else None,
                chunk_index=i,
                total_chunks=len(chunks),
            )
            results.append(result)

        merged = _merge_chunk_results(results)
        logger.info(
            "%s: merged %d chunks → %d motions, %d councillors present",
            source_hint or "document",
            len(chunks),
            len(merged.motions),
            len(merged.councillors_present),
        )
        return merged

    def _make_user_content(
        self,
        chunk_text: str,
        council_name: str | None = None,
        meeting_date_hint: str | None = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
    ) -> str:
        """Build the user message content for a single chunk."""
        hints = []
        if council_name:
            hints.append(f"Council: {council_name}")
        if meeting_date_hint:
            hints.append(f"Meeting date: {meeting_date_hint}")
        hint = ("\n".join(hints) + "\n\n") if hints else ""

        if chunk_index > 0:
            continuation = (
                f"NOTE: This is part {chunk_index + 1} of {total_chunks} of a long meeting "
                f"minutes document. Meeting metadata (council name, date, type, location, "
                f"councillors present/apology) was already extracted from part 1. "
                f"For this part: set council_name, meeting_date, meeting_type, location, "
                f"councillors_present, and councillors_apology to null/empty — "
                f"extract only the agenda items and entities in this section.\n\n"
            )
        else:
            continuation = ""

        return (
            f"{hint}{continuation}"
            f"Extract all entities from the following council meeting minutes:\n\n"
            f"---\n{chunk_text}\n---"
        )

    def _extract_chunk(
        self,
        chunk_text: str,
        source_hint: str = "",
        council_name: str | None = None,
        meeting_date_hint: str | None = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
    ) -> ExtractedMeeting:
        """Extract from a single chunk of text and return an ExtractedMeeting."""
        user_content = self._make_user_content(
            chunk_text, council_name, meeting_date_hint, chunk_index, total_chunks
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

        # Override with known context if Claude omitted these fields (chunk 0 only)
        if chunk_index == 0:
            overrides: dict = {}
            if council_name and not result.council_name:
                overrides["council_name"] = council_name
            if not result.meeting_date:
                if meeting_date_hint:
                    overrides["meeting_date"] = date.fromisoformat(meeting_date_hint)
                else:
                    parsed = _parse_date_from_text(chunk_text)
                    if parsed:
                        overrides["meeting_date"] = parsed
            if overrides:
                result = result.model_copy(update=overrides)

        logger.info(
            "Extracted chunk %d/%d: %d motions, %d councillors present",
            chunk_index + 1,
            total_chunks,
            len(result.motions),
            len(result.councillors_present),
        )
        return result

    def extract_from_pdf(
        self,
        pdf_path: Path,
        council_name: str | None = None,
        meeting_date_hint: str | None = None,
        max_chars: "int | None" = DEFAULT_MAX_CHARS,
    ) -> "tuple[ExtractedMeeting, str]":
        """Extract text from PDF then run extraction. Returns (result, raw_text)."""
        logger.info("Reading PDF: %s", pdf_path)
        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            raise ValueError(f"No text extracted from {pdf_path}")
        result = self.extract(
            text,
            source_hint=pdf_path.name,
            council_name=council_name,
            meeting_date_hint=meeting_date_hint,
            max_chars=max_chars,
        )
        return result, text


# ---------------------------------------------------------------------------
# Batch API helpers
# ---------------------------------------------------------------------------

    def build_batch_requests(
        self,
        pdfs: "list[Path]",
        max_chars: "int | None",
        council_name: str | None = None,
        manifest: "dict | None" = None,
    ) -> "tuple[list[dict], dict[str, dict]]":
        """
        Build Anthropic batch API request dicts for a list of PDFs.

        Reads each PDF, splits into chunks, and produces one request per chunk.
        Skips PDFs that cannot be read or contain no text.

        Returns:
            requests: list of {"custom_id": str, "params": dict}
            id_map:   {custom_id: {pdf_path, chunk_idx, n_chunks, meeting_date_hint}}
        """
        if manifest is None:
            manifest = {}

        requests: list[dict] = []
        id_map: dict[str, dict] = {}

        for pdf in pdfs:
            meta = manifest.get(pdf.name, {})
            date_hint: "str | None" = meta.get("meeting_date")

            try:
                text = extract_text_from_pdf(pdf)
            except Exception as exc:
                logger.error("Batch build: failed to read %s: %s", pdf.name, exc)
                continue
            if not text.strip():
                logger.warning("Batch build: no text from %s, skipping", pdf.name)
                continue

            if max_chars is not None:
                chunks = [_chunk_text(text, max_chars)[0]]
            else:
                chunks = _chunk_text(text, DEFAULT_MAX_CHARS)

            n = len(chunks)
            for i, chunk in enumerate(chunks):
                cid = f"{pdf.stem}__c{i}of{n}"
                params: dict = dict(
                    model=self._model,
                    max_tokens=64_000,
                    system=_SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": self._make_user_content(
                            chunk,
                            council_name=council_name,
                            meeting_date_hint=date_hint if i == 0 else None,
                            chunk_index=i,
                            total_chunks=n,
                        ),
                    }],
                )
                requests.append({"custom_id": cid, "params": params})
                id_map[cid] = {
                    "pdf_path": str(pdf),
                    "chunk_idx": i,
                    "n_chunks": n,
                    "meeting_date_hint": date_hint if i == 0 else None,
                }

        return requests, id_map

    def submit_batch(self, requests: "list[dict]") -> str:
        """Submit requests to the Anthropic batch API. Returns the batch_id."""
        batch = self._client.messages.batches.create(requests=requests)
        logger.info("Submitted batch %s (%d requests)", batch.id, len(requests))
        return batch.id

    def retrieve_batch_results(
        self,
        batch_id: str,
    ) -> "tuple[str, dict[str, ExtractedMeeting | Exception]]":
        """
        Check batch status and retrieve parsed results if finished.

        Returns (processing_status, {custom_id: ExtractedMeeting | Exception}).
        If processing_status != 'ended', the results dict is empty.
        """
        batch = self._client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            return batch.processing_status, {}

        results: "dict[str, ExtractedMeeting | Exception]" = {}
        for item in self._client.messages.batches.results(batch_id):
            cid = item.custom_id
            if item.result.type == "succeeded":
                raw = next(
                    (b.text for b in item.result.message.content if b.type == "text"),
                    None,
                )
                if raw is None:
                    results[cid] = ValueError("No text block in batch response")
                    continue
                raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
                raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
                try:
                    parsed = ExtractedMeeting.model_validate_json(raw)
                    results[cid] = parsed
                except Exception as exc:
                    exc.raw_llm_response = raw  # type: ignore[attr-defined]
                    results[cid] = exc
            else:
                detail = ""
                try:
                    detail = f": {item.result.error.error.message}"
                except AttributeError:
                    pass
                results[cid] = RuntimeError(f"Batch request {item.result.type}{detail}")

        return "ended", results


# ---------------------------------------------------------------------------
# Persistence helpers: write extraction results into the database
# ---------------------------------------------------------------------------


def _resolve_offset(text: str, quote: str) -> "tuple[int, int] | tuple[None, None]":
    """Return (char_offset, char_length) of the first verbatim occurrence of quote in text.

    Stored as a best-effort convenience for UI/lookup (e.g. highlighting a span).
    Do NOT use char_offset IS NULL as a hallucination signal — validation code
    should normalise both source text and quote at query time before matching.
    """
    if not text or not quote:
        return None, None
    idx = text.find(quote)
    if idx == -1:
        return None, None
    return idx, len(quote)




def _get_or_create_councillor(session, given_name: str, family_name: str):
    from src.models import Councillor

    given_name = given_name or ""
    family_name = family_name or ""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{given_name}-{family_name}".lower()).strip("-")
    obj = session.query(Councillor).filter_by(slug=slug).first()
    if obj:
        return obj
    obj = Councillor(given_name=given_name, family_name=family_name, slug=slug)
    session.add(obj)
    session.flush()
    return obj


def save_extraction(
    session,
    council_id: int,
    extracted: ExtractedMeeting,
    pdf_path: Path | None = None,
    text: str | None = None,
    pdf_url: str | None = None,
) -> int:
    """
    Persist an ExtractedMeeting into the database.

    Returns the Meeting.id of the created record.
    """
    if not extracted.meeting_date:
        raise ValueError("meeting_date is required but could not be determined")
    from src.models import (
        ApplicationStatus,
        Appointment,
        BudgetItem,
        BuildingPermit,
        CommitteeReport,
        CommunitySubmission,
        DelegatedDecision,
        Deputation,
        ExtractionEvidence,
        InterestDeclaration,
        InterestDeclarationType,
        Meeting,
        Motion,
        MotionOutcome,
        OtherItem,
        PermitStatus,
        Petition,
        PlanningApplication,
        PublicQuestion,
        Site,
        Tender,
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
    else:
        # Clear all existing entities so re-extraction doesn't duplicate rows.
        # Must delete in dependency order (children before parents).
        mid = meeting.id
        motion_ids = [r[0] for r in session.query(Motion.id).filter_by(meeting_id=mid)]
        if motion_ids:
            app_ids = [r[0] for r in session.query(PlanningApplication.id).filter(
                PlanningApplication.motion_id.in_(motion_ids)
            )]
            if app_ids:
                session.query(CommunitySubmission).filter(
                    CommunitySubmission.application_id.in_(app_ids)
                ).delete(synchronize_session=False)
            session.query(PlanningApplication).filter(
                PlanningApplication.motion_id.in_(motion_ids)
            ).delete(synchronize_session=False)
            session.query(Vote).filter(
                Vote.motion_id.in_(motion_ids)
            ).delete(synchronize_session=False)
        session.query(Motion).filter_by(meeting_id=mid).delete(synchronize_session=False)
        for _Model in (
            PublicQuestion, Deputation, Petition, Appointment, CommitteeReport,
            BudgetItem, InterestDeclaration, Tender, DelegatedDecision,
            BuildingPermit, OtherItem, ExtractionEvidence,
        ):
            session.query(_Model).filter_by(meeting_id=mid).delete(synchronize_session=False)
        session.flush()
        logger.info("Cleared existing entities for meeting id=%d (re-extraction)", mid)

    if pdf_path and not meeting.minutes_pdf_path:
        meeting.minutes_pdf_path = str(pdf_path)
    if pdf_url:
        meeting.minutes_pdf_url = pdf_url
    if text:
        meeting.minutes_text = text
    meeting.extracted_at = datetime.utcnow()

    session.flush()

    # Closure: insert ExtractionEvidence rows for an entity's source_quotes.
    # char_offset=None when the quote cannot be found verbatim (hallucination flag).
    def _ev(entity_table: str, entity_id: int, source_quotes: list) -> None:
        for quote in source_quotes:
            offset, length = _resolve_offset(text or "", quote)
            session.add(ExtractionEvidence(
                meeting_id=meeting.id,
                entity_table=entity_table,
                entity_id=entity_id,
                quote_text=quote,
                char_offset=offset,
                char_length=length,
            ))

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
        _ev("motions", motion.id, em.source_quotes)

        # Individual votes — deduplicate by councillor (LLM occasionally lists same
        # councillor twice in one motion, violating the UNIQUE(motion_id, councillor_id) constraint)
        seen_councillor_keys: set[str] = set()
        for ev in em.individual_votes:
            key = f"{ev.councillor_given_name or ''}|{ev.councillor_family_name or ''}".lower()
            if key in seen_councillor_keys:
                logger.warning(
                    "Duplicate vote for councillor '%s %s' in motion %s — skipping",
                    ev.councillor_given_name, ev.councillor_family_name, em.item_number,
                )
                continue
            seen_councillor_keys.add(key)
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
            _ev("planning_applications", app.id, ep.source_quotes)

            for es in ep.community_submissions:
                submission = CommunitySubmission(
                    application_id=app.id,
                    submitter_name=es.submitter_name,
                    submitter_type=es.submitter_type,
                    position=es.position,
                    summary=es.summary,
                )
                session.add(submission)

    for eq in extracted.public_questions:
        pq = PublicQuestion(
            meeting_id=meeting.id,
            questioner_name=eq.questioner_name,
            question_summary=eq.question_summary,
            response_summary=eq.response_summary,
        )
        session.add(pq)
        session.flush()
        _ev("public_questions", pq.id, eq.source_quotes)

    for ed in extracted.deputations:
        dep = Deputation(
            meeting_id=meeting.id,
            presenter_name=ed.presenter_name,
            topic=ed.topic,
            summary=ed.summary,
        )
        session.add(dep)
        session.flush()
        _ev("deputations", dep.id, ed.source_quotes)

    for ep in extracted.petitions:
        pet = Petition(
            meeting_id=meeting.id,
            subject=ep.subject,
            presented_by=ep.presented_by,
            signatory_count=ep.signatory_count,
        )
        session.add(pet)
        session.flush()
        _ev("petitions", pet.id, ep.source_quotes)

    for ea in extracted.appointments:
        apt = Appointment(meeting_id=meeting.id, role=ea.role, body_name=ea.body_name)
        if ea.councillor:
            gn = ea.councillor.given_name or ""
            fn = ea.councillor.family_name or ""
            if gn or fn:
                apt.councillor_id = _get_or_create_councillor(session, gn, fn).id
        session.add(apt)
        session.flush()
        _ev("appointments", apt.id, ea.source_quotes)

    for ec in extracted.committee_reports:
        cr = CommitteeReport(
            meeting_id=meeting.id,
            committee_name=ec.committee_name,
            item_count=ec.item_count,
            summary=ec.summary,
        )
        session.add(cr)
        session.flush()
        _ev("committee_reports", cr.id, ec.source_quotes)

    for eb in extracted.budget_items:
        bi = BudgetItem(
            meeting_id=meeting.id,
            item_number=eb.item_number,
            description=eb.description,
            amount=eb.amount,
            is_confidential=eb.is_confidential,
        )
        session.add(bi)
        session.flush()
        _ev("budget_items", bi.id, eb.source_quotes)

    for ei in extracted.interest_declarations:
        decl = InterestDeclaration(
            meeting_id=meeting.id,
            interest_type=InterestDeclarationType(ei.interest_type) if ei.interest_type else None,
            description=ei.description,
            item_reference=ei.item_reference,
        )
        if ei.councillor:
            gn = ei.councillor.given_name or ""
            fn = ei.councillor.family_name or ""
            if gn or fn:
                decl.councillor_id = _get_or_create_councillor(session, gn, fn).id
        session.add(decl)
        session.flush()
        _ev("interest_declarations", decl.id, ei.source_quotes)

    for et in extracted.tenders:
        tender = Tender(
            meeting_id=meeting.id,
            reference_number=et.reference_number,
            description=et.description,
            awarded_to=et.awarded_to,
            amount=et.amount,
            is_confidential=et.is_confidential,
        )
        session.add(tender)
        session.flush()
        _ev("tenders", tender.id, et.source_quotes)

    for ed in extracted.delegated_decisions:
        dd = DelegatedDecision(
            meeting_id=meeting.id,
            item_number=ed.item_number,
            description=ed.description,
            officer_title=ed.officer_title,
            is_confidential=ed.is_confidential,
        )
        session.add(dd)
        session.flush()
        _ev("delegated_decisions", dd.id, ed.source_quotes)

    for ep in extracted.building_permits:
        bp = BuildingPermit(
            meeting_id=meeting.id,
            reference_number=ep.reference_number,
            site_address=ep.site_address,
            description=ep.description,
            estimated_value=ep.estimated_value,
            status=PermitStatus(ep.status) if ep.status else None,
        )
        session.add(bp)
        session.flush()
        _ev("building_permits", bp.id, ep.source_quotes)

    for eo in extracted.other_items:
        oi = OtherItem(
            meeting_id=meeting.id,
            item_number=eo.item_number,
            item_type=eo.item_type,
            description=eo.description,
            is_confidential=eo.is_confidential,
        )
        session.add(oi)
        session.flush()
        _ev("other_items", oi.id, eo.source_quotes)

    session.commit()
    logger.info("Saved meeting id=%d with %d motions", meeting.id, len(extracted.motions))
    return meeting.id
