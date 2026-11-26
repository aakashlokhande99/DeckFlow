"""Day 6 integration tests: URL canonicalization, web search execution, and source registration."""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project, Source
from app.research.mock_search import MockSearchProvider
from app.research.search_base import SearchResult
from app.research.source_registrar import SourceRegistrar
from app.research.url_utils import canonicalize_url


def test_canonicalize_url_strips_tracking() -> None:
    url_1 = "https://www.mckinsey.com/insights/ai?utm_source=twitter&utm_medium=social#section-1"
    url_2 = "https://www.mckinsey.com/insights/ai/?utm_medium=social&utm_source=twitter"
    url_3 = "https://WWW.MCKINSEY.COM/insights/ai"

    c1 = canonicalize_url(url_1)
    c2 = canonicalize_url(url_2)
    c3 = canonicalize_url(url_3)

    assert c1 == "https://www.mckinsey.com/insights/ai"
    assert c2 == "https://www.mckinsey.com/insights/ai"
    assert c3 == "https://www.mckinsey.com/insights/ai"
    assert c1 == c2 == c3


def test_canonicalize_url_preserves_meaningful_params() -> None:
    url = "https://example.com/reports?id=123&category=tech&utm_campaign=spring"
    c = canonicalize_url(url)
    assert "utm_campaign" not in c
    assert "category=tech" in c
    assert "id=123" in c


@pytest.mark.asyncio
async def test_source_registrar_collapses_duplicates(db_session: AsyncSession) -> None:
    """Test duplicate URLs across queries collapse into a single database record."""
    # 1. Create a dummy project
    project = Project(
        topic="SMR Commercial Feasibility",
        objective="Assess small modular nuclear reactor costs and licensing timeline.",
        audience="Investment Committee",
        geography="North America",
        time_horizon="2025-2035",
        research_depth="standard",
    )
    db_session.add(project)
    await db_session.flush()

    # 2. Setup mock search with overlapping/duplicate URLs (differing only by query params and fragment)
    query_1_results = [
        SearchResult(
            title="SMR LCOE Analysis - Lazard",
            url="https://www.lazard.com/research-insights/smr-lcoe/?utm_source=google",
            snippet="Lazard Levelized Cost of Energy study for advanced nuclear reactors.",
            publisher="Lazard",
            pub_date="2024-04-12",
        ),
        SearchResult(
            title="World Nuclear Association - SMRs",
            url="https://world-nuclear.org/information-library/nuclear-fuel-cycle/nuclear-power-reactors/small-nuclear-power-reactors.aspx",
            snippet="Overview of international SMR designs and regulatory progress.",
            publisher="WNA",
            pub_date="2024-02-01",
        ),
    ]

    query_2_results = [
        # Duplicate of Lazard result with different UTM params and fragment
        SearchResult(
            title="Lazard LCOE Report (Mirror)",
            url="https://www.lazard.com/research-insights/smr-lcoe#download-pdf",
            snippet="Same report different snippet.",
            publisher="Lazard Insights",
        ),
        SearchResult(
            title="NRC Licensing Guidance",
            url="https://www.nrc.gov/reactors/new-reactors/advanced/licensing.html",
            snippet="US Nuclear Regulatory Commission licensing rules for part 53.",
            publisher="US NRC",
        ),
    ]

    mock_search = MockSearchProvider(
        query_results={
            "query_1": query_1_results,
            "query_2": query_2_results,
        }
    )

    registrar = SourceRegistrar(db=db_session, search_provider=mock_search)

    # 3. Execute registration
    sources = await registrar.search_and_register(
        project_id=project.id,
        queries=["query_1", "query_2"],
    )

    # 4. Verify that 4 raw results collapsed to exactly 3 unique sources
    assert len(sources) == 3
    urls = [s.canonical_url for s in sources]
    assert "https://www.lazard.com/research-insights/smr-lcoe" in urls
    assert "https://world-nuclear.org/information-library/nuclear-fuel-cycle/nuclear-power-reactors/small-nuclear-power-reactors.aspx" in urls
    assert "https://www.nrc.gov/reactors/new-reactors/advanced/licensing.html" in urls

    # Check that metadata and timestamps are populated
    lazard = next(s for s in sources if "lazard.com" in s.canonical_url)
    assert lazard.publisher == "Lazard"
    assert lazard.access_time is not None
    assert lazard.raw_metadata is not None
    assert "original_url" in lazard.raw_metadata

    # 5. Idempotency check: re-run search with same queries
    re_registered = await registrar.search_and_register(
        project_id=project.id,
        queries=["query_1"],
    )
    # Total count in DB remains 3
    db_sources = (await db_session.execute(
        select(Source).where(Source.project_id == project.id)
    )).scalars().all()
    assert len(db_sources) == 3
