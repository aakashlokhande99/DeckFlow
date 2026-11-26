"""Automated Test Suite for Milestone 3 (M3): Webhook Notifications & Review Gates.

Covers:
- Slack Block Kit payload structure & fields (build_slack_slide_review_payload).
- MS Teams Adaptive Card 1.4 payload structure & FactSet (build_teams_slide_review_payload).
- SSRF prevention (validate_url blocking private IPs, link-local, loopback, accepting safe URLs).
- WebhookDispatcher 3-attempt exponential backoff retry on HTTP 500 & network error (pytest-httpx).
- Webhook registration, listing, deletion, and test ping REST API endpoints (/api/webhooks).
- Review gate triggers on slide storyline generation and synthesis review pause.
- Delivery persistence to WebhookDelivery in database.
"""

from __future__ import annotations

import socket
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest_httpx import HTTPXMock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import is_safe_url, validate_url
from app.db.enums import ProjectStatus, SlideLayout
from app.db.models import Insight, Project, SlideSpec, WebhookDelivery, WebhookSubscription
from app.notifications.dispatcher import WebhookDispatcher, WebhookSSRFError
from app.notifications.payloads import (
    build_generic_payload,
    build_slack_slide_review_payload,
    build_slack_synthesis_review_payload,
    build_teams_slide_review_payload,
    build_teams_synthesis_review_payload,
    format_slide_summary,
)
from app.notifications.service import WebhookService
from app.presentation.storyline import StorylineGenerator
from app.workflow.nodes import human_review_pause_node


# =============================================================================
# Offline DNS Mocking Fixture (Safe for SSRF testing without real internet DNS)
# =============================================================================

@pytest.fixture(autouse=True)
def mock_dns_for_tests(monkeypatch):
    """Mock socket.getaddrinfo so tests can run in offline sandboxes without external DNS."""
    def _mock_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # Loopback and private
        if host in {"localhost", "metadata.google.internal"} or host.startswith("127."):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        if host in {"10.0.0.1", "192.168.1.1", "169.254.169.254"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, 0))]
        # Safe public IP for public test domains
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _mock_getaddrinfo)


# =============================================================================
# 1. Payload Structure Tests
# =============================================================================

class TestWebhookPayloadBuilders:
    """Verifies compliance with Slack Block Kit and MS Teams Adaptive Card specifications."""

    def test_slack_block_kit_slide_review_structure(self):
        project_id = uuid.uuid4()
        topic = "SMR Industrial Microgrids"
        audience = "C-Suite Executives"
        total_slides = 11
        slide_summary = [
            {"slide_order": 1, "title": "Executive Cover", "layout": "title"},
            {"slide_order": 2, "title": "Strategic Thesis", "layout": "two_column"},
        ]
        review_url = f"http://localhost:3000/projects/{project_id}/storyline"

        payload = build_slack_slide_review_payload(
            project_id=project_id,
            topic=topic,
            audience=audience,
            total_slides=total_slides,
            slide_summary=slide_summary,
            review_url=review_url,
        )

        assert "text" in payload
        assert topic in payload["text"]
        blocks = payload["blocks"]
        assert len(blocks) == 5

        # 1. Header Block
        assert blocks[0]["type"] == "header"
        assert "Slide Review Gate" in blocks[0]["text"]["text"]

        # 2. Section with Fields
        assert blocks[1]["type"] == "section"
        fields = blocks[1]["fields"]
        assert len(fields) == 4
        field_texts = [f["text"] for f in fields]
        assert any(topic in t for t in field_texts)
        assert any("11 slides" in t for t in field_texts)
        assert any(audience in t for t in field_texts)
        assert any("Awaiting Slide Approval" in t for t in field_texts)

        # 3. Storyline Summary Section
        assert blocks[2]["type"] == "section"
        assert "Executive Cover" in blocks[2]["text"]["text"]

        # 4. Actions Block with Review Button
        assert blocks[3]["type"] == "actions"
        button = blocks[3]["elements"][0]
        assert button["type"] == "button"
        assert button["url"] == review_url
        assert button["style"] == "primary"

        # 5. Context Block
        assert blocks[4]["type"] == "context"
        assert "Consulting Deck Generator" in blocks[4]["elements"][0]["text"]

    def test_teams_adaptive_card_slide_review_structure(self):
        project_id = uuid.uuid4()
        topic = "SMR Industrial Microgrids"
        audience = "C-Suite Executives"
        total_slides = 11
        slide_summary = ["Slide 1: Executive Cover", "Slide 2: Strategic Thesis"]
        review_url = f"http://localhost:3000/projects/{project_id}/storyline"

        payload = build_teams_slide_review_payload(
            project_id=project_id,
            topic=topic,
            audience=audience,
            total_slides=total_slides,
            slide_summary=slide_summary,
            review_url=review_url,
        )

        assert payload["type"] == "message"
        assert len(payload["attachments"]) == 1
        attachment = payload["attachments"][0]
        assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"

        card = attachment["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"

        # Header TextBlock
        assert card["body"][0]["type"] == "TextBlock"
        assert "Slide Review Gate" in card["body"][0]["text"]

        # FactSet
        factset = card["body"][1]
        assert factset["type"] == "FactSet"
        facts = {f["title"]: f["value"] for f in factset["facts"]}
        assert facts["Project:"] == topic
        assert facts["Total Slides:"] == "11 slides configured"
        assert facts["Audience:"] == audience
        assert facts["Gate Status:"] == "Awaiting Slide Approval"

        # Action OpenUrl Button
        action = card["actions"][0]
        assert action["type"] == "Action.OpenUrl"
        assert action["url"] == review_url

    def test_synthesis_review_payload_builders(self):
        project_id = uuid.uuid4()
        slack = build_slack_synthesis_review_payload(
            project_id=project_id,
            topic="Renewable Integration",
            audience="VP of Engineering",
            qa_summary="Overall Passed: True. Issues: 0.",
            review_url="http://localhost:3000/projects/1/review",
        )
        assert slack["blocks"][0]["type"] == "header"
        assert "Synthesis Review Gate" in slack["blocks"][0]["text"]["text"]

        teams = build_teams_synthesis_review_payload(
            project_id=project_id,
            topic="Renewable Integration",
            audience="VP of Engineering",
            qa_summary="Overall Passed: True. Issues: 0.",
            review_url="http://localhost:3000/projects/1/review",
        )
        assert teams["attachments"][0]["content"]["body"][0]["text"] == "🔬 Synthesis Review Gate: Review Required"


# =============================================================================
# 2. SSRF Protection Tests
# =============================================================================

class TestSSRFValidation:
    """Verifies that SSRF attack vectors are strictly prevented."""

    @pytest.mark.parametrize(
        "blocked_url",
        [
            "http://127.0.0.1/webhook",
            "http://127.0.0.1:8000/api/hook",
            "http://localhost:8080/hook",
            "http://10.0.0.1/internal",
            "http://192.168.1.1/admin",
            "http://169.254.169.254/latest/meta-data/",
            "ftp://example.com/webhook",
            "gopher://example.com/",
            "",
            "not-a-url",
        ],
    )
    def test_ssrf_rejects_unsafe_urls(self, blocked_url: str):
        dispatcher = WebhookDispatcher()
        with pytest.raises((ValueError, WebhookSSRFError)):
            dispatcher.validate_destination_url(blocked_url)

    @pytest.mark.parametrize(
        "allowed_url",
        [
            "https://hooks.slack.com/services/T00/B00/X00",
            "https://outlook.office.com/webhook/abc-123",
            "https://api.example.com/webhooks/incoming",
            "https://93.184.216.34/webhook",
        ],
    )
    def test_ssrf_allows_safe_public_urls(self, allowed_url: str):
        dispatcher = WebhookDispatcher()
        validated = dispatcher.validate_destination_url(allowed_url)
        assert validated == allowed_url


# =============================================================================
# 3. Dispatcher Retry & Delivery Tests (pytest-httpx)
# =============================================================================

class TestWebhookDispatcherWithMocks:
    """Tests async HTTP delivery and exponential backoff retry mechanics."""

    @pytest.mark.asyncio
    async def test_dispatch_success_first_attempt(self, httpx_mock: HTTPXMock, db_session: AsyncSession):
        target_url = "https://hooks.slack.com/services/T00/B00/OK"
        httpx_mock.add_response(
            url=target_url,
            method="POST",
            status_code=200,
            text="ok",
        )

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)
        delivery = await dispatcher.dispatch(
            url=target_url,
            payload={"text": "hello"},
            event_type="slide_review_gate",
        )

        assert delivery.success is True
        assert delivery.status_code == 200
        assert delivery.attempt_count == 1
        assert delivery.response_body == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_retries_on_http_500_and_recovers(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        target_url = "https://hooks.slack.com/services/T00/B00/RETRY"
        # First call fails with 500, second succeeds with 200
        httpx_mock.add_response(url=target_url, method="POST", status_code=500, text="Internal Server Error")
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="ok")

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)
        delivery = await dispatcher.dispatch(
            url=target_url,
            payload={"text": "retry test"},
            event_type="slide_review_gate",
        )

        assert delivery.success is True
        assert delivery.status_code == 200
        assert delivery.attempt_count == 2
        assert len(httpx_mock.get_requests()) == 2

    @pytest.mark.asyncio
    async def test_dispatch_permanent_failure_after_3_attempts(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        target_url = "https://hooks.slack.com/services/T00/B00/FAIL"
        # 3 consecutive 503 errors
        for _ in range(3):
            httpx_mock.add_response(url=target_url, method="POST", status_code=503, text="Service Unavailable")

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)
        delivery = await dispatcher.dispatch(
            url=target_url,
            payload={"text": "fail test"},
            event_type="slide_review_gate",
        )

        assert delivery.success is False
        assert delivery.status_code == 503
        assert delivery.attempt_count == 3
        assert len(httpx_mock.get_requests()) == 3

    @pytest.mark.asyncio
    async def test_dispatch_retries_on_network_transport_error(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        target_url = "https://hooks.slack.com/services/T00/B00/NETWORK"
        # First call raises connection error, second succeeds
        httpx_mock.add_exception(httpx.ConnectError("Network unreachable"), url=target_url)
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="ok")

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=3, base_delay=0.01)
        delivery = await dispatcher.dispatch(
            url=target_url,
            payload={"text": "network retry test"},
            event_type="slide_review_gate",
        )

        assert delivery.success is True
        assert delivery.status_code == 200
        assert delivery.attempt_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_hmac_secret_signature(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        target_url = "https://api.example.com/secure-webhook"
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="accepted")

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=1, base_delay=0.01)
        await dispatcher.dispatch(
            url=target_url,
            payload={"data": "confidential"},
            secret="super-secret-key-12345",
        )

        sent_requests = httpx_mock.get_requests()
        assert len(sent_requests) == 1
        headers = sent_requests[0].headers
        assert "x-webhook-signature" in headers
        assert headers["x-webhook-signature"].startswith("sha256=")


# =============================================================================
# 4. REST API Endpoints Tests
# =============================================================================

class TestWebhookAPIEndpoints:
    """Tests CRUD and test ping operations via REST endpoints."""

    @pytest.mark.asyncio
    async def test_create_webhook_subscription_success(self, async_client: AsyncClient):
        payload = {
            "target_type": "slack",
            "url": "https://hooks.slack.com/services/T00/B00/API",
            "events": ["slide_review_gate"],
            "secret": "my-secret-key",
            "is_active": True,
        }
        res = await async_client.post("/api/webhooks", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["target_type"] == "slack"
        assert data["url"] == payload["url"]
        assert data["events"] == ["slide_review_gate"]
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_webhook_subscription_ssrf_rejected(self, async_client: AsyncClient):
        payload = {
            "target_type": "generic",
            "url": "http://127.0.0.1:8000/internal-endpoint",
            "events": ["slide_review_gate"],
        }
        res = await async_client.post("/api/webhooks", json=payload)
        assert res.status_code == 400
        assert "Invalid or unsafe webhook URL" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_and_delete_webhook_subscriptions(self, async_client: AsyncClient):
        # 1. Create a subscription
        create_res = await async_client.post(
            "/api/webhooks",
            json={
                "target_type": "teams",
                "url": "https://outlook.office.com/webhook/list-test",
                "events": ["slide_review_gate", "synthesis_review_gate"],
            },
        )
        assert create_res.status_code == 201
        sub_id = create_res.json()["id"]

        # 2. List subscriptions
        list_res = await async_client.get("/api/webhooks")
        assert list_res.status_code == 200
        subs = list_res.json()
        assert any(s["id"] == sub_id for s in subs)

        # 3. Get single subscription
        get_res = await async_client.get(f"/api/webhooks/{sub_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == sub_id

        # 4. Delete subscription
        del_res = await async_client.delete(f"/api/webhooks/{sub_id}")
        assert del_res.status_code == 204

        # 5. Verify deleted
        get_after = await async_client.get(f"/api/webhooks/{sub_id}")
        assert get_after.status_code == 404

    @pytest.mark.asyncio
    async def test_test_ping_endpoint_ad_hoc(
        self, async_client: AsyncClient, httpx_mock: HTTPXMock
    ):
        target_url = "https://hooks.slack.com/services/T00/B00/PING"
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="ok")

        res = await async_client.post(
            "/api/webhooks/test",
            json={"url": target_url, "target_type": "slack"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["status_code"] == 200
        assert data["attempt_count"] == 1


# =============================================================================
# 5. Service & Trigger Integration Tests
# =============================================================================

class TestWebhookServiceAndTriggers:
    """Tests webhook dispatch integration with review gate lifecycle."""

    @pytest.mark.asyncio
    async def test_service_dispatches_to_db_and_env_urls(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        from sqlalchemy import delete
        # Clean any leftover subscriptions from earlier tests
        await db_session.execute(delete(WebhookSubscription))
        await db_session.commit()

        project_id = uuid.uuid4()
        db_slack_url = "https://hooks.slack.com/services/DB/SLACK"
        env_teams_url = "https://outlook.office.com/webhook/ENV/TEAMS"

        # Mock responses
        httpx_mock.add_response(url=db_slack_url, method="POST", status_code=200, text="ok")
        httpx_mock.add_response(url=env_teams_url, method="POST", status_code=200, text="ok")

        # 1. Register subscription in DB
        sub = WebhookSubscription(
            id=uuid.uuid4(),
            target_type="slack",
            url=db_slack_url,
            events=["slide_review_gate"],
            project_id=project_id,
            is_active=True,
        )
        db_session.add(sub)
        await db_session.commit()

        # 2. Configure environment variable URL
        dispatcher = WebhookDispatcher(db=db_session, max_attempts=1, base_delay=0.01)
        with patch.object(settings, "TEAMS_WEBHOOK_URL", env_teams_url):
            service = WebhookService(db=db_session, dispatcher=dispatcher)
            deliveries = await service.dispatch_slide_review_gate(
                project_id=project_id,
                topic="Advanced Energy Storage",
                audience="Strategy Committee",
                total_slides=11,
                slide_summary=["Slide 1: Executive Cover", "Slide 2: Market Dynamics"],
                session=db_session,
            )

        assert len(deliveries) == 2
        assert all(d.success for d in deliveries)

        # Check DB audit records
        stmt = select(WebhookDelivery).where(WebhookDelivery.project_id == project_id)
        saved = (await db_session.execute(stmt)).scalars().all()
        assert len(saved) >= 2

    @pytest.mark.asyncio
    async def test_synthesis_review_gate_trigger(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        from sqlalchemy import delete
        await db_session.execute(delete(WebhookSubscription))
        await db_session.commit()

        project_id = uuid.uuid4()
        slack_url = "https://hooks.slack.com/services/SYNTHESIS"
        httpx_mock.add_response(url=slack_url, method="POST", status_code=200, text="ok")

        dispatcher = WebhookDispatcher(db=db_session, max_attempts=1, base_delay=0.01)
        with patch.object(settings, "SLACK_WEBHOOK_URL", slack_url):
            service = WebhookService(db=db_session, dispatcher=dispatcher)
            deliveries = await service.dispatch_synthesis_review_gate(
                project_id=project_id,
                topic="AI Chip Architectures",
                audience="Engineering Leadership",
                qa_summary="Passed: True. Citations: 100%.",
                session=db_session,
            )

        assert len(deliveries) == 1
        assert deliveries[0].success is True
        assert deliveries[0].event_type == "synthesis_review_gate"

    @pytest.mark.asyncio
    async def test_storyline_generation_invokes_webhook_service(
        self, db_session: AsyncSession
    ):
        """Verify generate_storyline triggers webhook dispatch."""
        # 1. Create project + approved insight
        project = Project(
            id=uuid.uuid4(),
            topic="Next-Gen Computing",
            objective="Evaluate silicon photonics vs optical interconnects",
            audience="Board of Directors",
            geography="Global",
            time_horizon="2026-2030",
            status=ProjectStatus.approved.value,
        )
        db_session.add(project)
        await db_session.flush()

        insight = Insight(
            id=uuid.uuid4(),
            project_id=project.id,
            executive_summary="Optical interconnects deliver 10x bandwidth per watt.",
            findings=[
                {
                    "id": "F1",
                    "finding": "Photonics reduce latency by 60%.",
                    "evidence_ids": ["src-001"],
                    "confidence": "high",
                }
            ],
            is_approved=True,
            version=1,
        )
        db_session.add(insight)
        await db_session.commit()

        # 2. Mock trigger_slide_review_gate on WebhookService
        with patch("app.notifications.service.WebhookService.trigger_slide_review_gate") as mock_trigger:
            generator = StorylineGenerator(db=db_session)
            outline = await generator.generate_storyline(project.id, force_regenerate=True)

            assert outline.total_slides == 11
            assert mock_trigger.called
            call_kwargs = mock_trigger.call_args[1]
            assert call_kwargs["project_id"] == project.id
            assert call_kwargs["topic"] == project.topic
            assert call_kwargs["total_slides"] == 11
            assert call_kwargs["session"] is None

    @pytest.mark.asyncio
    async def test_subscription_deletion_preserves_delivery_audit_records(
        self, db_session: AsyncSession
    ):
        """Verify deleting a WebhookSubscription keeps WebhookDelivery rows with subscription_id = None."""
        project_id = uuid.uuid4()
        sub_id = uuid.uuid4()

        sub = WebhookSubscription(
            id=sub_id,
            target_type="slack",
            url="https://hooks.slack.com/services/AUDIT/PRESERVE",
            events=["slide_review_gate"],
            project_id=project_id,
            is_active=True,
        )
        db_session.add(sub)
        await db_session.flush()

        delivery_id = uuid.uuid4()
        delivery = WebhookDelivery(
            id=delivery_id,
            subscription_id=sub.id,
            project_id=project_id,
            event_type="slide_review_gate",
            payload={"event": "slide_review_gate", "project_id": str(project_id)},
            status_code=200,
            response_body="ok",
            attempt_count=1,
            success=True,
        )
        db_session.add(delivery)
        await db_session.commit()

        # Delete the subscription
        stmt_sub = select(WebhookSubscription).where(WebhookSubscription.id == sub_id)
        sub_to_delete = (await db_session.execute(stmt_sub)).scalar_one()
        await db_session.delete(sub_to_delete)
        await db_session.commit()

        # Verify delivery still exists in DB and subscription_id is now None
        stmt_del = select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        persisted_del = (await db_session.execute(stmt_del)).scalar_one_or_none()
        assert persisted_del is not None, "WebhookDelivery must NOT be deleted when subscription is deleted"
        assert persisted_del.subscription_id is None, "WebhookDelivery.subscription_id must be NULL after subscription deletion"
        assert persisted_del.success is True
        assert persisted_del.event_type == "slide_review_gate"

    @pytest.mark.asyncio
    async def test_trigger_synthesis_review_gate_background_persists_deliveries(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        """Verify trigger_synthesis_review_gate_background binds fresh session to dispatcher and saves WebhookDelivery."""
        project_id = uuid.uuid4()
        target_url = "https://hooks.slack.com/services/SYNTHESIS/BACKGROUND"
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="ok")

        # Create subscription in DB
        sub = WebhookSubscription(
            id=uuid.uuid4(),
            target_type="slack",
            url=target_url,
            events=["synthesis_review_gate"],
            project_id=project_id,
            is_active=True,
        )
        db_session.add(sub)
        await db_session.commit()

        # Initialize WebhookService with NO db (db=None, simulating background task initialization)
        service = WebhookService(enable_in_tests=True)
        assert service.db is None
        assert service.dispatcher.db is None

        # Trigger background synthesis review gate
        task = service.trigger_synthesis_review_gate_background(
            project_id=project_id,
            topic="Quantum Computing Scalability",
            audience="Board of Directors",
            qa_summary="Gate passed. 12 citations verified.",
            session=None,
        )
        assert task is not None
        await task

        # Verify delivery record was persisted to DB
        stmt = select(WebhookDelivery).where(
            WebhookDelivery.project_id == project_id,
            WebhookDelivery.event_type == "synthesis_review_gate",
        )
        deliveries = (await db_session.execute(stmt)).scalars().all()
        assert len(deliveries) >= 1
        assert deliveries[0].success is True
        assert deliveries[0].subscription_id == sub.id
        assert deliveries[0].status_code == 200

    @pytest.mark.asyncio
    async def test_trigger_slide_review_gate_session_isolation_persists_deliveries(
        self, httpx_mock: HTTPXMock, db_session: AsyncSession
    ):
        """Verify trigger_slide_review_gate with session=None runs background dispatch cleanly and persists WebhookDelivery."""
        project_id = uuid.uuid4()
        target_url = "https://outlook.office.com/webhook/SLIDE/ISOLATED"
        httpx_mock.add_response(url=target_url, method="POST", status_code=200, text="ok")

        # Create subscription in DB
        sub = WebhookSubscription(
            id=uuid.uuid4(),
            target_type="teams",
            url=target_url,
            events=["slide_review_gate"],
            project_id=project_id,
            is_active=True,
        )
        db_session.add(sub)
        await db_session.commit()

        # Initialize WebhookService with NO db (db=None, simulating caller passing session=None)
        service = WebhookService(enable_in_tests=True)
        assert service.db is None

        task = service.trigger_slide_review_gate(
            project_id=project_id,
            topic="Clean Hydrogen Electrolyzers",
            audience="Investment Committee",
            total_slides=11,
            slide_summary=["Slide 1: Executive Cover", "Slide 2: Levelized Cost of Hydrogen"],
            session=None,
        )
        assert task is not None
        await task

        # Verify delivery record was persisted to DB
        stmt = select(WebhookDelivery).where(
            WebhookDelivery.project_id == project_id,
            WebhookDelivery.event_type == "slide_review_gate",
        )
        deliveries = (await db_session.execute(stmt)).scalars().all()
        assert len(deliveries) >= 1
        assert deliveries[0].success is True
        assert deliveries[0].subscription_id == sub.id
        assert deliveries[0].status_code == 200
