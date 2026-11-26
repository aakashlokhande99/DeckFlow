"""Tier 3: Pairwise Cross-Feature Interaction Test Suite (14 Tests).

Tests exercising multi-feature integrations:
- Corporate templates combined with scorecard/metrics in PPTX, PDF, and HTML
- External webhook notifications triggered by slide review gate with SSRF safety
- Multi-format API export matrix across themes and formats
- Infrastructure alignment between Compose, K8s, Helm, and CI/CD
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import validate_url
from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source, WebhookDelivery, WebhookSubscription
from app.notifications.dispatcher import WebhookDispatcher, WebhookSSRFError
from app.notifications.service import WebhookService
from app.presentation.html_viewer import HTMLPresentationGenerator
from app.presentation.pdf_exporter import ExecutivePDFExporter
from app.presentation.renderer import PresentationRenderer
from app.presentation.templates import get_template


class TestTier3PairwiseInteractions:
    """Tier 3: Cross-Feature interaction test cases."""

    # -------------------------------------------------------------------------
    # Pairwise 1: McKinsey Navy + Scorecard & Metrics + PPTX
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_mckinsey_scorecard_metrics_pptx(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """F7 + F8 + F11: McKinsey Navy palette applied to scorecard and metrics in PPTX."""
        data = await seed_consulting_project(is_approved=True, include_scorecard_and_metrics=True)
        template = get_template("mckinsey_navy")
        renderer = PresentationRenderer(db=db_session, template=template)
        artifact = await renderer.render(data["project_id"])

        assert artifact is not None
        assert os.path.exists(artifact.file_path)
        assert artifact.file_size_bytes > 0
        assert renderer.font_heading == "Calibri"

    # -------------------------------------------------------------------------
    # Pairwise 2: BCG Emerald + Scorecard & Metrics + PPTX
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_bcg_scorecard_metrics_pptx(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """F7 + F8 + F11: BCG Emerald palette with Arial font applied to PPTX."""
        data = await seed_consulting_project(is_approved=True, include_scorecard_and_metrics=True)
        template = get_template("bcg_emerald")
        renderer = PresentationRenderer(db=db_session, template=template)
        artifact = await renderer.render(data["project_id"])

        assert artifact is not None
        assert os.path.exists(artifact.file_path)
        assert renderer.font_heading == "Arial"
        assert template.palette.primary == "#064E3B"

    # -------------------------------------------------------------------------
    # Pairwise 3: Bain Crimson + Scorecard & Metrics + PDF
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_bain_scorecard_metrics_pdf(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """F7 + F8 + F9: Bain Crimson executive PDF memo with NumberedCanvas."""
        data = await seed_consulting_project(is_approved=True, include_scorecard_and_metrics=True)
        template = get_template("bain_crimson")
        exporter = ExecutivePDFExporter(db=db_session, template=template)
        file_path, size, file_hash = await exporter.export(data["project_id"])

        assert os.path.exists(file_path)
        assert size > 0
        assert len(file_hash) == 64
        with open(file_path, "rb") as f:
            assert f.read(5) == b"%PDF-"

    # -------------------------------------------------------------------------
    # Pairwise 4: Goldman Slate + Scorecard & Metrics + HTML
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_goldman_scorecard_metrics_html(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """F7 + F8 + F10: Goldman Slate interactive HTML viewer with scorecard & metrics."""
        data = await seed_consulting_project(is_approved=True, include_scorecard_and_metrics=True)
        template = get_template("goldman_slate")
        generator = HTMLPresentationGenerator(db=db_session, template=template)
        file_path, size, file_hash = await generator.generate(data["project_id"])

        assert os.path.exists(file_path)
        content = Path(file_path).read_text(encoding="utf-8")
        assert f"--c-primary: {template.palette.primary}" in content
        assert f"--c-accent: {template.palette.accent}" in content
        assert "scorecard" in content.lower() or "dimension" in content.lower()

    # -------------------------------------------------------------------------
    # Pairwise 5: Modern Tech + PDF and HTML Parity
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_modern_tech_pdf_and_html_parity(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """F7 + F9 + F10: Modern Tech theme applied consistently across PDF and HTML."""
        data = await seed_consulting_project(is_approved=True)
        template = get_template("modern_tech")
        pid = data["project_id"]

        pdf_exporter = ExecutivePDFExporter(db=db_session, template=template)
        pdf_path, pdf_size, _ = await pdf_exporter.export(pid)

        html_generator = HTMLPresentationGenerator(db=db_session, template=template)
        html_path, html_size, _ = await html_generator.generate(pid)

        assert os.path.exists(pdf_path)
        assert os.path.exists(html_path)
        assert template.palette.accent == "#0D9488"
        assert f"--c-accent: #0D9488" in Path(html_path).read_text(encoding="utf-8")

    # -------------------------------------------------------------------------
    # Pairwise 6: Slack Webhook + Review Gate Trigger + SSRF Validation
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_slack_webhook_on_storyline_review_gate(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """F12 + F13 + F14: Slide review gate triggers Slack Block Kit alert with valid URL."""
        sub = await seed_webhook_sub(
            target_type="slack",
            url="https://hooks.slack.com/services/T00/B11/X22",
            events=["slide_review_gate"],
        )
        service = WebhookService(db=db_session)

        mock_resp = httpx.Response(200, json={"ok": True})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            deliveries = await service.dispatch_slide_review_gate(
                project_id=uuid.uuid4(),
                topic="AI Transformation Advisory",
                audience="Steering Committee",
                total_slides=11,
                slide_summary=["Slide 1: Vision", "Slide 2: Roadmap"],
                session=db_session,
            )
            slack_delivery = next((d for d in deliveries if d.subscription_id == sub.id), None)
            assert slack_delivery is not None
            assert slack_delivery.success is True
            assert slack_delivery.status_code == 200

    # -------------------------------------------------------------------------
    # Pairwise 7: Teams Webhook + Review Gate Trigger + SSRF Validation
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_teams_webhook_on_storyline_review_gate(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """F12 + F13 + F14: Slide review gate triggers MS Teams Adaptive Card alert."""
        sub = await seed_webhook_sub(
            target_type="teams",
            url="https://outlook.office.com/webhook/enterprise-teams-gate",
            events=["slide_review_gate"],
        )
        service = WebhookService(db=db_session)

        mock_resp = httpx.Response(200, text="1")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            deliveries = await service.dispatch_slide_review_gate(
                project_id=uuid.uuid4(),
                topic="Cloud Operating Model",
                audience="C-Suite",
                total_slides=9,
                slide_summary=["Slide 1: Cover"],
                session=db_session,
            )
            teams_delivery = next((d for d in deliveries if d.subscription_id == sub.id), None)
            assert teams_delivery is not None
            assert teams_delivery.success is True

    # -------------------------------------------------------------------------
    # Pairwise 8: Review Gate SSRF Protection on Blocked Target
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_webhook_ssrf_blocking_on_storyline_gate(self, db_session: AsyncSession):
        """F13 + F14: SSRF protection blocks dispatch to private address without crashing."""
        dispatcher = WebhookDispatcher(db=db_session)
        with pytest.raises(WebhookSSRFError):
            dispatcher.validate_destination_url("http://10.0.0.1/internal/hook")

    # -------------------------------------------------------------------------
    # Pairwise 9: Helm & K8s Health Probes Alignment
    # -------------------------------------------------------------------------
    def test_pairwise_helm_k8s_probes_alignment(self, workspace_root: Path):
        """F3 + F4 + F6: Helm backend deployment probes match K8s 06-backend.yaml probes."""
        k8s_backend = workspace_root / "deploy" / "k8s" / "06-backend.yaml"
        helm_backend = workspace_root / "deploy" / "helm" / "consulting-deck" / "templates" / "backend-deployment.yaml"

        with open(k8s_backend, encoding="utf-8") as f:
            k8s_docs = list(yaml.safe_load_all(f))
            k8s_dep = next(d for d in k8s_docs if d.get("kind") == "Deployment")
            k8s_container = k8s_dep["spec"]["template"]["spec"]["containers"][0]
            k8s_liveness_path = k8s_container["livenessProbe"]["httpGet"]["path"]

        helm_content = helm_backend.read_text(encoding="utf-8")
        assert k8s_liveness_path in helm_content
        assert "/api/health" in helm_content

    # -------------------------------------------------------------------------
    # Pairwise 10: Compose vs K8s Resource Limits Alignment
    # -------------------------------------------------------------------------
    def test_pairwise_compose_k8s_resources_alignment(self, workspace_root: Path):
        """F1 + F3: Compose resource limits align with K8s container resources."""
        compose_file = workspace_root / "deploy" / "docker-compose.prod.yml"
        k8s_backend_file = workspace_root / "deploy" / "k8s" / "06-backend.yaml"

        with open(compose_file, encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)
        with open(k8s_backend_file, encoding="utf-8") as f:
            k8s_docs = list(yaml.safe_load_all(f))
            k8s_dep = next(d for d in k8s_docs if d.get("kind") == "Deployment")

        compose_limit_cpu = float(compose_data["services"]["backend"]["deploy"]["resources"]["limits"]["cpus"])
        k8s_limit_cpu_str = k8s_dep["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["cpu"]
        k8s_limit_cpu = float(k8s_limit_cpu_str.rstrip("m")) / 1000.0 if "m" in k8s_limit_cpu_str else float(k8s_limit_cpu_str)

        assert compose_limit_cpu == k8s_limit_cpu

    # -------------------------------------------------------------------------
    # Pairwise 11: CI/CD Dockerfile and Compose Validation Steps
    # -------------------------------------------------------------------------
    def test_pairwise_ci_dockerfile_and_compose_validation(self, workspace_root: Path):
        """F1 + F2 + F5: CI workflow validates both Dockerfiles and docker-compose.prod.yml."""
        ci_file = workspace_root / ".github" / "workflows" / "ci.yml"
        with open(ci_file, encoding="utf-8") as f:
            ci_data = yaml.safe_load(f)

        steps = ci_data["jobs"]["container-validate"]["steps"]
        step_runs = [s.get("run", "") for s in steps]
        assert any("deploy/docker-compose.prod.yml" in r for r in step_runs)
        assert any("backend/Dockerfile" in r for r in step_runs)
        assert any("frontend/Dockerfile" in r for r in step_runs)

    # -------------------------------------------------------------------------
    # Pairwise 12: API Export All Formats for BCG Emerald
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_api_export_all_formats_bcg(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """F7 + F11: Multi-format export for BCG Emerald across pptx, pdf, and html."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]

        for fmt, expected_mime in [
            ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            ("pdf", "application/pdf"),
            ("html", "text/html"),
        ]:
            resp = await async_client.get(f"/api/projects/{pid}/artifact?format={fmt}&template=bcg_emerald")
            assert resp.status_code == status.HTTP_200_OK
            assert expected_mime in resp.headers["content-type"]

    # -------------------------------------------------------------------------
    # Pairwise 13: Webhook Subscription CRUD and Test Ping
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_webhook_subscription_crud_and_test_ping(self, async_client: AsyncClient):
        """F12 + F14: Register subscription, verify in DB, trigger test ping."""
        from datetime import datetime, timezone

        create_payload = {
            "target_type": "slack",
            "url": "https://hooks.slack.com/services/pairwise/test/ping",
            "events": ["slide_review_gate"],
            "is_active": True,
        }
        create_resp = await async_client.post("/api/webhooks", json=create_payload)
        assert create_resp.status_code == status.HTTP_201_CREATED
        sub_id = uuid.UUID(create_resp.json()["id"])

        mock_delivery = WebhookDelivery(
            id=uuid.uuid4(),
            subscription_id=sub_id,
            event_type="test_ping",
            status_code=200,
            response_body="ok",
            attempt_count=1,
            success=True,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(WebhookDispatcher, "dispatch", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = mock_delivery
            test_resp = await async_client.post(f"/api/webhooks/{sub_id}/test")
            assert test_resp.status_code == status.HTTP_200_OK
            data = test_resp.json()
            assert data["success"] is True
            assert data["status_code"] == 200

    # -------------------------------------------------------------------------
    # Pairwise 14: Storyline Approval Gate Unblocks All Exporters
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_pairwise_storyline_approval_gate_unblocks_all_exporters(
        self, async_client: AsyncClient, db_session: AsyncSession, seed_consulting_project
    ):
        """F8 + F9 + F10 + F11: Unapproved synthesis blocks all exports; approving unblocks all 3."""
        data = await seed_consulting_project(is_approved=False)
        pid = data["project_id"]

        # 1. Unapproved: all 3 formats return 400 Bad Request
        for fmt in ["pptx", "pdf", "html"]:
            resp = await async_client.get(f"/api/projects/{pid}/artifact?format={fmt}")
            assert resp.status_code == status.HTTP_400_BAD_REQUEST

        # 2. Approve synthesis and slides
        data["insight"].is_approved = True
        for s in data["slides"]:
            s.is_approved = True
        data["project"].status = ProjectStatus.approved.value
        await db_session.commit()

        # 3. Approved: all 3 formats return 200 OK
        for fmt in ["pptx", "pdf", "html"]:
            resp = await async_client.get(f"/api/projects/{pid}/artifact?format={fmt}")
            assert resp.status_code == status.HTTP_200_OK
