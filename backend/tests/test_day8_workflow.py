"""Day 8 tests: LangGraph state machine, research nodes integration, and checkpointing."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ConfidenceLevel
from app.db.models import EvidenceClaim, Project, Source
from app.llm.mock import MockLLMProvider
from app.research.mock_search import MockSearchProvider
from app.research.planner import ResearchPlanner
from app.research.safe_fetcher import FetchResponse, SafeFetcher
from app.research.search_base import SearchResult
from app.research.synthesizer import ConsultingSynthesizer
from app.schemas.project import ResearchPlan
from app.schemas.synthesis import ConsultingSynthesis, SynthesisFinding
from app.workflow.graph import create_research_graph
from app.workflow.nodes import (
    build_evidence_node,
    fetch_and_extract_node,
    plan_research_node,
    quality_gate_node,
    search_sources_node,
    synthesize_node,
    validate_brief_node,
)
from app.workflow.state import ResearchWorkflowState


class MockSafeFetcher:
    """Mock fetcher returning deterministic HTML content instantly without network calls."""
    async def fetch(self, url: str) -> FetchResponse:
        content = b"<html><body><h1>Nuclear Energy Economic Outlook</h1><p>Capital costs average $4,500/kW. Commercial deployment timeline remains uncertain pending regulatory licensing approvals.</p></body></html>"
        return FetchResponse(
            url=url,
            canonical_url=url,
            status_code=200,
            content_type="text/html",
            content_bytes=content,
            content_hash="mock_sha256_hash_abcdef",
            byte_count=len(content),
        )


@pytest.fixture
def mock_plan() -> ResearchPlan:
    return ResearchPlan(
        questions=[
            "What is the market size and expected CAGR for industrial SMRs?",
            "What are the major capital expenditure benchmarks per megawatt?",
        ],
        search_queries=[
            "industrial SMR capital expenditure benchmarks",
            "small modular reactor market size CAGR 2030",
        ],
        scope_notes="Focuses on heavy industry and data center off-grid power.",
        exclusions=["Residential solar", "Offshore wind"],
    )


@pytest.mark.asyncio
async def test_workflow_individual_nodes(
    db_session: AsyncSession, mock_plan: ResearchPlan
) -> None:
    """Test step-by-step node execution."""
    project = Project(
        topic="SMR Energy Economics",
        objective="Assess capital costs and commercial adoption for data centers.",
        audience="Tech Infrastructure Executives",
        geography="North America",
        time_horizon="2025-2035",
    )
    db_session.add(project)
    await db_session.flush()

    state: ResearchWorkflowState = {
        "project_id": str(project.id),
        "topic": project.topic,
        "objective": project.objective,
        "audience": project.audience,
        "geography": project.geography,
        "time_horizon": project.time_horizon,
        "research_depth": "standard",
    }

    # 1. Validate Brief Node
    v_res = await validate_brief_node(state)
    assert v_res["current_step"] == "validate_brief"
    assert len(v_res["errors"]) == 0
    state.update(v_res)  # type: ignore

    # 2. Plan Research Node
    mock_llm = MockLLMProvider(structured_responses={"ResearchPlan": mock_plan})
    p_res = await plan_research_node(state, planner=ResearchPlanner(llm_provider=mock_llm))
    assert p_res["current_step"] == "plan_research"
    assert "plan" in p_res
    state.update(p_res)  # type: ignore

    # 3. Search Sources Node
    mock_search = MockSearchProvider(
        default_results=[
            SearchResult(
                title="SMR Benchmark Report",
                url="https://iea.org/reports/smr-2024",
                snippet="IEA economic analysis of nuclear technologies.",
                publisher="International Energy Agency",
                pub_date="2024-03-01",
            )
        ]
    )
    s_res = await search_sources_node(state, db=db_session, search_provider=mock_search)
    assert s_res["current_step"] == "search_sources"
    assert len(s_res["source_ids"]) > 0
    state.update(s_res)  # type: ignore

    # 4. Fetch & Extract Node (using MockSafeFetcher for offline speed)
    f_res = await fetch_and_extract_node(state, fetcher=MockSafeFetcher())  # type: ignore
    assert f_res["current_step"] == "fetch_and_extract"
    assert len(f_res["extracted_texts"]) > 0
    state.update(f_res)  # type: ignore

    # 5. Build Evidence Node
    e_res = await build_evidence_node(state, db=db_session)
    assert e_res["current_step"] == "build_evidence"
    assert len(e_res["evidence_claim_ids"]) > 0
    state.update(e_res)  # type: ignore

    # 6. Synthesize Node
    claims_stmt = select(EvidenceClaim).where(EvidenceClaim.project_id == project.id)
    claims = (await db_session.execute(claims_stmt)).scalars().all()
    first_claim_id = str(claims[0].id) if claims else str(uuid.uuid4())
    mock_synthesis = ConsultingSynthesis(
        executive_summary="SMRs offer modular deployment advantages.",
        findings=[
            SynthesisFinding(
                id="F1",
                finding="Capital costs average $4,500/kW.",
                evidence_ids=[first_claim_id],
                confidence=ConfidenceLevel.high,
                is_uncertain=False,
            )
        ],
        implications=[],
        recommendations=[],
        risks=[],
        gaps=[],
    )
    synth_mock_llm = MockLLMProvider(structured_responses={"ConsultingSynthesis": mock_synthesis})
    synth_res = await synthesize_node(
        state,
        db=db_session,
        synthesizer=ConsultingSynthesizer(db=db_session, llm_provider=synth_mock_llm),
    )
    assert synth_res["current_step"] == "synthesize"
    state.update(synth_res)  # type: ignore

    # 7. Quality Gate Node
    q_res = await quality_gate_node(state, db=db_session)
    assert q_res["current_step"] == "quality_gate"
    assert q_res["status"] == "awaiting_review"

    # Verify project in DB was updated to awaiting_review
    await db_session.refresh(project)
    assert project.status == "awaiting_review"


@pytest.mark.asyncio
async def test_end_to_end_research_graph_execution(
    db_session: AsyncSession, mock_plan: ResearchPlan, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test full LangGraph state machine execution with MemorySaver checkpointer."""
    project = Project(
        topic="Solid State Battery EV Commercialization",
        objective="Assess automotive OEM timelines, energy density breakthroughs, and cell manufacturing yields.",
        audience="Automotive OEM Board",
        geography="Global",
        time_horizon="2025-2030",
        research_depth="standard",
    )
    db_session.add(project)
    await db_session.flush()

    # Pre-configure mock synthesis response
    mock_synth = ConsultingSynthesis(
        executive_summary="Solid-state cells offer higher energy density.",
        findings=[],
        implications=[],
        recommendations=[],
        risks=[],
        gaps=[],
    )

    # Patch planner, search, and fetcher to use deterministic mock instances
    mock_llm = MockLLMProvider(
        structured_responses={
            "ResearchPlan": mock_plan,
            "ConsultingSynthesis": mock_synth,
        }
    )
    monkeypatch.setattr(
        "app.workflow.nodes.get_llm_provider",
        lambda *args, **kwargs: mock_llm,
    )
    monkeypatch.setattr(
        "app.research.planner.get_llm_provider",
        lambda *args, **kwargs: mock_llm,
    )
    monkeypatch.setattr(
        "app.research.synthesizer.get_llm_provider",
        lambda *args, **kwargs: mock_llm,
    )
    monkeypatch.setattr(
        "app.research.source_registrar.get_search_provider",
        lambda *args, **kwargs: MockSearchProvider(),
    )
    monkeypatch.setattr(
        "app.workflow.nodes.SafeFetcher",
        lambda *args, **kwargs: MockSafeFetcher(),
    )

    saver = MemorySaver()
    # Execute graph with review interrupt disabled to test end-to-end completion flow
    graph = create_research_graph(checkpointer=saver, interrupt_on_review=False)

    initial_state: ResearchWorkflowState = {
        "project_id": str(project.id),
        "topic": project.topic,
        "objective": project.objective,
        "audience": project.audience,
        "geography": project.geography,
        "time_horizon": project.time_horizon,
        "research_depth": project.research_depth,
        "status": "running",
        "errors": [],
    }

    config = {"configurable": {"thread_id": str(project.id)}}
    final_state = await graph.ainvoke(initial_state, config=config)

    assert "plan" in final_state
    assert len(final_state["source_ids"]) > 0
    assert len(final_state["evidence_claim_ids"]) > 0

    # Verify checkpoint exists
    checkpoint = saver.get(config)
    assert checkpoint is not None

    # Idempotent re-run on same thread: verifies graph resumes without corrupting or duplicating sources
    db_sources_before = (
        await db_session.execute(select(Source).where(Source.project_id == project.id))
    ).scalars().all()
    count_before = len(db_sources_before)

    resumed_state = await graph.ainvoke(final_state, config=config)
    assert resumed_state is not None

    db_sources_after = (
        await db_session.execute(select(Source).where(Source.project_id == project.id))
    ).scalars().all()
    assert len(db_sources_after) == count_before


@pytest.mark.asyncio
async def test_run_project_endpoint(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test POST /api/projects/{id}/run initiates workflow."""
    mock_task = MagicMock()
    mock_task.id = "mock-celery-task-id"
    monkeypatch.setattr(
        "app.worker.execute_research_workflow.delay",
        lambda *args, **kwargs: mock_task,
    )

    brief = {
        "topic": "Grid-Scale Battery Energy Storage",
        "objective": "Assess lithium-iron-phosphate vs sodium-ion economics.",
        "audience": "Utility Regulators & Investors",
        "geography": "North America",
        "time_horizon": "2025-2030",
        "research_depth": "quick",
    }
    create_res = await async_client.post("/api/projects", json=brief)
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # Trigger run endpoint
    run_res = await async_client.post(f"/api/projects/{project_id}/run")
    assert run_res.status_code == 202
    data = run_res.json()
    assert data["status"] == "queued"
    assert data["project_id"] == project_id
    assert data["task_id"] == "mock-celery-task-id"

    # Verify project status in DB changed to running
    get_res = await async_client.get(f"/api/projects/{project_id}")
    assert get_res.json()["status"] == "running"
