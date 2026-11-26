"""SQLAlchemy 2.0 ORM models — all 7 domain tables.

Relationships
-------------
Project  1──* Source
Project  1──* EvidenceClaim
Project  1──* Insight
Project  1──* Feedback
Project  1──* SlideSpec
Project  1──1 Artifact

Evidence claims reference source IDs as a PostgreSQL UUID array (no join table
needed for the MVP; the source records are relationally traceable).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import types, TypeDecorator

from app.db.base import Base
from app.db.enums import (
    ArtifactType,
    ConfidenceLevel,
    ProjectStatus,
    ResearchDepth,
    ReviewDecision,
    SlideLayout,
)


class StringArray(TypeDecorator):
    """Platform-independent array of UUIDs (native ARRAY on PostgreSQL, JSON on SQLite)."""
    impl = types.JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(UUID(as_uuid=True)))
        return dialect.type_descriptor(types.JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            result = []
            for v in value:
                if isinstance(v, uuid.UUID):
                    result.append(v)
                elif isinstance(v, str):
                    try:
                        result.append(uuid.UUID(v))
                    except (ValueError, AttributeError):
                        pass
            return result
        return [str(v) for v in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        result = []
        for v in value:
            if isinstance(v, uuid.UUID):
                result.append(str(v))
            elif isinstance(v, str):
                result.append(v)
            else:
                result.append(str(v))
        return result

# ---------------------------------------------------------------------------
# Helper: PostgreSQL-native enum type strings
# ---------------------------------------------------------------------------
# SQLAlchemy maps Python enum values via String; the migration creates the
# actual PostgreSQL ENUM types using raw DDL (see the Alembic migration).
# ---------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Brief fields
    topic: Mapped[str] = mapped_column(String(500))
    objective: Mapped[str] = mapped_column(Text)
    audience: Mapped[str | None] = mapped_column(String(300), nullable=True, default="Executive Leadership")
    geography: Mapped[str | None] = mapped_column(String(300), nullable=True, default="Global")
    time_horizon: Mapped[str | None] = mapped_column(String(200), nullable=True)
    additional_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_depth: Mapped[str] = mapped_column(
        String(50), default=ResearchDepth.standard.value
    )

    # Workflow state
    status: Mapped[str] = mapped_column(
        String(50), default=ProjectStatus.draft.value, index=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    sources: Mapped[list["Source"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    evidence_claims: Mapped[list["EvidenceClaim"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    slide_specs: Mapped[list["SlideSpec"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifact: Mapped["Artifact | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    webhook_deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_url", name="uq_sources_project_url"),
        Index("ix_sources_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pub_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    access_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="sources")


class EvidenceClaim(Base):
    __tablename__ = "evidence_claims"
    __table_args__ = (Index("ix_evidence_claims_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    # Array of source UUIDs supporting this claim (relationally traceable)
    source_ids: Mapped[list] = mapped_column(StringArray, default=list)
    claim_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(
        String(50), default=ConfidenceLevel.medium.value
    )
    is_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    is_assumption: Mapped[bool] = mapped_column(Boolean, default=False)
    is_contradiction: Mapped[bool] = mapped_column(Boolean, default=False)
    is_gap: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped["Project"] = relationship(back_populates="evidence_claims")


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (Index("ix_insights_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    executive_summary: Mapped[str] = mapped_column(Text)
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    implications: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    risks: Mapped[list] = mapped_column(JSONB, default=list)
    limitations: Mapped[list] = mapped_column(JSONB, default=list)
    gaps: Mapped[list] = mapped_column(JSONB, default=list)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    qa_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1")

    project: Mapped["Project"] = relationship(back_populates="insights")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="insight")
    slide_specs: Mapped[list["SlideSpec"]] = relationship(back_populates="insight")


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    insight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(50))  # ReviewDecision value
    user_edits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped["Project"] = relationship(back_populates="feedback")
    insight: Mapped["Insight | None"] = relationship(back_populates="feedback")


class SlideSpec(Base):
    __tablename__ = "slide_specs"
    __table_args__ = (Index("ix_slide_specs_project_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    insight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insights.id", ondelete="CASCADE")
    )

    slide_order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    key_message: Mapped[str] = mapped_column(Text)
    layout: Mapped[str] = mapped_column(String(50), default=SlideLayout.two_column.value)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_ids: Mapped[list] = mapped_column(StringArray, default=list)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["Project"] = relationship(back_populates="slide_specs")
    insight: Mapped["Insight"] = relationship(back_populates="slide_specs")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,  # one current artifact per project
    )
    slide_spec_snapshot: Mapped[list] = mapped_column(JSONB, default=list)
    file_path: Mapped[str] = mapped_column(String(1000))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pptx_hash: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    artifact_type: Mapped[str] = mapped_column(
        String(20), default=ArtifactType.pptx.value
    )

    project: Mapped["Project"] = relationship(back_populates="artifact")


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        Index("ix_webhook_subscriptions_project_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(50))  # "slack", "teams", "generic"
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str | None] = mapped_column(String(200), nullable=True)
    events: Mapped[list] = mapped_column(JSONB, default=lambda: ["slide_review_gate", "synthesis_review_gate"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="subscription"
    )
    project: Mapped["Project | None"] = relationship(back_populates="webhook_subscriptions")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_project_id", "project_id"),
        Index("ix_webhook_deliveries_subscription_id", "subscription_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    success: Mapped[bool] = mapped_column(Boolean, default=False)

    subscription: Mapped["WebhookSubscription | None"] = relationship(back_populates="deliveries")
    project: Mapped["Project | None"] = relationship(back_populates="webhook_deliveries")

