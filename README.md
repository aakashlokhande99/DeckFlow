# AI Consulting Workflow Platform

> **An enterprise research-to-presentation platform with strict human-in-the-loop approval gates.**  
> Translates strategic client briefs into empirical web research, evidence-grounded consulting synthesis, and executive-ready deliverables (`.pptx`, `.pdf`, `.html`).

---

## 1. What Is This Project?

The **AI Consulting Workflow Platform** is a full-stack, multi-agent research and presentation engineering system built with **FastAPI**, **LangGraph**, **Celery**, **PostgreSQL**, **Redis**, and **Next.js 14**.

Given a structured consulting brief (client problem statement, industry, target audience, strategic objectives, and optional boundaries), the platform:
1. **Plans** a targeted set of research questions.
2. **Searches & Fetches** live web sources (HTML pages and PDFs) through an SSRF-hardened fetcher.
3. **Extracts & Ground-Truths** atomic `EvidenceClaim` records linked to canonicalized `Source` URLs with SHA-256 content hashes.
4. **Synthesizes** a structured consulting dossier (Executive Summary, Findings, Implications, Recommendations, Risks, and Gaps) using an automated **5-point Synthesis Quality Gate**.
5. **Pauses at a Mandatory Human Review Gate**, notifying reviewers in the UI and via Slack/MS Teams webhooks so a human can inspect every citation and choose to **Approve**, **Revise**, or **Research More**.
6. **Generates & Exports** an editable 8–12 slide storyline into **Widescreen 16:9 PowerPoint (`.pptx`)**, **Executive Summary PDF (`.pdf`)**, or **Standalone Interactive HTML (`.html`)** across 5 corporate brand templates.

---

## 2. Why Is It Needed & What Is the Impact?

Management consulting and strategy teams spend a disproportionate share of engagement hours on repetitive, manual preparation before high-value partner/client discussions can happen:
- **Manual desk research & source verification:** Searching across industry reports, PDFs, and news, deduplicating links, and tracking where each number came from.
- **Synthesis & QA:** Structuring raw notes into MECE-style findings, implications, and prioritized recommendations while ensuring no claim goes uncited.
- **Deck formatting & multi-format packaging:** Translating a storyline into branded 16:9 slides, executive leave-behind PDFs, and interactive viewers.

### Typical Time-Savings Impact
| Workflow Phase | Traditional Manual Effort | With AI Consulting Platform | Estimated Time Saved |
| :--- | :--- | :--- | :--- |
| **Desk Research & Source Extraction** | 4–8 hours per brief | 2–5 minutes (automated search, fetch, & claim extraction) | **~85–90%** |
| **Synthesis & Citation Audit** | 3–5 hours of structuring & cross-checking | 10–15 minutes (automated draft + 5-point QA + human review) | **~80–85%** |
| **Slide Storyline & Deck Formatting** | 4–6 hours in PowerPoint / PDF layout | < 2 minutes (storyline studio + 1-click `.pptx`/`.pdf`/`.html` export) | **~90%+** |
| **End-to-End First-Draft Turnaround** | **1.5–2.5 workdays** | **~20–30 minutes** (including human review) | **~10–15+ hours saved per deck** |

*(Note: Estimates reflect typical single-brief consulting analyst workflows; actual savings vary by topic complexity and depth of human revision cycles.)*

---

## 3. Complex Issues Resolved & How

Building a production-grade AI workflow that produces auditable executive deliverables—rather than unverified LLM prose—required solving several non-trivial engineering challenges:

1. **Preventing LLM Hallucinations & Unverifiable Claims**
   - **Problem:** LLMs frequently invent statistics or cite non-existent sources when synthesizing broad web research.
   - **Solution:** Implemented deterministic `EvidenceClaim` registration (`app/research/evidence_builder.py`) tied to canonicalized `Source` records (`app/research/url_utils.py`) with SHA-256 content hashes. Every material finding must reference valid `evidence_ids`, enforced by both `SynthesisQualityGate` and `GroundingEvaluator` before human review, plus a hard **HTTP 400 gate** blocking storyline/deck generation until `insight.is_approved == True`.

2. **SSRF & Open-Redirect Vulnerabilities in Autonomous Web Fetching and Webhooks**
   - **Problem:** An autonomous research agent and user-configured webhook system both make outbound HTTP requests to untrusted URLs, creating Server-Side Request Forgery (SSRF) risks against internal networks and cloud metadata endpoints (`169.254.169.254`).
   - **Solution:** Built `app/core/security.py` (`validate_url` / `is_safe_url`) and `SafeFetcher` (`app/research/safe_fetcher.py`) to block loopback, RFC 1918 private subnets, link-local/metadata IPs, and non-HTTP(S) schemes. DNS resolution is checked via `socket.getaddrinfo`, redirects are disabled at the HTTP client level and manually re-validated at every hop (up to 5 redirects), and downloads are capped at 5 MB and 50 PDF pages.

3. **Human-in-the-Loop Pause/Resume Across Async API, Celery Workers, and LangGraph**
   - **Problem:** Long-running research cannot block HTTP requests, yet the workflow must pause cleanly for human inspection and resume from the exact state based on the reviewer's decision (`approve`, `revise`, or `research_more`).
   - **Solution:** Coupled a 8-node LangGraph `StateGraph` (`interrupt_before=["human_review"]`) with Celery background tasks (`app/worker.py`), PostgreSQL persistence, and a Redis pub/sub event bus (`app/core/events.py`) streaming live progress over WebSockets (`/api/ws/projects/{project_id}`).

4. **Cross-Database Portability Between PostgreSQL (Prod) and SQLite (Tests)**
   - **Problem:** Production uses PostgreSQL `ARRAY` columns via `asyncpg`, while fast isolated E2E tests use in-memory SQLite.
   - **Solution:** Implemented a custom SQLAlchemy `StringArray` `TypeDecorator` in `app/db/models.py` that transparently maps to native PostgreSQL arrays in production and JSON-serialized text in SQLite.

5. **Multi-Format Executive Rendering with Brand Consistency**
   - **Problem:** Supporting 10 consulting slide layouts (`title`, `executive_summary`, `two_column`, `three_insight`, `comparison`, `roadmap`, `risk_matrix`, `scorecard`, `metrics`, `closing`) across 5 corporate brand palettes (`mckinsey_navy`, `bcg_emerald`, `bain_crimson`, `goldman_slate`, `modern_tech`) and 3 output formats.
   - **Solution:** Created a unified `CorporateTemplate` schema (`app/schemas/template.py`) consumed by `PresentationRenderer` (`python-pptx`), `ExecutivePDFExporter` (`ReportLab Platypus` with two-pass `NumberedCanvas`), and `HTMLPresentationGenerator` (standalone single-file viewer with keyboard navigation, speaker notes, and overview grid).

---

## 4. Architecture

### System Overview

![System Architecture](docs/architecture.jpg)

### LangGraph Workflow State Machine (`backend/app/workflow/graph.py`)
1. `validate_brief` → Validates brief inputs (routes to `END` on validation errors).
2. `plan_research` → Generates structured `ResearchPlan` questions.
3. `search_sources` → Queries configured search provider (`serpapi` or `mock`).
4. `fetch_and_extract` → Downloads HTML/PDF via `SafeFetcher`, canonicalizes URLs, computes SHA-256 hashes, and extracts text.
5. `build_evidence` → Registers atomic `EvidenceClaim` records linked to `Source` IDs.
6. `synthesize` → Produces `ConsultingSynthesis` using configured LLM (`gemini`, `openai`, or `mock`).
7. `quality_gate` → Runs the 5-point `SynthesisQualityGate`.
8. `human_review` → Pauses (`interrupt_before=["human_review"]`) and dispatches Slack Block Kit / MS Teams Adaptive Card alerts. Reviewer decision routes to `END` (`approve`), `synthesize` (`revise`), or `search_sources` (`research_more`).

---

## 5. Steps to Recreate This Project

### Prerequisites
- **Python:** 3.11+
- **Node.js:** 18+ or 20 LTS
- **Docker & Docker Compose:** v2+ (recommended for full stack)
- **PostgreSQL 16** and **Redis 7** (if running locally without Docker)

### 1. Clone & Configure Environment
```bash
git clone <your-repo-url>
cd "Consulting agent"
cp .env.example .env
```

Edit `.env` with your credentials (or use `mock` providers for offline/local testing):
```ini
DATABASE_URL=postgresql+asyncpg://consulting:consulting@localhost:5432/consulting_db
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
SECRET_KEY=replace-with-a-secure-random-32-plus-char-key

# AI & Search Providers (gemini | openai | mock, serpapi | mock)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
SEARCH_PROVIDER=serpapi
SERPAPI_KEY=your-serpapi-key

# Optional Observability
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 2. Option A: Run Full Stack with Docker Compose
```bash
docker-compose up --build
```
- **Frontend UI:** `http://localhost:3000`
- **Backend API:** `http://localhost:8000`
- **Swagger / OpenAPI Docs:** `http://localhost:8000/docs`
- *(Note: `docker-compose.yml` exposes Postgres on host port `5433` and Redis on `6380` to avoid local port collisions.)*

For production-hardened containers, Kubernetes manifests, and Helm charts, see [`deploy/docker-compose.prod.yml`](deploy/docker-compose.prod.yml), [`deploy/k8s/`](deploy/k8s/), and [`deploy/helm/consulting-deck/`](deploy/helm/consulting-deck/).

### 3. Option B: Local Development (Without Docker for App Processes)

**Backend API:**
```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Celery Worker** (in a separate terminal):
```bash
cd backend
celery -A app.worker worker --loglevel=info --concurrency=2
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### 4. Verify with Tests & Builds
```bash
# Backend test suite (unit, integration, 4-tier opaque-box E2E, acceptance)
python -m pytest backend/tests -v

# Frontend typecheck & production build
cd frontend
npm run typecheck
npm run build
```

---

## 6. How AI Evaluation & Observability Work

### Automated Quality Gate (`backend/app/research/quality_gate.py`)
Before any synthesis reaches a human reviewer, `SynthesisQualityGate` evaluates 5 deterministic checks and produces a `QACheckResult`:
1. **Citation Completeness (40% weight, min 80%):** Verifies findings cite `evidence_ids`.
2. **Research Question Coverage (35% weight, min 70%):** Token-overlap check ensuring `ResearchPlan` questions are addressed.
3. **Recommendation Actionability (25% weight, min 75%):** Ensures recommendations include concrete actions (≥15 chars), timeframes, and priorities (`high`/`medium`/`low`).
4. **Contradiction Detection:** Flags conflicting `EvidenceClaim` items and risk statements.
5. **Duplicate Finding Detection:** Computes pairwise Jaccard similarity across findings and fails the gate if any pair shares >70% vocabulary.

### Quantitative Grounding & Regression Suite (`backend/app/evaluation/`)
- **`GroundingEvaluator` (`grounding_eval.py`):** Computes an `EvaluationScoreCard` across 4 pillars:
  - `grounding_score` (40% weight, default min `0.85`): Verifies every non-uncertain finding references real `valid_evidence_ids` (catches hallucinated IDs).
  - `citation_coverage` (25% weight, default min `0.80`): Fraction of research questions covered (with consulting acronym expansion such as `capex`, `opex`, `cagr`, `smr`, `ev`).
  - `completeness_score` (25% weight, default min `0.90`): Checks presence of all 6 mandatory consulting sections.
  - `schema_conformance` (10% weight, default min `1.0`): Strict Pydantic `ConsultingSynthesis` validation.
- **`RegressionRunner` (`regression_runner.py`):** Runs benchmark `EvaluationTestCase` suites and raises `EvaluationRegressionError` if any case drops below release thresholds.

### Observability & Tracing (`backend/app/observability/langfuse.py`)
- **`ObservabilityTracer`:** Provides a `@contextlib.contextmanager` `span(...)` wrapper for LLM, tool, chain, and workflow executions.
- Captures **latency (ms)**, **input/output token counts**, **estimated USD cost**, **status (`success` | `error`)**, and **project metadata**.
- Emits structured JSON logs via `structlog` (`trace_recorded`) and supports Langfuse credentials (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`).

---

## 7. AI & Application Security Measures

- **Mandatory Human-in-the-Loop Gate:** No storyline or presentation artifact can be generated or downloaded until `insight.is_approved == True`; unapproved requests are rejected with `HTTP 400 Bad Request`.
- **SSRF & DNS-Rebinding Defense (`app/core/security.py`, `app/research/safe_fetcher.py`):**
  - Restricts schemes strictly to `http` and `https`.
  - Blocks loopback (`127.0.0.0/8`, `::1`), RFC 1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local / cloud metadata endpoints (`169.254.169.254`, `fd00:ec2::254`, `metadata.google.internal`), multicast, and reserved IPv4/IPv6 ranges.
  - Resolves hostnames via `socket.getaddrinfo` and rejects if **any** resolved IP is blocked or resolution fails.
  - Disables automatic HTTP redirects and re-validates every `Location` header target (max 5 hops).
- **Resource & Parser Safeguards:** `SafeFetcher` enforces a 12s timeout, 5 MB max response size, and strict `ALLOWED_CONTENT_TYPES` (`text/html`, `application/pdf`, `text/plain`, `application/xhtml+xml`); PDF extraction is capped at 50 pages.
- **Webhook Security (`app/notifications/dispatcher.py`):** Validates every registered webhook URL against SSRF rules before saving and before dispatching, retries with exponential backoff, logs deliveries to `webhook_deliveries`, and signs payloads with **HMAC-SHA256** (`X-Webhook-Signature: sha256=...`) when a secret is provided.
- **HTTP Hardening & Secret Handling (`app/main.py`, `app/core/config.py`):**
  - Security response headers middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin`.
  - All API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `SERPAPI_KEY`, `LANGFUSE_*`) are stored as Pydantic `SecretStr` to prevent accidental exposure in logs.

---

## 8. Future Scope (Room for Improvement)

1. **Multi-Tenant Authentication & RBAC:** Add organization-scoped JWT authentication and role-based access control (`admin`, `reviewer`, `consultant`, `viewer`) on API routes and WebSocket connections.
2. **Durable LangGraph Checkpointing:** Replace the in-memory `MemorySaver` checkpointer in `create_research_graph` with a persistent PostgreSQL-backed LangGraph checkpointer so paused human-review workflows survive worker restarts.
3. **Full Langfuse SDK Span Export & LLM-as-a-Judge:** Forward `ObservabilityTracer` spans directly to Langfuse Cloud/self-hosted traces and augment token-overlap checks with semantic NLI / LLM-as-a-judge claim verification.
4. **Native Data Charts & Document Ingestion:** Allow users to upload proprietary PDFs, spreadsheets, or memos into the evidence pipeline and render native `python-pptx` / SVG charts (bar, waterfall, line) from extracted numerical series.
5. **Egress Proxy & DNS Pinning:** Route `SafeFetcher` and `WebhookDispatcher` traffic through a dedicated network egress proxy or pin resolved IPs at connection time to eliminate residual TOCTOU DNS-rebinding windows.
