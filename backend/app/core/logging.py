"""Structlog configuration for the AI Consulting Workflow backend.

Usage
-----
Call ``configure_logging()`` once during application startup (inside the
FastAPI lifespan function).  After that, obtain loggers with::

    import structlog
    logger = structlog.get_logger(__name__)

Bound variables
---------------
Callers can attach per-request context with::

    structlog.contextvars.bind_contextvars(
        project_id=str(project.id),
        workflow_run_id=str(run.id),
        node_name="synthesis",
    )
    structlog.contextvars.clear_contextvars()   # at request end
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Set up structlog and the standard-library logging bridge."""

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.ENVIRONMENT == "production":
        # JSON output for log aggregation (Datadog, Cloud Logging, etc.)
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Pretty colored console output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
