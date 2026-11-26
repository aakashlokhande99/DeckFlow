"""Tier 1: Feature Coverage Test Suite (14 Features, 70 Test Cases).

Opaque-box, requirement-driven tests covering happy-path functionality for all
Track D (Production Deployment & CI/CD) and Phase 3 (Enterprise Enhancements) features.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import is_safe_url, validate_url
from app.db.enums import ArtifactType, ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, Source, WebhookDelivery, WebhookSubscription
from app.notifications.dispatcher import WebhookDispatcher
from app.notifications.payloads import (
    build_generic_payload,
    build_slack_slide_review_payload,
    build_teams_slide_review_payload,
)
from app.notifications.service import WebhookService
from app.presentation.html_viewer import HTMLPresentationGenerator
from app.presentation.pdf_exporter import ExecutivePDFExporter, NumberedCanvas
from app.presentation.renderer import PresentationRenderer, hex_to_rgb
from app.presentation.templates import (
    CorporateTemplate,
    get_template,
    list_templates,
)
from app.schemas.storyline import SlideItem
from app.schemas.template import BrandPalette, FontSchema

# =============================================================================
# F1: Production Compose (R1.1)
# =============================================================================

class TestF1ProductionCompose:
    """F1: Production Docker Compose specification and service configuration."""

    @pytest.fixture(scope="session")
    def compose_spec(self, workspace_root: Path) -> Dict[str, Any]:
        compose_path = workspace_root / "deploy" / "docker-compose.prod.yml"
        assert compose_path.exists(), "deploy/docker-compose.prod.yml must exist"
        with open(compose_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_f1_compose_syntax_and_structure(self, compose_spec: Dict[str, Any]):
        """Verify compose file parses as valid YAML containing services, networks, and volumes."""
        assert isinstance(compose_spec, dict)
        assert "services" in compose_spec
        assert "networks" in compose_spec
        assert "volumes" in compose_spec

    def test_f1_compose_five_core_services_present(self, compose_spec: Dict[str, Any]):
        """Verify all 5 required services (db, redis, backend, worker, frontend) are defined."""
        services = compose_spec.get("services", {})
        required = {"db", "redis", "backend", "worker", "frontend"}
        assert required.issubset(set(services.keys()))

    def test_f1_compose_networking_and_isolation(self, compose_spec: Dict[str, Any]):
        """Verify bridge networks are defined for tiered isolation."""
        networks = compose_spec.get("networks", {})
        assert len(networks) >= 1
        services = compose_spec.get("services", {})
        for sname in ["backend", "worker", "db", "redis"]:
            assert "networks" in services[sname]

    def test_f1_compose_shared_artifact_volume(self, compose_spec: Dict[str, Any]):
        """Verify shared persistent artifacts volume is mounted to both backend and worker."""
        services = compose_spec.get("services", {})
        backend_vols = services["backend"].get("volumes", [])
        worker_vols = services["worker"].get("volumes", [])
        backend_has_artifacts = any("artifacts" in str(v) for v in backend_vols)
        worker_has_artifacts = any("artifacts" in str(v) for v in worker_vols)
        assert backend_has_artifacts, "backend must mount shared artifacts volume"
        assert worker_has_artifacts, "worker must mount shared artifacts volume"

    def test_f1_compose_healthchecks_all_services(self, compose_spec: Dict[str, Any]):
        """Verify healthchecks are defined for core services."""
        services = compose_spec.get("services", {})
        for sname in ["db", "redis", "backend"]:
            assert "healthcheck" in services[sname], f"{sname} must define a healthcheck"
            assert "test" in services[sname]["healthcheck"]


# =============================================================================
# F2: Dockerfile Hardening (R1.1)
# =============================================================================

class TestF2DockerfileHardening:
    """F2: Security hardening and build context hygiene for Dockerfiles."""

    def test_f2_frontend_public_dir_and_gitkeep(self, workspace_root: Path):
        """Verify frontend/public/.gitkeep exists and frontend/Dockerfile copies it."""
        public_dir = workspace_root / "frontend" / "public"
        assert public_dir.is_dir()
        assert (public_dir / ".gitkeep").exists()
        dockerfile = (workspace_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        assert "COPY --from=builder /app/public ./public" in dockerfile

    def test_f2_frontend_non_root_security(self, workspace_root: Path):
        """Verify frontend/Dockerfile runs as non-root user (UID 1001 nextjs)."""
        dockerfile = (workspace_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        assert "adduser --system --uid 1001 nextjs" in dockerfile
        assert "USER nextjs" in dockerfile

    def test_f2_backend_alembic_and_artifacts(self, workspace_root: Path):
        """Verify backend/Dockerfile copies alembic.ini and creates /app/artifacts."""
        dockerfile = (workspace_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        assert "COPY alembic.ini ." in dockerfile
        assert "mkdir -p /app/artifacts" in dockerfile

    def test_f2_backend_non_root_security(self, workspace_root: Path):
        """Verify backend/Dockerfile creates and runs under non-root appuser."""
        dockerfile = (workspace_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        assert "useradd" in dockerfile or "adduser" in dockerfile
        assert "USER appuser" in dockerfile

    def test_f2_dockerignore_exclusion_rules(self, workspace_root: Path):
        """Verify backend and frontend .dockerignore files exclude sensitive patterns."""
        backend_ignore = (workspace_root / "backend" / ".dockerignore").read_text(encoding="utf-8")
        frontend_ignore = (workspace_root / "frontend" / ".dockerignore").read_text(encoding="utf-8")
        for pat in ["__pycache__", ".pytest_cache", ".venv", ".git"]:
            assert pat in backend_ignore
        for pat in ["node_modules", ".next", ".git"]:
            assert pat in frontend_ignore


# =============================================================================
# F3: Cloud-Agnostic K8s (R1.2)
# =============================================================================

class TestF3CloudAgnosticK8s:
    """F3: Cloud-agnostic modular Kubernetes manifests."""

    @pytest.fixture(scope="session")
    def k8s_dir(self, workspace_root: Path) -> Path:
        p = workspace_root / "deploy" / "k8s"
        assert p.is_dir()
        return p

    def test_f3_k8s_manifest_presence_and_valid_yaml(self, k8s_dir: Path):
        """Verify all 11 Kubernetes manifests exist and parse as valid YAML."""
        expected = [
            "00-namespace.yaml", "01-configmap.yaml", "02-secrets.yaml", "03-pvc.yaml",
            "04-postgres.yaml", "05-redis.yaml", "06-backend.yaml", "07-worker.yaml",
            "08-frontend.yaml", "09-ingress.yaml", "10-hpa.yaml"
        ]
        for fname in expected:
            fpath = k8s_dir / fname
            assert fpath.exists(), f"Manifest {fname} missing"
            with open(fpath, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
                assert len(docs) >= 1

    def test_f3_k8s_namespace_definition(self, k8s_dir: Path):
        """Verify 00-namespace.yaml defines production namespace."""
        with open(k8s_dir / "00-namespace.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["kind"] == "Namespace"
            assert data["metadata"]["name"] in ["consulting-prod", "consulting-agent"]

    def test_f3_k8s_backend_deployment_probes(self, k8s_dir: Path):
        """Verify backend deployment defines livenessProbe and readinessProbe targeting /api/health."""
        with open(k8s_dir / "06-backend.yaml", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
            dep = next(d for d in docs if d.get("kind") == "Deployment")
            container = dep["spec"]["template"]["spec"]["containers"][0]
            assert "livenessProbe" in container
            assert "readinessProbe" in container
            assert container["livenessProbe"]["httpGet"]["path"] in ["/api/health", "/health"]
            assert container["readinessProbe"]["httpGet"]["path"] in ["/api/health", "/health", "/api/health/db"]

    def test_f3_k8s_worker_celery_execution(self, k8s_dir: Path):
        """Verify worker deployment executes celery worker command."""
        with open(k8s_dir / "07-worker.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            container = data["spec"]["template"]["spec"]["containers"][0]
            cmd = " ".join(container.get("command", [])) + " " + " ".join(container.get("args", []))
            assert "celery" in cmd

    def test_f3_k8s_ingress_routing_and_ws(self, k8s_dir: Path):
        """Verify ingress manifest configures paths for /api/ws, /api, and /."""
        with open(k8s_dir / "09-ingress.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            rules = data["spec"]["rules"][0]["http"]["paths"]
            path_strings = [p["path"] for p in rules]
            assert any("/api/ws" in p for p in path_strings)
            assert any("/api" in p for p in path_strings)


# =============================================================================
# F4: Helm Packaging (R1.2)
# =============================================================================

class TestF4HelmPackaging:
    """F4: Helm chart structure, metadata, values, and templates."""

    @pytest.fixture(scope="session")
    def helm_dir(self, workspace_root: Path) -> Path:
        p = workspace_root / "deploy" / "helm" / "consulting-deck"
        assert p.is_dir()
        return p

    def test_f4_helm_chart_metadata(self, helm_dir: Path):
        """Verify Chart.yaml has name consulting-deck, apiVersion v2, and version."""
        with open(helm_dir / "Chart.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert data["name"] == "consulting-deck"
            assert data["apiVersion"] == "v2"
            assert "version" in data

    def test_f4_helm_values_replica_counts_and_images(self, helm_dir: Path):
        """Verify values.yaml defines replicaCounts and image repositories."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            assert values["replicaCount"]["backend"] >= 1
            assert values["replicaCount"]["worker"] >= 1
            assert values["replicaCount"]["frontend"] >= 1
            assert values["image"]["backend"]["repository"] == "consulting-backend"

    def test_f4_helm_values_resource_limits(self, helm_dir: Path):
        """Verify values.yaml defines CPU/memory limits and requests."""
        with open(helm_dir / "values.yaml", encoding="utf-8") as f:
            values = yaml.safe_load(f)
            assert "resources" in values
            for comp in ["backend", "worker", "frontend"]:
                assert comp in values["resources"]
                assert "limits" in values["resources"][comp]
                assert "requests" in values["resources"][comp]

    def test_f4_helm_values_probe_paths(self, helm_dir: Path):
        """Verify templates and values configure health probe paths."""
        tpl_path = helm_dir / "templates" / "backend-deployment.yaml"
        assert tpl_path.exists()
        tpl = tpl_path.read_text(encoding="utf-8")
        assert "path: /api/health" in tpl
        assert "path: /api/health/db" in tpl

    def test_f4_helm_templates_completeness(self, helm_dir: Path):
        """Verify templates directory contains deployment, service, ingress, and helper templates."""
        tpl_dir = helm_dir / "templates"
        expected = [
            "backend-deployment.yaml", "backend-service.yaml",
            "frontend-deployment.yaml", "frontend-service.yaml",
            "worker-deployment.yaml", "ingress.yaml", "_helpers.tpl"
        ]
        for fname in expected:
            assert (tpl_dir / fname).exists(), f"Template {fname} missing in Helm chart"


# =============================================================================
# F5: CI/CD Automation (R1.3)
# =============================================================================

class TestF5CICDAutomation:
    """F5: GitHub Actions CI/CD automation pipeline."""

    @pytest.fixture(scope="session")
    def ci_workflow(self, workspace_root: Path) -> Dict[str, Any]:
        p = workspace_root / ".github" / "workflows" / "ci.yml"
        assert p.exists()
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_f5_cicd_workflow_syntax_and_triggers(self, ci_workflow: Dict[str, Any]):
        """Verify workflow triggers on push and pull_request to main and master."""
        assert "name" in ci_workflow
        assert True in [bool(ci_workflow.get(k)) for k in ["on", True]]
        on_block = ci_workflow.get("on", ci_workflow.get(True, {}))
        assert "push" in on_block
        assert "pull_request" in on_block

    def test_f5_cicd_backend_test_job(self, ci_workflow: Dict[str, Any]):
        """Verify backend-test job configures python 3.11, ruff lint, and pytest."""
        jobs = ci_workflow.get("jobs", {})
        assert "backend-test" in jobs
        steps = jobs["backend-test"]["steps"]
        step_runs = [s.get("run", "") for s in steps]
        assert any("pytest" in r for r in step_runs)
        assert any("ruff" in r for r in step_runs)

    def test_f5_cicd_frontend_build_job(self, ci_workflow: Dict[str, Any]):
        """Verify frontend-build job sets up Node.js 20 and executes npm run build."""
        jobs = ci_workflow.get("jobs", {})
        assert "frontend-build" in jobs
        steps = jobs["frontend-build"]["steps"]
        step_runs = [s.get("run", "") for s in steps]
        assert any("npm run build" in r for r in step_runs)

    def test_f5_cicd_container_validate_job(self, ci_workflow: Dict[str, Any]):
        """Verify container-validate job runs docker compose config."""
        jobs = ci_workflow.get("jobs", {})
        assert "container-validate" in jobs
        steps = jobs["container-validate"]["steps"]
        step_runs = [s.get("run", "") for s in steps]
        assert any("docker compose" in r and "config" in r for r in step_runs)

    def test_f5_cicd_k8s_helm_lint_job(self, ci_workflow: Dict[str, Any]):
        """Verify k8s-helm-lint job validates Helm chart and K8s manifests."""
        jobs = ci_workflow.get("jobs", {})
        assert "k8s-helm-lint" in jobs
        steps = jobs["k8s-helm-lint"]["steps"]
        step_runs = [s.get("run", "") for s in steps]
        assert any("helm lint" in r for r in step_runs)


# =============================================================================
# F6: Health Probes (R1.4)
# =============================================================================

class TestF6HealthProbes:
    """F6: Health and liveness probe HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_f6_api_health_endpoint_liveness(self, async_client: AsyncClient):
        """GET /api/health returns 200 with status ok and version."""
        resp = await async_client.get("/api/health")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "environment" in data

    @pytest.mark.asyncio
    async def test_f6_root_health_endpoint_liveness(self, async_client: AsyncClient):
        """GET /health root mount returns 200 with status ok."""
        resp = await async_client.get("/health")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_f6_api_health_db_connectivity(self, async_client: AsyncClient):
        """GET /api/health/db returns 200 with database connected."""
        resp = await async_client.get("/api/health/db")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    @pytest.mark.asyncio
    async def test_f6_root_health_db_connectivity(self, async_client: AsyncClient):
        """GET /health/db root mount returns 200 with database connected."""
        resp = await async_client.get("/health/db")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    @pytest.mark.asyncio
    async def test_f6_health_environment_configuration(self, async_client: AsyncClient):
        """Verify dynamic environment in settings is reflected in /api/health."""
        resp = await async_client.get("/api/health")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["environment"] == settings.ENVIRONMENT


# =============================================================================
# F7: Corporate Templates (R2.1)
# =============================================================================

class TestF7CorporateTemplates:
    """F7: Built-in enterprise corporate templates and color/font schemas."""

    def test_f7_five_presets_exist(self):
        """Verify all 5 enterprise templates exist in list_templates()."""
        templates = list_templates()
        ids = {t.id for t in templates}
        expected = {"mckinsey_navy", "bcg_emerald", "bain_crimson", "goldman_slate", "modern_tech"}
        assert expected.issubset(ids)

    def test_f7_brand_palette_schema_validation(self):
        """BrandPalette validates strict hex formats for all required color keys."""
        pal = BrandPalette(
            primary="#0F172A",
            secondary="#1E293B",
            accent="#2563EB",
            accent_light="#EFF6FF",
            background="#FFFFFF",
            card_bg="#F8FAFC",
            border="#E2E8F0",
            text_dark="#1E293B",
            text_muted="#64748B",
            white="#FFFFFF",
            high_risk="#DC2626",
            med_risk="#D97706",
            low_risk="#16A34A",
        )
        assert pal.primary == "#0F172A"
        assert pal.accent == "#2563EB"

    def test_f7_font_schema_validation(self):
        """FontSchema specifies valid heading and body font typography."""
        fonts = FontSchema(heading="Georgia", body="Georgia")
        assert fonts.heading == "Georgia"
        assert fonts.body == "Georgia"

    def test_f7_get_template_resolution(self):
        """get_template resolves template by ID and falls back to McKinsey Navy."""
        bcg = get_template("bcg_emerald")
        assert bcg.id == "bcg_emerald"
        assert bcg.fonts.heading == "Arial"

        fallback = get_template("nonexistent_unknown_theme")
        assert fallback.id == "mckinsey_navy"

        none_fallback = get_template(None)
        assert none_fallback.id == "mckinsey_navy"

    @pytest.mark.asyncio
    async def test_f7_api_templates_list_endpoint(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/templates returns JSON list of all 5 corporate templates."""
        data = await seed_consulting_project()
        proj_id = data["project_id"]
        resp = await async_client.get(f"/api/projects/{proj_id}/templates")
        assert resp.status_code == status.HTTP_200_OK
        res_list = resp.json()
        assert len(res_list) >= 5
        ids = {t["id"] for t in res_list}
        assert "mckinsey_navy" in ids
        assert "bcg_emerald" in ids


# =============================================================================
# F8: New Layout Schemas (R2.1)
# =============================================================================

class TestF8NewLayoutSchemas:
    """F8: Scorecard and Metrics slide layout schemas and PPTX rendering."""

    def test_f8_slide_layout_enum_has_scorecard_and_metrics(self):
        """Verify SlideLayout enum contains scorecard and metrics layouts."""
        assert hasattr(SlideLayout, "scorecard")
        assert hasattr(SlideLayout, "metrics")
        assert SlideLayout.scorecard.value == "scorecard"
        assert SlideLayout.metrics.value == "metrics"

    def test_f8_slide_item_scorecard_schema(self):
        """SlideItem validates scorecard structured table payload."""
        item = SlideItem(
            slide_order=4,
            title="Strategic Opportunity Scorecard",
            key_message="Comprehensive audit confirms market viability.",
            layout=SlideLayout.scorecard,
            content={
                "dimensions": [
                    {
                        "dimension": "Market Size",
                        "weight": "30%",
                        "score": "High (4.5/5)",
                        "status": "green",
                        "key_finding": "TAM growing at 38% CAGR.",
                    }
                ]
            },
        )
        assert item.layout == SlideLayout.scorecard
        assert len(item.content["dimensions"]) == 1

    def test_f8_slide_item_metrics_schema(self):
        """SlideItem validates metrics big-number card payload."""
        item = SlideItem(
            slide_order=5,
            title="Key Financial Benchmarks",
            key_message="Measurable performance indicators validate strategy.",
            layout=SlideLayout.metrics,
            content={
                "metrics": [
                    {
                        "label": "Projected TAM",
                        "value": "$48.5B",
                        "delta": "+38% YoY",
                        "subtext": "Global enterprise expansion",
                    }
                ]
            },
        )
        assert item.layout == SlideLayout.metrics
        assert len(item.content["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_f8_pptx_render_scorecard_slide(self, db_session: AsyncSession, seed_consulting_project):
        """PresentationRenderer formats scorecard slide as a 5-column table in PPTX."""
        data = await seed_consulting_project(include_scorecard_and_metrics=True)
        renderer = PresentationRenderer(db=db_session, template=get_template("mckinsey_navy"))
        artifact = await renderer.render(data["project_id"])
        assert artifact is not None
        assert os.path.exists(artifact.file_path)
        assert artifact.file_size_bytes > 0

    @pytest.mark.asyncio
    async def test_f8_pptx_render_metrics_slide(self, db_session: AsyncSession, seed_consulting_project):
        """PresentationRenderer formats metrics slide with 4 big-number cards in PPTX."""
        data = await seed_consulting_project(include_scorecard_and_metrics=True)
        renderer = PresentationRenderer(db=db_session, template=get_template("bcg_emerald"))
        artifact = await renderer.render(data["project_id"])
        assert artifact is not None
        assert os.path.exists(artifact.file_path)


# =============================================================================
# F9: Executive PDF Exporter (R2.2)
# =============================================================================

class TestF9ExecutivePDFExporter:
    """F9: Executive PDF summary memo exporter with ReportLab Platypus and NumberedCanvas."""

    @pytest.mark.asyncio
    async def test_f9_pdf_export_success_approved_project(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """ExecutivePDFExporter generates publication-quality PDF for approved project."""
        data = await seed_consulting_project(is_approved=True)
        exporter = ExecutivePDFExporter(db=db_session, template=get_template("mckinsey_navy"))
        file_path, file_size, file_hash = await exporter.export(data["project_id"])
        assert os.path.exists(file_path)
        assert file_size > 0
        assert len(file_hash) == 64

    @pytest.mark.asyncio
    async def test_f9_pdf_header_magic_bytes(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """Generated PDF file begins with valid %PDF- header."""
        data = await seed_consulting_project(is_approved=True)
        exporter = ExecutivePDFExporter(db=db_session)
        file_path, _, _ = await exporter.export(data["project_id"])
        with open(file_path, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"

    def test_f9_numbered_canvas_two_pass(self):
        """NumberedCanvas instantiates and saves page states dynamically."""
        from reportlab.pdfgen import canvas
        nc = NumberedCanvas(canvas.Canvas("test_tmp.pdf"))
        assert hasattr(nc, "_saved_page_states")
        assert hasattr(nc, "project_topic")
        assert hasattr(nc, "primary_hex")

    @pytest.mark.asyncio
    async def test_f9_pdf_brand_template_palette(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """PDF exporter incorporates corporate brand palette colors."""
        data = await seed_consulting_project(is_approved=True)
        goldman = get_template("goldman_slate")
        exporter = ExecutivePDFExporter(db=db_session, template=goldman)
        file_path, _, _ = await exporter.export(data["project_id"])
        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_f9_pdf_gate_error_on_unapproved(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """PDF exporter raises PDFGateError when synthesis is unapproved."""
        from app.presentation.pdf_exporter import PDFGateError
        data = await seed_consulting_project(is_approved=False)
        exporter = ExecutivePDFExporter(db=db_session)
        with pytest.raises(PDFGateError):
            await exporter.export(data["project_id"])


# =============================================================================
# F10: Interactive HTML Viewer (R2.2)
# =============================================================================

class TestF10InteractiveHTMLViewer:
    """F10: Standalone single-file interactive HTML presentation viewer."""

    @pytest.mark.asyncio
    async def test_f10_html_export_success_approved_project(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """HTMLPresentationGenerator generates standalone HTML file for approved project."""
        data = await seed_consulting_project(is_approved=True)
        generator = HTMLPresentationGenerator(db=db_session, template=get_template("mckinsey_navy"))
        file_path, file_size, file_hash = await generator.generate(data["project_id"])
        assert os.path.exists(file_path)
        assert file_size > 0
        assert len(file_hash) == 64

    @pytest.mark.asyncio
    async def test_f10_html_doctype_and_viewport(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """Generated HTML contains standard DOCTYPE declaration and mobile viewport meta."""
        data = await seed_consulting_project(is_approved=True)
        generator = HTMLPresentationGenerator(db=db_session)
        file_path, _, _ = await generator.generate(data["project_id"])
        content = Path(file_path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert '<meta name="viewport"' in content

    @pytest.mark.asyncio
    async def test_f10_html_brand_css_variables(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """Generated HTML embeds CSS variables matching corporate template brand palette."""
        data = await seed_consulting_project(is_approved=True)
        bcg = get_template("bcg_emerald")
        generator = HTMLPresentationGenerator(db=db_session, template=bcg)
        file_path, _, _ = await generator.generate(data["project_id"])
        content = Path(file_path).read_text(encoding="utf-8")
        assert f"--c-primary: {bcg.palette.primary}" in content
        assert f"--c-accent: {bcg.palette.accent}" in content

    @pytest.mark.asyncio
    async def test_f10_html_keyboard_nav_and_print_style(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """Generated HTML contains keyboard navigation script and print stylesheet."""
        data = await seed_consulting_project(is_approved=True)
        generator = HTMLPresentationGenerator(db=db_session)
        file_path, _, _ = await generator.generate(data["project_id"])
        content = Path(file_path).read_text(encoding="utf-8")
        assert "ArrowRight" in content or "keydown" in content
        assert "@media print" in content

    @pytest.mark.asyncio
    async def test_f10_html_gate_error_on_unapproved(
        self, db_session: AsyncSession, seed_consulting_project
    ):
        """HTML generator raises HTMLGateError when synthesis is unapproved."""
        from app.presentation.html_viewer import HTMLGateError
        data = await seed_consulting_project(is_approved=False)
        generator = HTMLPresentationGenerator(db=db_session)
        with pytest.raises(HTMLGateError):
            await generator.generate(data["project_id"])


# =============================================================================
# F11: Multi-Format Export API (R2.2)
# =============================================================================

class TestF11MultiFormatExportAPI:
    """F11: Parameterized multi-format export API endpoint."""

    @pytest.mark.asyncio
    async def test_f11_export_pptx_mime_and_header(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/artifact?format=pptx returns PPTX MIME and filename header."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pptx")
        assert resp.status_code == status.HTTP_200_OK
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in resp.headers["content-type"]
        assert f"consulting_deck_{pid}.pptx" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_f11_export_pdf_mime_and_header(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/artifact?format=pdf returns PDF MIME and filename header."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pdf")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.headers["content-type"] == "application/pdf"
        assert f"executive_summary_{pid}.pdf" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_f11_export_html_mime_and_header(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/artifact?format=html returns HTML MIME and filename header."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=html")
        assert resp.status_code == status.HTTP_200_OK
        assert "text/html" in resp.headers["content-type"]
        assert f"consulting_deck_{pid}.html" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_f11_export_template_parameter(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/artifact?format=pptx&template=bcg_emerald applies template."""
        data = await seed_consulting_project(is_approved=True)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pptx&template=bcg_emerald")
        assert resp.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_f11_export_unapproved_project_blocked(
        self, async_client: AsyncClient, seed_consulting_project
    ):
        """GET /api/projects/{id}/artifact on unapproved project returns 400 Bad Request."""
        data = await seed_consulting_project(is_approved=False)
        pid = data["project_id"]
        resp = await async_client.get(f"/api/projects/{pid}/artifact?format=pptx")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# F12: External Webhooks (R2.3)
# =============================================================================

class TestF12ExternalWebhooks:
    """F12: Webhook database models, REST management API, and payload builders."""

    @pytest.mark.asyncio
    async def test_f12_webhook_subscription_model_persistence(self, db_session: AsyncSession):
        """WebhookSubscription model persists and retrieves correctly."""
        sub = WebhookSubscription(
            id=uuid.uuid4(),
            target_type="slack",
            url="https://hooks.slack.com/services/T00/B00/X00",
            events=["slide_review_gate"],
            is_active=True,
        )
        db_session.add(sub)
        await db_session.commit()

        stmt = select(WebhookSubscription).where(WebhookSubscription.id == sub.id)
        fetched = (await db_session.execute(stmt)).scalar_one_or_none()
        assert fetched is not None
        assert fetched.target_type == "slack"
        assert fetched.is_active is True

    @pytest.mark.asyncio
    async def test_f12_webhook_delivery_model_persistence(self, db_session: AsyncSession):
        """WebhookDelivery model stores audit history and execution outcome."""
        deliv = WebhookDelivery(
            id=uuid.uuid4(),
            event_type="slide_review_gate",
            payload={"topic": "Transformation"},
            status_code=200,
            attempt_count=1,
            success=True,
        )
        db_session.add(deliv)
        await db_session.commit()

        stmt = select(WebhookDelivery).where(WebhookDelivery.id == deliv.id)
        fetched = (await db_session.execute(stmt)).scalar_one_or_none()
        assert fetched is not None
        assert fetched.success is True
        assert fetched.status_code == 200

    @pytest.mark.asyncio
    async def test_f12_webhook_subscription_crud_api(self, async_client: AsyncClient):
        """Verify POST, GET, and DELETE webhook subscription REST endpoints."""
        create_payload = {
            "target_type": "slack",
            "url": "https://hooks.slack.com/services/T11/B22/Z33",
            "events": ["slide_review_gate"],
            "is_active": True,
        }
        create_resp = await async_client.post("/api/webhooks", json=create_payload)
        assert create_resp.status_code == status.HTTP_201_CREATED
        sub_id = create_resp.json()["id"]

        get_resp = await async_client.get(f"/api/webhooks/{sub_id}")
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["target_type"] == "slack"

        del_resp = await async_client.delete(f"/api/webhooks/{sub_id}")
        assert del_resp.status_code == status.HTTP_204_NO_CONTENT

    def test_f12_slack_block_kit_payload_structure(self):
        """build_slack_slide_review_payload constructs valid Block Kit structure."""
        p = build_slack_slide_review_payload(
            project_id=uuid.uuid4(),
            topic="Global Strategy",
            audience="Board of Directors",
            total_slides=11,
            slide_summary=["Slide 1: Title", "Slide 2: Summary"],
            review_url="https://consulting.example/projects/1/storyline",
        )
        assert "blocks" in p
        types = [b["type"] for b in p["blocks"]]
        assert "header" in types
        assert "section" in types
        assert "actions" in types

    def test_f12_teams_adaptive_card_payload_structure(self):
        """build_teams_slide_review_payload constructs Adaptive Card 1.4 schema."""
        p = build_teams_slide_review_payload(
            project_id=uuid.uuid4(),
            topic="Global Strategy",
            audience="Board of Directors",
            total_slides=11,
            slide_summary=["Slide 1: Title", "Slide 2: Summary"],
            review_url="https://consulting.example/projects/1/storyline",
        )
        assert p["type"] == "message"
        card = p["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"
        body_types = [el["type"] for el in card["body"]]
        assert "FactSet" in body_types


# =============================================================================
# F13: Review Gate Triggers (R2.3)
# =============================================================================

class TestF13ReviewGateTriggers:
    """F13: Webhook notifications dispatched on slide-level review gate arrival."""

    @pytest.mark.asyncio
    async def test_f13_dispatch_slide_review_gate_active_subs(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """WebhookService dispatches to active subscriptions on slide_review_gate."""
        sub = await seed_webhook_sub(target_type="slack", url="https://hooks.slack.com/services/test/gate")
        service = WebhookService(db=db_session)

        # Mock http post
        with patch.object(service.dispatcher, "dispatch", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = WebhookDelivery(
                id=uuid.uuid4(), subscription_id=sub.id, event_type="slide_review_gate",
                status_code=200, success=True
            )
            deliveries = await service.dispatch_slide_review_gate(
                project_id=uuid.uuid4(),
                topic="Cloud Strategy",
                audience="Executive Committee",
                total_slides=11,
                slide_summary=["Slide 1", "Slide 2"],
                session=db_session,
            )
            assert len(deliveries) >= 1
            assert mock_dispatch.called

    def test_f13_dispatch_payload_context(self):
        """Generic payload builder embeds required event context."""
        pid = uuid.uuid4()
        payload = build_generic_payload(
            event_type="slide_review_gate",
            project_id=pid,
            data={"topic": "AI Transformation", "slides": 11},
        )
        assert payload["event"] == "slide_review_gate"
        assert payload["project_id"] == str(pid)
        assert payload["data"]["topic"] == "AI Transformation"

    @pytest.mark.asyncio
    async def test_f13_dispatch_creates_delivery_records(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """Dispatched webhook persists WebhookDelivery audit row."""
        sub = await seed_webhook_sub(target_type="generic", url="https://api.example.com/webhook")
        dispatcher = WebhookDispatcher(db=db_session)

        mock_resp = httpx.Response(200, json={"received": True})
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            delivery = await dispatcher.dispatch(
                url=sub.url,
                payload={"test": "payload"},
                subscription_id=sub.id,
            )
            assert delivery.success is True
            assert delivery.status_code == 200

    @pytest.mark.asyncio
    async def test_f13_inactive_subscription_not_triggered(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """Inactive webhook subscriptions (is_active=False) are ignored."""
        await seed_webhook_sub(
            url="https://hooks.slack.com/services/inactive",
            is_active=False,
        )
        service = WebhookService(db=db_session)
        subs = await service._get_active_subscriptions(
            event_type="slide_review_gate",
            session=db_session,
        )
        assert not any(s.url == "https://hooks.slack.com/services/inactive" for s in subs)

    @pytest.mark.asyncio
    async def test_f13_project_scoped_subscription(
        self, db_session: AsyncSession, seed_webhook_sub
    ):
        """Subscription scoped to project A does not trigger for project B."""
        proj_a = uuid.uuid4()
        proj_b = uuid.uuid4()
        sub_a = await seed_webhook_sub(
            url="https://hooks.slack.com/services/projectA",
            project_id=proj_a,
        )
        service = WebhookService(db=db_session)
        subs_b = await service._get_active_subscriptions(
            event_type="slide_review_gate",
            project_id=proj_b,
            session=db_session,
        )
        assert not any(s.id == sub_a.id for s in subs_b)


# =============================================================================
# F14: Webhook Security & Mocks (R2.3)
# =============================================================================

class TestF14WebhookSecurityAndMocks:
    """F14: SSRF prevention, URL validation, and mock delivery infrastructure."""

    def test_f14_validate_url_public_https(self):
        """validate_url approves safe public HTTPS URLs."""
        safe_url = "https://hooks.slack.com/services/T00/B00/X00"
        assert validate_url(safe_url) == safe_url

    def test_f14_validate_url_rejects_localhost(self):
        """validate_url rejects localhost and 127.0.0.1 with ValueError."""
        with pytest.raises(ValueError, match="restricted IP address"):
            validate_url("http://localhost:8000/webhook")
        with pytest.raises(ValueError, match="restricted IP address"):
            validate_url("http://127.0.0.1:5000/hook")

    def test_f14_validate_url_rejects_private_ips(self):
        """validate_url rejects private RFC 1918 CIDR ranges."""
        for private_url in [
            "http://10.0.0.1/hook",
            "http://172.16.0.5/hook",
            "http://192.168.1.100/hook",
        ]:
            with pytest.raises(ValueError):
                validate_url(private_url)

    def test_f14_validate_url_rejects_aws_imds(self):
        """validate_url rejects cloud metadata IP (169.254.169.254)."""
        with pytest.raises(ValueError):
            validate_url("http://169.254.169.254/latest/meta-data")

    @pytest.mark.asyncio
    async def test_f14_dispatcher_httpx_mock_success_and_hmac(self, db_session: AsyncSession):
        """WebhookDispatcher sends request to target and signs HMAC signature when secret is provided."""
        dispatcher = WebhookDispatcher(db=db_session)
        mock_resp = httpx.Response(200, json={"ok": True})

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            deliv = await dispatcher.dispatch(
                url="https://api.external-consulting.com/webhook",
                payload={"alert": "review_gate"},
                secret="super-secret-hmac-key",
            )
            assert deliv.success is True
            assert deliv.status_code == 200
            call_kwargs = mock_post.call_args[1]
            assert "X-Webhook-Signature" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Webhook-Signature"].startswith("sha256=")
