"""Webhook subscription management and test ping REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import validate_url
from app.db.models import WebhookDelivery, WebhookSubscription
from app.db.session import get_db
from app.notifications.dispatcher import WebhookDispatcher, WebhookSSRFError
from app.notifications.payloads import (
    build_generic_payload,
    build_slack_slide_review_payload,
    build_teams_slide_review_payload,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class WebhookSubscriptionCreate(BaseModel):
    target_type: Literal["slack", "teams", "generic"] = Field(
        default="generic",
        description="Target webhook receiver type ('slack', 'teams', 'generic')",
    )
    url: str = Field(..., description="Destination webhook URL")
    secret: Optional[str] = Field(None, description="Optional HMAC signing secret")
    events: List[str] = Field(
        default=["slide_review_gate", "synthesis_review_gate"],
        description="List of events to subscribe to",
    )
    project_id: Optional[uuid.UUID] = Field(None, description="Scope to specific project")
    organization_id: Optional[uuid.UUID] = Field(None, description="Scope to specific org")
    is_active: bool = Field(True, description="Whether subscription is enabled")


class WebhookSubscriptionResponse(BaseModel):
    id: uuid.UUID
    target_type: str
    url: str
    events: List[str]
    is_active: bool
    project_id: Optional[uuid.UUID]
    organization_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class WebhookTestRequest(BaseModel):
    url: Optional[str] = Field(None, description="URL to test (if testing ad-hoc without subscription)")
    target_type: Literal["slack", "teams", "generic"] = Field("generic", description="Target receiver type")
    event_type: str = Field("slide_review_gate", description="Event to test")


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    subscription_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    event_type: str
    status_code: Optional[int]
    response_body: Optional[str]
    attempt_count: int
    success: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    summary="Register a new webhook subscription",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookSubscriptionResponse,
)
async def create_webhook_subscription(
    payload: WebhookSubscriptionCreate = Body(...),
    db: AsyncSession = Depends(get_db),
) -> WebhookSubscriptionResponse:
    """Create a new webhook subscription. Validates destination URL against SSRF."""
    # 1. SSRF URL validation
    try:
        validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or unsafe webhook URL: {exc}",
        )

    subscription = WebhookSubscription(
        id=uuid.uuid4(),
        target_type=payload.target_type,
        url=payload.url,
        secret=payload.secret,
        events=payload.events,
        project_id=payload.project_id,
        is_active=payload.is_active,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    logger.info("webhook_subscription_created", id=str(subscription.id), url=subscription.url)
    return WebhookSubscriptionResponse(
        id=subscription.id,
        target_type=subscription.target_type,
        url=subscription.url,
        events=subscription.events,
        is_active=subscription.is_active,
        project_id=subscription.project_id,
        organization_id=None,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


@router.get(
    "",
    summary="List webhook subscriptions",
    response_model=List[WebhookSubscriptionResponse],
)
async def list_webhook_subscriptions(
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project"),
    db: AsyncSession = Depends(get_db),
) -> List[WebhookSubscriptionResponse]:
    """List all registered webhook subscriptions."""
    stmt = select(WebhookSubscription)
    if project_id:
        stmt = stmt.where(WebhookSubscription.project_id == project_id)

    result = await db.execute(stmt)
    subscriptions = result.scalars().all()

    return [
        WebhookSubscriptionResponse(
            id=s.id,
            target_type=s.target_type,
            url=s.url,
            events=s.events,
            is_active=s.is_active,
            project_id=s.project_id,
            organization_id=None,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in subscriptions
    ]


@router.get(
    "/{subscription_id}",
    summary="Get webhook subscription details",
    response_model=WebhookSubscriptionResponse,
)
async def get_webhook_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WebhookSubscriptionResponse:
    """Retrieve details of a single webhook subscription."""
    stmt = select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription {subscription_id} not found",
        )
    return WebhookSubscriptionResponse(
        id=sub.id,
        target_type=sub.target_type,
        url=sub.url,
        events=sub.events,
        is_active=sub.is_active,
        project_id=sub.project_id,
        organization_id=None,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


@router.delete(
    "/{subscription_id}",
    summary="Delete a webhook subscription",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an existing webhook subscription."""
    stmt = select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription {subscription_id} not found",
        )

    await db.delete(sub)
    await db.commit()
    logger.info("webhook_subscription_deleted", id=str(subscription_id))


@router.post(
    "/test",
    summary="Send a test webhook ping to an ad-hoc URL",
    response_model=WebhookDeliveryResponse,
)
async def test_webhook_ad_hoc(
    payload: WebhookTestRequest = Body(...),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """Send a test notification payload to a specified URL."""
    if not payload.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'url' is required for ad-hoc webhook test.",
        )

    dispatcher = WebhookDispatcher(db=db)
    try:
        dispatcher.validate_destination_url(payload.url)
    except WebhookSSRFError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SSRF validation error: {exc}",
        )

    # Build sample payload
    if payload.target_type == "slack":
        test_payload = build_slack_slide_review_payload(
            project_id=uuid.uuid4(),
            topic="Test Project: Enterprise Strategy",
            audience="Board of Directors",
            total_slides=11,
            slide_summary=["Slide 1: Executive Cover", "Slide 2: Strategic Vision"],
            review_url="http://localhost:3000/projects/test/storyline",
        )
    elif payload.target_type == "teams":
        test_payload = build_teams_slide_review_payload(
            project_id=uuid.uuid4(),
            topic="Test Project: Enterprise Strategy",
            audience="Board of Directors",
            total_slides=11,
            slide_summary=["Slide 1: Executive Cover", "Slide 2: Strategic Vision"],
            review_url="http://localhost:3000/projects/test/storyline",
        )
    else:
        test_payload = build_generic_payload(
            event_type=payload.event_type,
            project_id=uuid.uuid4(),
            data={"message": "Test ping from Enterprise Consulting Agent"},
        )

    delivery = await dispatcher.dispatch(
        url=payload.url,
        payload=test_payload,
        event_type="test_ping",
    )

    return WebhookDeliveryResponse(
        id=delivery.id,
        subscription_id=delivery.subscription_id,
        project_id=delivery.project_id,
        event_type=delivery.event_type,
        status_code=delivery.status_code,
        response_body=delivery.response_body,
        attempt_count=delivery.attempt_count,
        success=delivery.success,
        created_at=delivery.created_at,
    )


@router.post(
    "/{subscription_id}/test",
    summary="Send a test webhook ping to a saved subscription",
    response_model=WebhookDeliveryResponse,
)
async def test_webhook_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """Send a test ping using the configured webhook subscription."""
    stmt = select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook subscription {subscription_id} not found",
        )

    dispatcher = WebhookDispatcher(db=db)
    pid = sub.project_id or uuid.uuid4()

    if sub.target_type == "slack":
        test_payload = build_slack_slide_review_payload(
            project_id=pid,
            topic="Test Webhook Project",
            audience="Executive Committee",
            total_slides=11,
            slide_summary=["Slide 1: Executive Cover", "Slide 2: Strategic Roadmap"],
            review_url=f"http://localhost:3000/projects/{pid}/storyline",
        )
    elif sub.target_type == "teams":
        test_payload = build_teams_slide_review_payload(
            project_id=pid,
            topic="Test Webhook Project",
            audience="Executive Committee",
            total_slides=11,
            slide_summary=["Slide 1: Executive Cover", "Slide 2: Strategic Roadmap"],
            review_url=f"http://localhost:3000/projects/{pid}/storyline",
        )
    else:
        test_payload = build_generic_payload(
            event_type="test_ping",
            project_id=pid,
            data={"message": "Test ping for subscription", "subscription_id": str(sub.id)},
        )

    delivery = await dispatcher.dispatch(
        url=sub.url,
        payload=test_payload,
        event_type="test_ping",
        subscription_id=sub.id,
        project_id=sub.project_id,
        secret=sub.secret,
    )

    return WebhookDeliveryResponse(
        id=delivery.id,
        subscription_id=delivery.subscription_id,
        project_id=delivery.project_id,
        event_type=delivery.event_type,
        status_code=delivery.status_code,
        response_body=delivery.response_body,
        attempt_count=delivery.attempt_count,
        success=delivery.success,
        created_at=delivery.created_at,
    )
