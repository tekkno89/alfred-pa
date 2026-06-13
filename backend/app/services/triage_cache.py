"""Redis caching for triage pre-filter data."""

import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

MONITORED_CHANNELS_KEY = "triage:monitored_channels_set"
CHANNEL_USERS_PREFIX = "triage:channel_users:"
IGNORE_RULES_PREFIX = "triage:ignore_rules:"
CHANNEL_RULES_PREFIX = "triage:channel_rules:"

CACHE_TTL = 300  # 5 minutes


class TriageCacheService:
    """Manages Redis caches for triage pre-filter data.

    Caches:
    - Monitored channels SET (no TTL, invalidated on add/remove)
    - Channel users SET per channel (5 min TTL)
    - Ignore rules SET per user+channel (5 min TTL)
    - Channel rules HASH per user+channel (5 min TTL)
    """

    # --- Monitored Channels (existing) ---

    async def is_monitored_channel(self, channel_id: str) -> bool:
        """Check if a channel is in the monitored set. O(1)."""
        redis = await get_redis()
        return bool(await redis.sismember(MONITORED_CHANNELS_KEY, channel_id))

    async def add_channel(self, channel_id: str) -> None:
        """Add a channel to the monitored set."""
        redis = await get_redis()
        await redis.sadd(MONITORED_CHANNELS_KEY, channel_id)

    async def remove_channel(self, channel_id: str) -> None:
        """Remove a channel from the monitored set."""
        redis = await get_redis()
        await redis.srem(MONITORED_CHANNELS_KEY, channel_id)

    async def rebuild_set(self, db) -> None:
        """Rebuild the monitored channel set from the database."""
        from app.db.repositories.triage import MonitoredChannelRepository

        repo = MonitoredChannelRepository(db)
        channel_ids = await repo.get_all_active_channel_ids()
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.delete(MONITORED_CHANNELS_KEY)
        if channel_ids:
            pipe.sadd(MONITORED_CHANNELS_KEY, *channel_ids)
        await pipe.execute()
        logger.info(f"Rebuilt monitored channels set: {len(channel_ids)} channels")

    # --- Channel Users (which users monitor a channel) ---

    async def get_channel_users(self, channel_id: str) -> set[str] | None:
        """Get user IDs monitoring this channel. Returns None if not cached."""
        redis = await get_redis()
        key = f"{CHANNEL_USERS_PREFIX}{channel_id}"
        if not await redis.exists(key):
            return None
        members = await redis.smembers(key)
        return {m.decode() if isinstance(m, bytes) else m for m in members}

    async def set_channel_users(self, channel_id: str, user_ids: set[str]) -> None:
        """Cache the set of user IDs monitoring this channel."""
        redis = await get_redis()
        key = f"{CHANNEL_USERS_PREFIX}{channel_id}"
        pipe = redis.pipeline()
        pipe.delete(key)
        if user_ids:
            pipe.sadd(key, *user_ids)
        pipe.expire(key, CACHE_TTL)
        await pipe.execute()

    async def invalidate_channel_users(self, channel_id: str) -> None:
        """Invalidate the channel users cache for a channel."""
        redis = await get_redis()
        await redis.delete(f"{CHANNEL_USERS_PREFIX}{channel_id}")

    # --- Ignore Rules (which senders/bots to ignore per user+channel) ---

    async def is_sender_ignored(
        self, user_id: str, channel_id: str, sender_slack_id: str
    ) -> bool | None:
        """Check if sender is ignored. Returns None if not cached."""
        redis = await get_redis()
        key = f"{IGNORE_RULES_PREFIX}{user_id}:{channel_id}"
        if not await redis.exists(key):
            return None
        return bool(await redis.sismember(key, sender_slack_id))

    async def set_ignore_rules(
        self, user_id: str, channel_id: str, ignored_ids: set[str]
    ) -> None:
        """Cache the set of ignored sender/bot IDs for a user+channel."""
        redis = await get_redis()
        key = f"{IGNORE_RULES_PREFIX}{user_id}:{channel_id}"
        pipe = redis.pipeline()
        pipe.delete(key)
        if ignored_ids:
            pipe.sadd(key, *ignored_ids)
        else:
            # Store empty marker so we know cache is populated
            pipe.sadd(key, "__EMPTY__")
        pipe.expire(key, CACHE_TTL)
        await pipe.execute()

    async def invalidate_ignore_rules(self, user_id: str, channel_id: str) -> None:
        """Invalidate ignore rules cache for a user+channel."""
        redis = await get_redis()
        await redis.delete(f"{IGNORE_RULES_PREFIX}{user_id}:{channel_id}")

    # --- Channel Rules (user's channel config) ---

    async def get_channel_rules(
        self, user_id: str, channel_id: str
    ) -> dict[str, str] | None:
        """Get cached channel rules. Returns None if not cached."""
        redis = await get_redis()
        key = f"{CHANNEL_RULES_PREFIX}{user_id}:{channel_id}"
        if not await redis.exists(key):
            return None
        data = await redis.hgetall(key)
        return {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in data.items()
        }

    async def set_channel_rules(
        self, user_id: str, channel_id: str, rules: dict[str, str]
    ) -> None:
        """Cache channel rules for a user+channel."""
        redis = await get_redis()
        key = f"{CHANNEL_RULES_PREFIX}{user_id}:{channel_id}"
        pipe = redis.pipeline()
        pipe.delete(key)
        if rules:
            pipe.hset(key, mapping=rules)
        pipe.expire(key, CACHE_TTL)
        await pipe.execute()

    async def invalidate_channel_rules(self, user_id: str, channel_id: str) -> None:
        """Invalidate channel rules cache for a user+channel."""
        redis = await get_redis()
        await redis.delete(f"{CHANNEL_RULES_PREFIX}{user_id}:{channel_id}")
