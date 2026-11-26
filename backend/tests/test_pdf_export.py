"""Automated Tests for Executive PDF Summary Exporter and Gate Enforcement."""

from __future__ import annotations

import os
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source
from app.presentation.pdf_exporter import ExecutivePDFExporter, PDFGateError
from app.presentation.templates import get_template


@pytest.fixture
async def approved_pdf_project(db_session: AsyncSession) -> Project:
    """Fixture creating an approved project with insight and slide specs."""
    project = Project(
        topic="Enterprise Cloud FinOps Transformation",
        objective="Analyze cloud spend optimization, unit economics, and multi-cloud governance.",
        audience="Chief Financial Officer",
        geography="North America",
        time_horizon="2025-2028",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    source = Source(
        project_id=project.id,
        canonical_url="https://finops.org/benchmarks/2025",
        title="State of Cloud FinOps 2025",
        publisher="FinOps Foundation",
        access_time=project.created_at,
    )
    db_session.add(source)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Targeted FinOps interventions reduce unallocated cloud waste by 22-28% within 90 days.",
        findings=[
            {
                "claim": "Idle compute resources account for 34% of unallocated enterprise cloud spend.",
                "evidence": "Observed audit logs across 45 Fortune 500 Kubernetes clusters.",
                "confidence": "high",
            },
            {
                "claim": "Automated spot-instance lifecycle management yields 42% cost savings on batch workloads.",
                "evidence": "Benchmark data from tier-1 cloud providers.",
                "confidence": "high",
            },
        ],
        implications=[{"implication": "Reduces annual IT operating budget variance to under 4%."}],
        recommendations=[
            "Establish automated tagging policy and container rightsizing gates.",
            "Deploy centralized commitment discount optimizer across all cloud accounts.",
        ],
        risks=[
            {
                "risk": "Application latency degradation during aggressive container rightsizing.",
                "severity": "medium",
                "mitigation": "Enforce automated Canary testing and SLO circuit breakers.",
            }
        ],
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.flush()

    s1 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=1,
        title="Enterprise Cloud FinOps Transformation",
        key_message="Immediate optimization opportunities across compute and storage tiers.",
        layout=SlideLayout.title.value,
    )
    db_session.add(s1)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_pdf_export_generates_valid_pdf(
    db_session: AsyncSession, approved_pdf_project: Project, tmp_path: os.PathLike
):
    """Test ExecutivePDFExporter produces a non-empty, valid PDF file."""
    exporter = ExecutivePDFExporter(db=db_session, output_dir=str(tmp_path))
    file_path, file_size, file_hash = await exporter.export(approved_pdf_project.id)

    assert os.path.exists(file_path)
    assert file_size > 0
    assert len(file_hash) == 64

    # Verify PDF magic bytes (%PDF-)
    with open(file_path, "rb") as f:
        header = f.read(5)
    assert header == b"%PDF-", f"Expected %PDF- header, got {header!r}"


@pytest.mark.asyncio
async def test_pdf_export_gate_blocks_unapproved_insight(
    db_session: AsyncSession, tmp_path: os.PathLike
):
    """Test gate enforcement: PDF export raises PDFGateError on unapproved insight."""
    project = Project(
        topic="Unapproved FinOps Topic",
        objective="Assess unapproved cloud spend.",
        audience="Finance Committee",
        geography="Global",
        time_horizon="2025",
        status=ProjectStatus.awaiting_review.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Draft memo pending review.",
        is_approved=False,  # Unapproved!
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    exporter = ExecutivePDFExporter(db=db_session, output_dir=str(tmp_path))
    with pytest.raises(PDFGateError, match="has not been approved"):
        await exporter.export(project.id)


@pytest.mark.asyncio
async def test_pdf_export_nonexistent_project_raises_error(
    db_session: AsyncSession, tmp_path: os.PathLike
):
    """Test exporting a non-existent project raises PDFGateError."""
    exporter = ExecutivePDFExporter(db=db_session, output_dir=str(tmp_path))
    with pytest.raises(PDFGateError, match="not found"):
        await exporter.export(uuid.uuid4())


@pytest.mark.asyncio
async def test_pdf_export_with_custom_template(
    db_session: AsyncSession, approved_pdf_project: Project, tmp_path: os.PathLike
):
    """Test PDF export executes successfully with Goldman Slate corporate theme."""
    template = get_template("goldman_slate")
    exporter = ExecutivePDFExporter(
        db=db_session, output_dir=str(tmp_path), template=template
    )
    file_path, file_size, file_hash = await exporter.export(approved_pdf_project.id)

    assert os.path.exists(file_path)
    assert file_size > 0
    with open(file_path, "rb") as f:
        assert f.read(5) == b"%PDF-"


@pytest.mark.asyncio
async def test_pdf_download_api_endpoint(
    async_client: AsyncClient, approved_pdf_project: Project
):
    """Test GET /api/projects/{id}/artifact?format=pdf returns 200 and valid PDF."""
    resp = await async_client.get(
        f"/api/projects/{approved_pdf_project.id}/artifact?format=pdf&template=bcg_emerald"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "executive_summary_" in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-")
