"""Webhook notification service coordinating alert dispatching across DB subscriptions and environment URLs."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any, Dict, List, Optional, Union

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import WebhookDelivery, WebhookSubscription
import app.db.session as db_session_module
from app.notifications.dispatcher import WebhookDispatcher
from app.notifications.payloads import (
    build_generic_payload,
    build_slack_slide_review_payload,
    build_slack_synthesis_review_payload,
    build_teams_slide_review_payload,
    build_teams_synthesis_review_payload,
)

logger = structlog.get_logger(__name__)


class WebhookService:
    """Orchestrates delivery of review gate alerts to configured endpoints."""

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        dispatcher: Optional[WebhookDispatcher] = None,
        enable_in_tests: bool = False,
    ) -> None:
        self.db = db
        self.dispatcher = dispatcher or WebhookDispatcher(db=db)
        self.enable_in_tests = enable_in_tests

    async def _get_active_subscriptions(
        self,
        event_type: str,
        project_id: Optional[uuid.UUID] = None,
        session: Optional[AsyncSession] = None,
    ) -> List[WebhookSubscription]:
        """Fetch active webhook subscriptions interested in the given event."""
        s = session or self.db
        if s is None:
            return []

        stmt = select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True))
        if project_id:
            stmt = stmt.where(
                or_(
                    WebhookSubscription.project_id == project_id,
                    WebhookSubscription.project_id.is_(None),
                )
            )

        result = await s.execute(stmt)
        all_subs = result.scalars().all()

        # Filter by subscribed events
        matched: List[WebhookSubscription] = []
        for sub in all_subs:
            events = sub.events or []
            if event_type in events or "*" in events:
                matched.append(sub)

        return matched

    async def dispatch_slide_review_gate(
        self,
        project_id: Union[str, uuid.UUID],
        topic: str,
        audience: str,
        total_slides: int,
        slide_summary: Union[str, List[Any]],
        session: Optional[AsyncSession] = None,
    ) -> List[WebhookDelivery]:
        """Dispatch slide review gate alerts to all configured webhooks."""
        pid = uuid.UUID(str(project_id))
        review_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/projects/{pid}/storyline"
        deliveries: List[WebhookDelivery] = []

        # 1. Fetch DB subscriptions
        subs: List[WebhookSubscription] = []
        active_session = session or self.db
        if active_session is not None:
            try:
                subs = await self._get_active_subscriptions(
                    event_type="slide_review_gate",
                    project_id=pid,
                    session=active_session,
                )
            except Exception as exc:
                logger.warning("webhook_fetch_subscriptions_failed", error=str(exc))

        # 2. Build payloads cache
        slack_payload = build_slack_slide_review_payload(
            project_id=pid,
            topic=topic,
            audience=audience,
            total_slides=total_slides,
            slide_summary=slide_summary,
            review_url=review_url,
        )
        teams_payload = build_teams_slide_review_payload(
            project_id=pid,
            topic=topic,
            audience=audience,
            total_slides=total_slides,
            slide_summary=slide_summary,
            review_url=review_url,
        )
        generic_payload = build_generic_payload(
            event_type="slide_review_gate",
            project_id=pid,
            data={
                "topic": topic,
                "audience": audience,
                "total_slides": total_slides,
                "review_url": review_url,
            },
        )

        # 3. Dispatch to DB subscriptions — reuse self.dispatcher so test mocks remain valid;
        #    update its db session reference if a session was supplied.
        dispatcher = self.dispatcher
        if session is not None and hasattr(dispatcher, "db"):
            dispatcher.db = session

        for sub in subs:
            payload = generic_payload
            if sub.target_type == "slack":
                payload = slack_payload
            elif sub.target_type == "teams":
                payload = teams_payload

            try:
                delivery = await dispatcher.dispatch(
                    url=sub.url,
                    payload=payload,
                    event_type="slide_review_gate",
                    subscription_id=sub.id,
                    project_id=pid,
                    secret=sub.secret,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("webhook_dispatch_failed", sub_id=str(sub.id), url=sub.url, error=str(exc))

        # 4. Dispatch to environment URLs if configured
        if settings.SLACK_WEBHOOK_URL:
            try:
                delivery = await dispatcher.dispatch(
                    url=settings.SLACK_WEBHOOK_URL,
                    payload=slack_payload,
                    event_type="slide_review_gate",
                    project_id=pid,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("env_slack_webhook_failed", url=settings.SLACK_WEBHOOK_URL, error=str(exc))

        if settings.TEAMS_WEBHOOK_URL:
            try:
                delivery = await dispatcher.dispatch(
                    url=settings.TEAMS_WEBHOOK_URL,
                    payload=teams_payload,
                    event_type="slide_review_gate",
                    project_id=pid,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("env_teams_webhook_failed", url=settings.TEAMS_WEBHOOK_URL, error=str(exc))

        return deliveries

    async def dispatch_synthesis_review_gate(
        self,
        project_id: Union[str, uuid.UUID],
        topic: str,
        audience: str,
        qa_summary: str,
        session: Optional[AsyncSession] = None,
    ) -> List[WebhookDelivery]:
        """Dispatch synthesis review gate alerts to all configured webhooks."""
        pid = uuid.UUID(str(project_id))
        review_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/projects/{pid}/review"
        deliveries: List[WebhookDelivery] = []

        # 1. Fetch DB subscriptions
        subs: List[WebhookSubscription] = []
        active_session = session or self.db
        if active_session is not None:
            try:
                subs = await self._get_active_subscriptions(
                    event_type="synthesis_review_gate",
                    project_id=pid,
                    session=active_session,
                )
            except Exception as exc:
                logger.warning("webhook_fetch_subscriptions_failed", error=str(exc))

        # 2. Build payloads cache
        slack_payload = build_slack_synthesis_review_payload(
            project_id=pid,
            topic=topic,
            audience=audience,
            qa_summary=qa_summary,
            review_url=review_url,
        )
        teams_payload = build_teams_synthesis_review_payload(
            project_id=pid,
            topic=topic,
            audience=audience,
            qa_summary=qa_summary,
            review_url=review_url,
        )
        generic_payload = build_generic_payload(
            event_type="synthesis_review_gate",
            project_id=pid,
            data={
                "topic": topic,
                "audience": audience,
                "qa_summary": qa_summary,
                "review_url": review_url,
            },
        )

        # 3. Dispatch to DB subscriptions — reuse self.dispatcher so test mocks remain valid
        dispatcher = self.dispatcher
        if session is not None and hasattr(dispatcher, "db"):
            dispatcher.db = session

        for sub in subs:
            payload = generic_payload
            if sub.target_type == "slack":
                payload = slack_payload
            elif sub.target_type == "teams":
                payload = teams_payload

            try:
                delivery = await dispatcher.dispatch(
                    url=sub.url,
                    payload=payload,
                    event_type="synthesis_review_gate",
                    subscription_id=sub.id,
                    project_id=pid,
                    secret=sub.secret,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("webhook_dispatch_failed", sub_id=str(sub.id), url=sub.url, error=str(exc))

        # 4. Dispatch to environment URLs if configured
        if settings.SLACK_WEBHOOK_URL:
            try:
                delivery = await dispatcher.dispatch(
                    url=settings.SLACK_WEBHOOK_URL,
                    payload=slack_payload,
                    event_type="synthesis_review_gate",
                    project_id=pid,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("env_slack_webhook_failed", url=settings.SLACK_WEBHOOK_URL, error=str(exc))

        if settings.TEAMS_WEBHOOK_URL:
            try:
                delivery = await dispatcher.dispatch(
                    url=settings.TEAMS_WEBHOOK_URL,
                    payload=teams_payload,
                    event_type="synthesis_review_gate",
                    project_id=pid,
                )
                deliveries.append(delivery)
            except Exception as exc:
                logger.error("env_teams_webhook_failed", url=settings.TEAMS_WEBHOOK_URL, error=str(exc))

        return deliveries

    def trigger_slide_review_gate(
        self,
        project_id: Union[str, uuid.UUID],
        topic: str,
        audience: str,
        total_slides: int,
        slide_summary: Union[str, List[Any]],
        session: Optional[AsyncSession] = None,
    ) -> Optional[asyncio.Task]:
        """Trigger slide review gate dispatch non-blockingly."""
        has_env_urls = bool(settings.SLACK_WEBHOOK_URL or settings.TEAMS_WEBHOOK_URL)
        if "pytest" in sys.modules and not has_env_urls and not getattr(self, "enable_in_tests", False):
            return None

        async def _run() -> None:
            try:
                if session is not None:
                    await self.dispatch_slide_review_gate(
                        project_id=project_id,
                        topic=topic,
                        audience=audience,
                        total_slides=total_slides,
                        slide_summary=slide_summary,
                        session=session,
                    )
                else:
                    async with db_session_module.AsyncSessionLocal() as fresh_session:
                        await self.dispatch_slide_review_gate(
                            project_id=project_id,
                            topic=topic,
                            audience=audience,
                            total_slides=total_slides,
                            slide_summary=slide_summary,
                            session=fresh_session,
                        )
            except Exception as exc:
                logger.warning("background_slide_webhook_error", error=str(exc))

        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(_run())
        except RuntimeError:
            return None

    trigger_slide_review_gate_background = trigger_slide_review_gate

    def trigger_synthesis_review_gate(
        self,
        project_id: Union[str, uuid.UUID],
        topic: str,
        audience: str,
        qa_summary: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[asyncio.Task]:
        """Trigger synthesis review gate dispatch non-blockingly."""
        has_env_urls = bool(settings.SLACK_WEBHOOK_URL or settings.TEAMS_WEBHOOK_URL)
        if "pytest" in sys.modules and not has_env_urls and not getattr(self, "enable_in_tests", False):
            return None

        async def _run() -> None:
            try:
                if session is not None:
                    await self.dispatch_synthesis_review_gate(
                        project_id=project_id,
                        topic=topic,
                        audience=audience,
                        qa_summary=qa_summary,
                        session=session,
                    )
                else:
                    async with db_session_module.AsyncSessionLocal() as fresh_session:
                        await self.dispatch_synthesis_review_gate(
                            project_id=project_id,
                            topic=topic,
                            audience=audience,
                            qa_summary=qa_summary,
                            session=fresh_session,
                        )
            except Exception as exc:
                logger.warning("background_synthesis_webhook_error", error=str(exc))

        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(_run())
        except RuntimeError:
            return None

    trigger_synthesis_review_gate_background = trigger_synthesis_review_gate
