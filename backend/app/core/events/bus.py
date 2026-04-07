"""Event bus interface for general-purpose pub/sub.

Provides a topic-based event system used for coding job completion events
and extensible for future event types. This is separate from the existing
Redis-based SSE relay (NotificationService) — admins can use the same Redis
instance or configure a different backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

# Handler receives (topic, payload) — e.g. ("coding.plan_complete", {...})
EventHandler = Callable[[str, dict], Awaitable[None]]


class EventBus(ABC):
    """Abstract base for event bus providers."""

    @abstractmethod
    async def publish(self, topic: str, payload: dict) -> None:
        """Publish an event to a topic."""
        ...

    @abstractmethod
    async def subscribe(
        self, topic_pattern: str, handler: EventHandler
    ) -> None:
        """Subscribe to a topic pattern.

        Supports wildcards — e.g. 'coding.*' matches 'coding.plan_complete'.
        Multiple subscriptions can be registered before calling start().
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start consuming events. Called in app lifespan after subscribing."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop consuming. Called on app shutdown."""
        ...
