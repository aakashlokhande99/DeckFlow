# E2E Test Infra: Enterprise AI Consulting Deck Generator (Track D & Phase 3)

## Test Philosophy
- **Opaque-box & Requirement-driven**: All test cases test the system strictly against the requirements defined in `ORIGINAL_REQUEST.md` and interfaces in `PROJECT.md`. Tests interact with the system via HTTP endpoints (`httpx.AsyncClient` ASGI transport), CLI/file specifications (PyYAML verification for K8s/Helm/Compose/CI), and binary/document output inspection (ReportLab PDF stream headers, python-pptx presentation inspection, HTML DOM validation).
- **Zero dependency on internal implementation private methods**: Tests do not mock or depend on internal function details; they assert public interfaces, contracts, schemas, headers, status codes, and output artifacts.
- **Methodology**: Systematic 4-tier design:
  - **Tier 1: Feature Coverage (>=5 per feature)**: Isolated happy-path verification of all 14 features across Track D and Phase 3.
  - **Tier 2: Boundary & Corner Cases (>=5 per feature)**: Edge cases, invalid inputs, hex code validation, missing parameters, enum limits, SSRF boundaries, and structural syntax limits.
  - **Tier 3: Cross-Feature Interactions (Pairwise)**: Tests exercising multiple features together (e.g. Corporate Templates with Scorecard/Metrics layouts in PPTX, PDF, and HTML; Webhook subscriptions triggered by Storyline review gate with SSRF protection; Helm chart values overriding K8s probe paths).
  - **Tier 4: Real-World Application Scenarios**: Multi-feature end-to-end consulting deck workflows (e.g., full lifecycle from research approval to multi-template export across McKinsey, BCG, and Bain, triggering Slack Block Kit and MS Teams Adaptive Card notifications with full delivery logging).

## Feature Inventory & Test Coverage Matrix
| # | Feature | Source (Requirement) | Tier 1 (Happy) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|----------------------|:--------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | Production Compose | R1.1 (`deploy/docker-compose.prod.yml`) | 5 | 5 | ✓ | ✓ |
| 2 | Dockerfile Hardening | R1.1 (`backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore`) | 5 | 5 | ✓ | ✓ |
| 3 | Cloud-Agnostic K8s | R1.2 (`deploy/k8s/` 00-namespace to 10-hpa) | 5 | 5 | ✓ | ✓ |
| 4 | Helm Packaging | R1.2 (`deploy/helm/consulting-deck/`) | 5 | 5 | ✓ | ✓ |
| 5 | CI/CD Automation | R1.3 (`.github/workflows/ci.yml`) | 5 | 5 | ✓ | ✓ |
| 6 | Health Probe Fixes | R1.4 (`/api/health`, `/health`, probes) | 5 | 5 | ✓ | ✓ |
| 7 | Corporate Templates | R2.1 (5 presets: McKinsey, BCG, Bain, Goldman, Tech) | 5 | 5 | ✓ | ✓ |
| 8 | New Layout Schemas | R2.1 (`scorecard`, `metrics` layouts) | 5 | 5 | ✓ | ✓ |
| 9 | Executive PDF Exporter | R2.2 (ReportLab Platypus, NumberedCanvas) | 5 | 5 | ✓ | ✓ |
| 10 | Interactive HTML Viewer | R2.2 (Standalone HTML presentation viewer) | 5 | 5 | ✓ | ✓ |
| 11 | Multi-Format Export API | R2.2 (`GET /api/projects/{id}/artifact`) | 5 | 5 | ✓ | ✓ |
| 12 | External Webhooks | R2.3 (Slack Block Kit & MS Teams Adaptive Cards) | 5 | 5 | ✓ | ✓ |
| 13 | Review Gate Triggers | R2.3 (Slide storyline review gate dispatch) | 5 | 5 | ✓ | ✓ |
| 14 | Webhook Security & Mocks | R2.3 (SSRF validation `validate_url`, retries) | 5 | 5 | ✓ | ✓ |
| **Total** | **14 Features** | | **70** | **70** | **14** | **8** |

Total Planned Test Cases: **162** tests.

## Test Architecture
- **Location**: `backend/tests/e2e/`
  - `backend/tests/e2e/__init__.py`
  - `backend/tests/e2e/conftest.py`: Shared E2E fixtures (in-memory DB, AsyncClient, sample project seeders, webhook receivers mock).
  - `backend/tests/e2e/test_tier1_features.py`: Tier 1 Feature Coverage tests (70 tests across 14 features).
  - `backend/tests/e2e/test_tier2_boundaries.py`: Tier 2 Boundary & Corner Case tests (70 tests across 14 features).
  - `backend/tests/e2e/test_tier3_pairwise.py`: Tier 3 Cross-Feature Combination tests (14 tests).
  - `backend/tests/e2e/test_tier4_scenarios.py`: Tier 4 Real-World Application Scenarios (8 tests).
- **Test Runner Invocation**:
  ```bash
  python -m pytest backend/tests/e2e -v
  ```
- **Pass/Fail Semantics**: All tests must pass with exit code 0. Zero warnings treated as failures if deprecations occur.
- **Fixture Isolation**:
  - In-memory SQLite with PostgreSQL dialect compatibility for deterministic, fast database operations.
  - `pytest-httpx` intercepts all external webhook requests deterministically.
  - Temp directory isolation for all generated export files.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Lifecycle: Strategy Deck Generation to McKinsey PPTX with Scorecard & Metrics | F7, F8, F11 | High |
| 2 | Executive Memo Workflow: BCG Emerald PDF Export with Numbered Canvas & Multi-Page | F7, F9, F11 | High |
| 3 | Interactive Client Portal: Bain Crimson HTML Presentation Viewer with Keyboard Nav | F7, F10, F11 | High |
| 4 | Enterprise Slack Notification Flow on Slide Review Gate Arrival with Block Kit Actions | F12, F13, F14 | High |
| 5 | Enterprise MS Teams Notification Flow on Review Gate Arrival with Adaptive Card 1.4 | F12, F13, F14 | High |
| 6 | Multi-Channel Alerting & Resilient Webhook Retry on Transient Network Failure | F12, F13, F14 | High |
| 7 | Full Enterprise Multi-Format Export Bundle (PPTX + PDF + HTML) for Goldman Sachs Theme | F7, F8, F9, F10, F11 | High |
| 8 | Cloud Deployment Verification: Compose + K8s Probes + Helm Chart + CI Pipeline Matrix | F1, F2, F3, F4, F5, F6 | High |

## Coverage Thresholds
- Tier 1: >= 5 tests per feature (70 tests)
- Tier 2: >= 5 tests per feature (70 tests)
- Tier 3: >= 14 pairwise cross-feature tests
- Tier 4: >= 8 realistic enterprise application scenarios
- **Overall Target**: >= 162 total test cases with 100% pass rate.
