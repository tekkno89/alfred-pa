"""Notification service for SSE and webhook dispatching."""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import WebhookRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications via SSE and webhooks."""

    # Class-level storage for SSE clients (user_id -> list of queues)
    _sse_clients: dict[str, list[asyncio.Queue]] = defaultdict(list)
    _lock = asyncio.Lock()

    def __init__(self, db: AsyncSession):
        self.db = db
        self.webhook_repo = WebhookRepository(db)

    @classmethod
    async def register_sse_client(cls, user_id: str) -> asyncio.Queue:
        """
        Register an SSE client for a user.

        Args:
            user_id: The user's ID

        Returns:
            Queue to receive events from
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with cls._lock:
            cls._sse_clients[user_id].append(queue)
        logger.info(f"SSE client registered for user {user_id}")
        return queue

    @classmethod
    async def unregister_sse_client(cls, user_id: str, queue: asyncio.Queue) -> None:
        """
        Unregister an SSE client.

        Args:
            user_id: The user's ID
            queue: The queue to unregister
        """
        async with cls._lock:
            if user_id in cls._sse_clients:
                try:
                    cls._sse_clients[user_id].remove(queue)
                    if not cls._sse_clients[user_id]:
                        del cls._sse_clients[user_id]
                except ValueError:
                    pass
        logger.info(f"SSE client unregistered for user {user_id}")

    @classmethod
    async def publish_to_sse(cls, user_id: str, event_type: str, payload: dict) -> int:
        """
        Publish an event to all SSE clients for a user.

        Args:
            user_id: The user's ID
            event_type: Type of event
            payload: Event payload

        Returns:
            Number of clients notified
        """
        async with cls._lock:
            clients = cls._sse_clients.get(user_id, []).copy()

        if not clients:
            return 0

        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **payload,
        }

        notified = 0
        for queue in clients:
            try:
                queue.put_nowait(event)
                notified += 1
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full for user {user_id}")

        return notified

    async def dispatch_webhooks(
        self, user_id: str, event_type: str, payload: dict
    ) -> list[dict[str, Any]]:
        """
        Dispatch webhooks for an event.

        Args:
            user_id: The user's ID
            event_type: Type of event
            payload: Event payload

        Returns:
            List of results with webhook name and success status
        """
        webhooks = await self.webhook_repo.get_enabled_for_event(user_id, event_type)

        if not webhooks:
            return []

        event_data = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "data": payload,
        }

        results = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for webhook in webhooks:
                result = await self._send_webhook(client, webhook.name, webhook.url, event_data)
                results.append(result)

        return results

    async def _send_webhook(
        self,
        client: httpx.AsyncClient,
        name: str,
        url: str,
        data: dict,
    ) -> dict[str, Any]:
        """Send a single webhook request."""
        try:
            response = await client.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
            )
            return {
                "name": name,
                "success": response.is_success,
                "status_code": response.status_code,
            }
        except httpx.RequestError as e:
            logger.error(f"Webhook request failed for {name}: {e}")
            return {
                "name": name,
                "success": False,
                "error": str(e),
            }

    async def publish(
        self, user_id: str, event_type: str, payload: dict
    ) -> dict[str, Any]:
        """
        Publish an event to both SSE clients and webhooks.

        Args:
            user_id: The user's ID
            event_type: Type of event
            payload: Event payload

        Returns:
            Summary of notifications sent
        """
        # Publish to SSE clients
        sse_count = await self.publish_to_sse(user_id, event_type, payload)

        # Dispatch webhooks
        webhook_results = await self.dispatch_webhooks(user_id, event_type, payload)

        return {
            "sse_clients_notified": sse_count,
            "webhooks_sent": len(webhook_results),
            "webhook_results": webhook_results,
        }


async def format_sse_event(event: dict) -> str:
    """Format an event for SSE transmission."""
    event_type = event.get("type", "message")
    data = json.dumps(event)
    return f"event: {event_type}\ndata: {data}\n\n"
