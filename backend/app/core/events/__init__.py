"""Event bus factory.

Returns the configured EventBus implementation based on
``settings.coding_event_bus_provider``.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.events.bus import EventBus, EventHandler

__all__ = ["EventBus", "EventHandler", "get_event_bus"]

_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return a singleton EventBus for the configured provider."""
    global _instance
    if _instance is not None:
        return _instance

    settings = get_settings()
    provider = settings.coding_event_bus_provider

    if provider == "redis":
        from app.core.events.redis import RedisEventBus

        _instance = RedisEventBus()
    elif provider == "gcp_pubsub":
        raise NotImplementedError(
            "GCP Pub/Sub event bus is not yet implemented. "
            "Set CODING_EVENT_BUS_PROVIDER=redis for now."
        )
    elif provider == "kafka":
        raise NotImplementedError(
            "Kafka event bus is not yet implemented. "
            "Set CODING_EVENT_BUS_PROVIDER=redis for now."
        )
    else:
        raise ValueError(f"Unknown event bus provider: {provider}")

    return _instance
