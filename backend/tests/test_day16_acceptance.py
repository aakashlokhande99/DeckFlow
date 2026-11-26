"""Day 16 tests: Full end-to-end acceptance test, security hardening, and release gates."""

from __future__ import annotations

import io
import uuid
import pytest
from httpx import AsyncClient
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import validate_url
from app.db.enums import ConfidenceLevel, ProjectStatus
from app.db.models import EvidenceClaim, Insight, Project, Source
from app.llm.mock import MockLLMProvider
from app.presentation.storyline import StorylineGenerator
from app.schemas.project import ResearchPlan
from app.schemas.synthesis import (
    ConsultingSynthesis,
    SynthesisFinding,
    SynthesisGap,
    SynthesisImplication,
    SynthesisRecommendation,
    SynthesisRisk,
)


@pytest.mark.asyncio
async def test_full_end_to_end_acceptance_workflow(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full E2E acceptance: Brief -> Research -> Review -> Storyline -> PPTX Download."""
    # -----------------------------------------------------------------------
    # Step 1: Create Project Brief
    # -----------------------------------------------------------------------
    brief = {
        "topic": "Direct Air Carbon Capture (DAC) Unit Economics",
        "objective": "Assess levelized cost of CO2 removal, thermodynamic energy intensity, and commercial scale.",
        "audience": "Infrastructure Investment Committee",
        "geography": "Global & North America",
        "time_horizon": "2025-2035",
        "research_depth": "standard",
    }
    create_res = await async_client.post("/api/projects", json=brief)
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # -----------------------------------------------------------------------
    # Step 2: Simulate Research & Synthesis Phase (with grounded evidence)
    # -----------------------------------------------------------------------
    # Add verified sources and evidence claims to database
    from datetime import datetime, timezone
    source = Source(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        canonical_url="https://iea.org/reports/direct-air-capture-2024",
        title="IEA Direct Air Capture Report 2024",
        publisher="International Energy Agency",
        access_time=datetime.now(timezone.utc),
    )
    db_session.add(source)
    await db_session.flush()

    claim1 = EvidenceClaim(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        source_ids=[source.id],
        claim_text="Levelized cost of direct air capture currently ranges between $400 and $700 per metric ton of CO2.",
        confidence=ConfidenceLevel.high.value,
        version=1,
    )
    claim2 = EvidenceClaim(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        source_ids=[source.id],
        claim_text="Thermal desorption energy requirements exceed 1,500 kWh per ton of captured CO2 in solid-sorbent systems.",
        confidence=ConfidenceLevel.high.value,
        version=1,
    )
    db_session.add_all([claim1, claim2])
    await db_session.flush()

    # Create Insight representing research output awaiting review
    insight = Insight(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        executive_summary="Direct Air Capture requires significant CapEx deflation and low-cost geothermal/nuclear power to achieve the $100/ton milestone.",
        findings=[
            {
                "id": "F1",
                "finding": "DAC removal costs currently range from $400 to $700 per ton.",
                "evidence_ids": [str(claim1.id)],
                "confidence": "high",
            },
            {
                "id": "F2",
                "finding": "Thermal desorption consumes >1,500 kWh per ton of captured CO2.",
                "evidence_ids": [str(claim2.id)],
                "confidence": "high",
            },
        ],
        implications=[
            {"implication": "Co-location with dedicated zero-carbon heat/power is mandatory for commercial viability."}
        ],
        recommendations=[
            {
                "recommendation": "Require developer projects to secure firm power purchase agreements below $35/MWh.",
                "priority": "immediate",
            }
        ],
        risks=[
            {
                "risk": "Parasitic energy load makes grid-connected facilities carbon-positive if grid intensity is high.",
                "severity": "high",
                "mitigation": "Enforce strict hourly matching with renewable or nuclear generation.",
            }
        ],
        limitations=[{"limitation": "Solid-sorbent degradation rates in field conditions are undisclosed."}],
        gaps=[{"gap": "Commercial scale off-take pricing contracts in compliance carbon markets."}],
        citations=[],
        qa_report={"passed": True, "composite_score": 0.94},
        is_approved=False,  # Human review pending!
        version=1,
    )
    db_session.add(insight)

    # Project transitions to awaiting_review
    p_stmt = select(Project).where(Project.id == uuid.UUID(project_id))
    proj = (await db_session.execute(p_stmt)).scalar_one()
    proj.status = ProjectStatus.awaiting_review.value
    await db_session.commit()

    # -----------------------------------------------------------------------
    # Step 3: Human Review Gate Inspection & Gate Enforcement
    # -----------------------------------------------------------------------
    # 3a. Verify GET /review returns complete evidence and synthesis report
    review_res = await async_client.get(f"/api/projects/{project_id}/review")
    assert review_res.status_code == 200
    rev_data = review_res.json()
    assert rev_data["project_status"] == "awaiting_review"
    assert len(rev_data["evidence"]) == 2
    assert len(rev_data["insight"]["findings"]) == 2
    assert rev_data["insight"]["is_approved"] is False

    # 3b. Verify Gate: Attempting to generate storyline BEFORE approval is blocked!
    storyline_gate_res = await async_client.get(f"/api/projects/{project_id}/storyline")
    assert storyline_gate_res.status_code == 400
    assert "Cannot generate storyline from unapproved research" in storyline_gate_res.json()["detail"]

    # 3c. Verify Gate: Attempting to download PPTX BEFORE approval is blocked!
    pptx_gate_res = await async_client.get(f"/api/projects/{project_id}/artifact")
    assert pptx_gate_res.status_code == 400
    assert "has not been approved" in pptx_gate_res.json()["detail"]

    # -----------------------------------------------------------------------
    # Step 4: Human Review Decision (Approval)
    # -----------------------------------------------------------------------
    approve_payload = {
        "action": "approve",
        "comments": "Approved after reviewing IEA evidence claims and thermal desorption energy metrics.",
    }
    approve_res = await async_client.post(f"/api/projects/{project_id}/review", json=approve_payload)
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # -----------------------------------------------------------------------
    # Step 5: Generate & Review Slide Storyline
    # -----------------------------------------------------------------------
    # Now that research is approved, GET /storyline succeeds
    storyline_res = await async_client.get(f"/api/projects/{project_id}/storyline")
    assert storyline_res.status_code == 200
    outline_data = storyline_res.json()
    assert 8 <= outline_data["total_slides"] <= 12
    slides = outline_data["slides"]

    # Reorder/edit storyline and accept
    slides[0]["title"] = "DAC Commercialization: Investment Committee Briefing"
    update_storyline_payload = {
        "slides": slides,
        "approve_all": True,
    }
    submit_storyline_res = await async_client.post(
        f"/api/projects/{project_id}/storyline",
        json=update_storyline_payload,
    )
    assert submit_storyline_res.status_code == 200
    assert submit_storyline_res.json()["is_approved"] is True

    # -----------------------------------------------------------------------
    # Step 6: Render & Download PPTX Deck
    # -----------------------------------------------------------------------
    artifact_res = await async_client.get(f"/api/projects/{project_id}/artifact")
    assert artifact_res.status_code == 200
    assert (
        artifact_res.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

    # -----------------------------------------------------------------------
    # Step 7: Verify Downloaded Presentation Integrity
    # -----------------------------------------------------------------------
    deck_stream = io.BytesIO(artifact_res.content)
    prs = Presentation(deck_stream)
    assert len(prs.slides) == 11
    assert round(prs.slide_width.inches, 2) == 13.33
    assert round(prs.slide_height.inches, 2) == 7.50

    # Verify action title on cover slide
    cover_text = ""
    for s in prs.slides[0].shapes:
        if s.has_text_frame:
            for p in s.text_frame.paragraphs:
                cover_text += p.text + " "
    assert "DAC Commercialization: Investment Committee Briefing" in cover_text


@pytest.mark.asyncio
async def test_security_hardening_headers(async_client: AsyncClient) -> None:
    """Verify production security response headers are present on all responses."""
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Referrer-Policy" in res.headers


@pytest.mark.asyncio
async def test_security_ssrf_blocking() -> None:
    """Verify SSRF protection strictly blocks internal IPs and metadata endpoints."""
    # Loopback
    with pytest.raises(ValueError):
        validate_url("http://127.0.0.1:8000")
    with pytest.raises(ValueError):
        validate_url("http://localhost:3000")

    # Private RFC 1918
    with pytest.raises(ValueError):
        validate_url("http://10.0.0.1/admin")
    with pytest.raises(ValueError):
        validate_url("http://192.168.1.1/secret")
    with pytest.raises(ValueError):
        validate_url("http://172.16.0.5/api")

    # AWS / GCP cloud metadata
    with pytest.raises(ValueError):
        validate_url("http://169.254.169.254/latest/meta-data/")

    # Disallowed scheme
    with pytest.raises(ValueError):
        validate_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        validate_url("ftp://example.com/file")
    with pytest.raises(ValueError):
        validate_url("javascript:alert(1)")
