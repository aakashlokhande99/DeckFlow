"""Day 13 tests: Slide storyline generation, non-negotiable human gate, and outline editing."""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec
from app.presentation.storyline import (
    StorylineGateError,
    StorylineGenerator,
    StorylineValidationError,
)
from app.schemas.storyline import SlideItem, StorylineUpdateRequest


@pytest.fixture
async def approved_project(db_session: AsyncSession) -> tuple[Project, Insight]:
    """Create project with an approved synthesis insight."""
    project = Project(
        topic="Modular Nuclear Reactors in Industrial Microgrids",
        objective="Assess capital costs, safety licensing, and power reliability for off-grid operations.",
        audience="Industrial Enterprise C-Suite",
        geography="North America",
        time_horizon="2025-2035",
        status=ProjectStatus.awaiting_review.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="SMRs provide firm 95%+ capacity factor power at $75/MWh levelized cost after FOAK learning curve.",
        findings=[
            {
                "id": "F1",
                "finding": "SMR capital costs average $4,500/kW for NOAK builds.",
                "evidence_ids": ["src-claim-001", "src-claim-002"],
                "confidence": "high",
            },
            {
                "id": "F2",
                "finding": "Passive safety systems eliminate active cooling requirements during station blackout.",
                "evidence_ids": ["src-claim-003"],
                "confidence": "high",
            },
        ],
        implications=[
            {"implication": "Microgrid operators can eliminate diesel generator backup reliance."}
        ],
        recommendations=[
            {
                "recommendation": "Initiate combined NRC Part 50/52 licensing application with designated reactor vendor.",
                "priority": "immediate",
            }
        ],
        risks=[
            {
                "risk": "Regulatory approval delay past 36 months.",
                "severity": "high",
                "mitigation": "Partner with vendors holding certified standard designs.",
            }
        ],
        limitations=[{"limitation": "HALEU fuel supply chain constraints."}],
        gaps=[{"gap": "Local transmission interconnection tariffs."}],
        citations=[],
        is_approved=True,  # Approved!
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(insight)
    return project, insight


@pytest.mark.asyncio
async def test_storyline_gate_blocks_unapproved_synthesis(db_session: AsyncSession) -> None:
    """Non-negotiable rule: No storyline can be generated from unapproved research."""
    project = Project(
        topic="Unapproved Research Topic",
        objective="Verify gate blocks generation.",
        audience="Executive Board",
        geography="Global",
        time_horizon="2025",
        status=ProjectStatus.awaiting_review.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Draft synthesis pending human review.",
        is_approved=False,  # Unapproved!
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    generator = StorylineGenerator(db=db_session)
    with pytest.raises(StorylineGateError, match="Cannot generate storyline from unapproved research"):
        await generator.generate_storyline(project.id)


@pytest.mark.asyncio
async def test_storyline_gate_blocks_missing_insight(db_session: AsyncSession) -> None:
    """Blocks storyline generation if no research synthesis exists."""
    project = Project(
        topic="Fresh Project Without Research",
        objective="Should fail cleanly.",
        audience="Board",
        geography="Global",
        time_horizon="2025",
    )
    db_session.add(project)
    await db_session.commit()

    generator = StorylineGenerator(db=db_session)
    with pytest.raises(StorylineGateError, match="No research synthesis found"):
        await generator.generate_storyline(project.id)


@pytest.mark.asyncio
async def test_storyline_generation_success(
    db_session: AsyncSession, approved_project: tuple[Project, Insight]
) -> None:
    """Verify storyline generation produces 8-12 slides with non-empty titles and source links."""
    project, insight = approved_project
    generator = StorylineGenerator(db=db_session)

    outline = await generator.generate_storyline(project.id)
    assert 8 <= outline.total_slides <= 12
    assert outline.project_id == str(project.id)
    assert outline.insight_id == str(insight.id)
    assert outline.is_approved is False

    # Check slide order continuity 1..N
    orders = [s.slide_order for s in outline.slides]
    assert orders == list(range(1, len(outline.slides) + 1))

    # Assert all slides have non-empty titles and valid layouts
    for slide in outline.slides:
        assert len(slide.title.strip()) > 3
        assert len(slide.key_message.strip()) > 5
        assert isinstance(slide.layout, SlideLayout)
        assert isinstance(slide.content, dict)

    # Assert factual slides link source IDs
    empirical_slide = outline.slides[3]  # Slide 4
    assert len(empirical_slide.source_ids) > 0
    assert "src-claim-001" in empirical_slide.source_ids


@pytest.mark.asyncio
async def test_storyline_update_and_reorder(
    db_session: AsyncSession, approved_project: tuple[Project, Insight]
) -> None:
    """Verify reordering, editing, and validating slide specs."""
    project, _ = approved_project
    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id)

    # Reorder slides: swap slide 2 and slide 3
    updated_slides = [s.model_copy() for s in outline.slides]
    slide2 = updated_slides[1]
    slide3 = updated_slides[2]

    slide2.slide_order = 3
    slide2.title = "Updated Slide 2 Title"
    slide3.slide_order = 2
    slide3.title = "Updated Slide 3 Title"

    updated_outline = await generator.update_storyline(
        project_id=project.id,
        slides=updated_slides,
        approve_all=False,
    )
    assert updated_outline.total_slides == outline.total_slides

    # Verify in DB
    specs = (
        await db_session.execute(
            select(SlideSpec).where(SlideSpec.project_id == project.id).order_by(SlideSpec.slide_order.asc())
        )
    ).scalars().all()
    assert specs[1].title == "Updated Slide 3 Title"
    assert specs[2].title == "Updated Slide 2 Title"


@pytest.mark.asyncio
async def test_storyline_rejects_non_contiguous_order(
    db_session: AsyncSession, approved_project: tuple[Project, Insight]
) -> None:
    """Verify validation error when slide sequence contains gaps or duplicates."""
    project, _ = approved_project
    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id)

    invalid_slides = [s.model_copy() for s in outline.slides]
    invalid_slides[0].slide_order = 5  # gap: 5, 2, 3, 4 ...

    with pytest.raises(StorylineValidationError, match="contiguous 1-based sequence"):
        await generator.update_storyline(project_id=project.id, slides=invalid_slides)


@pytest.mark.asyncio
async def test_storyline_approve_all_transitions_project_status(
    db_session: AsyncSession, approved_project: tuple[Project, Insight]
) -> None:
    """Verify approve_all marks all slides approved and advances project to 'approved'."""
    project, _ = approved_project
    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id)

    updated = await generator.update_storyline(
        project_id=project.id,
        slides=outline.slides,
        approve_all=True,
    )
    assert updated.is_approved is True

    await db_session.refresh(project)
    assert project.status == ProjectStatus.approved.value


@pytest.mark.asyncio
async def test_storyline_api_endpoints(
    async_client: AsyncClient, db_session: AsyncSession, approved_project: tuple[Project, Insight]
) -> None:
    """Verify GET and POST /api/projects/{id}/storyline endpoints."""
    project, _ = approved_project

    # 1. GET storyline
    res_get = await async_client.get(f"/api/projects/{project.id}/storyline")
    assert res_get.status_code == 200
    data = res_get.json()
    assert 8 <= data["total_slides"] <= 12
    assert len(data["slides"]) == data["total_slides"]

    # 2. POST update storyline with edits
    slides_data = data["slides"]
    slides_data[0]["title"] = "Custom Executive Title from Client Review"
    update_payload = {"slides": slides_data, "approve_all": True}

    res_post = await async_client.post(
        f"/api/projects/{project.id}/storyline",
        json=update_payload,
    )
    assert res_post.status_code == 200
    updated_data = res_post.json()
    assert updated_data["is_approved"] is True
    assert updated_data["slides"][0]["title"] == "Custom Executive Title from Client Review"
