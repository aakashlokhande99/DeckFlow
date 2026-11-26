"""Initial schema — all 7 domain tables.

Revision ID: 0001
Revises:
Create Date: 2026-11-20
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# PostgreSQL enum type names (must match values in app/db/enums.py)
# ---------------------------------------------------------------------------
project_status_enum = postgresql.ENUM(
    "draft", "running", "awaiting_review", "revision_requested",
    "approved", "generating", "completed", "failed",
    name="projectstatus",
)
research_depth_enum = postgresql.ENUM(
    "quick", "standard", "deep",
    name="researchdepth",
)
review_decision_enum = postgresql.ENUM(
    "approve", "revise", "research_more",
    name="reviewdecision",
)
slide_layout_enum = postgresql.ENUM(
    "title", "executive_summary", "two_column", "three_insight",
    "chart", "comparison", "roadmap", "risk_matrix", "closing",
    name="slidelayout",
)
confidence_level_enum = postgresql.ENUM(
    "high", "medium", "low", "uncertain",
    name="confidencelevel",
)
artifact_type_enum = postgresql.ENUM(
    "pptx",
    name="artifacttype",
)


def upgrade() -> None:
    # --- Create enum types ---
    project_status_enum.create(op.get_bind(), checkfirst=True)
    research_depth_enum.create(op.get_bind(), checkfirst=True)
    review_decision_enum.create(op.get_bind(), checkfirst=True)
    slide_layout_enum.create(op.get_bind(), checkfirst=True)
    confidence_level_enum.create(op.get_bind(), checkfirst=True)
    artifact_type_enum.create(op.get_bind(), checkfirst=True)

    # --- 1. projects ---
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("audience", sa.String(300), nullable=False),
        sa.Column("geography", sa.String(300), nullable=False),
        sa.Column("time_horizon", sa.String(200), nullable=False),
        sa.Column("research_depth", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("workflow_run_id", sa.String(200), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_projects_status", "projects", ["status"])

    # --- 2. sources ---
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("publisher", sa.String(300), nullable=True),
        sa.Column("pub_date", sa.Date, nullable=True),
        sa.Column("access_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"])
    op.create_unique_constraint("uq_sources_project_url", "sources", ["project_id", "canonical_url"])

    # --- 3. evidence_claims ---
    op.create_table(
        "evidence_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("is_uncertain", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_assumption", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_contradiction", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_gap", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_evidence_claims_project_id", "evidence_claims", ["project_id"])

    # --- 4. insights ---
    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(200), nullable=True),
        sa.Column("executive_summary", sa.Text, nullable=False),
        sa.Column("findings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("implications", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("recommendations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("risks", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("limitations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("gaps", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("citations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("qa_report", postgresql.JSONB, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("prompt_version", sa.String(50), nullable=False, server_default="v1"),
    )
    op.create_index("ix_insights_project_id", "insights", ["project_id"])

    # --- 5. feedback ---
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("insights.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("user_edits", postgresql.JSONB, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("section", sa.String(200), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_feedback_project_id", "feedback", ["project_id"])

    # --- 6. slide_specs ---
    op.create_table(
        "slide_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("insights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slide_order", sa.Integer, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("key_message", sa.Text, nullable=False),
        sa.Column("layout", sa.String(50), nullable=False, server_default="two_column"),
        sa.Column("content", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("source_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_slide_specs_project_id", "slide_specs", ["project_id"])

    # --- 7. artifacts ---
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slide_spec_snapshot", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("pptx_hash", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("artifact_type", sa.String(20), nullable=False, server_default="pptx"),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("slide_specs")
    op.drop_table("feedback")
    op.drop_table("insights")
    op.drop_table("evidence_claims")
    op.drop_table("sources")
    op.drop_table("projects")

    artifact_type_enum.drop(op.get_bind(), checkfirst=True)
    confidence_level_enum.drop(op.get_bind(), checkfirst=True)
    slide_layout_enum.drop(op.get_bind(), checkfirst=True)
    review_decision_enum.drop(op.get_bind(), checkfirst=True)
    research_depth_enum.drop(op.get_bind(), checkfirst=True)
    project_status_enum.drop(op.get_bind(), checkfirst=True)
