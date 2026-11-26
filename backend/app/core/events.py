"""Real-time event bus and WebSocket connection manager for live agent streaming.

Provides:
  - EventBus: Hybrid Redis Pub/Sub with in-memory fallback for local/test environments
  - ConnectionManager: Per-project WebSocket connection pool with broadcast capabilities
  - Standardized event schemas for agent progress, QA checks, and gate alerts
"""

from __future__ import annotations

import asyncio
import datetime
import json
from typing import Any, Dict, List, Optional, Set
import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)


class EventBus:
    """Pub/Sub event bus supporting Redis with transparent in-memory fallback."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._redis_client: Any | None = None
        self._redis_listener_task: asyncio.Task | None = None

    async def init_redis(self, redis_url: str) -> None:
        """Attempt to connect to Redis for multi-worker pub/sub."""
        try:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(
                redis_url, encoding="utf-8", decode_responses=True
            )
            await self._redis_client.ping()
            logger.info("event_bus_redis_connected", url=redis_url)
        except Exception as exc:
            logger.warning(
                "event_bus_redis_unavailable_using_in_memory",
                error=str(exc),
            )
            self._redis_client = None

    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        """Publish event message to a channel (e.g. 'project:UUID')."""
        payload = json.dumps(message, default=str)

        # 1. In-memory subscribers broadcast
        if channel in self._subscribers:
            dead_queues = []
            for q in list(self._subscribers[channel]):
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    dead_queues.append(q)
            for dq in dead_queues:
                self._subscribers[channel].discard(dq)

        # 2. Redis broadcast if available
        if self._redis_client:
            try:
                await self._redis_client.publish(channel, payload)
            except Exception as exc:
                logger.warning("event_bus_redis_publish_failed", channel=channel, error=str(exc))

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Subscribe an in-memory queue to a channel."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        if channel not in self._subscribers:
            self._subscribers[channel] = set()
        self._subscribers[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        """Remove a queue subscriber."""
        if channel in self._subscribers:
            self._subscribers[channel].discard(q)
            if not self._subscribers[channel]:
                del self._subscribers[channel]


class ConnectionManager:
    """Manages active WebSockets and handles broadcasting to connected clients."""

    def __init__(self, event_bus: EventBus) -> None:
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.event_bus = event_bus

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        """Accept WebSocket connection and register to project channel."""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        self.active_connections[project_id].add(websocket)
        logger.info(
            "websocket_client_connected",
            project_id=project_id,
            active_clients=len(self.active_connections[project_id]),
        )

    def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        """Unregister WebSocket connection on disconnect."""
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(
            "websocket_client_disconnected",
            project_id=project_id,
        )

    async def broadcast_to_project(self, project_id: str, message: Dict[str, Any]) -> None:
        """Send JSON message to all active WebSockets on a project."""
        connections = self.active_connections.get(project_id, set()).copy()
        if not connections:
            return

        dead_connections: List[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead, project_id)


# Global singletons
event_bus = EventBus()
ws_manager = ConnectionManager(event_bus)


def create_agent_event(
    event_type: str,
    project_id: str,
    step: str,
    agent_name: str,
    progress: int,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Helper to create a standardized agent progress event."""
    return {
        "type": event_type,
        "project_id": str(project_id),
        "step": step,
        "agent": agent_name,
        "progress": max(0, min(100, progress)),
        "message": message,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": data or {},
    }
