"""Redis-backed event bus using pub/sub channels.

Topics are mapped to Redis channels with the prefix 'alfred:events:'.
Pattern subscriptions use Redis PSUBSCRIBE for wildcard matching.
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.events.bus import EventBus, EventHandler

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "alfred:events:"


class RedisEventBus(EventBus):
    """Event bus backed by Redis pub/sub."""

    def __init__(self) -> None:
        self._subscriptions: list[tuple[str, EventHandler]] = []
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def publish(self, topic: str, payload: dict) -> None:
        settings = get_settings()
        client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        try:
            channel = f"{CHANNEL_PREFIX}{topic}"
            message = json.dumps(payload)
            await client.publish(channel, message)
            logger.debug(f"Published event to {channel}")
        finally:
            await client.close()

    async def subscribe(
        self, topic_pattern: str, handler: EventHandler
    ) -> None:
        self._subscriptions.append((topic_pattern, handler))

    async def start(self) -> None:
        if not self._subscriptions:
            logger.info("EventBus: no subscriptions registered, not starting")
            return

        settings = get_settings()
        client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        self._pubsub = client.pubsub()

        # Subscribe to all registered patterns
        for pattern, _ in self._subscriptions:
            channel_pattern = f"{CHANNEL_PREFIX}{pattern}"
            await self._pubsub.psubscribe(channel_pattern)
            logger.info(f"EventBus: subscribed to {channel_pattern}")

        self._running = True
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("EventBus: Redis listener started")

    async def stop(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        logger.info("EventBus: stopped")

    async def _listen(self) -> None:
        """Background task that listens for pub/sub messages."""
        assert self._pubsub is not None

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break

                if message["type"] != "pmessage":
                    continue

                channel: str = message["channel"]
                pattern: str = message["pattern"]
                raw_data: str = message["data"]

                # Extract topic from channel (strip prefix)
                topic = channel.removeprefix(CHANNEL_PREFIX)

                try:
                    payload = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"EventBus: invalid JSON on {channel}")
                    continue

                # Dispatch to matching handlers
                for sub_pattern, handler in self._subscriptions:
                    sub_channel = f"{CHANNEL_PREFIX}{sub_pattern}"
                    if sub_channel == pattern:
                        try:
                            await handler(topic, payload)
                        except Exception:
                            logger.exception(
                                f"EventBus: handler error for {topic}"
                            )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("EventBus: listener crashed")
