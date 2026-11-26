"""WebSocket router for live agent execution streaming and gate notifications."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.events import event_bus, ws_manager
from app.db.models import Project
import app.db.session as db_session_module

router = APIRouter(prefix="/ws", tags=["websockets"])
logger = structlog.get_logger(__name__)


@router.websocket("/projects/{project_id}")
async def project_agent_stream(
    websocket: WebSocket,
    project_id: str,
    token: Optional[str] = Query(default=None),
) -> None:
    """Stream live agent execution events, progress percentages, and gate alerts."""
    # 1. Validate project ID format
    try:
        pid = uuid.UUID(project_id)
    except (ValueError, TypeError):
        await websocket.close(code=4000, reason="Invalid project ID UUID")
        return

    # 2. Check project existence
    async with db_session_module.AsyncSessionLocal() as session:
        stmt = select(Project).where(Project.id == pid)
        project = (await session.execute(stmt)).scalar_one_or_none()
        if not project:
            await websocket.close(code=4004, reason="Project not found")
            return

        initial_status = project.status
        topic = project.topic

    # 3. Accept connection
    await ws_manager.connect(websocket, str(pid))
    channel = f"project:{project_id}"
    event_queue = event_bus.subscribe(channel)

    # Send initial connection frame
    try:
        await websocket.send_json({
            "type": "connected",
            "project_id": str(project_id),
            "status": initial_status,
            "topic": topic,
            "message": "Connected to real-time agent execution stream.",
        })
    except Exception:
        event_bus.unsubscribe(channel, event_queue)
        ws_manager.disconnect(websocket, str(pid))
        return

    # 4. Concurrently handle outbound event streaming and inbound client pings
    async def _stream_events() -> None:
        """Push published agent events to the WebSocket."""
        try:
            while True:
                event = await event_queue.get()
                await websocket.send_json(event)
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        except Exception as exc:
            logger.warning("ws_stream_events_error", project_id=project_id, error=str(exc))

    async def _receive_client_messages() -> None:
        """Handle incoming client heartbeats/pings."""
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except Exception:
                    pass
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    stream_task = asyncio.create_task(_stream_events())
    receive_task = asyncio.create_task(_receive_client_messages())

    try:
        # Wait until either the client disconnects or an error occurs
        done, pending = await asyncio.wait(
            [stream_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        event_bus.unsubscribe(channel, event_queue)
        ws_manager.disconnect(websocket, str(pid))
