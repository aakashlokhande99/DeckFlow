"""Asynchronous Webhook Dispatcher with SSRF validation and exponential backoff retries."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from typing import Any, Dict, Optional

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import validate_url
from app.db.models import WebhookDelivery

logger = structlog.get_logger(__name__)


class WebhookSSRFError(ValueError):
    """Raised when a webhook destination URL fails SSRF safety checks."""
    pass


class WebhookDispatcher:
    """Dispatches HTTP webhook notifications with SSRF validation, retries, and audit logging."""

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        client: Optional[httpx.AsyncClient] = None,
        max_attempts: int = 3,
        base_delay: float = 0.2,
    ) -> None:
        self.db = db
        self.client = client
        self.max_attempts = max_attempts
        self.base_delay = base_delay

    def validate_destination_url(self, url: str) -> str:
        """Validate URL against SSRF protection policies."""
        try:
            return validate_url(url)
        except ValueError as exc:
            logger.warning("webhook_ssrf_blocked", url=url, reason=str(exc))
            raise WebhookSSRFError(f"SSRF validation failed: {exc}") from exc

    async def dispatch(
        self,
        url: str,
        payload: Dict[str, Any],
        event_type: str = "slide_review_gate",
        subscription_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        secret: Optional[str] = None,
    ) -> WebhookDelivery:
        """Deliver webhook payload with SSRF validation and exponential backoff retries."""
        # 1. SSRF Validation
        validated_url = self.validate_destination_url(url)

        # 2. Prepare headers & signature
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Enterprise-AI-Consulting-Agent/1.0",
        }
        if secret:
            payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
            signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        # 3. HTTP Delivery loop with retries
        status_code: Optional[int] = None
        response_body: Optional[str] = None
        success = False
        attempt = 0

        async def _send_request(http_client: httpx.AsyncClient) -> None:
            nonlocal status_code, response_body, success, attempt
            for i in range(1, self.max_attempts + 1):
                attempt = i
                try:
                    resp = await http_client.post(
                        validated_url,
                        json=payload,
                        headers=headers,
                        timeout=10.0,
                    )
                    status_code = resp.status_code
                    response_body = resp.text[:2000] if resp.text else ""

                    if 200 <= resp.status_code < 300:
                        success = True
                        logger.info(
                            "webhook_dispatch_success",
                            url=validated_url,
                            status_code=status_code,
                            attempt=attempt,
                        )
                        break

                    # Retry only on 5xx server errors
                    if resp.status_code >= 500 and i < self.max_attempts:
                        delay = self.base_delay * (2 ** (i - 1))
                        logger.warning(
                            "webhook_server_error_retry",
                            url=validated_url,
                            status_code=status_code,
                            attempt=attempt,
                            next_delay=delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            "webhook_dispatch_rejected",
                            url=validated_url,
                            status_code=status_code,
                            attempt=attempt,
                        )
                        break

                except httpx.TransportError as exc:
                    response_body = f"{type(exc).__name__}: {str(exc)}"
                    status_code = None
                    if i < self.max_attempts:
                        delay = self.base_delay * (2 ** (i - 1))
                        logger.warning(
                            "webhook_transport_error_retry",
                            url=validated_url,
                            error=str(exc),
                            attempt=attempt,
                            next_delay=delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "webhook_transport_error_final",
                            url=validated_url,
                            error=str(exc),
                            attempt=attempt,
                        )

        if self.client is not None:
            await _send_request(self.client)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await _send_request(client)

        # 4. Record delivery in DB
        delivery = WebhookDelivery(
            id=uuid.uuid4(),
            subscription_id=subscription_id,
            project_id=project_id,
            event_type=event_type,
            payload=payload,
            status_code=status_code,
            response_body=response_body,
            attempt_count=attempt,
            success=success,
        )

        if self.db is not None:
            try:
                self.db.add(delivery)
                await self.db.commit()
            except Exception as exc:
                logger.warning("webhook_delivery_db_record_failed", error=str(exc))
                try:
                    await self.db.rollback()
                except Exception:
                    pass

        return delivery
