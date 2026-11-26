"""FastAPI application entry point for AI Consulting Workflow."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: configure logging and event bus then yield."""
    configure_logging()
    logger.info(
        "startup",
        environment=settings.ENVIRONMENT,
        version="0.1.0",
    )
    # Initialize Redis event bus if available
    from app.core.events import event_bus
    await event_bus.init_redis(settings.REDIS_URL)

    yield
    logger.info("shutdown")


app = FastAPI(
    title="AI Consulting Workflow API",
    version="0.1.0",
    description="Research-to-presentation pipeline with explicit human approval gates.",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
if settings.ENVIRONMENT == "development":
    allowed_origins = ["*"]
else:
    allowed_origins = getattr(settings, "ALLOWED_ORIGINS", [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inject enterprise hardening security response headers."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.api.health import router as health_router  # noqa: E402
from app.api.projects import router as projects_router  # noqa: E402
from app.api.webhooks import router as webhooks_router  # noqa: E402
from app.api.ws import router as ws_router  # noqa: E402

app.include_router(health_router, prefix="/api")
app.include_router(health_router, prefix="")
app.include_router(projects_router, prefix="/api/projects")
app.include_router(webhooks_router, prefix="/api")
app.include_router(ws_router, prefix="/api")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.warning("validation_error", detail=exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )
