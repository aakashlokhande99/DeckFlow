"""Day 5 tests: LLM & Search provider adapters, ResearchPlan generation, and error handling."""

from __future__ import annotations

import pytest
from app.llm.base import LLMTimeoutError, LLMValidationError
from app.llm.factory import get_llm_provider
from app.llm.mock import MockLLMProvider
from app.research.factory import get_search_provider
from app.research.mock_search import MockSearchProvider
from app.research.planner import ResearchPlanner
from app.research.search_base import SearchResult, SearchTimeoutError
from app.schemas.project import ProjectBrief, ResearchPlan


@pytest.fixture
def sample_brief() -> ProjectBrief:
    return ProjectBrief(
        topic="Enterprise Cloud Migration ROI in Banking",
        objective="Assess economic payback, latency gains, and regulatory constraints for tier-1 banks moving core banking workloads to multi-cloud.",
        audience="Chief Information Officer & CFO",
        geography="North America",
        time_horizon="2025-2028",
        research_depth="standard",
    )


@pytest.fixture
def mock_research_plan() -> ResearchPlan:
    return ResearchPlan(
        questions=[
            "What is the average TCO reduction observed by global retail banks after migrating core processing to public cloud?",
            "What are the primary operational resilience and regulatory hurdles (e.g. DORA, OCC requirements)?",
            "What migration patterns (lift-and-shift vs. cloud-native replatforming) yield the highest ROI within 36 months?",
        ],
        search_queries=[
            "tier 1 bank cloud migration TCO McKinsey Bain BCG",
            "core banking multi-cloud regulatory compliance OCC DORA",
            "cloud migration payback period retail banking benchmark",
        ],
        scope_notes="Focuses on tier-1 and large regional retail and commercial banking institutions.",
        exclusions=[
            "Crypto/DeFi platforms",
            "Small credit unions under $5B AUM",
            "Consumer retail mobile UI redesigns",
        ],
    )


# ---------------------------------------------------------------------------
# Search Provider Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_search_provider_default() -> None:
    provider = MockSearchProvider()
    results = await provider.search("test query", num_results=2)
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].url.startswith("https://")
    assert results[0].publisher is not None


@pytest.mark.asyncio
async def test_mock_search_provider_query_specific() -> None:
    custom_results = [
        SearchResult(title="Custom Title", url="https://custom.com/report", snippet="Custom snippet")
    ]
    provider = MockSearchProvider(query_results={"target query": custom_results})
    results = await provider.search("target query")
    assert len(results) == 1
    assert results[0].title == "Custom Title"


@pytest.mark.asyncio
async def test_mock_search_provider_timeout() -> None:
    provider = MockSearchProvider(simulate_timeout=True)
    with pytest.raises(SearchTimeoutError, match="timeout"):
        await provider.search("any query")


# ---------------------------------------------------------------------------
# LLM Provider Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_llm_provider_text() -> None:
    provider = MockLLMProvider(default_text="Strategic synthesis response")
    text = await provider.generate_text("Prompt")
    assert text == "Strategic synthesis response"
    assert len(provider.call_history) == 1


@pytest.mark.asyncio
async def test_mock_llm_provider_structured(mock_research_plan: ResearchPlan) -> None:
    provider = MockLLMProvider(
        structured_responses={"ResearchPlan": mock_research_plan}
    )
    result = await provider.generate_structured("Generate plan", response_model=ResearchPlan)
    assert isinstance(result, ResearchPlan)
    assert len(result.questions) == 3
    assert len(result.search_queries) == 3
    assert len(result.exclusions) == 3


@pytest.mark.asyncio
async def test_mock_llm_provider_timeout() -> None:
    provider = MockLLMProvider(simulate_timeout=True)
    with pytest.raises(LLMTimeoutError, match="timeout"):
        await provider.generate_text("test")


@pytest.mark.asyncio
async def test_mock_llm_provider_validation_error() -> None:
    provider = MockLLMProvider(simulate_validation_error=True)
    with pytest.raises(LLMValidationError, match="validation error"):
        await provider.generate_structured("prompt", response_model=ResearchPlan)


# ---------------------------------------------------------------------------
# Research Planner Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_research_planner_success(
    sample_brief: ProjectBrief, mock_research_plan: ResearchPlan
) -> None:
    llm = MockLLMProvider(structured_responses={"ResearchPlan": mock_research_plan})
    planner = ResearchPlanner(llm_provider=llm)

    plan = await planner.plan(sample_brief)
    assert isinstance(plan, ResearchPlan)
    assert len(plan.questions) == 3
    assert len(plan.search_queries) == 3
    assert "tier 1 bank" in plan.search_queries[0]
    assert len(plan.exclusions) > 0


@pytest.mark.asyncio
async def test_research_planner_handles_llm_failure(sample_brief: ProjectBrief) -> None:
    llm = MockLLMProvider(simulate_timeout=True)
    planner = ResearchPlanner(llm_provider=llm)

    with pytest.raises(LLMTimeoutError):
        await planner.plan(sample_brief)


# ---------------------------------------------------------------------------
# Factory Tests
# ---------------------------------------------------------------------------

def test_factories_return_mock_instances() -> None:
    llm = get_llm_provider("mock")
    assert isinstance(llm, MockLLMProvider)

    search = get_search_provider("mock")
    assert isinstance(search, MockSearchProvider)


def test_factories_reject_invalid_providers() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider("non_existent_provider_xyz")

    with pytest.raises(ValueError, match="Unsupported search provider"):
        get_search_provider("non_existent_search_xyz")
