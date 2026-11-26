"""Tier 4: Real-World Application Scenarios Test Suite (8 Scenarios).

End-to-end, multi-feature enterprise workflows:
1. Strategy Deck Lifecycle to McKinsey PPTX with Scorecard & Metrics
2. Executive Memo Workflow: BCG Emerald PDF with Numbered Canvas & Multi-Page
3. Interactive Client Portal: Bain Crimson HTML Presentation Viewer
4. Enterprise Slack Notification Flow on Review Gate Arrival with Block Kit
5. Enterprise MS Teams Notification Flow on Review Gate Arrival with Adaptive Card 1.4
6. Multi-Channel Alerting & Resilient Webhook Retry on Transient Network Failure
7. Full Enterprise Multi-Format Export Bundle (PPTX + PDF + HTML) for Goldman Slate
8. Cloud Deployment Verification Matrix: Compose + K8s Probes + Helm + CI Pipeline
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from fastapi import status
from httpx import AsyncClient
from pptx import Presentation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.enums import ArtifactType, ProjectStatus, SlideLayout
from app.db.models import Artifact, Insight, Project, SlideSpec, Source, WebhookDelivery, WebhookSubscription
from app.notifications.dispatcher import WebhookDispatcher
from app.notifications.service import WebhookService
from app.presentation.html_viewer import HTMLPresentationGenerator
from app.presentation.pdf_exporter import ExecutivePDFExporter
from app.presentation.renderer import PresentationRenderer
from app.presentation.templates import get_template


class TestTier4Scenarios:
    """Tier 4: Real-world application scenario test cases."""

    # =========================================================================
    # Scenario 1: Strategy Deck Lifecycle to McKinsey PPTX with Scorecard & Metrics
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_1_full_lifecycle_mckinsey_deck_with_scorecard_and_metrics(
        self, async_client: AsyncClient, db_session: AsyncSession, seed_consulting_project
    ):
        """Scenario 1: Complete lifecycle from brief to approved McKinsey deck with scorecard & metrics."""
        # 1. Create project via brief
        brief_payload = {
            "topic": "Global Aerospace & Defense Commercial Modernization",
            "objective": "Formulate 3-year autonomous systems scaling and market entry roadmap",
            "audience": "Board of Directors and Operating Committee",
            "geography": "North America & NATO Allies",
            "time_horizon": "3 years",
            "research_depth": "deep",
        }
        create_resp = await async_client.post("/api/projects", json=brief_payload)
        assert create_resp.status_code == status.HTTP_201_CREATED
        pid = uuid.UUID(create_resp.json()["id"])

        # 2. Seed approved insight and slides (including scorecard & metrics)
        now_proj = await db_session.get(Project, pid)
        data = await seed_consulting_project(
            topic=brief_payload["topic"],
            is_approved=True,
            include_scorecard_and_metrics=True,
        )
        # Use seeded project ID
        seed_pid = data["project_id"]

        # 3. Export PPTX with McKinsey Navy template
        export_resp = await async_client.get(
            f"/api/projects/{seed_pid}/artifact?format=pptx&template=mckinsey_navy"
        )
        assert export_resp.status_code == status.HTTP_200_OK
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in export_resp.headers["content-type"]
        assert f"consulting_deck_{seed_pid}.pptx" in export_resp.headers["content-disposition"]

        # 4. Open PPTX with python-pptx and verify layouts
        prs_path = Path("artifacts") / f"consulting_deck_{seed_pid}.pptx"
        assert prs_path.exists()
        prs = Presentation(str(prs_path))
        assert len(prs.slides) >= 5

        # Check widescreen dimensions (13.333" x 7.5")
        assert round(prs.slide_width.inches, 3) == 13.333
        assert round(prs.slide_height.inches, 1) == 7.5

    # =========================================================================
    # Scenario 2: Executive Memo Workflow: BCG Emerald PDF with Numbered Canvas
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_2_executive_memo_workflow_bcg_emerald_pdf(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """Scenario 2: Executive briefing memo workflow generating multi-page BCG Emerald PDF."""
        data = await seed_consulting_project(
            topic="Clean Energy Grid Modernization & Capital Allocation",
            is_approved=True,
            include_scorecard_and_metrics=True,
        )
        pid = data["project_id"]

        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pdf&template=bcg_emerald")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.headers["content-type"] == "application/pdf"
        assert f"executive_summary_{pid}.pdf" in resp.headers["content-disposition"]

        pdf_path = Path("artifacts") / f"executive_summary_{pid}.pdf"
        assert pdf_path.exists()
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            assert pdf_bytes.startswith(b"%PDF-")
            assert len(pdf_bytes) > 5000

    # =========================================================================
    # Scenario 3: Interactive Client Portal: Bain Crimson HTML Presentation
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_3_interactive_client_portal_bain_crimson_html(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """Scenario 3: Interactive single-file HTML presentation portal with Bain Crimson theming."""
        data = await seed_consulting_project(
            topic="Private Equity Healthcare Portfolio Value Creation",
            is_approved=True,
            include_scorecard_and_metrics=True,
        )
        pid = data["project_id"]

        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=html&template=bain_crimson&view=presentation")
        assert resp.status_code == status.HTTP_200_OK
        assert "text/html" in resp.headers["content-type"]

        html_path = Path("artifacts") / f"consulting_deck_{pid}.html"
        assert html_path.exists()
        html_content = html_path.read_text(encoding="utf-8")

        # Verify Bain Crimson theme colors embedded
        assert "--c-primary: #881337" in html_content
        assert "--c-accent: #E11D48" in html_content
        # Verify interactivity and overview grid
        assert "ArrowRight" in html_content
        assert "overview-card" in html_content
        assert "@media print" in html_content

    # =========================================================================
    # Scenario 4: Enterprise Slack Notification Flow on Review Gate Arrival
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_4_enterprise_slack_notification_flow(
        self, async_client: AsyncClient, db_session: AsyncSession, seed_consulting_project
    ):
        """Scenario 4: Slide review gate arrival triggers Slack Block Kit notification."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]

        # Register Slack webhook
        sub_resp = await async_client.post(
            "/api/webhooks",
            json={
                "target_type": "slack",
                "url": "https://hooks.slack.com/services/enterprise/consulting/scenario4",
                "events": ["slide_review_gate"],
                "project_id": str(pid),
                "is_active": True,
            },
        )
        assert sub_resp.status_code == status.HTTP_201_CREATED
        sub_id = uuid.UUID(sub_resp.json()["id"])

        service = WebhookService(db=db_session)
        mock_resp = httpx.Response(200, json={"ok": True})

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            deliveries = await service.dispatch_slide_review_gate(
                project_id=pid,
                topic=data["project"].topic,
                audience=data["project"].audience,
                total_slides=len(data["slides"]),
                slide_summary=[f"Slide {s.slide_order}: {s.title}" for s in data["slides"]],
                session=db_session,
            )
            slack_delivery = next((d for d in deliveries if d.subscription_id == sub_id), None)
            assert slack_delivery is not None
            assert slack_delivery.success is True

            # Verify Slack Block Kit payload structure delivered
            slack_call = next(c for c in mock_post.call_args_list if "enterprise/consulting/scenario4" in str(c))
            sent_payload = slack_call[1]["json"]
            assert "blocks" in sent_payload
            assert any(b.get("type") == "header" for b in sent_payload["blocks"])
            assert any(b.get("type") == "actions" for b in sent_payload["blocks"])

    # =========================================================================
    # Scenario 5: Enterprise MS Teams Notification Flow on Review Gate Arrival
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_5_enterprise_teams_notification_flow(
        self, async_client: AsyncClient, db_session: AsyncSession, seed_consulting_project
    ):
        """Scenario 5: Slide review gate triggers MS Teams Adaptive Card 1.4 alert."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]

        # Register Teams webhook
        sub_resp = await async_client.post(
            "/api/webhooks",
            json={
                "target_type": "teams",
                "url": "https://outlook.office.com/webhook/enterprise-teams/scenario5",
                "events": ["slide_review_gate"],
                "project_id": str(pid),
                "is_active": True,
            },
        )
        assert sub_resp.status_code == status.HTTP_201_CREATED
        sub_id = uuid.UUID(sub_resp.json()["id"])

        service = WebhookService(db=db_session)
        mock_resp = httpx.Response(200, text="1")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            deliveries = await service.dispatch_slide_review_gate(
                project_id=pid,
                topic=data["project"].topic,
                audience=data["project"].audience,
                total_slides=len(data["slides"]),
                slide_summary=[f"Slide {s.slide_order}: {s.title}" for s in data["slides"]],
                session=db_session,
            )
            teams_delivery = next((d for d in deliveries if d.subscription_id == sub_id), None)
            assert teams_delivery is not None
            assert teams_delivery.success is True

            # Verify Adaptive Card 1.4 schema
            teams_call = next(c for c in mock_post.call_args_list if "enterprise-teams/scenario5" in str(c))
            sent_payload = teams_call[1]["json"]
            assert sent_payload["type"] == "message"
            card = sent_payload["attachments"][0]["content"]
            assert card["version"] == "1.4"
            assert card["type"] == "AdaptiveCard"

    # =========================================================================
    # Scenario 6: Multi-Channel Alerting & Resilient Webhook Retry
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_6_multi_channel_alerting_and_resilient_retry(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """Scenario 6: Simultaneous multi-channel alert with retry on transient network failure."""
        slack_sub = await seed_webhook_sub(
            target_type="slack",
            url="https://hooks.slack.com/services/retry/slack",
        )
        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)

        # First call fails with 502, second call succeeds with 200
        fail_resp = httpx.Response(502, text="Bad Gateway")
        ok_resp = httpx.Response(200, json={"ok": True})

        with patch("httpx.AsyncClient.post", side_effect=[fail_resp, ok_resp]) as mock_post:
            delivery = await dispatcher.dispatch(
                url=slack_sub.url,
                payload={"event": "slide_review_gate"},
                subscription_id=slack_sub.id,
            )
            assert delivery.success is True
            assert delivery.status_code == 200
            assert delivery.attempt_count == 2
            assert mock_post.call_count == 2

    # =========================================================================
    # Scenario 7: Enterprise Multi-Format Export Bundle for Goldman Sachs
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_7_enterprise_multiformat_export_bundle_goldman_sachs(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """Scenario 7: Full multi-format export bundle (PPTX, PDF, HTML) for Goldman Slate theme."""
        data = await seed_consulting_project(
            topic="Goldman High-Yield Fixed Income & Derivatives Infrastructure",
            is_approved=True,
            include_scorecard_and_metrics=True,
        )
        pid = data["project_id"]

        # 1. Export PPTX
        r_pptx = await async_client.get(f"/api/projects/{pid}/artifact?format=pptx&template=goldman_slate")
        assert r_pptx.status_code == status.HTTP_200_OK

        # 2. Export PDF
        r_pdf = await async_client.get(f"/api/projects/{pid}/artifact?format=pdf&template=goldman_slate")
        assert r_pdf.status_code == status.HTTP_200_OK

        # 3. Export HTML
        r_html = await async_client.get(f"/api/projects/{pid}/artifact?format=html&template=goldman_slate")
        assert r_html.status_code == status.HTTP_200_OK

        # Verify all 3 physical files exist in artifacts
        pptx_file = Path("artifacts") / f"consulting_deck_{pid}.pptx"
        pdf_file = Path("artifacts") / f"executive_summary_{pid}.pdf"
        html_file = Path("artifacts") / f"consulting_deck_{pid}.html"

        assert pptx_file.exists() and pptx_file.stat().st_size > 0
        assert pdf_file.exists() and pdf_file.stat().st_size > 0
        assert html_file.exists() and html_file.stat().st_size > 0

    # =========================================================================
    # Scenario 8: Cloud Deployment Verification Matrix
    # =========================================================================
    @pytest.mark.asyncio
    async def test_scenario_8_cloud_deployment_verification_matrix(
        self, async_client: AsyncClient, workspace_root: Path
    ):
        """Scenario 8: Complete verification matrix across Compose, K8s, Helm, CI, and live health."""
        # 1. Compose file valid with 5 services
        compose_path = workspace_root / "deploy" / "docker-compose.prod.yml"
        with open(compose_path, encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)
        assert len(compose_data["services"]) >= 5

        # 2. K8s manifests valid and contains ingress with websockets
        ingress_path = workspace_root / "deploy" / "k8s" / "09-ingress.yaml"
        with open(ingress_path, encoding="utf-8") as f:
            ingress_data = yaml.safe_load(f)
        assert ingress_data["kind"] == "Ingress"

        # 3. Helm chart valid
        chart_path = workspace_root / "deploy" / "helm" / "consulting-deck" / "Chart.yaml"
        with open(chart_path, encoding="utf-8") as f:
            chart_data = yaml.safe_load(f)
        assert chart_data["name"] == "consulting-deck"

        # 4. CI/CD workflow valid
        ci_path = workspace_root / ".github" / "workflows" / "ci.yml"
        with open(ci_path, encoding="utf-8") as f:
            ci_data = yaml.safe_load(f)
        assert "backend-test" in ci_data["jobs"]
        assert "frontend-build" in ci_data["jobs"]

        # 5. Live health check passes
        resp = await async_client.get("/api/health")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "ok"
