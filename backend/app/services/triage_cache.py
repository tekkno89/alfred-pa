"""Redis cache service for triage monitored channels."""

import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

MONITORED_CHANNELS_KEY = "triage:monitored_channels_set"


class TriageCacheService:
    """Manages the Redis SET of monitored Slack channel IDs for O(1) lookups."""

    async def is_monitored_channel(self, channel_id: str) -> bool:
        """Check if a channel is in the monitored set. O(1)."""
        redis_client = await get_redis()
        return await redis_client.sismember(MONITORED_CHANNELS_KEY, channel_id)

    async def add_channel(self, channel_id: str) -> None:
        """Add a channel to the monitored set."""
        redis_client = await get_redis()
        await redis_client.sadd(MONITORED_CHANNELS_KEY, channel_id)

    async def remove_channel(self, channel_id: str) -> None:
        """Remove a channel from the monitored set."""
        redis_client = await get_redis()
        await redis_client.srem(MONITORED_CHANNELS_KEY, channel_id)

    async def rebuild_set(self, db) -> None:
        """Rebuild the monitored channel set from the database.

        Called on worker startup to ensure Redis is in sync.
        """
        from app.db.repositories.triage import MonitoredChannelRepository

        repo = MonitoredChannelRepository(db)
        channel_ids = await repo.get_all_active_channel_ids()

        redis_client = await get_redis()
        # Atomic rebuild: delete then re-add
        pipe = redis_client.pipeline()
        pipe.delete(MONITORED_CHANNELS_KEY)
        if channel_ids:
            pipe.sadd(MONITORED_CHANNELS_KEY, *channel_ids)
        await pipe.execute()

        logger.info(
            f"Rebuilt triage monitored channels set: {len(channel_ids)} channels"
        )
