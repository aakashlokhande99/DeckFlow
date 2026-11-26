"""Celery background worker application and async task definitions."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path
import structlog
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Project
from app.workflow.graph import create_research_graph
from app.workflow.state import ResearchWorkflowState

logger = structlog.get_logger(__name__)

# Use NullPool in worker to prevent connection sharing across different asyncio event loops
worker_engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=settings.ENVIRONMENT == "development",
)
WorkerSessionLocal = async_sessionmaker(
    worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Initialize Celery app
celery_app = Celery(
    "consulting_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "cleanup-artifacts-daily": {
            "task": "tasks.cleanup_old_artifacts",
            "schedule": crontab(hour=0, minute=0),
        },
    },
)


async def _async_execute_research(project_id_str: str) -> dict:
    """Async routine to load project, execute research graph, and update state."""
    project_id = uuid.UUID(project_id_str)

    async with WorkerSessionLocal() as session:
        stmt = select(Project).where(Project.id == project_id)
        project = (await session.execute(stmt)).scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id_str} not found in database.")

        project.status = "running"
        project.workflow_run_id = str(uuid.uuid4())
        await session.commit()

        initial_state: ResearchWorkflowState = {
            "project_id": project_id_str,
            "topic": project.topic,
            "objective": project.objective,
            "audience": project.audience or "Executive Leadership",
            "geography": project.geography or "Global",
            "time_horizon": project.time_horizon or "2025-2030",
            "additional_context": project.additional_context or "",
            "research_depth": project.research_depth,
            "workflow_run_id": project.workflow_run_id,
            "status": "running",
            "errors": [],
        }

    graph = create_research_graph()
    thread_config = {"configurable": {"thread_id": project_id_str}}

    try:
        final_state = await graph.ainvoke(initial_state, config=thread_config)
        logger.info("research_workflow_completed", project_id=project_id_str)
        return final_state
    except Exception as exc:
        logger.error("research_workflow_failed", project_id=project_id_str, error=str(exc))
        async with WorkerSessionLocal() as session:
            stmt = select(Project).where(Project.id == project_id)
            proj = (await session.execute(stmt)).scalar_one_or_none()
            if proj:
                proj.status = "failed"
                proj.error_message = str(exc)
                await session.commit()
        raise


@celery_app.task(name="tasks.execute_research_workflow", bind=True)
def execute_research_workflow(self, project_id: str) -> dict:
    """Celery synchronous entrypoint wrapping the async research workflow."""
    logger.info("celery_task_started", task_id=self.request.id, project_id=project_id)
    return asyncio.run(_async_execute_research(project_id))


@celery_app.task(name="tasks.cleanup_old_artifacts")
def cleanup_old_artifacts(retention_days: int | None = None) -> dict:
    """Scan the artifacts directory and purge files exceeding the retention threshold."""
    days = retention_days if retention_days is not None else settings.ARTIFACT_RETENTION_DAYS
    cutoff_time = time.time() - (days * 86400)
    
    # Try multiple common paths for artifacts directory
    potential_dirs = [
        Path("artifacts"),
        Path(__file__).resolve().parent.parent.parent / "artifacts",
        Path.cwd() / "artifacts",
    ]
    
    target_dir: Path | None = None
    for d in potential_dirs:
        if d.is_dir():
            target_dir = d
            break
            
    if target_dir is None:
        logger.info("artifact_cleanup_skipped_no_directory")
        return {"deleted_count": 0, "status": "directory_not_found"}
        
    deleted_count = 0
    errors = []
    
    for item in target_dir.iterdir():
        if item.is_file() and item.suffix.lower() in {".pptx", ".pdf", ".html"}:
            try:
                mtime = item.stat().st_mtime
                if mtime < cutoff_time:
                    item.unlink()
                    deleted_count += 1
            except Exception as exc:
                errors.append(f"{item.name}: {str(exc)}")
                
    logger.info(
        "artifact_cleanup_completed",
        deleted_count=deleted_count,
        retention_days=days,
        errors=len(errors),
    )
    return {
        "deleted_count": deleted_count,
        "retention_days": days,
        "errors": errors,
        "status": "success",
    }

