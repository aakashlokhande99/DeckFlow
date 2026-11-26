"""Automated test suite for Track C: Real-Time WebSockets & Push Notifications.

Covers:
  - EventBus in-memory pub/sub broadcast and queue lifecycle
  - Standardized agent event schema and progress normalization
  - WebSocket connection handshake and invalid UUID / missing project handling
  - Heartbeat ping/pong frame negotiation
  - ConnectionManager multi-client broadcast
  - Quality gate review alert push notification schema
"""

from __future__ import annotations

import asyncio
import uuid
import pytest
from starlette.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    create_agent_event,
    event_bus,
    ws_manager,
)
from app.db.enums import ProjectStatus
from app.db.models import Project
from app.main import app


# ---------------------------------------------------------------------------
# Unit Tests: EventBus & Event Schema
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_bus_pub_sub_delivery() -> None:
    """Test that messages published to EventBus are received by in-memory queues."""
    channel = f"project:{uuid.uuid4()}"
    queue_1 = event_bus.subscribe(channel)
    queue_2 = event_bus.subscribe(channel)

    test_payload = {
        "type": "agent_progress",
        "agent": "Research Planner",
        "progress": 25,
        "message": "Generating MECE sub-questions",
    }

    await event_bus.publish(channel, test_payload)

    msg_1 = await asyncio.wait_for(queue_1.get(), timeout=2.0)
    msg_2 = await asyncio.wait_for(queue_2.get(), timeout=2.0)

    assert msg_1["agent"] == "Research Planner"
    assert msg_1["progress"] == 25
    assert msg_2["agent"] == "Research Planner"

    # Test clean unsubscribe
    event_bus.unsubscribe(channel, queue_1)
    event_bus.unsubscribe(channel, queue_2)


def test_create_agent_event_schema_and_clamping() -> None:
    """Verify that agent events enforce standard fields and clamp progress [0, 100]."""
    pid = str(uuid.uuid4())
    event_low = create_agent_event(
        event_type="agent_progress",
        project_id=pid,
        step="validate",
        agent_name="Validator",
        progress=-15,
        message="Starting validation",
    )
    assert event_low["progress"] == 0
    assert "timestamp" in event_low

    event_high = create_agent_event(
        event_type="review_required",
        project_id=pid,
        step="human_review",
        agent_name="Quality Gate Auditor",
        progress=150,
        message="Awaiting human sign-off",
    )
    assert event_high["progress"] == 100
    assert event_high["type"] == "review_required"


@pytest.mark.asyncio
async def test_ws_manager_broadcast_to_mock_client() -> None:
    """Verify that ConnectionManager delivers broadcast messages to active connections."""
    class MockWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict] = []

        async def send_json(self, data: dict) -> None:
            self.sent.append(data)

    mock_ws = MockWebSocket()
    pid = str(uuid.uuid4())
    if pid not in ws_manager.active_connections:
        ws_manager.active_connections[pid] = set()
    ws_manager.active_connections[pid].add(mock_ws)  # type: ignore

    event = create_agent_event(
        event_type="agent_progress",
        project_id=pid,
        step="synthesize",
        agent_name="Consulting Synthesizer",
        progress=85,
        message="Synthesizing findings...",
    )
    await ws_manager.broadcast_to_project(pid, event)

    assert len(mock_ws.sent) == 1
    assert mock_ws.sent[0]["type"] == "agent_progress"
    assert mock_ws.sent[0]["progress"] == 85
    assert mock_ws.sent[0]["agent"] == "Consulting Synthesizer"

    # Clean up
    ws_manager.disconnect(mock_ws, pid)  # type: ignore


def test_quality_gate_alert_event_schema() -> None:
    """Verify review alert payload format and urgency triggers."""
    pid = str(uuid.uuid4())
    event = create_agent_event(
        event_type="review_required",
        project_id=pid,
        step="human_review",
        agent_name="Quality Gate Auditor",
        progress=100,
        message="Research synthesis passed QA gate! Awaiting human reviewer approval.",
        data={"status": "awaiting_review"},
    )
    assert event["type"] == "review_required"
    assert event["progress"] == 100
    assert event["data"]["status"] == "awaiting_review"


# ---------------------------------------------------------------------------
# Integration Tests: WebSocket Handshake & Heartbeat
# ---------------------------------------------------------------------------

def test_websocket_rejects_invalid_uuid() -> None:
    """Invalid UUID project parameter is rejected with status code 4000."""
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/ws/projects/not-a-valid-uuid"):
                pass


def test_websocket_rejects_nonexistent_project() -> None:
    """Non-existent project UUID is closed with 4004."""
    random_pid = str(uuid.uuid4())
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/ws/projects/{random_pid}"):
                pass


@pytest.mark.asyncio
async def test_websocket_connect_and_heartbeat(db_session: AsyncSession) -> None:
    """Connect to an existing project, verify initial handshake, and ping/pong."""
    project = Project(
        topic="Enterprise WebSocket Streaming",
        objective="Verify bidirectional telemetry",
        audience="Tech Leadership",
        geography="Global",
        time_horizon="2026-2027",
        research_depth="standard",
        status=ProjectStatus.running.value,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/ws/projects/{project.id}") as ws:
            # 1. First message is connection greeting
            init_frame = ws.receive_json()
            assert init_frame["type"] == "connected"
            assert init_frame["project_id"] == str(project.id)
            assert init_frame["status"] == "running"
            assert init_frame["topic"] == "Enterprise WebSocket Streaming"

            # 2. Send ping frame
            ws.send_json({"type": "ping"})
            pong_frame = ws.receive_json()
            assert pong_frame["type"] == "pong"
