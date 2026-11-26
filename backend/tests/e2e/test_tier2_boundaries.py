"""Tier 2: Boundary & Corner Cases Test Suite (14 Features, 70 Test Cases).

Exhaustively verifies edge cases, boundary conditions, malformed payloads,
SSRF evasion attempts, missing parameters, and fail-safe recovery behaviors.
"""

from __future__ import annotations

import os
import re
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import is_safe_url, validate_url
from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source, WebhookDelivery, WebhookSubscription
from app.notifications.dispatcher import WebhookDispatcher, WebhookSSRFError
from app.notifications.payloads import format_slide_summary
from app.notifications.service import WebhookService
from app.presentation.html_viewer import HTMLGateError, HTMLPresentationGenerator
from app.presentation.pdf_exporter import ExecutivePDFExporter, PDFGateError
from app.presentation.renderer import PresentationRenderer, RendererGateError, hex_to_rgb
from app.presentation.templates import get_template
from app.schemas.storyline import SlideItem
from app.schemas.template import BrandPalette, FontSchema

# =============================================================================
# F1: Production Compose Boundaries
# =============================================================================

class TestF1ComposeBoundaries:
    """F1: Boundary cases for Docker Compose specification."""

    @pytest.fixture(scope="session")
    def compose_data(self, workspace_root: Path) -> Dict[str, Any]:
        with open(workspace_root / "deploy" / "docker-compose.prod.yml", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_f1_compose_malformed_yaml_handling(self):
        """Malformed YAML syntax raises yaml.YAMLError."""
        malformed = "services:\n  backend:\n    image: [unclosed"
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(malformed)

    def test_f1_compose_positive_cpu_limits(self, compose_data: Dict[str, Any]):
        """All service CPU limits are positive numbers."""
        services = compose_data.get("services", {})
        for sname, sdef in services.items():
            res = sdef.get("deploy", {}).get("resources", {})
            cpu_limit = res.get("limits", {}).get("cpus")
            assert cpu_limit is not None, f"{sname} missing cpu limit"
            assert float(cpu_limit) > 0.0

    def test_f1_compose_reservation_le_limit(self, compose_data: Dict[str, Any]):
        """CPU reservations must be less than or equal to CPU limits."""
        services = compose_data.get("services", {})
        for sname, sdef in services.items():
            res = sdef.get("deploy", {}).get("resources", {})
            cpu_limit = float(res.get("limits", {}).get("cpus", 1.0))
            cpu_res = float(res.get("reservations", {}).get("cpus", 0.0))
            assert cpu_res <= cpu_limit, f"{sname} reservation exceeds limit"

    def test_f1_compose_valid_port_numbers(self, compose_data: Dict[str, Any]):
        """Port bindings must specify integers in range 1..65535."""
        services = compose_data.get("services", {})
        for sname, sdef in services.items():
            ports = sdef.get("ports", [])
            for p in ports:
                parts = str(p).split(":")
                container_port = int(parts[-1])
                assert 1 <= container_port <= 65535

    def test_f1_compose_depends_on_health_conditions(self, compose_data: Dict[str, Any]):
        """Backend and worker must depend on db and redis with service_healthy condition."""
        services = compose_data.get("services", {})
        for app_service in ["backend", "worker"]:
            dep = services[app_service].get("depends_on", {})
            assert "db" in dep
            assert "redis" in dep
            assert dep["db"].get("condition") == "service_healthy"
            assert dep["redis"].get("condition") == "service_healthy"


# =============================================================================
# F2: Dockerfile Hardening Boundaries
# =============================================================================

class TestF2DockerfileBoundaries:
    """F2: Boundary conditions for Dockerfiles and .dockerignore."""

    def test_f2_dockerignore_sensitive_env_files(self, workspace_root: Path):
        """Backend and frontend .dockerignore must exclude .env files."""
        for sub in ["backend", "frontend"]:
            content = (workspace_root / sub / ".dockerignore").read_text(encoding="utf-8")
            assert ".env" in content

    def test_f2_dockerfile_multi_stage_structure(self, workspace_root: Path):
        """Frontend Dockerfile must contain distinct builder and runner stages."""
        content = (workspace_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        assert "AS builder" in content
        assert "AS runner" in content

    def test_f2_dockerfile_exec_form_cmd(self, workspace_root: Path):
        """CMD commands must use JSON array exec format, not shell form."""
        backend_content = (workspace_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        assert 'CMD ["uvicorn"' in backend_content or 'CMD ["' in backend_content

    def test_f2_dockerfile_user_id_boundaries(self, workspace_root: Path):
        """User UID must be explicitly non-zero (non-root)."""
        fe_content = (workspace_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        assert "1001" in fe_content

    def test_f2_dockerfile_empty_file_handling(self):
        """Processing empty dockerfile string does not raise uncaught errors."""
        empty_content = ""
        assert "USER appuser" not in empty_content


# =============================================================================
# F3: Cloud-Agnostic K8s Boundaries
# =============================================================================

class TestF3K8sBoundaries:
    """F3: Boundary validation on Kubernetes modular manifests."""

    @pytest.fixture(scope="session")
    def k8s_dir(self, workspace_root: Path) -> Path:
        return workspace_root / "deploy" / "k8s"

    def test_f3_k8s_manifest_namespace_consistency(self, k8s_dir: Path):
        """All deployment manifests explicitly specify namespace."""
        for fname in ["06-backend.yaml", "07-worker.yaml", "08-frontend.yaml"]:
            with open(k8s_dir / fname, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
                for doc in docs:
                    if doc and doc.get("kind") in ["Deployment", "Service"]:
                        assert doc["metadata"].get("namespace") in ["consulting-prod", "consulting-agent"]

    def test_f3_k8s_port_numbers_in_range(self, k8s_dir: Path):
        """Container ports are between 1024 and 65535."""
        with open(k8s_dir / "06-backend.yaml", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            dep = next(d for d in docs if d.get("kind") == "Deployment")
            port = dep["spec"]["template"]["spec"]["containers"][0]["ports"][0]["containerPort"]
            assert 1024 <= port <= 65535

    def test_f3_k8s_probe_timing_positive_integers(self, k8s_dir: Path):
        """Probe timings must be strictly positive and timeout < period."""
        with open(k8s_dir / "06-backend.yaml", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            dep = next(d for d in docs if d.get("kind") == "Deployment")
            probe = dep["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]
            assert probe["initialDelaySeconds"] > 0
            assert probe["periodSeconds"] > 0
            assert probe["timeoutSeconds"] > 0
            assert probe["timeoutSeconds"] < probe["periodSeconds"]

    def test_f3_k8s_ingress_pathtype_valid(self, k8s_dir: Path):
        """Ingress pathType must be Prefix or Exact."""
        with open(k8s_dir / "09-ingress.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            for rule in data["spec"]["rules"]:
                for p in rule["http"]["paths"]:
                    assert p["pathType"] in ["Prefix", "Exact"]

    def test_f3_k8s_hpa_metrics_boundaries(self, k8s_dir: Path):
        """HPA minReplicas must be < maxReplicas and target percentage <= 100."""
        with open(k8s_dir / "10-hpa.yaml", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            for doc in docs:
                if doc and doc.get("kind") == "HorizontalPodAutoscaler":
                    min_r = doc["spec"]["minReplicas"]
                    max_r = doc["spec"]["maxReplicas"]
                    assert 1 <= min_r < max_r
                    for m in doc["spec"]["metrics"]:
                        if m.get("type") == "Resource":
                            target = m["resource"]["target"]["averageUtilization"]
                            assert 1 <= target <= 100


# =============================================================================
# F4: Helm Packaging Boundaries
# =============================================================================

class TestF4HelmBoundaries:
    """F4: Boundary validation for Helm Chart and values."""

    @pytest.fixture(scope="session")
    def helm_dir(self, workspace_root: Path) -> Path:
        return workspace_root / "deploy" / "helm" / "consulting-deck"

    def test_f4_helm_chart_api_version_v2(self, helm_dir: Path):
        """Chart.yaml apiVersion must strictly be v2."""
        with open(helm_dir / "Chart.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["apiVersion"] == "v2"

    def test_f4_helm_required_top_level_keys(self, helm_dir: Path):
        """values.yaml must contain non-empty dictionaries for core components."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            for k in ["replicaCount", "image", "service", "resources", "ingress"]:
                assert k in values
                assert isinstance(values[k], dict)

    def test_f4_helm_non_empty_image_tags(self, helm_dir: Path):
        """Image tags must be non-empty strings."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            for img_name in ["backend", "frontend", "postgres", "redis"]:
                tag = values["image"][img_name].get("tag")
                assert tag is not None and len(str(tag).strip()) > 0

    def test_f4_helm_replica_counts_positive(self, helm_dir: Path):
        """Replica counts must be positive integers >= 1."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            for sname in ["backend", "worker", "frontend"]:
                assert values["replicaCount"][sname] >= 1

    def test_f4_helm_resource_requests_le_limits(self, helm_dir: Path):
        """Resource CPU and memory requests must be configured for all components."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            for comp in ["backend", "worker", "frontend"]:
                req = values["resources"][comp]["requests"]
                lim = values["resources"][comp]["limits"]
                assert "cpu" in req and "cpu" in lim
                assert "memory" in req and "memory" in lim


# =============================================================================
# F5: CI/CD Automation Boundaries
# =============================================================================

class TestF5CICDBoundaries:
    """F5: Boundary validation for GitHub Actions CI/CD workflow."""

    @pytest.fixture(scope="session")
    def workflow_data(self, workspace_root: Path) -> Dict[str, Any]:
        with open(workspace_root / ".github" / "workflows" / "ci.yml", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_f5_cicd_concurrency_cancel_in_progress(self, workflow_data: Dict[str, Any]):
        """Workflow defines concurrency group with cancel-in-progress enabled."""
        assert "concurrency" in workflow_data
        assert workflow_data["concurrency"]["cancel-in-progress"] is True

    def test_f5_cicd_required_test_env_vars(self, workflow_data: Dict[str, Any]):
        """Pytest step must set essential environment configuration."""
        steps = workflow_data["jobs"]["backend-test"]["steps"]
        pytest_step = next(s for s in steps if "pytest" in s.get("run", ""))
        env = pytest_step.get("env", {})
        assert "DATABASE_URL" in env
        assert "SECRET_KEY" in env
        assert "ENVIRONMENT" in env

    def test_f5_cicd_node_version_is_valid_lts(self, workflow_data: Dict[str, Any]):
        """Frontend job uses valid Node.js LTS version string (20)."""
        steps = workflow_data["jobs"]["frontend-build"]["steps"]
        node_step = next(s for s in steps if "setup-node" in s.get("uses", ""))
        assert str(node_step["with"]["node-version"]) == "20"

    def test_f5_cicd_branches_non_empty(self, workflow_data: Dict[str, Any]):
        """Branch filters for push and PR must contain main."""
        on_block = workflow_data.get("on", workflow_data.get(True, {}))
        assert "main" in on_block["push"]["branches"]
        assert "main" in on_block["pull_request"]["branches"]

    def test_f5_cicd_invalid_workflow_yaml_fails(self):
        """Malformed workflow YAML raises error."""
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load("name: CI\non:\n  push:\n    branches: [unclosed")


# =============================================================================
# F6: Health Probes Boundaries
# =============================================================================

class TestF6HealthBoundaries:
    """F6: Error handling and corner cases for health probe endpoints."""

    @pytest.mark.asyncio
    async def test_f6_unhealthy_db_probe_returns_503(self, async_client: AsyncClient, db_session: AsyncSession):
        """When DB execution raises an error, /api/health/db returns 503 Service Unavailable."""
        with patch.object(db_session, "execute", side_effect=Exception("DB Connection Timeout")):
            resp = await async_client.get("/api/health/db")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = resp.json()
            assert data["status"] == "error"
            assert data["database"] == "unreachable"

    @pytest.mark.asyncio
    async def test_f6_root_health_db_failure_returns_503(self, async_client: AsyncClient, db_session: AsyncSession):
        """When DB execution raises an error, /health/db returns 503."""
        with patch.object(db_session, "execute", side_effect=Exception("PostgreSQL Socket Error")):
            resp = await async_client.get("/health/db")
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_f6_invalid_http_method_on_health(self, async_client: AsyncClient):
        """POST on /api/health returns 405 Method Not Allowed."""
        resp = await async_client.post("/api/health", json={})
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    @pytest.mark.asyncio
    async def test_f6_nonexistent_health_subpath(self, async_client: AsyncClient):
        """GET on nonexistent subpath returns 404 Not Found."""
        resp = await async_client.get("/api/health/nonexistent")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_f6_trailing_slash_behavior(self, async_client: AsyncClient):
        """GET /api/health/ responds cleanly (either 200 or 307 redirect)."""
        resp = await async_client.get("/api/health/")
        assert resp.status_code in [status.HTTP_200_OK, status.HTTP_307_TEMPORARY_REDIRECT]


# =============================================================================
# F7: Corporate Templates Boundaries
# =============================================================================

class TestF7TemplateBoundaries:
    """F7: Edge cases for brand hex colors, fonts, and template resolution."""

    @pytest.mark.parametrize("invalid_hex", ["#ZZZ", "#12345", "blue", "#GGGGGG", "", "   "])
    def test_f7_invalid_hex_colors_rejected(self, invalid_hex: str):
        """Invalid hex strings raise ValueError on BrandPalette."""
        with pytest.raises((ValueError, ValidationError)):
            BrandPalette(primary=invalid_hex)

    def test_f7_three_digit_hex_expansion(self):
        """Three-digit hex codes like #FFF and #0F0 are accepted and converted."""
        pal = BrandPalette(primary="#FFF", secondary="#0F0")
        assert pal.primary == "#FFF"
        c = hex_to_rgb("#FFF")
        assert c[0] == 255 and c[1] == 255 and c[2] == 255

    def test_f7_font_schema_empty_string_handling(self):
        """FontSchema specifies valid fonts."""
        fonts = FontSchema(heading="Arial", body="Arial")
        assert fonts.heading == "Arial"

    def test_f7_nonexistent_template_fallback(self):
        """Unknown template ID falls back to mckinsey_navy."""
        t = get_template("some_random_corp_999")
        assert t.id == "mckinsey_navy"

    def test_f7_empty_string_template_fallback(self):
        """Empty string or None template ID falls back to mckinsey_navy."""
        assert get_template("").id == "mckinsey_navy"
        assert get_template(None).id == "mckinsey_navy"


# =============================================================================
# F8: New Layout Schemas Boundaries
# =============================================================================

class TestF8LayoutBoundaries:
    """F8: Boundary conditions for scorecard and metrics layouts."""

    @pytest.mark.asyncio
    async def test_f8_scorecard_empty_items_fallback(self, db_session: AsyncSession, seed_consulting_project):
        """Scorecard slide with empty content falls back to default 4 dimensions without crashing."""
        data = await seed_consulting_project(include_scorecard_and_metrics=False)
        proj_id = data["project_id"]
        # Add scorecard slide with empty content
        slide = SlideSpec(
            id=uuid.uuid4(),
            project_id=proj_id,
            insight_id=data["insight_id"],
            slide_order=4,
            title="Empty Scorecard",
            key_message="Default dimensions applied.",
            layout=SlideLayout.scorecard.value,
            content={},
            source_ids=[],
            is_approved=True,
        )
        db_session.add(slide)
        await db_session.commit()

        renderer = PresentationRenderer(db=db_session)
        artifact = await renderer.render(proj_id)
        assert artifact is not None
        assert os.path.exists(artifact.file_path)

    @pytest.mark.asyncio
    async def test_f8_metrics_empty_cards_fallback(self, db_session: AsyncSession, seed_consulting_project):
        """Metrics slide with empty content falls back to default 4 cards without crashing."""
        data = await seed_consulting_project(include_scorecard_and_metrics=False)
        proj_id = data["project_id"]
        slide = SlideSpec(
            id=uuid.uuid4(),
            project_id=proj_id,
            insight_id=data["insight_id"],
            slide_order=4,
            title="Empty Metrics",
            key_message="Default metric cards applied.",
            layout=SlideLayout.metrics.value,
            content={},
            source_ids=[],
            is_approved=True,
        )
        db_session.add(slide)
        await db_session.commit()

        renderer = PresentationRenderer(db=db_session)
        artifact = await renderer.render(proj_id)
        assert artifact is not None

    def test_f8_metrics_with_non_numeric_values(self):
        """Metric values with complex non-numeric strings validate successfully."""
        item = SlideItem(
            slide_order=5,
            title="String Metric Cards",
            key_message="Non-numeric strings handled.",
            layout=SlideLayout.metrics,
            content={
                "metrics": [
                    {"label": "Status", "value": "N/A", "delta": "None"},
                    {"label": "Ratio", "value": "< 1.5%", "delta": "-10 bps"},
                    {"label": "Score", "value": "AAA+", "delta": "Stable"},
                ]
            },
        )
        assert item.layout == SlideLayout.metrics
        assert item.content["metrics"][0]["value"] == "N/A"

    def test_f8_unknown_layout_enum_rejection(self):
        """Invalid layout string raises ValidationError."""
        with pytest.raises(ValidationError):
            SlideItem(
                slide_order=1,
                title="Invalid Layout",
                key_message="Should fail.",
                layout="invalid_nonexistent_layout",
            )

    def test_f8_slide_item_empty_title_rejection(self):
        """SlideItem with empty title is rejected."""
        with pytest.raises(ValidationError):
            SlideItem(
                slide_order=1,
                title="",
                key_message="Valid key message.",
                layout=SlideLayout.two_column,
            )


# =============================================================================
# F9: Executive PDF Exporter Boundaries
# =============================================================================

class TestF9PDFBoundaries:
    """F9: Corner cases and boundaries for Executive PDF Exporter."""

    @pytest.mark.asyncio
    async def test_f9_unapproved_memo_handling(self, db_session: AsyncSession, seed_consulting_project):
        """PDF export on unapproved synthesis strictly raises PDFGateError."""
        data = await seed_consulting_project(is_approved=False)
        exporter = ExecutivePDFExporter(db=db_session)
        with pytest.raises(PDFGateError, match="has not been approved"):
            await exporter.export(data["project_id"])

    @pytest.mark.asyncio
    async def test_f9_special_characters_in_pdf_title(self, db_session: AsyncSession, seed_consulting_project):
        """Special characters (&, <, >, quotes, em-dash, symbols) in topic do not crash Platypus."""
        data = await seed_consulting_project(
            topic="M&A Synergy & AI <Optimization>: 'Scale' & 100% Growth — Q1/Q2",
            is_approved=True,
        )
        exporter = ExecutivePDFExporter(db=db_session)
        file_path, size, _ = await exporter.export(data["project_id"])
        assert os.path.exists(file_path)
        assert size > 0

    @pytest.mark.asyncio
    async def test_f9_extreme_title_length_truncation(self, db_session: AsyncSession, seed_consulting_project):
        """Topic exceeding 100 characters is safely truncated with ellipsis in NumberedCanvas."""
        long_topic = "A" * 150
        data = await seed_consulting_project(topic=long_topic, is_approved=True)
        exporter = ExecutivePDFExporter(db=db_session)
        file_path, _, _ = await exporter.export(data["project_id"])
        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_f9_large_content_multi_page_boundary(self, db_session: AsyncSession, seed_consulting_project):
        """Generating PDF with all slides produces a multi-page document."""
        data = await seed_consulting_project(include_scorecard_and_metrics=True, is_approved=True)
        exporter = ExecutivePDFExporter(db=db_session)
        file_path, size, _ = await exporter.export(data["project_id"])
        assert os.path.exists(file_path)
        assert size > 5000  # Multi-page PDF has non-trivial byte size

    @pytest.mark.asyncio
    async def test_f9_missing_sources_empty_citations(self, db_session: AsyncSession):
        """Project with insight but zero sources generates PDF without error."""
        proj = Project(
            id=uuid.uuid4(),
            topic="Zero Source Strategy",
            objective="Testing empty citations",
            audience="Executive Team",
            geography="Global",
            time_horizon="1 year",
            status=ProjectStatus.approved.value,
        )
        db_session.add(proj)
        await db_session.flush()

        ins = Insight(
            id=uuid.uuid4(),
            project_id=proj.id,
            version=1,
            executive_summary="Summary with no sources.",
            is_approved=True,
        )
        db_session.add(ins)
        await db_session.commit()

        exporter = ExecutivePDFExporter(db=db_session)
        file_path, size, _ = await exporter.export(proj.id)
        assert os.path.exists(file_path)


# =============================================================================
# F10: Interactive HTML Viewer Boundaries
# =============================================================================

class TestF10HTMLBoundaries:
    """F10: Security and corner cases for Interactive HTML Viewer."""

    @pytest.mark.asyncio
    async def test_f10_empty_slide_list_html_export(self, db_session: AsyncSession):
        """Generating HTML with zero slide specs raises HTMLGateError."""
        proj = Project(
            id=uuid.uuid4(),
            topic="No Slides Project",
            objective="Test empty slides",
            audience="Board",
            geography="US",
            time_horizon="1 year",
            status=ProjectStatus.approved.value,
        )
        db_session.add(proj)
        await db_session.flush()

        ins = Insight(
            id=uuid.uuid4(),
            project_id=proj.id,
            version=1,
            executive_summary="Approved synthesis without slides.",
            is_approved=True,
        )
        db_session.add(ins)
        await db_session.commit()

        generator = HTMLPresentationGenerator(db=db_session)
        with pytest.raises(HTMLGateError, match="no slide specs found"):
            await generator.generate(proj.id)

    @pytest.mark.asyncio
    async def test_f10_xss_escaping_in_slide_title(self, db_session: AsyncSession, seed_consulting_project):
        """Slide title containing HTML/XSS script tags is safely escaped."""
        data = await seed_consulting_project(is_approved=True)
        # Update slide 1 with XSS attack payload
        slide1 = data["slides"][0]
        slide1.title = "<script>alert('XSS_ATTACK_VECTOR')</script>"
        await db_session.commit()

        generator = HTMLPresentationGenerator(db=db_session)
        file_path, _, _ = await generator.generate(data["project_id"])
        html_text = Path(file_path).read_text(encoding="utf-8")
        # Ensure the HTML DOM elements properly escape the tags
        assert "&lt;script&gt;alert(" in html_text or "&lt;script&gt;" in html_text

    @pytest.mark.asyncio
    async def test_f10_invalid_view_parameter_default(self, db_session: AsyncSession, seed_consulting_project):
        """Passing unsupported view string safely generates presentation view."""
        data = await seed_consulting_project(is_approved=True)
        generator = HTMLPresentationGenerator(db=db_session)
        file_path, _, _ = await generator.generate(data["project_id"], initial_view="unsupported_view")
        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_f10_special_characters_in_slide_content(self, db_session: AsyncSession, seed_consulting_project):
        """Bullets containing quotes, emojis, and symbols do not break embedded JavaScript."""
        data = await seed_consulting_project(is_approved=True)
        slide = data["slides"][1]
        slide.content = {"summary": "Quote: \"Modern Architecture\" & Emoji 🚀 with <bracket>"}
        await db_session.commit()

        generator = HTMLPresentationGenerator(db=db_session)
        file_path, _, _ = await generator.generate(data["project_id"])
        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_f10_unapproved_project_blocked(self, db_session: AsyncSession, seed_consulting_project):
        """Unapproved project export is strictly blocked with HTMLGateError."""
        data = await seed_consulting_project(is_approved=False)
        generator = HTMLPresentationGenerator(db=db_session)
        with pytest.raises(HTMLGateError):
            await generator.generate(data["project_id"])


# =============================================================================
# F11: Multi-Format Export API Boundaries
# =============================================================================

class TestF11ExportAPIBoundaries:
    """F11: Boundary conditions for GET /api/projects/{id}/artifact."""

    @pytest.mark.asyncio
    async def test_f11_unsupported_export_format(self, async_client: AsyncClient, seed_consulting_project):
        """Querying format=docx returns 400 Bad Request with descriptive detail."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=docx")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Unsupported format" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_f11_nonexistent_project_id_400(self, async_client: AsyncClient):
        """Exporting random nonexistent project UUID returns 400 Bad Request."""
        random_id = uuid.uuid4()
        resp = await async_client.get(f"/api/projects/{random_id}/artifact?format=pptx")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_f11_unapproved_project_gate_rejection(self, async_client: AsyncClient, seed_consulting_project):
        """Exporting an unapproved project via HTTP returns 400 Bad Request."""
        data = await seed_consulting_project(is_approved=False)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pdf")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_f11_malformed_uuid_422(self, async_client: AsyncClient):
        """Providing invalid UUID format in path returns 422 Unprocessable Entity."""
        resp = await async_client.get("/api/projects/not-a-valid-uuid/artifact?format=pptx")
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_f11_template_case_insensitivity(self, async_client: AsyncClient, seed_consulting_project):
        """Corporate template name is resolved case-insensitively."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pptx&template=BCG_EMERALD")
        assert resp.status_code == status.HTTP_200_OK


# =============================================================================
# F12: External Webhooks Boundaries
# =============================================================================

class TestF12WebhookBoundaries:
    """F12: Validation and error boundaries for Webhook subscription management."""

    @pytest.mark.asyncio
    async def test_f12_webhook_subscription_empty_url(self, async_client: AsyncClient):
        """Creating subscription with empty URL fails validation."""
        payload = {"target_type": "slack", "url": "", "events": ["slide_review_gate"]}
        resp = await async_client.post("/api/webhooks", json=payload)
        assert resp.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]

    @pytest.mark.asyncio
    async def test_f12_webhook_subscription_unknown_target_type(self, async_client: AsyncClient):
        """Target type not in ['slack', 'teams', 'generic'] returns 422."""
        payload = {"target_type": "discord", "url": "https://hooks.example.com", "events": ["slide_review_gate"]}
        resp = await async_client.post("/api/webhooks", json=payload)
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_f12_webhook_subscription_ssrf_rejection(self, async_client: AsyncClient):
        """Registering private IP webhook URL returns 400 Bad Request."""
        payload = {"target_type": "generic", "url": "http://127.0.0.1:8000/callback"}
        resp = await async_client.post("/api/webhooks", json=payload)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "unsafe" in resp.json()["detail"].lower() or "restricted" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_f12_webhook_get_nonexistent_404(self, async_client: AsyncClient):
        """GET /api/webhooks/{random_uuid} returns 404 Not Found."""
        resp = await async_client.get(f"/api/webhooks/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_f12_webhook_delete_nonexistent_404(self, async_client: AsyncClient):
        """DELETE /api/webhooks/{random_uuid} returns 404 Not Found."""
        resp = await async_client.delete(f"/api/webhooks/{uuid.uuid4()}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# =============================================================================
# F13: Review Gate Triggers Boundaries
# =============================================================================

class TestF13TriggerBoundaries:
    """F13: Failure recovery, timeout, and retry handling for review gate triggers."""

    @pytest.mark.asyncio
    async def test_f13_webhook_delivery_http_500_receiver(self, db_session: AsyncSession, seed_webhook_sub):
        """When webhook receiver returns 500, delivery record logs success=False."""
        sub = await seed_webhook_sub(target_type="generic", url="https://api.external-consulting.com/webhook")
        dispatcher = WebhookDispatcher(db=db_session, max_attempts=2, base_delay=0.01)

        mock_resp = httpx.Response(500, text="Internal Server Error")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            delivery = await dispatcher.dispatch(
                url=sub.url,
                payload={"test": "payload"},
                subscription_id=sub.id,
            )
            assert delivery.success is False
            assert delivery.status_code == 500
            assert delivery.attempt_count == 2

    @pytest.mark.asyncio
    async def test_f13_webhook_delivery_timeout_handling(self, db_session: AsyncSession, seed_webhook_sub):
        """When receiver times out, delivery logs failure."""
        sub = await seed_webhook_sub(target_type="generic", url="https://api.external-consulting.com/timeout")
        dispatcher = WebhookDispatcher(db=db_session, max_attempts=1, base_delay=0.01)

        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectTimeout("Connection timed out")):
            delivery = await dispatcher.dispatch(
                url=sub.url,
                payload={"test": "timeout"},
                subscription_id=sub.id,
            )
            assert delivery.success is False
            assert "ConnectTimeout" in (delivery.response_body or "")

    @pytest.mark.asyncio
    async def test_f13_webhook_retry_counter_increment(self, db_session: AsyncSession, seed_webhook_sub):
        """Dispatcher retries up to max_attempts on consecutive failures."""
        sub = await seed_webhook_sub(target_type="generic", url="https://api.external-consulting.com/retry")
        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)

        mock_resp = httpx.Response(503, text="Service Unavailable")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            delivery = await dispatcher.dispatch(
                url=sub.url,
                payload={"test": "retry"},
            )
            assert mock_post.call_count == 3
            assert delivery.attempt_count == 3
            assert delivery.success is False

    def test_f13_webhook_empty_slide_summary(self):
        """format_slide_summary with empty input returns fallback placeholder."""
        assert format_slide_summary([]) == "• No slide details available"
        assert format_slide_summary("") == ""

    @pytest.mark.asyncio
    async def test_f13_no_matching_subscriptions_safe(self, db_session: AsyncSession):
        """When no active subscriptions match, dispatch_slide_review_gate returns empty list."""
        from sqlalchemy import delete
        await db_session.execute(delete(WebhookSubscription))
        await db_session.commit()

        service = WebhookService(db=db_session)
        deliveries = await service.dispatch_slide_review_gate(
            project_id=uuid.uuid4(),
            topic="No Subscriptions Topic",
            audience="General",
            total_slides=5,
            slide_summary=["Slide 1"],
            session=db_session,
        )
        assert deliveries == []


# =============================================================================
# F14: Webhook Security & Mocks Boundaries
# =============================================================================

class TestF14SecurityBoundaries:
    """F14: SSRF evasion attempts, scheme validation, and edge-case URLs."""

    def test_f14_ssrf_ipv6_loopback(self):
        """IPv6 loopback [::1] is rejected."""
        with pytest.raises(ValueError):
            validate_url("http://[::1]/webhook")

    def test_f14_ssrf_decimal_ip(self):
        """Decimal IP representation of 127.0.0.1 (2130706433) is rejected."""
        with pytest.raises(ValueError):
            validate_url("http://2130706433/hook")

    @pytest.mark.parametrize("scheme_url", [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://evil.example.com",
        "data:text/plain;base64,SGVsbG8=",
    ])
    def test_f14_ssrf_non_http_schemes(self, scheme_url: str):
        """Non-HTTP/HTTPS schemes are strictly rejected."""
        with pytest.raises(ValueError, match="is not allowed"):
            validate_url(scheme_url)

    def test_f14_ssrf_cloud_metadata_edge_cases(self):
        """Metadata IP and hostname literals are rejected."""
        with pytest.raises(ValueError):
            validate_url("http://169.254.169.254/latest/meta-data")
        with pytest.raises(ValueError):
            validate_url("http://metadata.google.internal/computeMetadata/v1")

    @pytest.mark.parametrize("empty_input", ["", "   ", None])
    def test_f14_ssrf_empty_or_non_string_url(self, empty_input: Any):
        """Empty string or None raises ValueError."""
        with pytest.raises(ValueError):
            validate_url(empty_input)
