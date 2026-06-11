"""
Pydantic schemas for LLM extraction output.

Validators are deliberately lenient — Claude's natural output varies:
  - Councillor names may arrive as "Cr John Smith" strings or objects
  - Votes may arrive as {"for": [...], "against": [...]} dicts or lists
  - Enum values may be uppercase ("CARRIED") or sentence-case
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TITLES = re.compile(
    r"^\s*(Cr\.?|Councillor|Mayor|Deputy\s+Mayor|Presiding\s+Member|"
    r"Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s+",
    re.IGNORECASE,
)


def _parse_name_string(name: str) -> tuple[str, str]:
    """
    Split 'Cr John Smith' → ('John', 'Smith'), best-effort.
    Single-word names after title stripping are treated as family names
    (e.g. 'Cr Barlow' → ('', 'Barlow')).
    """
    name = _TITLES.sub("", name).strip()
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return "", parts[0] if parts else name


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class ExtractedCouncillor(BaseModel):
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    role: Optional[str] = None
    ward: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_string(cls, v: Any) -> Any:
        """Accept a bare name string like 'Cr John Smith'."""
        if isinstance(v, str):
            given, family = _parse_name_string(v)
            return {"given_name": given or None, "family_name": family or None}
        return v

    @model_validator(mode="after")
    def normalise_names(self) -> "ExtractedCouncillor":
        """If only one name field is set, ensure it's family_name (conventional for single names)."""
        if self.family_name is None and self.given_name is not None:
            self.family_name = self.given_name
            self.given_name = None
        return self


class ExtractedVote(BaseModel):
    councillor_given_name: Optional[str] = None
    councillor_family_name: Optional[str] = None

    @model_validator(mode="after")
    def normalise_names(self) -> "ExtractedVote":
        if self.councillor_family_name is None and self.councillor_given_name is not None:
            self.councillor_family_name = self.councillor_given_name
            self.councillor_given_name = None
        return self
    choice: Literal["for", "against", "abstain", "absent"]
    declared_interest: bool = False
    interest_description: Optional[str] = None

    @field_validator("choice", mode="before")
    @classmethod
    def normalise_choice(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class ExtractedCommunitySubmission(BaseModel):
    submitter_name: Optional[str] = None
    submitter_type: Optional[Literal["individual", "organisation", "business"]] = None
    position: Optional[Literal["support", "object", "neutral"]] = None
    summary: Optional[str] = None

    @field_validator("submitter_type", "position", mode="before")
    @classmethod
    def normalise_lower(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class ExtractedPlanningApplication(BaseModel):
    reference_number: Optional[str] = None
    site_address: Optional[str] = None
    applicant_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[
        Literal["pending", "approved", "refused", "deferred", "withdrawn", "appealed"]
    ] = None
    estimated_value: Optional[float] = None
    community_submissions: list[ExtractedCommunitySubmission] = Field(default_factory=list)
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class ExtractedPublicQuestion(BaseModel):
    questioner_name: Optional[str] = None
    question_summary: Optional[str] = None
    response_summary: Optional[str] = None
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedDeputation(BaseModel):
    presenter_name: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedPetition(BaseModel):
    subject: Optional[str] = None
    presented_by: Optional[str] = None
    signatory_count: Optional[int] = None
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("signatory_count", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return int(v.replace(",", "").strip())
            except ValueError:
                return None
        return v


class ExtractedAppointment(BaseModel):
    councillor: Optional[ExtractedCouncillor] = None
    role: Optional[str] = None
    body_name: Optional[str] = None
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedCommitteeReport(BaseModel):
    committee_name: Optional[str] = None
    item_count: Optional[int] = None
    summary: Optional[str] = None
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedBudgetItem(BaseModel):
    item_number: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    is_confidential: bool = False
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return float(v.replace(",", "").replace("$", "").strip())
            except ValueError:
                return None
        return v


class ExtractedInterestDeclaration(BaseModel):
    councillor: Optional[ExtractedCouncillor] = None
    interest_type: Optional[Literal["financial", "impartiality", "proximity", "other"]] = None
    description: Optional[str] = None
    item_reference: Optional[str] = None
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("interest_type", mode="before")
    @classmethod
    def normalise_lower(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v


class ExtractedTender(BaseModel):
    reference_number: Optional[str] = None
    description: Optional[str] = None
    awarded_to: Optional[str] = None
    amount: Optional[float] = None
    is_confidential: bool = False
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return float(v.replace(",", "").replace("$", "").strip())
            except ValueError:
                return None
        return v


class ExtractedDelegatedDecision(BaseModel):
    item_number: Optional[str] = None
    description: Optional[str] = None
    officer_title: Optional[str] = None
    is_confidential: bool = False
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedBuildingPermit(BaseModel):
    reference_number: Optional[str] = None
    site_address: Optional[str] = None
    description: Optional[str] = None
    estimated_value: Optional[float] = None
    status: Optional[Literal["approved", "refused", "deferred"]] = None
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("estimated_value", mode="before")
    @classmethod
    def coerce_value(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return float(v.replace(",", "").replace("$", "").strip())
            except ValueError:
                return None
        return v


class ExtractedOtherItem(BaseModel):
    item_number: Optional[str] = None
    item_type: str
    description: str
    is_confidential: bool = False
    source_quotes: list[str] = Field(default_factory=list)


class ExtractedMotion(BaseModel):
    item_number: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    motion_text: Optional[str] = None
    officer_recommendation: Optional[str] = None
    moved_by: Optional[ExtractedCouncillor] = None
    seconded_by: Optional[ExtractedCouncillor] = None
    is_confidential: bool = False
    outcome: Optional[
        Literal["carried", "lost", "withdrawn", "deferred", "lapsed"]
    ] = None
    votes_for: Optional[int] = None
    votes_against: Optional[int] = None
    votes_abstain: Optional[int] = None
    individual_votes: list[ExtractedVote] = Field(default_factory=list)
    planning_application: Optional[ExtractedPlanningApplication] = None
    tags: list[str] = Field(default_factory=list)
    source_quotes: list[str] = Field(default_factory=list)

    @field_validator("votes_for", "votes_against", "votes_abstain", mode="before")
    @classmethod
    def coerce_vote_count(cls, v: Any) -> Any:
        """If Claude returns a list of individual votes instead of a count, use the length."""
        if isinstance(v, list):
            return len(v) or None
        return v

    @field_validator("outcome", mode="before")
    @classmethod
    def normalise_outcome(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.lower().strip()
            for word in ("carried", "lost", "withdrawn", "deferred", "lapsed"):
                if v.startswith(word):
                    return word
            return None  # unrecognised outcome — store as null rather than failing
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v  # type: ignore[return-value]

    @field_validator("individual_votes", mode="before")
    @classmethod
    def coerce_votes_dict(cls, v: Any) -> Any:
        """
        Accept Claude's common dict format:
          {"for": ["Cr Smith", ...], "against": [...], "abstain": [...]}
        and expand it to a list of ExtractedVote-compatible dicts.
        Anything that is not a list or dict is silently dropped.
        """
        if not isinstance(v, (dict, list)):
            return []
        if not isinstance(v, dict):
            return v
        votes = []
        for choice, names in v.items():
            if not isinstance(names, list):
                continue
            choice_norm = choice.lower()
            for name in names:
                given, family = _parse_name_string(str(name))
                votes.append({
                    "councillor_given_name": given,
                    "councillor_family_name": family,
                    "choice": choice_norm,
                })
        return votes


# ---------------------------------------------------------------------------
# Top-level extraction output
# ---------------------------------------------------------------------------


class ExtractedMeeting(BaseModel):
    """
    Everything extracted from a single set of meeting minutes.
    This is the schema Claude must return as JSON.
    """

    document_type: Optional[str] = Field(
        default=None,
        description="Document type: 'minutes', 'agenda', 'addendum', 'briefing_notes', 'unknown'"
    )
    council_name: Optional[str] = Field(
        default=None,
        description="Full official name of the council, e.g. 'City of Cambridge'"
    )
    meeting_type: Optional[str] = Field(
        default=None,
        description="e.g. 'Ordinary Council Meeting', 'Special Meeting', 'Committee Meeting'",
    )
    meeting_date: Optional[date] = Field(default=None, description="Date of the meeting (YYYY-MM-DD)")
    location: Optional[str] = Field(default=None)
    councillors_present: list[ExtractedCouncillor] = Field(default_factory=list)
    councillors_apology: list[ExtractedCouncillor] = Field(default_factory=list)
    motions: list[ExtractedMotion] = Field(default_factory=list)
    public_questions: list[ExtractedPublicQuestion] = Field(default_factory=list)
    deputations: list[ExtractedDeputation] = Field(default_factory=list)
    petitions: list[ExtractedPetition] = Field(default_factory=list)
    appointments: list[ExtractedAppointment] = Field(default_factory=list)
    committee_reports: list[ExtractedCommitteeReport] = Field(default_factory=list)
    budget_items: list[ExtractedBudgetItem] = Field(default_factory=list)
    interest_declarations: list[ExtractedInterestDeclaration] = Field(default_factory=list)
    tenders: list[ExtractedTender] = Field(default_factory=list)
    delegated_decisions: list[ExtractedDelegatedDecision] = Field(default_factory=list)
    building_permits: list[ExtractedBuildingPermit] = Field(default_factory=list)
    other_items: list[ExtractedOtherItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def unwrap_envelope(cls, v: Any) -> Any:
        """
        Handle Claude wrapping output in an envelope at any depth, e.g.:
          {"meeting": {...}}  or  {"data": {"meeting": {...}}}
        Searches recursively for the dict with the most matching meeting fields.
        """
        if not isinstance(v, dict):
            return v
        _MEETING_FIELDS = frozenset({
            "council_name", "meeting_date", "meeting_type", "location",
            "motions", "councillors_present", "councillors_apology", "other_items",
            "public_questions", "deputations", "petitions", "appointments",
            "committee_reports", "budget_items", "interest_declarations",
            "tenders", "delegated_decisions", "building_permits",
        })

        def _score(d: dict) -> int:
            return len(_MEETING_FIELDS & d.keys())

        def _find(d: dict, depth: int = 0) -> "dict | None":
            if depth > 6:
                return None
            best: "dict | None" = None
            best_score = 0
            if _score(d) > best_score:
                best, best_score = d, _score(d)
            for val in d.values():
                if isinstance(val, dict):
                    found = _find(val, depth + 1)
                    if found is not None and _score(found) > best_score:
                        best, best_score = found, _score(found)
            return best if best_score >= 2 else None

        found = _find(v)
        return found if found is not None else v
