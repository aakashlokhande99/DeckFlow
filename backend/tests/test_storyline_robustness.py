"""Unit and integration tests for storyline error resilience and PostgreSQL compatibility."""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus
from app.db.models import Insight, Project, SlideSpec, StringArray
from app.presentation.html_viewer import HTMLPresentationGenerator
from app.presentation.renderer import PresentationRenderer
from app.presentation.storyline import StorylineGenerator
from app.schemas.storyline import SlideItem


def test_string_array_postgresql_resilience():
    """Verify StringArray filters out non-UUID strings on PostgreSQL to prevent DataError."""
    sa = StringArray()
    valid_uuid_1 = uuid.uuid4()
    valid_uuid_str = str(uuid.uuid4())
    mixed_input = [
        valid_uuid_1,
        "src-claim-001",
        valid_uuid_str,
        "not-a-real-uuid",
        "E1",
    ]

    pg_bound = sa.process_bind_param(mixed_input, postgresql.dialect())
    assert len(pg_bound) == 2
    assert all(isinstance(x, uuid.UUID) for x in pg_bound)
    assert pg_bound[0] == valid_uuid_1
    assert str(pg_bound[1]) == valid_uuid_str

    # Verify SQLite preserves all strings
    sqlite_bound = sa.process_bind_param(mixed_input, sqlite.dialect())
    assert len(sqlite_bound) == 5
    assert all(isinstance(x, str) for x in sqlite_bound)

    # Verify result_value always returns strings
    res = sa.process_result_value(pg_bound, postgresql.dialect())
    assert len(res) == 2
    assert all(isinstance(x, str) for x in res)


@pytest.mark.asyncio
async def test_storyline_generator_resilient_to_edge_case_data(db_session: AsyncSession):
    """Test storyline generation handles recommendations with 'action', None fields, short objectives, etc."""
    project = Project(
        topic="AI Data Center Microgrids",
        objective="Test",  # short objective (< 5 chars)
        audience="C-Suite",
        geography="North America",
        time_horizon="2026-2030",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    # Insight with real schema structures:
    # - recommendations have 'action' (not 'recommendation') and some None fields
    # - gaps have 'gap_description' (not 'gap')
    # - limitations is a list of strings
    # - non-UUID evidence_ids
    insight = Insight(
        project_id=project.id,
        executive_summary="Executive synthesis test summary.",
        findings=[
            {
                "id": "F1",
                "finding": "Power reliability is critical for AI clusters.",
                "evidence_ids": ["src-001", "non-uuid-claim"],
                "confidence": "high",
            }
        ],
        implications=[{"implication": "Grid interconnect delays demand off-grid generation."}],
        recommendations=[
            {
                "id": "R1",
                "action": "Procure modular generation equipment.",
                "recommendation": None,  # Explicit None to test NoneType subscript bug
                "timeframe": "0-6 months",
                "priority": "high",
            }
        ],
        risks=[
            {
                "id": "RK1",
                "risk": "Supply chain bottlenecks",
                "severity": "medium",
                "mitigation": "Dual-source critical hardware.",
            }
        ],
        gaps=[
            {
                "id": "G1",
                "gap_description": "Microgrid switchgear transient response logs.",
                "impact_on_decision": "Requires pilot testing.",
            }
        ],
        limitations=["Public vendor benchmark data limited to FOAK deployments."],
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id, force_regenerate=True)

    assert outline is not None
    assert outline.total_slides == 11
    assert len(outline.slides) == 11

    # Verify Slide 1 objective defaulted safely
    assert len(outline.slides[0].key_message) >= 5

    # Verify Slide 7 used recommendation action without crashing on None
    rec_slide = outline.slides[6]
    cards = rec_slide.content.get("cards", [])
    assert len(cards) >= 1
    assert "Procure modular generation equipment" in cards[0]["text"]

    # Test update_storyline with non-UUID slide id (e.g. from frontend)
    slides_to_update = outline.slides
    slides_to_update[0].id = "temp-frontend-id-123"
    updated = await generator.update_storyline(project.id, slides_to_update, approve_all=True)
    assert updated is not None
    assert updated.is_approved is True


@pytest.mark.asyncio
async def test_auto_generate_storyline_in_renderer(db_session: AsyncSession, tmp_path):
    """Verify storyline generator creates slide specs that unblock renderer and HTML exporter."""
    project = Project(
        topic="SMR Grid Stability",
        objective="Assess capital costs and power reliability.",
        audience="Board of Directors",
        geography="US",
        time_horizon="2026-2035",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Solid commercial case for SMR deployment.",
        findings=[{"id": "F1", "finding": "LCOE is competitive.", "evidence_ids": []}],
        implications=[{"implication": "Significant CapEx optimization."}],
        recommendations=[{"id": "R1", "action": "Charter pilot project."}],
        risks=[{"id": "RK1", "risk": "Licensing timeline risk."}],
        limitations=[],
        gaps=[],
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    # Generate storyline first
    generator = StorylineGenerator(db=db_session)
    outline = await generator.generate_storyline(project.id)
    assert outline.total_slides == 11

    # Now renderer succeeds
    renderer = PresentationRenderer(db=db_session, output_dir=str(tmp_path))
    artifact = await renderer.render(project.id)
    assert artifact is not None
    assert artifact.file_size_bytes > 0

    # Verify HTML presentation generator succeeds
    html_gen = HTMLPresentationGenerator(db=db_session, output_dir=str(tmp_path))
    path, size, _ = await html_gen.generate(project.id)
    assert size > 0


@pytest.mark.asyncio
async def test_download_artifact_updates_project_status_to_completed(
    async_client, db_session: AsyncSession
):
    """Verify downloading PPT artifact transitions project status to completed."""
    project = Project(
        topic="Hyperscale AI SMRs",
        objective="Assess capital costs and power reliability for off-grid operations.",
        audience="Executive Board",
        geography="North America",
        time_horizon="2026-2035",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Solid commercial case for SMR deployment in hyperscale data centers.",
        findings=[{"id": "F1", "finding": "NOAK capital costs are competitive.", "evidence_ids": []}],
        implications=[{"implication": "Significant CapEx optimization."}],
        recommendations=[{"id": "R1", "action": "Mobilize procurement consortium."}],
        risks=[{"id": "RK1", "risk": "NRC licensing delay risk."}],
        limitations=[],
        gaps=[],
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    # Pre-generate storyline
    gen = StorylineGenerator(db=db_session)
    await gen.generate_storyline(project.id)

    # 1. Download artifact via API endpoint
    resp = await async_client.get(f"/api/projects/{project.id}/artifact?format=pptx")
    assert resp.status_code == 200

    # 2. Verify project details reflect status completed
    proj_resp = await async_client.get(f"/api/projects/{project.id}")
    assert proj_resp.status_code == 200
    proj_data = proj_resp.json()
    assert proj_data["status"] == "completed"
