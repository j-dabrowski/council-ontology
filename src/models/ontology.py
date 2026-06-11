"""
SQLAlchemy ORM models for the council ontology.

Three-layer ontology:
  Semantic  — entities and relationships (Council, Councillor, Site, etc.)
  Kinetic   — actions and their preconditions/consequences (Motion, Vote, PlanningApplication)
  Dynamic   — feedback loops and emergent patterns (Relationship, future: timeseries views)
"""

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class VoteChoice(str, enum.Enum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"
    ABSENT = "absent"


class MotionOutcome(str, enum.Enum):
    CARRIED = "carried"
    LOST = "lost"
    WITHDRAWN = "withdrawn"
    DEFERRED = "deferred"
    LAPSED = "lapsed"


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"
    DEFERRED = "deferred"
    WITHDRAWN = "withdrawn"
    APPEALED = "appealed"


class RelationshipKind(str, enum.Enum):
    # Councillor–councillor
    ALLY = "ally"
    OPPONENT = "opponent"
    COALITION = "coalition"
    # Councillor–site / councillor–applicant
    DECLARED_INTEREST = "declared_interest"
    # Motion–motion
    AMENDS = "amends"
    SUPERSEDES = "supersedes"
    RELATES_TO = "relates_to"
    # Site–planning_application
    SUBJECT_OF = "subject_of"


class InterestDeclarationType(str, enum.Enum):
    FINANCIAL = "financial"
    IMPARTIALITY = "impartiality"
    PROXIMITY = "proximity"
    OTHER = "other"


class PermitStatus(str, enum.Enum):
    APPROVED = "approved"
    REFUSED = "refused"
    DEFERRED = "deferred"


# ---------------------------------------------------------------------------
# Semantic layer — core entities
# ---------------------------------------------------------------------------


class Council(Base):
    __tablename__ = "councils"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(10), default="WA")
    website: Mapped[Optional[str]] = mapped_column(String(500))
    minutes_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="council")
    councillors: Mapped[list["CouncillorTerm"]] = relationship(back_populates="council")
    sites: Mapped[list["Site"]] = relationship(back_populates="council")

    def __repr__(self) -> str:
        return f"<Council {self.short_name}>"


class Councillor(Base):
    """A person who has served on one or more councils."""

    __tablename__ = "councillors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Canonical identifier derived from name for deduplication
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    party: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    terms: Mapped[list["CouncillorTerm"]] = relationship(back_populates="councillor")
    votes: Mapped[list["Vote"]] = relationship(back_populates="councillor")

    def __repr__(self) -> str:
        return f"<Councillor {self.given_name} {self.family_name}>"


class CouncillorTerm(Base):
    """A councillor's tenure on a specific council (ward, role, dates)."""

    __tablename__ = "councillor_terms"
    __table_args__ = (
        UniqueConstraint("councillor_id", "council_id", "term_start", name="uq_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    councillor_id: Mapped[int] = mapped_column(ForeignKey("councillors.id"))
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    ward: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[Optional[str]] = mapped_column(String(100))  # Mayor, Deputy Mayor, etc.
    term_start: Mapped[Optional[date]] = mapped_column(Date)
    term_end: Mapped[Optional[date]] = mapped_column(Date)

    councillor: Mapped["Councillor"] = relationship(back_populates="terms")
    council: Mapped["Council"] = relationship(back_populates="councillors")


class Site(Base):
    """A physical location that appears in planning or other matters."""

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    lot_number: Mapped[Optional[str]] = mapped_column(String(100))
    deposited_plan: Mapped[Optional[str]] = mapped_column(String(50))
    suburb: Mapped[Optional[str]] = mapped_column(String(100))
    zoning: Mapped[Optional[str]] = mapped_column(String(100))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    council: Mapped["Council"] = relationship(back_populates="sites")
    planning_applications: Mapped[list["PlanningApplication"]] = relationship(
        back_populates="site"
    )

    def __repr__(self) -> str:
        return f"<Site {self.address}>"


# ---------------------------------------------------------------------------
# Kinetic layer — actions and events
# ---------------------------------------------------------------------------


class Meeting(Base):
    """A single council meeting (ordinary, special, committee, etc.)."""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    meeting_type: Mapped[str] = mapped_column(String(100), default="Ordinary Council Meeting")
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(300))
    # Source document
    minutes_pdf_url: Mapped[Optional[str]] = mapped_column(String(500))
    minutes_pdf_path: Mapped[Optional[str]] = mapped_column(String(500))
    minutes_text: Mapped[Optional[str]] = mapped_column(Text)
    document_type: Mapped[Optional[str]] = mapped_column(String(20))
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    council: Mapped["Council"] = relationship(back_populates="meetings")
    motions: Mapped[list["Motion"]] = relationship(back_populates="meeting")

    def __repr__(self) -> str:
        return f"<Meeting {self.council_id} {self.meeting_date}>"


class Motion(Base):
    """A formal motion moved at a meeting."""

    __tablename__ = "motions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"))
    item_number: Mapped[Optional[str]] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    moved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("councillors.id"))
    seconded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("councillors.id"))
    outcome: Mapped[Optional[MotionOutcome]] = mapped_column(Enum(MotionOutcome))
    votes_for: Mapped[Optional[int]] = mapped_column(Integer)
    votes_against: Mapped[Optional[int]] = mapped_column(Integer)
    votes_abstain: Mapped[Optional[int]] = mapped_column(Integer)
    # Raw text of the motion as extracted
    motion_text: Mapped[Optional[str]] = mapped_column(Text)
    officer_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    # LLM-assigned topic tags (comma-separated for simplicity)
    tags: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meeting: Mapped["Meeting"] = relationship(back_populates="motions")
    moved_by: Mapped[Optional["Councillor"]] = relationship(foreign_keys=[moved_by_id])
    seconded_by: Mapped[Optional["Councillor"]] = relationship(foreign_keys=[seconded_by_id])
    votes: Mapped[list["Vote"]] = relationship(back_populates="motion")
    planning_applications: Mapped[list["PlanningApplication"]] = relationship(
        back_populates="motion"
    )

    def __repr__(self) -> str:
        return f"<Motion {self.item_number}: {self.title[:60]}>"


class Vote(Base):
    """An individual councillor's vote on a motion."""

    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("motion_id", "councillor_id", name="uq_vote"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    motion_id: Mapped[int] = mapped_column(ForeignKey("motions.id"))
    councillor_id: Mapped[int] = mapped_column(ForeignKey("councillors.id"))
    choice: Mapped[VoteChoice] = mapped_column(Enum(VoteChoice), nullable=False)
    declared_interest: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_description: Mapped[Optional[str]] = mapped_column(Text)

    motion: Mapped["Motion"] = relationship(back_populates="votes")
    councillor: Mapped["Councillor"] = relationship(back_populates="votes")

    def __repr__(self) -> str:
        return f"<Vote councillor={self.councillor_id} motion={self.motion_id} {self.choice}>"


class PlanningApplication(Base):
    """A development application considered at a meeting."""

    __tablename__ = "planning_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    motion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("motions.id"))
    site_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sites.id"))
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    applicant_name: Mapped[Optional[str]] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    application_date: Mapped[Optional[date]] = mapped_column(Date)
    decision_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[ApplicationStatus]] = mapped_column(Enum(ApplicationStatus))
    conditions: Mapped[Optional[str]] = mapped_column(Text)
    appeal_lodged: Mapped[bool] = mapped_column(Boolean, default=False)
    appeal_outcome: Mapped[Optional[str]] = mapped_column(String(200))
    estimated_value: Mapped[Optional[float]] = mapped_column(Float)

    motion: Mapped[Optional["Motion"]] = relationship(back_populates="planning_applications")
    site: Mapped[Optional["Site"]] = relationship(back_populates="planning_applications")
    community_submissions: Mapped[list["CommunitySubmission"]] = relationship(
        back_populates="application"
    )

    def __repr__(self) -> str:
        return f"<PlanningApplication {self.reference_number}>"


class CommunitySubmission(Base):
    """A written submission from the public on a planning application or policy matter."""

    __tablename__ = "community_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[Optional[int]] = mapped_column(ForeignKey("planning_applications.id"))
    motion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("motions.id"))
    submitter_name: Mapped[Optional[str]] = mapped_column(String(300))
    submitter_type: Mapped[Optional[str]] = mapped_column(String(100))  # individual, org, business
    position: Mapped[Optional[str]] = mapped_column(String(20))  # support, object, neutral
    summary: Mapped[Optional[str]] = mapped_column(Text)
    received_date: Mapped[Optional[date]] = mapped_column(Date)

    application: Mapped[Optional["PlanningApplication"]] = relationship(
        back_populates="community_submissions"
    )

    def __repr__(self) -> str:
        return f"<CommunitySubmission {self.submitter_name} {self.position}>"


# ---------------------------------------------------------------------------
# Kinetic layer — meeting sub-items (Level 2 schema fields)
# ---------------------------------------------------------------------------


class PublicQuestion(Base):
    __tablename__ = "public_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    questioner_name: Mapped[Optional[str]] = mapped_column(String(300))
    question_summary: Mapped[Optional[str]] = mapped_column(Text)
    response_summary: Mapped[Optional[str]] = mapped_column(Text)


class Deputation(Base):
    __tablename__ = "deputations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    presenter_name: Mapped[Optional[str]] = mapped_column(String(300))
    topic: Mapped[Optional[str]] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text)


class Petition(Base):
    __tablename__ = "petitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    presented_by: Mapped[Optional[str]] = mapped_column(String(300))
    signatory_count: Mapped[Optional[int]] = mapped_column(Integer)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    councillor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("councillors.id"))
    role: Mapped[Optional[str]] = mapped_column(String(300))
    body_name: Mapped[Optional[str]] = mapped_column(String(300))


class CommitteeReport(Base):
    __tablename__ = "committee_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    committee_name: Mapped[Optional[str]] = mapped_column(String(300))
    item_count: Mapped[Optional[int]] = mapped_column(Integer)
    summary: Mapped[Optional[str]] = mapped_column(Text)


class BudgetItem(Base):
    __tablename__ = "budget_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    item_number: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    amount: Mapped[Optional[float]] = mapped_column(Float)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False)


class InterestDeclaration(Base):
    __tablename__ = "interest_declarations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    councillor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("councillors.id"))
    interest_type: Mapped[Optional[InterestDeclarationType]] = mapped_column(
        Enum(InterestDeclarationType)
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    item_reference: Mapped[Optional[str]] = mapped_column(String(200))


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    awarded_to: Mapped[Optional[str]] = mapped_column(String(300))
    amount: Mapped[Optional[float]] = mapped_column(Float)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False)


class DelegatedDecision(Base):
    __tablename__ = "delegated_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    item_number: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    officer_title: Mapped[Optional[str]] = mapped_column(String(200))
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False)


class BuildingPermit(Base):
    __tablename__ = "building_permits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    site_address: Mapped[Optional[str]] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)
    estimated_value: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[Optional[PermitStatus]] = mapped_column(Enum(PermitStatus))


class OtherItem(Base):
    __tablename__ = "other_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    item_number: Mapped[Optional[str]] = mapped_column(String(50))
    item_type: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False)


class ExtractionEvidence(Base):
    """
    Links an extracted entity to a verbatim quote from the source text.

    entity_table + entity_id form a logical FK to whichever entity table
    the quote supports (e.g. entity_table="motions", entity_id=42).
    A physical FK is not used because the target table varies per row.

    char_offset is null when the quote could not be found verbatim in the
    source text — these rows flag potential hallucinations for Level 3 review.
    """

    __tablename__ = "extraction_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    entity_table: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_offset: Mapped[Optional[int]] = mapped_column(Integer)
    char_length: Mapped[Optional[int]] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# Dynamic layer — relationships and emergent patterns
# ---------------------------------------------------------------------------


class Relationship(Base):
    """
    A typed edge between any two entities, supporting the dynamic layer.

    source_type / target_type hold the table name (e.g. "councillors", "motions").
    This is a simple adjacency-list approach; upgrade to a graph DB if the
    pattern-detection workload outgrows SQLite.
    """

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[RelationshipKind] = mapped_column(Enum(RelationshipKind), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Inferred weight: positive alignment, negative opposition
    weight: Mapped[Optional[float]] = mapped_column(Float)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    observed_at: Mapped[Optional[date]] = mapped_column(Date)

    def __repr__(self) -> str:
        return (
            f"<Relationship {self.kind} "
            f"{self.source_type}:{self.source_id} → "
            f"{self.target_type}:{self.target_id}>"
        )
