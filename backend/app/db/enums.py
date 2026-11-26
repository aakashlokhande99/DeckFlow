"""Project-wide enumerations.

Using standard Python ``enum.Enum`` (not SQLAlchemy Enum) so the same
classes can be reused in Pydantic schemas without circular imports.
"""

from __future__ import annotations

import enum


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    awaiting_review = "awaiting_review"
    revision_requested = "revision_requested"
    approved = "approved"
    generating = "generating"
    completed = "completed"
    failed = "failed"


class ResearchDepth(str, enum.Enum):
    quick = "quick"       # ~5 sources
    standard = "standard" # ~15 sources
    deep = "deep"         # ~30 sources


class ReviewDecision(str, enum.Enum):
    approve = "approve"
    revise = "revise"
    research_more = "research_more"


class SlideLayout(str, enum.Enum):
    title = "title"
    executive_summary = "executive_summary"
    two_column = "two_column"
    three_insight = "three_insight"
    chart = "chart"
    comparison = "comparison"
    roadmap = "roadmap"
    risk_matrix = "risk_matrix"
    closing = "closing"
    scorecard = "scorecard"
    metrics = "metrics"


class ArtifactType(str, enum.Enum):
    pptx = "pptx"


class ConfidenceLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    uncertain = "uncertain"
