"""Pydantic schemas and data contracts for projects and workflow states."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import (
    ConfidenceLevel,
    ProjectStatus,
    ResearchDepth,
    ReviewDecision,
    SlideLayout,
)


# ---------------------------------------------------------------------------
# Project Schemas
# ---------------------------------------------------------------------------

class ProjectBrief(BaseModel):
    """Input payload to create a new project."""
    topic: str = Field(..., min_length=3, max_length=500, description="Central topic or client question")
    objective: str = Field(..., min_length=10, description="Business objective or deliverable goal")
    audience: Optional[str] = Field(default="Executive Leadership", max_length=300, description="Target executive audience (optional)")
    geography: Optional[str] = Field(default="Global", max_length=300, description="Geographic scope (optional)")
    time_horizon: Optional[str] = Field(default=None, max_length=200, description="Strategic time horizon (optional)")
    additional_context: Optional[str] = Field(default=None, description="Additional context, notes, or focus areas (optional)")
    research_depth: ResearchDepth = Field(default=ResearchDepth.standard, description="quick, standard, or deep")

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "topic": "Generative AI in Retail Banking",
                "objective": "Evaluate commercial impact, key use cases, and deployment risks for tier-1 retail banks over next 3 years.",
                "audience": "Chief Strategy Officer & Head of Retail Banking",
                "geography": "North America & Western Europe",
                "time_horizon": "2025-2028",
                "additional_context": "Focus particularly on fraud detection and hyper-personalized wealth advisory.",
                "research_depth": "standard",
            }
        },
    )


class ProjectResponse(BaseModel):
    """Project representation returned by the API."""
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    topic: str
    objective: str
    audience: Optional[str] = None
    geography: Optional[str] = None
    time_horizon: Optional[str] = None
    additional_context: Optional[str] = None
    research_depth: ResearchDepth
    status: ProjectStatus
    workflow_run_id: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class DocumentResponse(BaseModel):
    """Uploaded research document metadata."""
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    size_bytes: int
    content_type: str
    uploaded_at: datetime
    extracted_char_count: int


# ---------------------------------------------------------------------------
# Core Workflow Data Contracts (Spec Section 3)
# ---------------------------------------------------------------------------

class ResearchPlan(BaseModel):
    """Generated research plan."""
    questions: List[str] = Field(default_factory=list, description="Target research questions")
    search_queries: List[str] = Field(default_factory=list, description="Search queries to execute")
    scope_notes: str = Field(default="", description="Scope boundaries and context notes")
    exclusions: List[str] = Field(default_factory=list, description="Explicit out-of-scope areas")


class SourceResponse(BaseModel):
    """Source evidence metadata."""
    id: uuid.UUID
    canonical_url: str
    title: Optional[str] = None
    publisher: Optional[str] = None
    pub_date: Optional[str] = None
    access_time: datetime
    content_hash: Optional[str] = None
    raw_metadata: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceClaimResponse(BaseModel):
    """Traceable claim backed by sources."""
    id: uuid.UUID
    claim_text: str
    source_ids: List[uuid.UUID]
    confidence: ConfidenceLevel
    is_uncertain: bool = False
    is_assumption: bool = False
    is_contradiction: bool = False
    is_gap: bool = False
    version: int = 1

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class InsightResponse(BaseModel):
    """Consulting synthesis report snapshot."""
    id: uuid.UUID
    run_id: Optional[str] = None
    executive_summary: str
    findings: List[dict[str, Any]] = Field(default_factory=list)
    implications: List[dict[str, Any]] = Field(default_factory=list)
    recommendations: List[dict[str, Any]] = Field(default_factory=list)
    risks: List[dict[str, Any]] = Field(default_factory=list)
    limitations: List[dict[str, Any]] = Field(default_factory=list)
    gaps: List[dict[str, Any]] = Field(default_factory=list)
    citations: List[dict[str, Any]] = Field(default_factory=list)
    qa_report: Optional[dict[str, Any]] = None
    version: int = 1
    is_approved: bool = False
    prompt_version: str = "v1"

    model_config = ConfigDict(from_attributes=True)


class ReviewDecisionRequest(BaseModel):
    """Human decision payload."""
    action: ReviewDecision = Field(..., description="approve | revise | research_more")
    comments: Optional[str] = Field(None, description="User comments/guidance")
    edited_items: Optional[dict[str, Any]] = Field(default=None, description="Inline edits made by human")
    rejected_ids: List[str] = Field(default_factory=list, description="IDs of rejected claims or findings")


class SlideSpecResponse(BaseModel):
    """Slide outline and content specification."""
    id: uuid.UUID
    slide_order: int
    title: str
    key_message: str
    layout: SlideLayout
    content: dict[str, Any]
    source_ids: List[uuid.UUID] = Field(default_factory=list)
    is_approved: bool = False

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
