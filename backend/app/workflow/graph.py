"""LangGraph StateGraph assembly with synthesis, QA quality gate, and human review pause."""

from __future__ import annotations

from typing import Any, Literal
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.workflow.nodes import (
    build_evidence_node,
    fetch_and_extract_node,
    human_review_pause_node,
    plan_research_node,
    quality_gate_node,
    search_sources_node,
    synthesize_node,
    validate_brief_node,
)
from app.workflow.state import ResearchWorkflowState


def route_after_validation(state: ResearchWorkflowState) -> Literal["plan_research", "__end__"]:
    """Conditional router: stop if validation errors are detected."""
    if state.get("errors"):
        return END
    return "plan_research"


def route_after_human_review(
    state: ResearchWorkflowState,
) -> Literal["search_sources", "synthesize", "__end__"]:
    """Route according to human review decision: approve | revise | research_more."""
    decision = (state.get("human_decision") or "approve").lower()

    if decision == "research_more":
        return "search_sources"
    elif decision == "revise":
        return "synthesize"
    else:
        # Default: approve
        return END


def create_research_graph(
    checkpointer: Any | None = None,
    interrupt_on_review: bool = True,
) -> Any:
    """Compile and return the executable research and synthesis workflow graph."""
    workflow = StateGraph(ResearchWorkflowState)

    # Register nodes
    workflow.add_node("validate_brief", validate_brief_node)
    workflow.add_node("plan_research", plan_research_node)
    workflow.add_node("search_sources", search_sources_node)
    workflow.add_node("fetch_and_extract", fetch_and_extract_node)
    workflow.add_node("build_evidence", build_evidence_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("quality_gate", quality_gate_node)
    workflow.add_node("human_review", human_review_pause_node)

    # Wire research sequence
    workflow.set_entry_point("validate_brief")
    workflow.add_conditional_edges("validate_brief", route_after_validation)
    workflow.add_edge("plan_research", "search_sources")
    workflow.add_edge("search_sources", "fetch_and_extract")
    workflow.add_edge("fetch_and_extract", "build_evidence")
    workflow.add_edge("build_evidence", "synthesize")
    workflow.add_edge("synthesize", "quality_gate")
    workflow.add_edge("quality_gate", "human_review")

    # Wire post-human review transitions
    workflow.add_conditional_edges("human_review", route_after_human_review)

    saver = checkpointer if checkpointer is not None else MemorySaver()
    interrupts = ["human_review"] if interrupt_on_review else []

    return workflow.compile(
        checkpointer=saver,
        interrupt_before=interrupts,
    )
