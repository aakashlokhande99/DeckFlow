# Project: Enterprise AI Consulting Deck Generator (Track D & Phase 3)

## Architecture
The system consists of:
- **Backend**: FastAPI asynchronous REST & WebSocket service powering the consulting deck engine.
- **Worker**: Celery distributed task runner backed by Redis for multi-agent research and deck compilation.
- **Workflow**: LangGraph state machine orchestrating 8 research/synthesis nodes with human-in-the-loop review gates.
- **Presentation Engine**: Modular export subsystem supporting PPTX (python-pptx with corporate brand palettes), Executive PDF summaries (ReportLab Platypus), and standalone interactive HTML presentation viewers.
- **Notification Subsystem**: Asynchronous webhook dispatcher sending Slack Block Kit and MS Teams Adaptive Cards upon review gate arrival with SSRF protection.
- **Frontend**: Next.js 14 App Router client with interactive slide storyline editor, export modal, and real-time WebSocket progress tracking.
- **Production Infrastructure**: Cloud-agnostic Kubernetes manifests (`deploy/k8s/`), Helm chart packaging (`deploy/helm/`), production Docker Compose (`deploy/docker-compose.prod.yml`), and GitHub Actions CI/CD pipeline (`.github/workflows/ci.yml`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Production Compose | `deploy/docker-compose.prod.yml` with resources, shared artifact volume, frontend healthcheck | M1 | R1.1 |
| 2 | Dockerfile Hardening | `backend/Dockerfile` (alembic.ini, artifacts dir), `frontend/Dockerfile` (public dir fix), `.dockerignore` | M1 | R1.1 |
| 3 | Cloud-Agnostic K8s | Modular manifests in `deploy/k8s/` (00-namespace to 10-hpa) with probes & persistent volumes | M1 | R1.2 |
| 4 | Helm Packaging | Helm chart in `deploy/helm/consulting-deck/` with values.yaml and full templating | M1 | R1.2 |
| 5 | CI/CD Automation | GitHub Actions `.github/workflows/ci.yml` (backend pytest, frontend build, container builds, k8s lint) | M1 | R1.3 |
| 6 | Health Probe Fixes | Harmonize `/api/health`, `/health`, and environment configuration | M1 | R1.4 |
| 7 | Corporate Templates | Brand palettes & font schemas with 5 enterprise presets (McKinsey, BCG, Bain, Goldman, Tech) | M2 | R2.1 |
| 8 | New Layout Schemas | Implement `scorecard` (KPI dimensions/ratings) and `metrics` (big numbers/deltas) layouts | M2 | R2.1 |
| 9 | Executive PDF Exporter | ReportLab Platypus generator with two-pass `NumberedCanvas` and executive summary memo layout | M2 | R2.2 |
| 10 | Interactive HTML Viewer | Standalone single-file HTML presentation viewer with keyboard nav, speaker notes, overview grid, print style | M2 | R2.2 |
| 11 | Multi-Format Export API | Parameterized `GET /api/projects/{id}/artifact?format={pptx|pdf|html}&template={template}` & Frontend UI | M2 | R2.2 |
| 12 | External Webhooks | Database models, Alembic migration, and service for Slack Block Kit & MS Teams Adaptive Cards | M3 | R2.3 |
| 13 | Review Gate Triggers | Webhook dispatch upon slide-level storyline generation & synthesis gate arrival | M3 | R2.3 |
| 14 | Webhook Security & Mocks | SSRF prevention (`validate_url`), exponential backoff retries, and `pytest-httpx` local mocks | M3 | R2.3 |
| 15 | E2E Testing Suite | Opaque-box 4-tier test suite (Tiers 1-4) publishing `TEST_READY.md` | E2E Track | Verification |
| 16 | Final E2E Pass & Hardening | 100% passing E2E tests and Tier 5 adversarial coverage hardening | M4 | Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Production Deployment & CI/CD | Dockerfile fixes, docker-compose.prod.yml, deploy/k8s/, deploy/helm/, .github/workflows/ci.yml, health endpoints | none | PLANNED |
| M2 | Brand Templates & Multi-Format Exporters | CorporateTemplate schemas & presets, scorecard/metrics layouts, Executive PDF exporter, Interactive HTML viewer, API & UI | none | PLANNED |
| M3 | Webhook Notifications & Review Gates | Webhook models, Slack Block Kit & Teams Adaptive Cards, SSRF validation, storyline gate triggers, pytest-httpx suite | none | PLANNED |
| E2E | E2E Testing Track | Independent requirement-driven test suite (Tiers 1-4) covering all features, produces TEST_READY.md | none | IN_PROGRESS |
| M4 | Final Integration & Hardening | Phase 1: 100% E2E test pass (Tiers 1-4); Phase 2: Tier 5 adversarial coverage hardening | M1, M2, M3, E2E | PLANNED |

## Interface Contracts
### Presentation Engine ↔ API / Frontend
- `GET /api/projects/{project_id}/artifact`
  - Query params:
    - `format`: `"pptx"` | `"pdf"` | `"html"` (default: `"pptx"`)
    - `template`: `"mckinsey_navy"` | `"bcg_emerald"` | `"bain_crimson"` | `"goldman_slate"` | `"modern_tech"` (default: `"mckinsey_navy"`)
    - `view`: `"presentation"` | `"document"` (default: `"presentation"`, for HTML format)
  - Responses:
    - `pptx`: `media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"`, filename=`consulting_deck_{project_id}.pptx`
    - `pdf`: `media_type="application/pdf"`, filename=`executive_summary_{project_id}.pdf`
    - `html`: `media_type="text/html; charset=utf-8"`, filename=`consulting_deck_{project_id}.html`

### Webhook Dispatcher ↔ External Receivers
- Trigger event: `"slide_review_gate"` (when `StorylineGenerator.generate_storyline` creates slide storyline)
- Slack payload format: JSON object with `text` summary, `blocks` containing Header, Fields (Project, Total Slides, Audience, Gate Status), Storyline Summary, and Actions element with Button linking to `http://<host>/projects/{id}/storyline`.
- MS Teams payload format: JSON object with `type: "message"`, `attachments` containing AdaptiveCard 1.4, FactSet, and `Action.OpenUrl` linking to `http://<host>/projects/{id}/storyline`.
- Security requirement: All target URLs must pass `backend/app/core/security.py:validate_url` to prevent SSRF before HTTP dispatch.

## Code Layout
- `backend/app/schemas/template.py`: BrandPalette, FontSchema, CorporateTemplate Pydantic schemas.
- `backend/app/presentation/templates.py`: Built-in enterprise corporate templates.
- `backend/app/presentation/renderer.py`: PresentationRenderer with custom palette injection, scorecard & metrics layouts.
- `backend/app/presentation/pdf_exporter.py`: ExecutivePDFExporter (ReportLab Platypus, NumberedCanvas).
- `backend/app/presentation/html_viewer.py`: HTMLPresentationGenerator (standalone responsive viewer).
- `backend/app/notifications/`: Webhook payload builders, dispatcher, and service.
- `backend/app/api/webhooks.py`: Webhook subscription REST endpoints.
- `frontend/src/components/ExportModal.tsx`: Corporate theme & export format modal.
- `deploy/docker-compose.prod.yml`: Production compose specification.
- `deploy/k8s/`: Cloud-agnostic Kubernetes manifests (00-10).
- `deploy/helm/consulting-deck/`: Helm chart packaging.
- `.github/workflows/ci.yml`: GitHub Actions automation.
