"""Typed State definition for the LangGraph research and synthesis workflow."""

from __future__ import annotations

from typing import Any, List, Optional
from typing_extensions import TypedDict


class ResearchWorkflowState(TypedDict, total=False):
    """Explicit state contract passed between LangGraph workflow nodes."""

    # Project Identifiers and Brief
    project_id: str
    topic: str
    objective: str
    audience: str
    geography: str
    time_horizon: str
    additional_context: Optional[str]
    research_depth: str

    # Workflow generated research artifacts
    plan: Optional[dict[str, Any]]
    source_ids: List[str]
    source_urls: List[str]
    extracted_texts: dict[str, str]  # source_id -> extracted clean text
    content_hashes: dict[str, str]   # source_id -> SHA256 hash
    evidence_claim_ids: List[str]

    # Synthesis & Quality
    insight_id: Optional[str]
    synthesis: Optional[dict[str, Any]]
    qa_report: Optional[dict[str, Any]]
    version: int

    # Human Review Pause & Decision Gate
    human_decision: Optional[str]  # approve | revise | research_more
    human_comments: Optional[str]
    human_edits: Optional[dict[str, Any]]
    rejected_ids: List[str]

    # Lifecycle & Observability
    current_step: str
    workflow_run_id: str
    status: str
    errors: List[str]
