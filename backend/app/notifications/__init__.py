"""Notification package for external webhooks and alerts."""

from app.notifications.dispatcher import WebhookDispatcher, WebhookSSRFError
from app.notifications.payloads import (
    build_generic_payload,
    build_slack_slide_review_payload,
    build_slack_synthesis_review_payload,
    build_teams_slide_review_payload,
    build_teams_synthesis_review_payload,
)
from app.notifications.service import WebhookService

__all__ = [
    "WebhookDispatcher",
    "WebhookSSRFError",
    "WebhookService",
    "build_slack_slide_review_payload",
    "build_teams_slide_review_payload",
    "build_slack_synthesis_review_payload",
    "build_teams_synthesis_review_payload",
    "build_generic_payload",
]
