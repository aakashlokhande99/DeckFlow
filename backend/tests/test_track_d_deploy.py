"""Automated Test Suite for Track D: Production Deployment, Orchestration & CI/CD.

Covers:
- Dockerfile hardening & .dockerignore exclusion rules.
- Production Docker Compose specification, resource limits, and healthchecks.
- Cloud-agnostic Kubernetes modular manifests (00-namespace through 10-hpa).
- Helm chart structure, metadata, values, and templates.
- Health probe endpoints (/api/health and /health root mount).
- GitHub Actions CI/CD automation pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import AsyncClient

from app.core.config import settings
from app.main import app

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# 1. Dockerfile Hardening & .dockerignore
# =============================================================================

class TestDockerfilesAndDockerignore:
    """Validates Dockerfile security hardening and build context hygiene."""

    def test_frontend_public_gitkeep_exists(self):
        public_dir = WORKSPACE_ROOT / "frontend" / "public"
        assert public_dir.is_dir(), "frontend/public directory must exist"
        gitkeep = public_dir / ".gitkeep"
        assert gitkeep.exists(), "frontend/public/.gitkeep must exist to prevent COPY failure"

    def test_frontend_dockerfile_hardening(self):
        dockerfile = WORKSPACE_ROOT / "frontend" / "Dockerfile"
        assert dockerfile.exists()
        content = dockerfile.read_text(encoding="utf-8")
        assert "COPY --from=builder /app/public ./public" in content
        assert "adduser --system --uid 1001 nextjs" in content
        assert "USER nextjs" in content

    def test_backend_dockerfile_alembic_and_artifacts(self):
        dockerfile = WORKSPACE_ROOT / "backend" / "Dockerfile"
        assert dockerfile.exists()
        content = dockerfile.read_text(encoding="utf-8")
        assert "COPY alembic.ini ." in content, "backend/Dockerfile must copy alembic.ini for migrations"
        assert "mkdir -p /app/artifacts" in content, "backend/Dockerfile must create /app/artifacts directory"
        assert "chown -R appuser:appgroup /app" in content
        assert "USER appuser" in content

    def test_backend_dockerfile_install_layer(self):
        readme = WORKSPACE_ROOT / "backend" / "README.md"
        assert readme.exists(), "backend/README.md must exist for pyproject.toml package build"
        dockerfile = WORKSPACE_ROOT / "backend" / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "COPY pyproject.toml README.md ./" in content
        assert "COPY app/ ./app/" in content
        assert "RUN pip install --prefix=/install ." in content
        assert "-e ." not in content

    def test_dockerignore_backend(self):
        ignore_file = WORKSPACE_ROOT / "backend" / ".dockerignore"
        assert ignore_file.exists(), "backend/.dockerignore must exist"
        content = ignore_file.read_text(encoding="utf-8")
        for pattern in ["__pycache__", ".pytest_cache", ".venv", ".git"]:
            assert pattern in content, f"Pattern {pattern} must be in backend/.dockerignore"

    def test_dockerignore_frontend(self):
        ignore_file = WORKSPACE_ROOT / "frontend" / ".dockerignore"
        assert ignore_file.exists(), "frontend/.dockerignore must exist"
        content = ignore_file.read_text(encoding="utf-8")
        for pattern in ["node_modules", ".next", ".git"]:
            assert pattern in content, f"Pattern {pattern} must be in frontend/.dockerignore"


# =============================================================================
# 2. Production Docker Compose
# =============================================================================

class TestProductionDockerCompose:
    """Validates production Docker Compose configuration and resource guarantees."""

    @pytest.fixture
    def compose_data(self):
        compose_file = WORKSPACE_ROOT / "deploy" / "docker-compose.prod.yml"
        assert compose_file.exists(), "deploy/docker-compose.prod.yml must exist"
        with open(compose_file, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_all_services_present(self, compose_data):
        services = compose_data.get("services", {})
        expected_services = {"db", "redis", "backend", "worker", "frontend"}
        assert expected_services.issubset(set(services.keys()))

    def test_resource_limits_configured(self, compose_data):
        services = compose_data.get("services", {})
        expected_limits = {
            "db": {"limits": {"cpus": "1.0", "memory": "1536M"}, "reservations": {"cpus": "0.25", "memory": "512M"}},
            "redis": {"limits": {"cpus": "0.5", "memory": "512M"}, "reservations": {"cpus": "0.1", "memory": "128M"}},
            "backend": {"limits": {"cpus": "1.0", "memory": "1536M"}, "reservations": {"cpus": "0.25", "memory": "512M"}},
            "worker": {"limits": {"cpus": "2.0", "memory": "3072M"}, "reservations": {"cpus": "0.5", "memory": "1024M"}},
            "frontend": {"limits": {"cpus": "0.5", "memory": "1024M"}, "reservations": {"cpus": "0.1", "memory": "256M"}},
        }
        for svc_name, expected in expected_limits.items():
            svc = services.get(svc_name, {})
            deploy = svc.get("deploy", {})
            resources = deploy.get("resources", {})
            limits = resources.get("limits", {})
            reservations = resources.get("reservations", {})

            assert str(limits.get("cpus")) == expected["limits"]["cpus"], f"{svc_name} cpu limit mismatch"
            assert str(limits.get("memory")) == expected["limits"]["memory"], f"{svc_name} memory limit mismatch"
            assert str(reservations.get("cpus")) == expected["reservations"]["cpus"], f"{svc_name} cpu reservation mismatch"
            assert str(reservations.get("memory")) == expected["reservations"]["memory"], f"{svc_name} memory reservation mismatch"

    def test_shared_artifacts_volume(self, compose_data):
        services = compose_data.get("services", {})
        backend_vols = services.get("backend", {}).get("volumes", [])
        worker_vols = services.get("worker", {}).get("volumes", [])

        assert any("artifacts_prod:/app/artifacts" in v for v in backend_vols), "backend must mount artifacts_prod volume"
        assert any("artifacts_prod:/app/artifacts" in v for v in worker_vols), "worker must mount artifacts_prod volume"

        top_volumes = compose_data.get("volumes", {})
        assert "artifacts_prod" in top_volumes, "top-level volumes must declare artifacts_prod"

    def test_healthchecks_defined(self, compose_data):
        services = compose_data.get("services", {})
        for svc_name in ["db", "redis", "backend", "frontend"]:
            svc = services.get(svc_name, {})
            health = svc.get("healthcheck", {})
            assert "test" in health, f"{svc_name} must have a healthcheck test defined"

    def test_serpapi_key_env_alignment(self, compose_data):
        services = compose_data.get("services", {})
        backend_env = services.get("backend", {}).get("environment", {})
        worker_env = services.get("worker", {}).get("environment", {})

        assert "SERPAPI_API_KEY" in backend_env or "SERPAPI_KEY" in backend_env
        assert "SERPAPI_API_KEY" in worker_env or "SERPAPI_KEY" in worker_env


# =============================================================================
# 3. Cloud-Agnostic Kubernetes Manifests
# =============================================================================

class TestKubernetesManifests:
    """Validates modular Kubernetes manifests under deploy/k8s/."""

    EXPECTED_FILES = [
        "00-namespace.yaml",
        "01-configmap.yaml",
        "02-secrets.yaml",
        "03-pvc.yaml",
        "04-postgres.yaml",
        "05-redis.yaml",
        "06-backend.yaml",
        "07-worker.yaml",
        "08-frontend.yaml",
        "09-ingress.yaml",
        "10-hpa.yaml",
    ]

    def test_manifest_files_presence(self):
        k8s_dir = WORKSPACE_ROOT / "deploy" / "k8s"
        assert k8s_dir.is_dir(), "deploy/k8s must exist"
        for filename in self.EXPECTED_FILES:
            file_path = k8s_dir / filename
            assert file_path.exists(), f"deploy/k8s/{filename} must exist"

    def test_all_manifests_valid_yaml(self):
        k8s_dir = WORKSPACE_ROOT / "deploy" / "k8s"
        for filename in self.EXPECTED_FILES:
            file_path = k8s_dir / filename
            with open(file_path, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
            assert len(docs) >= 1, f"{filename} must contain at least one YAML document"
            for doc in docs:
                if doc is None:
                    continue
                assert "apiVersion" in doc, f"Document in {filename} missing apiVersion"
                assert "kind" in doc, f"Document in {filename} missing kind"
                assert "metadata" in doc, f"Document in {filename} missing metadata"
                assert "name" in doc["metadata"], f"Document in {filename} missing metadata.name"

    def test_namespace_manifest(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "00-namespace.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["kind"] == "Namespace"
        assert doc["metadata"]["name"] == "consulting-prod"
        assert doc["metadata"]["labels"]["name"] == "consulting-prod"

    def test_all_manifests_consistent_namespace(self):
        k8s_dir = WORKSPACE_ROOT / "deploy" / "k8s"
        for filename in self.EXPECTED_FILES:
            if filename == "00-namespace.yaml":
                continue
            file_path = k8s_dir / filename
            with open(file_path, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
            for doc in docs:
                if doc and isinstance(doc, dict) and "metadata" in doc and "namespace" in doc["metadata"]:
                    assert doc["metadata"]["namespace"] == "consulting-prod", (
                        f"Document {doc.get('kind')} in {filename} must declare namespace consulting-prod"
                    )

    def test_configmap_and_secrets(self):
        cm_path = WORKSPACE_ROOT / "deploy" / "k8s" / "01-configmap.yaml"
        cm_doc = yaml.safe_load(cm_path.read_text(encoding="utf-8"))
        assert cm_doc["kind"] == "ConfigMap"
        assert cm_doc["metadata"]["name"] == "consulting-config"
        assert "ENVIRONMENT" in cm_doc["data"]
        assert "DATABASE_URL" in cm_doc["data"]
        # Credentials hygiene: ensure passwords are not in plaintext in ConfigMap
        assert "ChangeMeInProductionSecret2026!" not in cm_doc["data"]["DATABASE_URL"]
        assert "RedisSecretProd2026!" not in cm_doc["data"]["REDIS_URL"]
        assert "$(POSTGRES_USER)" in cm_doc["data"]["DATABASE_URL"]
        assert "$(POSTGRES_PASSWORD)" in cm_doc["data"]["DATABASE_URL"]

        sec_path = WORKSPACE_ROOT / "deploy" / "k8s" / "02-secrets.yaml"
        sec_doc = yaml.safe_load(sec_path.read_text(encoding="utf-8"))
        assert sec_doc["kind"] == "Secret"
        assert sec_doc["metadata"]["name"] == "consulting-secrets"
        assert "POSTGRES_PASSWORD" in sec_doc["stringData"]
        assert sec_doc["stringData"]["POSTGRES_PASSWORD"] == "ChangeMeInProductionSecret2026!"
        assert "SECRET_KEY" in sec_doc["stringData"]

    def test_pvc_manifests(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "03-pvc.yaml"
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        pvc_names = {d["metadata"]["name"]: d for d in docs if d}
        assert "consulting-artifacts-pvc" in pvc_names
        assert "postgres-data-pvc" in pvc_names
        assert "ReadWriteMany" in pvc_names["consulting-artifacts-pvc"]["spec"]["accessModes"]
        assert "ReadWriteOnce" in pvc_names["postgres-data-pvc"]["spec"]["accessModes"]
        assert pvc_names["consulting-artifacts-pvc"]["spec"]["storageClassName"] == "standard"
        assert pvc_names["postgres-data-pvc"]["spec"]["storageClassName"] == "standard"

    def test_backend_deployment_and_service(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "06-backend.yaml"
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        dep = next(d for d in docs if d["kind"] == "Deployment")
        svc = next(d for d in docs if d["kind"] == "Service")

        assert dep["metadata"]["name"] == "consulting-backend"
        assert dep["spec"]["replicas"] == 3
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert container["livenessProbe"]["httpGet"]["path"] == "/api/health"
        assert container["readinessProbe"]["httpGet"]["path"] in ["/api/health", "/api/health/db"]
        assert container["resources"]["requests"]["cpu"] == "250m"
        assert container["resources"]["limits"]["memory"] == "1536Mi"
        assert any(vm["name"] == "artifacts-volume" and vm["mountPath"] == "/app/artifacts" for vm in container["volumeMounts"])

        assert svc["metadata"]["name"] == "consulting-backend-svc"
        assert svc["spec"]["ports"][0]["port"] == 8000

    def test_worker_deployment(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "07-worker.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "consulting-worker"
        assert doc["spec"]["replicas"] == 4
        container = doc["spec"]["template"]["spec"]["containers"][0]
        assert "celery" in container["command"]
        assert container["resources"]["requests"]["cpu"] == "500m"
        assert container["resources"]["limits"]["memory"] == "3072Mi"

        # Celery probe validation: ensure probes are not neutered with || exit 0
        liveness_cmd = " ".join(container["livenessProbe"]["exec"]["command"])
        readiness_cmd = " ".join(container["readinessProbe"]["exec"]["command"])
        assert "|| exit 0" not in liveness_cmd, "Worker livenessProbe must not contain || exit 0"
        assert "|| exit 0" not in readiness_cmd, "Worker readinessProbe must not contain || exit 0"
        assert "inspect ping" in liveness_cmd
        assert "--timeout=5" in liveness_cmd
        assert container["livenessProbe"]["timeoutSeconds"] == 10
        assert container["livenessProbe"]["initialDelaySeconds"] == 30
        assert container["readinessProbe"]["initialDelaySeconds"] == 15

    def test_ingress_routing_and_ws(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "09-ingress.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["kind"] == "Ingress"
        annotations = doc["metadata"]["annotations"]
        assert annotations.get("nginx.ingress.kubernetes.io/websocket-services") == "consulting-backend-svc"
        rules = doc["spec"]["rules"][0]["http"]["paths"]
        paths = {p["path"]: p["backend"]["service"]["name"] for p in rules}
        assert "/api/ws" in paths and paths["/api/ws"] == "consulting-backend-svc"
        assert "/api" in paths and paths["/api"] == "consulting-backend-svc"
        assert "/" in paths and paths["/"] == "consulting-frontend-svc"

    def test_hpa_definitions(self):
        path = WORKSPACE_ROOT / "deploy" / "k8s" / "10-hpa.yaml"
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        hpa_targets = {d["metadata"]["name"]: d["spec"]["scaleTargetRef"]["name"] for d in docs if d}
        assert hpa_targets.get("consulting-backend-hpa") == "consulting-backend"
        assert hpa_targets.get("consulting-worker-hpa") == "consulting-worker"


# =============================================================================
# 4. Helm Chart Packaging
# =============================================================================

class TestHelmChartPackaging:
    """Validates Helm chart metadata, values, and templates."""

    @pytest.fixture
    def chart_dir(self):
        d = WORKSPACE_ROOT / "deploy" / "helm" / "consulting-deck"
        assert d.is_dir(), "deploy/helm/consulting-deck must exist"
        return d

    def test_chart_yaml(self, chart_dir):
        chart_file = chart_dir / "Chart.yaml"
        assert chart_file.exists()
        chart = yaml.safe_load(chart_file.read_text(encoding="utf-8"))
        assert chart["apiVersion"] == "v2"
        assert chart["name"] == "consulting-deck"
        assert chart["version"] == "0.1.0"
        assert chart["appVersion"] == "1.0.0"

    def test_values_yaml(self, chart_dir):
        values_file = chart_dir / "values.yaml"
        assert values_file.exists()
        values = yaml.safe_load(values_file.read_text(encoding="utf-8"))
        assert "replicaCount" in values
        assert values["replicaCount"]["backend"] == 3
        assert values["replicaCount"]["worker"] == 4
        assert values["replicaCount"]["frontend"] == 2
        assert "image" in values
        assert "service" in values
        assert "ingress" in values
        assert "resources" in values
        assert "persistence" in values
        assert values["persistence"].get("storageClass") == "standard"
        assert "postgres" in values
        assert "redis" in values

    def test_all_templates_present(self, chart_dir):
        templates_dir = chart_dir / "templates"
        expected_templates = [
            "_helpers.tpl",
            "configmap.yaml",
            "secrets.yaml",
            "pvc.yaml",
            "backend-deployment.yaml",
            "backend-service.yaml",
            "worker-deployment.yaml",
            "frontend-deployment.yaml",
            "frontend-service.yaml",
            "postgres.yaml",
            "redis.yaml",
            "ingress.yaml",
            "hpa.yaml",
            "tests/test-connection.yaml",
        ]
        for tpl in expected_templates:
            tpl_path = templates_dir / tpl
            assert tpl_path.exists(), f"Helm template {tpl} must exist"

    def test_helm_worker_probe_and_pvc_templates(self, chart_dir):
        worker_tpl = chart_dir / "templates" / "worker-deployment.yaml"
        worker_text = worker_tpl.read_text(encoding="utf-8")
        assert "|| exit 0" not in worker_text, "Helm worker probes must not be neutered with || exit 0"
        assert "--timeout=5" in worker_text

        pvc_tpl = chart_dir / "templates" / "pvc.yaml"
        pvc_text = pvc_tpl.read_text(encoding="utf-8")
        assert "storageClassName" in pvc_text
        assert ".Values.persistence.storageClass" in pvc_text


# =============================================================================
# 5. Health Probe Endpoints
# =============================================================================

class TestHealthEndpoints:
    """Tests health probe endpoints (/api/health and root /health)."""

    @pytest.mark.asyncio
    async def test_api_health_returns_ok(self, async_client: AsyncClient):
        resp = await async_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["environment"] == settings.ENVIRONMENT

    @pytest.mark.asyncio
    async def test_root_health_returns_ok(self, async_client: AsyncClient):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["environment"] == settings.ENVIRONMENT

    @pytest.mark.asyncio
    async def test_health_environment_dynamic(self, async_client: AsyncClient):
        with patch.object(settings, "ENVIRONMENT", "production"):
            resp = await async_client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json()["environment"] == "production"

            resp_root = await async_client.get("/health")
            assert resp_root.status_code == 200
            assert resp_root.json()["environment"] == "production"

    @pytest.mark.asyncio
    async def test_health_db_endpoint(self, async_client: AsyncClient):
        resp = await async_client.get("/api/health/db")
        assert resp.status_code == 200
        assert resp.json()["database"] == "connected"

        resp_root = await async_client.get("/health/db")
        assert resp_root.status_code == 200
        assert resp_root.json()["database"] == "connected"


# =============================================================================
# 6. CI/CD Workflow Pipeline
# =============================================================================

class TestCICDWorkflow:
    """Validates GitHub Actions CI/CD workflow configuration."""

    def test_workflow_syntax_and_jobs(self):
        workflow_path = WORKSPACE_ROOT / ".github" / "workflows" / "ci.yml"
        assert workflow_path.exists(), ".github/workflows/ci.yml must exist"
        content = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        assert "jobs" in content
        jobs = content["jobs"]
        assert "backend-test" in jobs
        assert "frontend-build" in jobs
        assert "container-validate" in jobs
        assert "k8s-helm-lint" in jobs

    def test_workflow_clean_runner_env_and_security(self):
        workflow_path = WORKSPACE_ROOT / ".github" / "workflows" / "ci.yml"
        content = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        # Verify backend-test defines required celery env vars
        steps = content["jobs"]["backend-test"]["steps"]
        pytest_step = next(s for s in steps if s.get("name") == "Run Pytest Suite")
        env = pytest_step.get("env", {})
        assert env.get("CELERY_BROKER_URL") == "redis://localhost:6379/0"
        assert env.get("CELERY_RESULT_BACKEND") == "redis://localhost:6379/0"

        # Verify container-validate does not suppress errors with || true
        cv_steps = content["jobs"]["container-validate"]["steps"]
        docker_step = next(s for s in cv_steps if s.get("name") == "Validate Dockerfile Syntax")
        run_script = docker_step.get("run", "")
        assert "|| true" not in run_script, "CI container validation must not suppress docker build errors"
