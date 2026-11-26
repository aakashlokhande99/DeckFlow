"""Automated Tests for Standalone Interactive HTML Presentation Viewer Generator."""

from __future__ import annotations

import os
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source
from app.presentation.html_viewer import HTMLGateError, HTMLPresentationGenerator
from app.presentation.templates import get_template


@pytest.fixture
async def approved_html_project(db_session: AsyncSession) -> Project:
    """Fixture creating an approved project with insight, sources, and multiple layout slide specs."""
    project = Project(
        topic="Autonomous AI Agents in Enterprise Workflow Orchestration",
        objective="Assess multi-agent reliability, human-in-the-loop review gates, and token cost economics.",
        audience="Chief Technology Officer",
        geography="Global",
        time_horizon="2025-2027",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    source = Source(
        project_id=project.id,
        canonical_url="https://arxiv.org/abs/2401.00001",
        title="Multi-Agent Orchestration Telemetry",
        publisher="AI Research Institute",
        access_time=project.created_at,
    )
    db_session.add(source)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Stateful multi-agent DAGs reduce task completion latency by 68% while preserving strict auditability.",
        findings=[
            {
                "claim": "Human-in-the-loop review gates prevent 99.4% of hallucinated action payloads.",
                "evidence": "Benchmark audit across 1,200 production evaluation runs.",
                "confidence": "high",
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
        title="Autonomous AI Agents in Enterprise Workflow",
        key_message="Multi-agent orchestration architecture overview.",
        layout=SlideLayout.title.value,
        source_ids=[str(source.id)],
    )
    s2 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=2,
        title="Executive Summary & Strategic Takeaways",
        key_message="Core pillars of autonomous enterprise workflow deployment.",
        layout=SlideLayout.executive_summary.value,
        content={
            "summary": "Stateful multi-agent DAGs reduce task completion latency by 68%.",
            "key_takeaways": ["Deterministic State Graphs", "Asynchronous Gate Telemetry", "Audit-Ready Provenance"],
        },
        source_ids=[str(source.id)],
    )
    s3 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=3,
        title="Enterprise Architecture Scorecard",
        key_message="Comprehensive assessment across governance and latency dimensions.",
        layout=SlideLayout.scorecard.value,
        content={
            "dimensions": [
                {
                    "dimension": "Latency & Throughput",
                    "weight": "40%",
                    "score": "High (4.8/5)",
                    "status": "green",
                    "key_finding": "Sub-second asynchronous edge dispatch.",
                },
                {
                    "dimension": "Human Gate Security",
                    "weight": "35%",
                    "score": "High (5.0/5)",
                    "status": "green",
                    "key_finding": "Cryptographic approval signatures on all gate transitions.",
                },
                {
                    "dimension": "Token Unit Cost",
                    "weight": "25%",
                    "score": "Medium (3.4/5)",
                    "status": "amber",
                    "key_finding": "High thinking budget increases token consumption.",
                },
            ]
        },
    )
    s4 = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=4,
        title="Key Performance Metrics",
        key_message="Core scalability and quality metrics.",
        layout=SlideLayout.metrics.value,
        content={
            "metrics": [
                {"label": "End-to-End Latency", "value": "1.2s", "delta": "-68% YoY", "subtext": "Median turn time"},
                {"label": "Gate Accuracy", "value": "99.4%", "delta": "Verified", "subtext": "Zero unreviewed bypasses"},
                {"label": "Parallel Scaling", "value": "1,000+", "delta": "Concurrent", "subtext": "Stateless worker pods"},
                {"label": "Token ROI", "value": "14.2x", "delta": "+3.4x", "subtext": "Value generated per token dollar"},
            ]
        },
    )
    db_session.add_all([s1, s2, s3, s4])
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_html_viewer_generates_valid_html(
    db_session: AsyncSession, approved_html_project: Project, tmp_path: os.PathLike
):
    """Test HTMLPresentationGenerator produces standalone, interactive HTML with all components."""
    generator = HTMLPresentationGenerator(db=db_session, output_dir=str(tmp_path))
    file_path, file_size, file_hash = await generator.generate(approved_html_project.id)

    assert os.path.exists(file_path)
    assert file_size > 0
    assert len(file_hash) == 64

    with open(file_path, "r", encoding="utf-8") as f:
        html_doc = f.read()

    # Valid HTML structure
    assert "<!DOCTYPE html>" in html_doc
    assert '<html lang="en">' in html_doc
    assert '<div class="slide-viewport"' in html_doc

    # Slides present
    assert 'id="slide-1"' in html_doc
    assert 'id="slide-2"' in html_doc
    assert 'id="slide-3"' in html_doc
    assert 'id="slide-4"' in html_doc

    # Interactive elements
    assert 'id="progress-bar"' in html_doc
    assert 'id="notes-drawer"' in html_doc
    assert 'id="overview-modal"' in html_doc

    # Keyboard & touch events embedded
    assert "addEventListener('keydown'" in html_doc
    assert "addEventListener('touchstart'" in html_doc
    assert "addEventListener('touchend'" in html_doc
    assert "ArrowRight" in html_doc
    assert "toggleNotes" in html_doc
    assert "toggleOverview" in html_doc
    assert "toggleFullscreen" in html_doc

    # Print stylesheet
    assert "@media print" in html_doc
    assert "page-break-after: always" in html_doc


def test_html_viewer_zero_cdn_dependencies(
    approved_html_project: Project, tmp_path: os.PathLike, db_session: AsyncSession
):
    """Verify generated HTML has zero external CDN dependencies for air-gapped viewing."""
    # Use sync read of generated file or direct render
    generator = HTMLPresentationGenerator(db=db_session, output_dir=str(tmp_path))
    html_content = generator._render_full_html(
        project=approved_html_project,
        insight=Insight(executive_summary="test", is_approved=True),
        slide_specs=[],
        source_map={},
        initial_view="presentation",
    )

    external_cdns = [
        "cdn.jsdelivr.net",
        "cdnjs.cloudflare.com",
        "unpkg.com",
        "fonts.googleapis.com",
        "stackpath.bootstrapcdn.com",
    ]
    for cdn in external_cdns:
        assert cdn not in html_content, f"Found external CDN reference: {cdn}"


@pytest.mark.asyncio
async def test_html_viewer_gate_blocks_unapproved_insight(
    db_session: AsyncSession, tmp_path: os.PathLike
):
    """Test gate enforcement: HTML presentation export raises HTMLGateError on unapproved insight."""
    project = Project(
        topic="Unapproved HTML Deck",
        objective="Verify gate blocks presentation export.",
        audience="Tech Reviewers",
        geography="Global",
        time_horizon="2025",
        status=ProjectStatus.draft.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Draft in progress.",
        is_approved=False,  # Unapproved!
        version=1,
    )
    db_session.add(insight)
    await db_session.commit()

    generator = HTMLPresentationGenerator(db=db_session, output_dir=str(tmp_path))
    with pytest.raises(HTMLGateError, match="has not been approved"):
        await generator.generate(project.id)


@pytest.mark.asyncio
async def test_html_viewer_document_mode_and_theming(
    db_session: AsyncSession, approved_html_project: Project, tmp_path: os.PathLike
):
    """Test generating HTML in executive document mode with Bain Crimson theme."""
    template = get_template("bain_crimson")
    generator = HTMLPresentationGenerator(
        db=db_session, output_dir=str(tmp_path), template=template
    )
    file_path, file_size, file_hash = await generator.generate(
        approved_html_project.id, initial_view="document"
    )

    with open(file_path, "r", encoding="utf-8") as f:
        html_doc = f.read()

    # Document mode applied to body
    assert '<body class="mode-document">' in html_doc

    # Theming variables injected
    assert "--color-primary: #881337;" in html_doc
    assert "--color-accent: #E11D48;" in html_doc
    assert '"Georgia"' in html_doc


@pytest.mark.asyncio
async def test_html_download_api_endpoint(
    async_client: AsyncClient, approved_html_project: Project
):
    """Test GET /api/projects/{id}/artifact?format=html returns 200 and text/html."""
    resp = await async_client.get(
        f"/api/projects/{approved_html_project.id}/artifact?format=html&template=modern_tech&view=presentation"
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "consulting_deck_" in resp.headers.get("content-disposition", "")
    assert "<!DOCTYPE html>" in resp.text
    assert "--color-accent: #0D9488;" in resp.text


@pytest.mark.asyncio
async def test_templates_api_endpoint(
    async_client: AsyncClient, approved_html_project: Project
):
    """Test GET /api/projects/{id}/templates returns list of 5 corporate brand presets."""
    resp = await async_client.get(f"/api/projects/{approved_html_project.id}/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 5

    template_ids = [t["id"] for t in data]
    assert "mckinsey_navy" in template_ids
    assert "bcg_emerald" in template_ids
    assert "bain_crimson" in template_ids
    assert "goldman_slate" in template_ids
    assert "modern_tech" in template_ids


@pytest.mark.asyncio
async def test_html_viewer_adversarial_xss_and_script_tag_breakout(
    db_session: AsyncSession, tmp_path: os.PathLike
):
    """Test HTMLPresentationGenerator defends against Stored DOM XSS and script tag breakout.

    Verifies:
    - HTML does NOT contain raw `</script>` inside the `<script>` block (script tag count equals expected count).
    - `<script>alert("PWNED")</script>` is HTML-escaped.
    - `"><img src=x onerror=alert(1)>` is HTML-escaped.
    """
    project = Project(
        topic="Adversarial Injection Security Audit",
        objective="Verify script tag breakout and DOM XSS sanitization in HTML presentation viewer.",
        audience="Security Architect",
        geography="Global",
        time_horizon="2025",
        status=ProjectStatus.approved.value,
    )
    db_session.add(project)
    await db_session.flush()

    insight = Insight(
        project_id=project.id,
        executive_summary="Adversarial injection verification testing.",
        is_approved=True,
        version=1,
    )
    db_session.add(insight)
    await db_session.flush()

    malicious_title = '</script><script>alert("PWNED")</script>'
    malicious_key_message = '"><img src=x onerror=alert(1)>'

    slide = SlideSpec(
        project_id=project.id,
        insight_id=insight.id,
        slide_order=1,
        title=malicious_title,
        key_message=malicious_key_message,
        layout=SlideLayout.title.value,
    )
    db_session.add(slide)
    await db_session.commit()

    generator = HTMLPresentationGenerator(db=db_session, output_dir=str(tmp_path))
    file_path, file_size, file_hash = await generator.generate(project.id)

    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        html_doc = f.read()

    # 1. Verify script tag count: exactly 1 opening <script> and 1 closing </script>.
    # Breakout attempts must NOT prematurely close the script block or create a new script block.
    assert html_doc.count("<script>") == 1
    assert html_doc.count("</script>") == 1

    # 2. Raw breakout string must NOT exist anywhere in the generated HTML
    assert '</script><script>alert("PWNED")</script>' not in html_doc
    assert '"><img src=x onerror=alert(1)>' not in html_doc

    # 3. Verify HTML escaping of title and key_message across the document (slide, overview, notes)
    assert "&lt;/script&gt;&lt;script&gt;alert(&quot;PWNED&quot;)&lt;/script&gt;" in html_doc
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in html_doc

