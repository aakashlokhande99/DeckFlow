"""Day 11 tests: Human Review Pause/Resume in LangGraph, /review GET payload, and POST decisions."""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, Insight, Project, Source
from app.workflow.graph import create_research_graph, route_after_human_review
from app.workflow.state import ResearchWorkflowState


@pytest.fixture
def base_state() -> ResearchWorkflowState:
    return {
        "project_id": str(uuid.uuid4()),
        "topic": "Autonomous Commercial Fleets",
        "objective": "Assess total cost of ownership and safety liability.",
        "audience": "Fleet Management Executives",
        "geography": "North America",
        "time_horizon": "2025-2030",
        "status": "awaiting_review",
        "version": 1,
    }


def test_route_after_human_review_decisions(base_state: ResearchWorkflowState) -> None:
    """Test conditional edge routing based on human decision."""
    # 1. Approve -> terminates research graph (ready for presentation sprint)
    state_approve = {**base_state, "human_decision": "approve"}
    assert route_after_human_review(state_approve) == "__end__"

    # 2. Revise -> returns to synthesis node
    state_revise = {**base_state, "human_decision": "revise"}
    assert route_after_human_review(state_revise) == "synthesize"

    # 3. Research More -> returns to search_sources node
    state_more = {**base_state, "human_decision": "research_more"}
    assert route_after_human_review(state_more) == "search_sources"


def test_langgraph_interrupt_at_human_review(base_state: ResearchWorkflowState) -> None:
    """Validate that LangGraph halts before human_review when configured with interrupt_on_review."""
    saver = MemorySaver()
    graph = create_research_graph(checkpointer=saver, interrupt_on_review=True)
    assert "human_review" in graph.interrupt_before_nodes


@pytest.mark.asyncio
async def test_get_and_post_review_api_endpoints(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test GET /api/projects/{id}/review payload and POST decision submission."""
    # 1. Create project in DB
    project = Project(
        topic="Modular Carbon Capture Units",
        objective="Assess absorption efficiency and capex per ton of CO2.",
        audience="Industrial Decarbonization Committee",
        geography="EU",
        time_horizon="2025-2030",
        status="awaiting_review",
    )
    db_session.add(project)
    await db_session.flush()

    source = Source(
        project_id=project.id,
        canonical_url="https://iea.org/ccus-report",
        title="IEA CCUS Benchmark",
        access_time=project.created_at,
    )
    db_session.add(source)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Direct air capture units achieve $220/ton with renewable power.",
        findings=[{"id": "F1", "finding": "Capture cost is $220/ton."}],
        implications=[{"id": "I1", "implication": "Cost parity requires carbon tax > $180/ton."}],
        recommendations=[{"id": "R1", "action": "Install pilot capture unit.", "timeframe": "0-6 months", "priority": "high"}],
        risks=[{"id": "RK1", "risk": "Solvent degradation.", "severity": "medium", "mitigation": "Thermal regeneration."}],
        qa_report={"passed": True, "overall_score": 0.92},
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    # 2. Test GET /api/projects/{id}/review
    get_res = await async_client.get(f"/api/projects/{project.id}/review")
    assert get_res.status_code == 200
    review_data = get_res.json()

    assert review_data["project_id"] == str(project.id)
    assert review_data["project_status"] == "awaiting_review"
    assert review_data["has_synthesis"] is True
    assert review_data["insight"]["executive_summary"] == insight.executive_summary
    assert review_data["insight"]["qa_report"]["overall_score"] == 0.92
    assert len(review_data["sources"]) == 1
    assert review_data["sources"][0]["canonical_url"] == "https://iea.org/ccus-report"

    # 3. Test POST /api/projects/{id}/review with 'revise' decision
    revise_payload = {
        "action": "revise",
        "comments": "Please elaborate on membrane vs solvent capital cost trade-offs.",
        "edited_items": {"findings": [{"id": "F1", "finding": "Capture cost is $200-$240/ton."}]},
        "rejected_ids": [],
    }
    revise_res = await async_client.post(
        f"/api/projects/{project.id}/review", json=revise_payload
    )
    assert revise_res.status_code == 200
    assert revise_res.json()["status"] == "revision_requested"
    assert "feedback_id" in revise_res.json()

    # Verify Feedback record in DB
    feedback_stmt = select(Feedback).where(Feedback.project_id == project.id)
    feedbacks = (await db_session.execute(feedback_stmt)).scalars().all()
    assert len(feedbacks) == 1
    assert feedbacks[0].decision == "revise"
    assert "membrane vs solvent" in feedbacks[0].comment

    # 4. Test POST /api/projects/{id}/review with 'approve' decision
    approve_payload = {
        "action": "approve",
        "comments": "Approved for executive slide deck.",
    }
    approve_res = await async_client.post(
        f"/api/projects/{project.id}/review", json=approve_payload
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # Check project and insight status in DB
    await db_session.refresh(project)
    await db_session.refresh(insight)
    assert project.status == "approved"
    assert insight.is_approved is True
