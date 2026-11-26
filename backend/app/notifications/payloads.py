"""Payload builders for external webhook notifications (Slack Block Kit & MS Teams Adaptive Cards)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Union


def format_slide_summary(slide_summary: Union[str, List[str], List[Dict[str, Any]]]) -> str:
    """Format slide summary list or string into bullet points."""
    if isinstance(slide_summary, str):
        return slide_summary
    if not slide_summary:
        return "• No slide details available"

    lines: List[str] = []
    for item in slide_summary:
        if isinstance(item, dict):
            slide_order = item.get("slide_order", "")
            title = item.get("title", "")
            layout = item.get("layout", "")
            lines.append(f"• Slide {slide_order}: {title} ({layout})")
        elif isinstance(item, str):
            prefix = "• " if not item.startswith("•") and not item.startswith("-") else ""
            lines.append(f"{prefix}{item}")
        else:
            lines.append(f"• {str(item)}")
    return "\n".join(lines)


def build_slack_slide_review_payload(
    project_id: Union[str, uuid.UUID],
    topic: str,
    audience: str,
    total_slides: int,
    slide_summary: Union[str, List[Any]],
    review_url: str,
) -> Dict[str, Any]:
    """Construct Slack Block Kit payload for slide review gate alert."""
    summary_text = format_slide_summary(slide_summary)
    pid_str = str(project_id)

    return {
        "text": f"📊 Slide Review Gate: Review Required for '{topic}'",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Slide Review Gate: Human Approval Required",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Project:*\n{topic}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Slides:*\n{total_slides} slides configured",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Audience:*\n{audience}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Review Gate:*\nAwaiting Slide Approval",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Storyline Summary:*\n{summary_text}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 Review & Approve Slides",
                            "emoji": True,
                        },
                        "style": "primary",
                        "url": review_url,
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Enterprise AI Consulting Deck Generator • LangGraph Human-in-the-Loop Gate",
                    }
                ],
            },
        ],
    }


def build_teams_slide_review_payload(
    project_id: Union[str, uuid.UUID],
    topic: str,
    audience: str,
    total_slides: int,
    slide_summary: Union[str, List[Any]],
    review_url: str,
) -> Dict[str, Any]:
    """Construct MS Teams Adaptive Card 1.4 payload for slide review gate alert."""
    summary_text = format_slide_summary(slide_summary)

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "text": "📊 Slide Review Gate: Review Required",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "Project:",
                                    "value": str(topic),
                                },
                                {
                                    "title": "Total Slides:",
                                    "value": f"{total_slides} slides configured",
                                },
                                {
                                    "title": "Audience:",
                                    "value": str(audience),
                                },
                                {
                                    "title": "Gate Status:",
                                    "value": "Awaiting Slide Approval",
                                },
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": (
                                "The consulting slide storyline has been generated from approved research synthesis. "
                                "Please inspect and approve the slide sequence before PPTX deck rendering.\n\n"
                                f"**Storyline Summary:**\n{summary_text}"
                            ),
                            "wrap": True,
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Review & Approve Slides",
                            "url": review_url,
                        }
                    ],
                },
            }
        ],
    }


def build_slack_synthesis_review_payload(
    project_id: Union[str, uuid.UUID],
    topic: str,
    audience: str,
    qa_summary: str,
    review_url: str,
) -> Dict[str, Any]:
    """Construct Slack Block Kit payload for synthesis review gate alert."""
    return {
        "text": f"🔬 Synthesis Review Gate: Human Approval Required for '{topic}'",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔬 Synthesis Review Gate: Human Approval Required",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Project:*\n{topic}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Audience:*\n{audience}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Review Gate:*\nAwaiting Synthesis Approval",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Status:*\nQA Audit Passed",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Quality Audit Summary:*\n{qa_summary}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 Review Synthesis Findings",
                            "emoji": True,
                        },
                        "style": "primary",
                        "url": review_url,
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Enterprise AI Consulting Deck Generator • LangGraph Human-in-the-Loop Gate",
                    }
                ],
            },
        ],
    }


def build_teams_synthesis_review_payload(
    project_id: Union[str, uuid.UUID],
    topic: str,
    audience: str,
    qa_summary: str,
    review_url: str,
) -> Dict[str, Any]:
    """Construct MS Teams Adaptive Card 1.4 payload for synthesis review gate alert."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "text": "🔬 Synthesis Review Gate: Review Required",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "Project:",
                                    "value": str(topic),
                                },
                                {
                                    "title": "Audience:",
                                    "value": str(audience),
                                },
                                {
                                    "title": "Gate Status:",
                                    "value": "Awaiting Synthesis Approval",
                                },
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": (
                                "Research synthesis has passed quality audit. "
                                f"Please review findings, implications, and recommendations:\n\n{qa_summary}"
                            ),
                            "wrap": True,
                        },
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "Review Synthesis Findings",
                            "url": review_url,
                        }
                    ],
                },
            }
        ],
    }


def build_generic_payload(
    event_type: str,
    project_id: Union[str, uuid.UUID],
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Generic JSON payload for generic webhooks."""
    return {
        "event": event_type,
        "project_id": str(project_id),
        "data": data,
    }
