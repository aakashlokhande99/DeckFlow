"""Observability, telemetry, and tracing module for LLM and workflow operations.

Instruments execution traces, latency (ms), token usage estimations, and cost tracking
with support for Langfuse / LangSmith export and structured logging fallback.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, Dict, Iterator, List, Optional
import structlog
from pydantic import BaseModel, Field

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Standard pricing model ($ per 1M tokens) - GPT-4o reference
COST_PER_M_INPUT_TOKENS = 2.50
COST_PER_M_OUTPUT_TOKENS = 10.00


class TraceRecord(BaseModel):
    """In-memory audit record for an executed operation span."""

    name: str
    run_type: str = "llm"  # llm | tool | chain | workflow
    project_id: Optional[str] = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    status: str = "success"  # success | error
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObservabilityTracer:
    """Singleton tracer managing observability spans and audit records."""

    def __init__(self) -> None:
        self._traces: List[TraceRecord] = []

    def record_trace(self, record: TraceRecord) -> None:
        """Store trace record in memory and emit structured log."""
        self._traces.append(record)
        logger.info(
            "trace_recorded",
            span_name=record.name,
            run_type=record.run_type,
            latency_ms=round(record.latency_ms, 2),
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cost_usd=round(record.estimated_cost_usd, 6),
            status=record.status,
            project_id=record.project_id,
        )

    def get_recent_traces(self, limit: int = 100) -> List[TraceRecord]:
        """Return recently recorded traces."""
        return self._traces[-limit:]

    def clear(self) -> None:
        """Clear recorded traces (useful for test resets)."""
        self._traces.clear()

    @contextlib.contextmanager
    def span(
        self,
        name: str,
        run_type: str = "workflow",
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        prompt_text: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Context manager measuring latency, tokens, cost, and status of a block."""
        start_time = time.perf_counter()
        span_ctx: Dict[str, Any] = {
            "name": name,
            "input_tokens": len(prompt_text or "") // 4 if prompt_text else 0,
            "output_tokens": 0,
            "output_text": "",
            "metadata": metadata or {},
        }
        status = "success"
        error_msg: Optional[str] = None

        try:
            yield span_ctx
        except Exception as exc:
            status = "error"
            error_msg = str(exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            out_tokens = span_ctx["output_tokens"]
            if not out_tokens and span_ctx["output_text"]:
                out_tokens = len(span_ctx["output_text"]) // 4

            in_tokens = span_ctx["input_tokens"]
            cost = (
                (in_tokens * COST_PER_M_INPUT_TOKENS / 1_000_000.0)
                + (out_tokens * COST_PER_M_OUTPUT_TOKENS / 1_000_000.0)
            )

            record = TraceRecord(
                name=name,
                run_type=run_type,
                project_id=project_id,
                latency_ms=latency_ms,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                estimated_cost_usd=cost,
                status=status,
                error_message=error_msg,
                metadata=span_ctx["metadata"],
            )
            self.record_trace(record)


# Global tracer instance
tracer = ObservabilityTracer()
