# Enterprise AI Consulting Agent - Backend

FastAPI asynchronous backend powering the Enterprise Consulting Deck Generator.

## Architecture
- **Framework**: FastAPI (Python 3.11+)
- **ORM / Database**: SQLAlchemy 2.0 (asyncio) + PostgreSQL + asyncpg
- **Task Queue**: Celery 5.4 + Redis 7.0
- **Multi-Agent Orchestration**: LangGraph
- **Deck Generation**: python-pptx, ReportLab (PDF), Standalone Interactive HTML
