"""Day 14 tests: PPTX rendering with python-pptx, reusable layouts, and artifact download."""

from __future__ import annotations

import io
import os
import uuid
import pytest
from httpx import AsyncClient
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus
from app.db.models import Artifact, Insight, Project, SlideSpec
from app.presentation.renderer import PresentationRenderer, RendererGateError
from app.presentation.storyline import StorylineGenerator


@pytest.fixture
async def approved_deck_project(db_session: AsyncSession) -> Project:
    """Create project with approved synthesis and generated storyline."""
    project = Project(
        topic="Solid-State EV Battery Commercialization",
        objective="Assess gravimetric energy density milestones, silicon-anode scaling, and gigafactory cell yield.",
        audience="Automotive OEM Board",
        geography="North America & Europe",
        time_horizon="2025-2030",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Solid-state cells achieve 450 Wh/kg gravimetric density with silicon-dominant anodes.",
        findings=[
            {
                "id": "F1",
                "finding": "Gen-1 solid electrolyte separators reduce dendrite risk at 3C fast charge rates.",
                "evidence_ids": ["ev-claim-001", "ev-claim-002"],
                "confidence": "high",
            },
            {
                "id": "F2",
                "finding": "Roll-to-roll manufacturing scrap rates remain elevated at 18-22%.",
                "evidence_ids": ["ev-claim-003"],
                "confidence": "medium",
            },
        ],
        implications=[
            {"implication": "Enables 600-mile passenger EV packs without chassis weight redesign."}
        ],
        recommendations=[
            {
                "recommendation": "Fund dedicated pilot line to qualify dry-electrode coating tooling.",
                "priority": "immediate",
            }
        ],
        risks=[
            {
                "risk": "Lithium metal foil supply shortage during pilot ramp.",
                "severity": "high",
                "mitigation": "Establish multi-year off-take agreements with dual suppliers.",
            }
        ],
        limitations=[{"limitation": "Cold weather cycling performance data is limited."}],
        gaps=[{"gap": "Proprietary cell degradation logs from OEM winter road tests."}],
        citations=[],
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    # Generate storyline
    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id)
    await generator.update_storyline(project.id, outline.slides, approve_all=True)

    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_renderer_gate_blocks_unapproved_project(db_session: AsyncSession) -> None:
    """Non-negotiable rule: No PowerPoint rendering before research is approved."""
    project = Project(
        topic="Unapproved AI Topic",
        objective="Assess LLM deployment.",
        audience="Tech Execs",
        geography="Global",
        time_horizon="2025",
        status=ProjectStatus.awaiting_review.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Pending review.",
        is_approved=False,  # Unapproved!
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    renderer = PresentationRenderer(db=db_session, output_dir="artifacts_test")
    with pytest.raises(RendererGateError, match="has not been approved"):
        await renderer.render(project.id)


@pytest.mark.asyncio
async def test_renderer_generates_valid_pptx(
    db_session: AsyncSession, approved_deck_project: Project, tmp_path: os.PathLike
) -> None:
    """Verify PPTX generation creates valid widescreen presentation with proper layout and metadata."""
    project = approved_deck_project
    renderer = PresentationRenderer(db=db_session, output_dir=str(tmp_path))

    artifact = await renderer.render(project.id)
    assert artifact is not None
    assert artifact.file_size_bytes is not None
    assert artifact.file_size_bytes > 0
    assert len(artifact.pptx_hash) == 64
    assert os.path.exists(artifact.file_path)

    # Open file with python-pptx to verify integrity
    prs = Presentation(artifact.file_path)
    # Check 16:9 widescreen dimensions (13.333" x 7.5")
    assert round(prs.slide_width.inches, 2) == 13.33
    assert round(prs.slide_height.inches, 2) == 7.50

    # Assert slide count matches storyline (11 slides)
    assert len(prs.slides) == 11

    # Verify each slide has shapes and text
    for i, slide in enumerate(prs.slides):
        assert len(slide.shapes) > 0
        # Check text in slide
        text_content = ""
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text_content += paragraph.text + " "
        assert len(text_content.strip()) > 10, f"Slide {i+1} has insufficient text"

    # Verify source citations exist on empirical slide
    empirical_slide = prs.slides[3]  # Slide 4
    empirical_text = ""
    for shape in empirical_slide.shapes:
        if shape.has_text_frame:
            for p in shape.text_frame.paragraphs:
                empirical_text += p.text + " "
    assert "Sources:" in empirical_text


@pytest.mark.asyncio
async def test_download_artifact_api_endpoint(
    async_client: AsyncClient, approved_deck_project: Project
) -> None:
    """Verify GET /api/projects/{id}/artifact delivers valid binary PPTX download."""
    project = approved_deck_project

    res = await async_client.get(f"/api/projects/{project.id}/artifact")
    assert res.status_code == 200
    assert (
        res.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert f"consulting_deck_{project.id}.pptx" in res.headers.get(
        "content-disposition", ""
    )

    # Read binary stream and verify with python-pptx
    deck_stream = io.BytesIO(res.content)
    prs = Presentation(deck_stream)
    assert len(prs.slides) == 11
