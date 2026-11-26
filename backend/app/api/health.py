"""FastAPI health-check endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("/health")
async def health() -> dict:
    """Basic liveness check."""
    return {"status": "ok", "version": "0.1.0", "environment": settings.ENVIRONMENT}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Database connectivity check."""
    try:
        await db.execute(text("SELECT 1"))
        return JSONResponse(content={"status": "ok", "database": "connected"})
    except Exception as exc:
        logger.error("db_health_check_failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unreachable"},
        )
