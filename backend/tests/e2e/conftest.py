"""Pytest configuration and shared fixtures for the E2E test suite."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import shutil
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

# Add backend and project root to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# SQLite compatibility compilers for PostgreSQL native types
# ---------------------------------------------------------------------------
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


# ---------------------------------------------------------------------------
# Test database engine and session maker (in-memory SQLite)
# ---------------------------------------------------------------------------
e2e_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
)

E2ESessionLocal = async_sessionmaker(
    e2e_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Point session module immediately to test session
import app.db.session
app.db.session.AsyncSessionLocal = E2ESessionLocal
app.db.session.engine = e2e_engine


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database():
    """Create all tables in the in-memory test database."""
    from app.db.base import Base
    import app.db.models  # noqa: F401

    app.db.session.AsyncSessionLocal = E2ESessionLocal
    app.db.session.engine = e2e_engine

    async with e2e_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with e2e_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await e2e_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for a test (rolls back on teardown)."""
    async with E2ESessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx.AsyncClient connected to the FastAPI app with test db override."""
    from app.db.session import get_db
    from app.main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def workspace_root() -> Path:
    """Return workspace root path."""
    return WORKSPACE_ROOT


# ---------------------------------------------------------------------------
# DNS Resolution Mocking (prevents offline DNS failures in sandbox)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_dns_resolution():
    """Mock socket.getaddrinfo to handle test domain resolution without external network."""
    orig_getaddrinfo = socket.getaddrinfo

    def _mock_getaddr(host, port, *args, **kwargs):
        if not host:
            return orig_getaddrinfo(host, port, *args, **kwargs)
        host_str = str(host).lower().strip("[]")
        # Blocked / loopback domains
        if host_str in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 80))]
        if host_str.isdigit():
            try:
                ip_val = str(ipaddress.IPv4Address(int(host_str)))
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip_val, port or 80))]
            except ValueError:
                pass
        if host_str.startswith("10.") or host_str.startswith("192.168.") or host_str.startswith("172."):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host_str, port or 80))]
        # Unresolvable domains for testing error handling
        if "unresolvable" in host_str or "nonexistent" in host_str:
            raise socket.gaierror(11001, "getaddrinfo failed")
        # Public domains (e.g. hooks.slack.com, api.example.com, etc.) -> safe public IP
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    with patch("socket.getaddrinfo", side_effect=_mock_getaddr):
        yield


# ---------------------------------------------------------------------------
# Seeding Helpers for E2E Tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seed_consulting_project(db_session: AsyncSession):
    """Factory fixture to create complete consulting projects with insights, sources, and slides."""
    from app.db.enums import ProjectStatus, SlideLayout
    from app.db.models import Insight, Project, SlideSpec, Source

    async def _creator(
        topic: str = "Enterprise Cloud Transformation & AI Strategy",
        objective: str = "Assess market opportunity and formulate a 3-year phased implementation roadmap",
        audience: str = "Board of Directors and C-Suite Executives",
        geography: str = "North America & EMEA",
        is_approved: bool = True,
        include_scorecard_and_metrics: bool = True,
    ) -> Dict[str, Any]:
        proj_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        project = Project(
            id=proj_id,
            topic=topic,
            objective=objective,
            audience=audience,
            geography=geography,
            time_horizon="3 years",
            research_depth="deep",
            status=ProjectStatus.approved.value if is_approved else ProjectStatus.awaiting_review.value,
        )
        db_session.add(project)
        await db_session.flush()

        # Add Sources
        sources = []
        for i in range(1, 6):
            s = Source(
                id=uuid.uuid4(),
                project_id=proj_id,
                canonical_url=f"https://research.gartner.example/report-{i}",
                title=f"Industry Benchmark Report {i} - Cloud & Enterprise AI",
                publisher="Gartner Research Advisory",
                access_time=now,
            )
            db_session.add(s)
            sources.append(s)
        await db_session.flush()

        # Add Insight
        insight_id = uuid.uuid4()
        insight = Insight(
            id=insight_id,
            project_id=proj_id,
            version=1,
            executive_summary=(
                "Enterprise AI adoption is accelerating at 38% CAGR. Early movers capture +1,350 bps "
                "margin expansion through modular architectures and automated workflows."
            ),
            findings=[
                {
                    "finding": "Cloud adoption has reached 84% penetration among Fortune 500 enterprises.",
                    "confidence": "high",
                    "evidence_ids": [str(sources[0].id)],
                },
                {
                    "finding": "Modular microservices architecture cuts deployment latency by 65%.",
                    "confidence": "high",
                    "evidence_ids": [str(sources[1].id)],
                },
            ],
            implications=[
                {"implication": "Legacy monolithic systems pose acute technical debt and margin drag."}
            ],
            recommendations=[
                {"recommendation": "Initiate 90-day pilot on core transaction processing workstreams."}
            ],
            risks=[
                {
                    "risk": "Regulatory and compliance delays in European operating units",
                    "severity": "medium",
                    "mitigation": "Establish early alignment with local data protection regulators.",
                }
            ],
            limitations=[{"limitation": "Vendor pricing models reflect preliminary standard rate cards."}],
            is_approved=is_approved,
        )
        db_session.add(insight)
        await db_session.flush()

        # Add Slides
        slides: List[SlideSpec] = []
        slide_order = 1

        # 1. Title
        slides.append(
            SlideSpec(
                id=uuid.uuid4(),
                project_id=proj_id,
                insight_id=insight_id,
                slide_order=slide_order,
                title="Strategic Assessment: Enterprise Cloud & AI",
                key_message="Strategic transformation agenda for executive leadership.",
                layout=SlideLayout.title.value,
                content={"topic": topic, "objective": objective, "audience": audience},
                source_ids=[],
                is_approved=is_approved,
            )
        )
        slide_order += 1

        # 2. Executive Summary
        slides.append(
            SlideSpec(
                id=uuid.uuid4(),
                project_id=proj_id,
                insight_id=insight_id,
                slide_order=slide_order,
                title="Executive Summary: Core Findings & Strategic Imperatives",
                key_message="Immediate modernization delivers sustainable competitive advantage.",
                layout=SlideLayout.executive_summary.value,
                content={
                    "summary": insight.executive_summary,
                    "key_takeaways": [
                        "84% enterprise adoption in tier-1 competitors.",
                        "+1,350 bps margin expansion via automation.",
                        "Critical execution risk requires governance controls.",
                    ],
                },
                source_ids=[str(sources[0].id)],
                is_approved=is_approved,
            )
        )
        slide_order += 1

        # 3. Two-Column Context
        slides.append(
            SlideSpec(
                id=uuid.uuid4(),
                project_id=proj_id,
                insight_id=insight_id,
                slide_order=slide_order,
                title="Macro Industry Dynamics & Problem Statement",
                key_message="Structural market shifts necessitate rapid technological realignment.",
                layout=SlideLayout.two_column.value,
                content={
                    "left_column": {
                        "heading": "Market Catalysts",
                        "bullets": ["Cloud-native migration.", "Accelerating AI efficiency."],
                    },
                    "right_column": {
                        "heading": "Strategic Challenges",
                        "bullets": ["Legacy technical debt.", "Talent constraints."],
                    },
                },
                source_ids=[str(sources[1].id)],
                is_approved=is_approved,
            )
        )
        slide_order += 1

        if include_scorecard_and_metrics:
            # 4. Scorecard Layout
            slides.append(
                SlideSpec(
                    id=uuid.uuid4(),
                    project_id=proj_id,
                    insight_id=insight_id,
                    slide_order=slide_order,
                    title="Strategic Opportunity Scorecard & Capability Audit",
                    key_message="High feasibility across financial and technological dimensions.",
                    layout=SlideLayout.scorecard.value,
                    content={
                        "dimensions": [
                            {
                                "dimension": "Market Attractiveness",
                                "weight": "30%",
                                "score": "High (4.5/5)",
                                "status": "green",
                                "key_finding": "TAM growing at 38% CAGR across key enterprise accounts.",
                            },
                            {
                                "dimension": "Defensible Moat",
                                "weight": "25%",
                                "score": "Medium (3.5/5)",
                                "status": "amber",
                                "key_finding": "Strong proprietary data assets with moderate switching costs.",
                            },
                            {
                                "dimension": "Financial Return",
                                "weight": "25%",
                                "score": "High (4.8/5)",
                                "status": "green",
                                "key_finding": "Payback velocity within 14 months and >32% projected IRR.",
                            },
                            {
                                "dimension": "Regulatory Overhead",
                                "weight": "20%",
                                "score": "Low (2.2/5)",
                                "status": "red",
                                "key_finding": "Evolving compliance frameworks require dedicated legal oversight.",
                            },
                        ]
                    },
                    source_ids=[str(sources[0].id), str(sources[1].id)],
                    is_approved=is_approved,
                )
            )
            slide_order += 1

            # 5. Metrics Layout
            slides.append(
                SlideSpec(
                    id=uuid.uuid4(),
                    project_id=proj_id,
                    insight_id=insight_id,
                    slide_order=slide_order,
                    title="Key Financial Benchmarks & Value Creation Metrics",
                    key_message="Quantifiable performance indicators validate investment thesis.",
                    layout=SlideLayout.metrics.value,
                    content={
                        "metrics": [
                            {
                                "label": "Projected TAM (2030)",
                                "value": "$48.5B",
                                "delta": "+38% YoY",
                                "subtext": "Global addressable market size",
                            },
                            {
                                "label": "EBITDA Margin Lift",
                                "value": "+1,350 bps",
                                "delta": "vs. Baseline",
                                "subtext": "Driven by autonomous pipeline processing",
                            },
                            {
                                "label": "Payback Velocity",
                                "value": "14 Mo.",
                                "delta": "-6 Mo. faster",
                                "subtext": "Rapid capital recovery timeline",
                            },
                            {
                                "label": "Error Reduction",
                                "value": "< 1.5%",
                                "delta": "from 12.0%",
                                "subtext": "Automated verification controls",
                            },
                        ]
                    },
                    source_ids=[str(sources[2].id)],
                    is_approved=is_approved,
                )
            )
            slide_order += 1

        # 6. Closing / Decision Gate
        slides.append(
            SlideSpec(
                id=uuid.uuid4(),
                project_id=proj_id,
                insight_id=insight_id,
                slide_order=slide_order,
                title="Executive Decision Gate & Immediate Action Plan",
                key_message="Approval requested to mobilize Phase 1 workstreams.",
                layout=SlideLayout.closing.value,
                content={
                    "call_to_action": "Board authorization for Phase 1 mobilization.",
                    "action_items": [
                        "Authorize project governance committee.",
                        "Finalize vendor architecture agreements.",
                    ],
                },
                source_ids=[],
                is_approved=is_approved,
            )
        )

        for s in slides:
            db_session.add(s)
        await db_session.commit()

        return {
            "project": project,
            "project_id": proj_id,
            "insight": insight,
            "insight_id": insight_id,
            "sources": sources,
            "slides": slides,
        }

    return _creator


@pytest_asyncio.fixture
async def seed_webhook_sub(db_session: AsyncSession):
    """Factory fixture to register a WebhookSubscription."""
    from app.db.models import WebhookSubscription

    async def _creator(
        url: str = "https://hooks.slack.com/services/T00/B00/X00",
        target_type: str = "slack",
        events: Optional[List[str]] = None,
        secret: Optional[str] = None,
        project_id: Optional[uuid.UUID] = None,
        is_active: bool = True,
    ) -> WebhookSubscription:
        sub = WebhookSubscription(
            id=uuid.uuid4(),
            target_type=target_type,
            url=url,
            secret=secret,
            events=events or ["slide_review_gate", "synthesis_review_gate"],
            project_id=project_id,
            is_active=is_active,
        )
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)
        return sub

    return _creator
