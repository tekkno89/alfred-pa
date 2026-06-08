# Plan 1: Infrastructure + Receive & Pre-filter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add new DB columns for delivery timing/grouping, extend Redis caching for pre-filter data, replace TriageEventRouter with a pre-filter worker that fans out message references (no content stored) to per-user queues.

**Architecture:** The Slack event handler is simplified to enqueue a lightweight pre-filter job with only message references. A pre-filter worker checks channel scope, ignore rules, and user eligibility via Redis-cached data, then fans out `(message_ref, user_id)` pairs to the existing `process_triage_job` worker (old pipeline stays active during transition). Cache invalidation is wired into all settings API endpoints.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Alembic, PostgreSQL, Redis, ARQ, FastAPI

**Spec:** `docs/superpowers/specs/2026-05-31-agent-driven-triage-design.md`

---

## File Structure

### New Files
- `backend/alembic/versions/056_add_delivery_timing_columns.py` — Migration for triage_classifications + triage_user_settings
- `backend/app/services/triage_prefilter.py` — Pre-filter worker logic
- `backend/tests/services/test_triage_prefilter.py` — Pre-filter unit tests

### Modified Files
- `backend/app/db/models/triage.py` — Add columns to TriageClassification and TriageUserSettings
- `backend/app/services/triage_cache.py` — Extend with ignore rules, channel users, channel rules caches
- `backend/app/api/triage.py` — Wire cache invalidation into settings endpoints
- `backend/app/api/slack.py` — Replace TriageEventRouter calls with pre-filter job enqueue
- `backend/app/worker/main.py` — Register new pre-filter worker function
- `backend/app/worker/tasks.py` — Add pre-filter task function
- `backend/tests/services/test_triage_cache.py` — Tests for extended cache

---

## Task 1: DB Migration — Delivery Timing & Grouping Columns

**Files:**
- Create: `backend/alembic/versions/056_add_delivery_timing_columns.py`
- Modify: `backend/app/db/models/triage.py:155-224` (TriageClassification)
- Modify: `backend/app/db/models/triage.py:18-69` (TriageUserSettings)

- [ ] **Step 1: Add columns to TriageClassification model**

In `backend/app/db/models/triage.py`, after line 210 (`processed_reason`), add:

```python
    # --- Agent-driven triage: delivery timing & grouping ---
    group_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    deliver_by: Mapped[datetime | None] = mapped_column(nullable=True)
    last_related_activity_at: Mapped[datetime | None] = mapped_column(nullable=True)
    settled_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)  # minutes
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

- [ ] **Step 2: Add columns to TriageUserSettings model**

In `backend/app/db/models/triage.py`, after line 61 (`active_hours_breakthrough`), add:

```python
    # --- Agent-driven triage: P1 delivery timing ---
    p1_max_wait_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    p1_settled_threshold_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
```

- [ ] **Step 3: Create Alembic migration**

Create `backend/alembic/versions/056_add_delivery_timing_columns.py`:

```python
"""add delivery timing and grouping columns

Revision ID: 056
Revises: 055
Create Date: 2026-06-07

"""

from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TriageClassification columns
    op.add_column("triage_classifications", sa.Column("group_id", sa.String(36), nullable=True))
    op.add_column("triage_classifications", sa.Column("deliver_by", sa.DateTime(timezone=True), nullable=True))
    op.add_column("triage_classifications", sa.Column("last_related_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("triage_classifications", sa.Column("settled_threshold", sa.Integer(), nullable=True))
    op.add_column("triage_classifications", sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("triage_classifications", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))

    op.create_index("idx_tc_group_id", "triage_classifications", ["group_id"], postgresql_where=sa.text("group_id IS NOT NULL"))
    op.create_index("idx_tc_delivery", "triage_classifications", ["user_id", "deliver_by"], postgresql_where=sa.text("queued_for_digest = true AND deliver_by IS NOT NULL"))

    # TriageUserSettings columns
    op.add_column("triage_user_settings", sa.Column("p1_max_wait_minutes", sa.Integer(), server_default="60", nullable=False))
    op.add_column("triage_user_settings", sa.Column("p1_settled_threshold_minutes", sa.Integer(), server_default="30", nullable=False))


def downgrade() -> None:
    op.drop_column("triage_user_settings", "p1_settled_threshold_minutes")
    op.drop_column("triage_user_settings", "p1_max_wait_minutes")

    op.drop_index("idx_tc_delivery", table_name="triage_classifications")
    op.drop_index("idx_tc_group_id", table_name="triage_classifications")

    op.drop_column("triage_classifications", "retry_count")
    op.drop_column("triage_classifications", "needs_review")
    op.drop_column("triage_classifications", "settled_threshold")
    op.drop_column("triage_classifications", "last_related_activity_at")
    op.drop_column("triage_classifications", "deliver_by")
    op.drop_column("triage_classifications", "group_id")
```

- [ ] **Step 4: Run migration locally**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run alembic upgrade head
```

- [ ] **Step 5: Verify migration**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run alembic current
```

Expected: `056 (head)`

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models/triage.py backend/alembic/versions/056_add_delivery_timing_columns.py
git commit -m "feat(db): add delivery timing and grouping columns

Add to triage_classifications: group_id, deliver_by,
last_related_activity_at, settled_threshold, needs_review, retry_count.
Add to triage_user_settings: p1_max_wait_minutes, p1_settled_threshold_minutes."
```

---

## Task 2: Extend TriageCacheService

**Files:**
- Modify: `backend/app/services/triage_cache.py`
- Create: `backend/tests/services/test_triage_cache.py`

- [ ] **Step 1: Write tests for new cache methods**

Create `backend/tests/services/test_triage_cache.py`:

```python
"""Tests for TriageCacheService extended caching."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=False)
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    redis.smembers = AsyncMock(return_value=set())
    redis.delete = AsyncMock()
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.expire = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    return redis


@pytest.fixture
def cache_service():
    from app.services.triage_cache import TriageCacheService
    return TriageCacheService()


class TestChannelUsersCache:
    @pytest.mark.asyncio
    async def test_get_channel_users_returns_cached(self, cache_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.smembers = AsyncMock(return_value={b"user1", b"user2"})
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_users("C123")
        assert result == {"user1", "user2"}

    @pytest.mark.asyncio
    async def test_get_channel_users_returns_none_when_not_cached(self, cache_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=0)
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.get_channel_users("C123")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_channel_users(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_channel_users("C123", {"user1", "user2"})
        mock_redis.delete.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()


class TestIgnoreRulesCache:
    @pytest.mark.asyncio
    async def test_is_sender_ignored_returns_true(self, cache_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.sismember = AsyncMock(return_value=True)
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_sender_ignored("user1", "C123", "U_SENDER")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_sender_ignored_returns_none_when_not_cached(self, cache_service, mock_redis):
        mock_redis.exists = AsyncMock(return_value=0)
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            result = await cache_service.is_sender_ignored("user1", "C123", "U_SENDER")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_ignore_rules(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.set_ignore_rules("user1", "C123", {"UBOT1", "UBOT2"})
        mock_redis.delete.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()


class TestCacheInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_channel_users(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_channel_users("C123")
        mock_redis.delete.assert_called_once_with("triage:channel_users:C123")

    @pytest.mark.asyncio
    async def test_invalidate_ignore_rules(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_ignore_rules("user1", "C123")
        mock_redis.delete.assert_called_once_with("triage:ignore_rules:user1:C123")

    @pytest.mark.asyncio
    async def test_invalidate_channel_rules(self, cache_service, mock_redis):
        with patch("app.services.triage_cache.get_redis", return_value=mock_redis):
            await cache_service.invalidate_channel_rules("user1", "C123")
        mock_redis.delete.assert_called_once_with("triage:channel_rules:user1:C123")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_triage_cache.py -v
```

Expected: FAIL (methods don't exist yet)

- [ ] **Step 3: Implement extended cache methods**

Replace `backend/app/services/triage_cache.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_triage_cache.py -v
```

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/triage_cache.py backend/tests/services/test_triage_cache.py
git commit -m "feat(cache): extend TriageCacheService with channel users, ignore rules, channel rules

New Redis caches with 5-min TTL:
- triage:channel_users:{channel_id} - user IDs monitoring a channel
- triage:ignore_rules:{user_id}:{channel_id} - ignored sender/bot IDs
- triage:channel_rules:{user_id}:{channel_id} - channel config hash

Each cache has get/set/invalidate methods."
```

---

## Task 3: Wire Cache Invalidation Into API Endpoints

**Files:**
- Modify: `backend/app/api/triage.py:92-105` (update_triage_settings)
- Modify: `backend/app/api/triage.py:295-314` (update_monitored_channel)
- Modify: `backend/app/api/triage.py:317-339` (remove_monitored_channel)
- Modify: `backend/app/api/triage.py:371-401` (add_source_rule)
- Modify: `backend/app/api/triage.py:404-427` (remove_source_rule)

- [ ] **Step 1: Add cache invalidation to update_monitored_channel**

In `backend/app/api/triage.py`, find the `update_monitored_channel` function (around line 295). After the DB update is committed, add:

```python
    # Invalidate caches for this channel
    cache = TriageCacheService()
    await cache.invalidate_channel_users(channel_id)
    await cache.invalidate_channel_rules(current_user.id, channel_id)
```

Ensure `TriageCacheService` is imported at the top of the file.

- [ ] **Step 2: Add cache invalidation to remove_monitored_channel**

In the `remove_monitored_channel` function (around line 317), after the delete, add:

```python
    cache = TriageCacheService()
    await cache.invalidate_channel_users(channel_id)
    await cache.invalidate_channel_rules(current_user.id, channel_id)
    await cache.invalidate_ignore_rules(current_user.id, channel_id)
```

- [ ] **Step 3: Add cache invalidation to add_source_rule**

In the `add_source_rule` function (around line 371), after the rule is created, add:

```python
    cache = TriageCacheService()
    await cache.invalidate_ignore_rules(current_user.id, channel_id)
```

- [ ] **Step 4: Add cache invalidation to remove_source_rule**

In the `remove_source_rule` function (around line 404), after the rule is deleted, add:

```python
    cache = TriageCacheService()
    await cache.invalidate_ignore_rules(current_user.id, channel_id)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/triage.py
git commit -m "feat(cache): wire cache invalidation into triage settings API endpoints

Invalidate Redis caches when:
- Monitored channel is updated/removed
- Source rules (ignore lists) are added/removed"
```

---

## Task 4: Build Pre-filter Worker

**Files:**
- Create: `backend/app/services/triage_prefilter.py`
- Create: `backend/tests/services/test_triage_prefilter.py`

- [ ] **Step 1: Write pre-filter tests**

Create `backend/tests/services/test_triage_prefilter.py`:

```python
"""Tests for triage pre-filter worker."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.triage_prefilter import TriagePrefilter


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.is_monitored_channel = AsyncMock(return_value=True)
    cache.get_channel_users = AsyncMock(return_value=None)
    cache.set_channel_users = AsyncMock()
    cache.is_sender_ignored = AsyncMock(return_value=None)
    cache.set_ignore_rules = AsyncMock()
    return cache


@pytest.fixture
def prefilter(mock_db, mock_cache):
    pf = TriagePrefilter(mock_db)
    pf.cache = mock_cache
    return pf


class TestChannelScopeCheck:
    @pytest.mark.asyncio
    async def test_unmonitored_channel_skipped(self, prefilter, mock_cache):
        mock_cache.is_monitored_channel = AsyncMock(return_value=False)
        result = await prefilter.get_applicable_users(
            channel_id="C_UNMONITORED",
            channel_type="channel",
            sender_slack_id="U_SENDER",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_monitored_channel_proceeds(self, prefilter, mock_cache, mock_db):
        mock_cache.is_monitored_channel = AsyncMock(return_value=True)
        mock_cache.get_channel_users = AsyncMock(return_value={"user1"})
        # Mock user lookup and should_triage
        with patch.object(prefilter, "_should_triage", return_value=True):
            with patch.object(prefilter, "_get_user_slack_id", return_value="U_OTHER"):
                result = await prefilter.get_applicable_users(
                    channel_id="C_MONITORED",
                    channel_type="channel",
                    sender_slack_id="U_SENDER",
                )
        assert len(result) == 1
        assert result[0] == "user1"


class TestSenderFiltering:
    @pytest.mark.asyncio
    async def test_sender_is_user_skipped(self, prefilter, mock_cache):
        mock_cache.is_monitored_channel = AsyncMock(return_value=True)
        mock_cache.get_channel_users = AsyncMock(return_value={"user1"})
        with patch.object(prefilter, "_should_triage", return_value=True):
            with patch.object(prefilter, "_get_user_slack_id", return_value="U_SENDER"):
                result = await prefilter.get_applicable_users(
                    channel_id="C123",
                    channel_type="channel",
                    sender_slack_id="U_SENDER",
                )
        assert result == []

    @pytest.mark.asyncio
    async def test_ignored_sender_skipped(self, prefilter, mock_cache):
        mock_cache.is_monitored_channel = AsyncMock(return_value=True)
        mock_cache.get_channel_users = AsyncMock(return_value={"user1"})
        mock_cache.is_sender_ignored = AsyncMock(return_value=True)
        with patch.object(prefilter, "_should_triage", return_value=True):
            with patch.object(prefilter, "_get_user_slack_id", return_value="U_OTHER"):
                result = await prefilter.get_applicable_users(
                    channel_id="C123",
                    channel_type="channel",
                    sender_slack_id="U_IGNORED",
                )
        assert result == []


class TestDMHandling:
    @pytest.mark.asyncio
    async def test_dm_skips_channel_check(self, prefilter, mock_cache):
        mock_cache.is_monitored_channel = AsyncMock(return_value=False)
        with patch.object(prefilter, "_get_dm_recipients", return_value=["user1"]):
            with patch.object(prefilter, "_should_triage", return_value=True):
                result = await prefilter.get_applicable_users(
                    channel_id="D_DM",
                    channel_type="im",
                    sender_slack_id="U_SENDER",
                    authorizations=[{"user_id": "U_RECIPIENT"}],
                )
        assert result == ["user1"]
        mock_cache.is_monitored_channel.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_triage_prefilter.py -v
```

Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Implement pre-filter**

Create `backend/app/services/triage_prefilter.py`:

```python
"""Triage pre-filter: deterministic message scoping and user fan-out.

Stage 2 of the agent-driven triage pipeline. No LLM calls.
Determines which Alfred users should receive a message for classification.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import UserRepository
from app.db.repositories.triage import (
    MonitoredChannelRepository,
    TriageUserSettingsRepository,
    ChannelSourceRuleRepository,
)
from app.services.focus import FocusModeService
from app.services.triage_cache import TriageCacheService

logger = logging.getLogger(__name__)


class TriagePrefilter:
    """Determines which users should receive a message for triage classification.

    Uses Redis-cached data for fast lookups:
    - Monitored channels SET
    - Channel users SET per channel
    - Ignore rules SET per user+channel

    Falls back to DB queries on cache miss, then populates cache.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cache = TriageCacheService()
        self.user_repo = UserRepository(db)
        self.channel_repo = MonitoredChannelRepository(db)
        self.settings_repo = TriageUserSettingsRepository(db)
        self.focus_service = FocusModeService(db)
        self.source_rule_repo = ChannelSourceRuleRepository(db)

    async def get_applicable_users(
        self,
        channel_id: str,
        channel_type: str,
        sender_slack_id: str,
        authorizations: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """Get list of user_ids that should receive this message for triage.

        Args:
            channel_id: Slack channel ID
            channel_type: "channel", "group", "im", "mpim"
            sender_slack_id: Slack user ID of the sender
            authorizations: Slack event authorizations (for DMs)

        Returns:
            List of Alfred user IDs that should receive this message
        """
        # DMs skip channel monitoring check
        if channel_type in ("im", "mpim"):
            return await self._get_dm_applicable_users(
                channel_id, sender_slack_id, authorizations or []
            )

        # Channel messages: check if channel is monitored
        if not await self.cache.is_monitored_channel(channel_id):
            return []

        return await self._get_channel_applicable_users(
            channel_id, sender_slack_id
        )

    async def _get_channel_applicable_users(
        self,
        channel_id: str,
        sender_slack_id: str,
    ) -> list[str]:
        """Get applicable users for a channel message."""
        # Get users monitoring this channel (cache or DB)
        user_ids = await self.cache.get_channel_users(channel_id)
        if user_ids is None:
            monitored = await self.channel_repo.get_users_for_channel(channel_id)
            user_ids = {str(mc.user_id) for mc in monitored if mc.is_active}
            await self.cache.set_channel_users(channel_id, user_ids)

        applicable = []
        for user_id in user_ids:
            # Skip if sender is the user themselves
            user_slack_id = await self._get_user_slack_id(user_id)
            if user_slack_id == sender_slack_id:
                continue

            # Check ignore rules (cache or DB)
            ignored = await self.cache.is_sender_ignored(
                user_id, channel_id, sender_slack_id
            )
            if ignored is None:
                # Cache miss: load from DB
                ignore_rules = await self.source_rule_repo.get_ignore_rules(
                    user_id, channel_id
                )
                ignored_ids = {r.slack_entity_id for r in ignore_rules}
                await self.cache.set_ignore_rules(user_id, channel_id, ignored_ids)
                ignored = sender_slack_id in ignored_ids
            if ignored:
                continue

            # Check if user has triage enabled
            if not await self._should_triage(user_id):
                continue

            applicable.append(user_id)

        return applicable

    async def _get_dm_applicable_users(
        self,
        channel_id: str,
        sender_slack_id: str,
        authorizations: list[dict[str, Any]],
    ) -> list[str]:
        """Get applicable users for a DM."""
        applicable = []
        for auth in authorizations:
            auth_slack_id = auth.get("user_id")
            if not auth_slack_id or auth_slack_id == sender_slack_id:
                continue
            # Is this an Alfred user?
            user = await self.user_repo.get_by_slack_id(auth_slack_id)
            if not user:
                continue
            if not await self._should_triage(str(user.id)):
                continue
            applicable.append(str(user.id))
        return applicable

    async def _should_triage(self, user_id: str) -> bool:
        """Check if user has triage enabled (always-on or focus mode)."""
        settings = await self.settings_repo.get_by_user_id(user_id)
        if not settings:
            return False
        if settings.is_always_on:
            return True
        return await self.focus_service.is_in_focus_mode(user_id)

    async def _get_user_slack_id(self, user_id: str) -> str | None:
        """Get a user's Slack ID from their Alfred user ID."""
        user = await self.user_repo.get(user_id)
        return user.slack_user_id if user else None
```

- [ ] **Step 4: Check if ChannelSourceRuleRepository has get_ignore_rules**

Read `backend/app/db/repositories/triage.py` and check if `ChannelSourceRuleRepository` has a `get_ignore_rules` method. If not, add one:

```python
async def get_ignore_rules(
    self, user_id: str, channel_id: str
) -> list[ChannelSourceRule]:
    """Get all ignore rules for a user+channel."""
    from app.db.models.triage import MonitoredChannel
    result = await self.db.execute(
        select(ChannelSourceRule)
        .join(MonitoredChannel, ChannelSourceRule.monitored_channel_id == MonitoredChannel.id)
        .where(MonitoredChannel.user_id == user_id)
        .where(MonitoredChannel.slack_channel_id == channel_id)
        .where(ChannelSourceRule.action == "ignore")
    )
    return list(result.scalars().all())
```

- [ ] **Step 5: Run tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_triage_prefilter.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/triage_prefilter.py backend/tests/services/test_triage_prefilter.py backend/app/db/repositories/triage.py
git commit -m "feat(prefilter): add triage pre-filter worker

Deterministic pre-filter that checks channel scope, ignore rules,
and user eligibility. Uses Redis-cached data with DB fallback.
Handles both channel messages and DMs."
```

---

## Task 5: Add Pre-filter Task and Register in Worker

**Files:**
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/worker/main.py`

- [ ] **Step 1: Add pre-filter task function**

In `backend/app/worker/tasks.py`, add after the existing `process_triage_job` function:

```python
async def prefilter_triage_message(
    ctx: dict,
    channel_id: str,
    channel_type: str,
    sender_slack_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    event_type: str = "message",
    bot_id: str | None = None,
    subtype: str | None = None,
    authorizations: list[dict] | None = None,
    message_text: str = "",  # Passed during transition for old pipeline compatibility
) -> dict:
    """
    Pre-filter a Slack message and fan out to per-user triage jobs.

    Stage 2 of the agent-driven triage pipeline.
    No message content is stored — only references are passed through.

    Args:
        ctx: ARQ context
        channel_id: Slack channel ID
        channel_type: "channel", "group", "im", "mpim"
        sender_slack_id: Slack user ID of sender
        message_ts: Message timestamp (unique ID in Slack)
        thread_ts: Thread parent timestamp (if reply)
        event_type: "message" or "app_mention"
        bot_id: Bot ID if sender is a bot
        subtype: Message subtype
        authorizations: Slack event authorizations (for DMs)

    Returns:
        Dict with status and count of users queued
    """
    from app.services.triage_prefilter import TriagePrefilter
    from app.worker.scheduler import get_redis_pool

    async with get_db_session() as db:
        prefilter = TriagePrefilter(db)
        applicable_users = await prefilter.get_applicable_users(
            channel_id=channel_id,
            channel_type=channel_type,
            sender_slack_id=sender_slack_id,
            authorizations=authorizations,
        )

    if not applicable_users:
        return {
            "status": "no_applicable_users",
            "channel_id": channel_id,
            "message_ts": message_ts,
        }

    # Fan out: enqueue one triage job per applicable user
    # During transition, we enqueue the existing process_triage_job
    pool = await get_redis_pool()
    for user_id in applicable_users:
        await pool.enqueue_job(
            "process_triage_job",
            user_id=user_id,
            event_type=event_type,
            channel_id=channel_id,
            sender_slack_id=sender_slack_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,  # Passed through for old pipeline; removed in Plan 2
            bot_id=bot_id,
        )

    logger.info(
        f"Pre-filter: message {message_ts} in {channel_id} "
        f"queued for {len(applicable_users)} users"
    )

    return {
        "status": "queued",
        "channel_id": channel_id,
        "message_ts": message_ts,
        "user_count": len(applicable_users),
    }
```

- [ ] **Step 2: Register in worker**

In `backend/app/worker/main.py`, add `prefilter_triage_message` to the `functions` list (around line 88):

```python
functions = [
    expire_focus_session,
    transition_pomodoro,
    send_todo_reminder,
    send_digest,
    process_triage_job,
    prefilter_triage_message,  # NEW
    refresh_slack_channel_cache,
    # ... rest of existing functions
]
```

And add the import at the top of the file.

- [ ] **Step 3: Commit**

```bash
git add backend/app/worker/tasks.py backend/app/worker/main.py
git commit -m "feat(worker): add prefilter_triage_message task

Pre-filter task receives message references, determines applicable users,
and fans out to per-user process_triage_job (existing pipeline).
No message content stored — references only."
```

---

## Task 6: Modify Slack Event Handler

**Files:**
- Modify: `backend/app/api/slack.py:383-403` (channel message path)
- Modify: `backend/app/api/slack.py:567-574` (DM/@mention path)

- [ ] **Step 1: Replace channel message triage routing**

In `backend/app/api/slack.py`, find lines 383-403 (channel message without mentions). Replace the `TriageEventRouter` call with a pre-filter job enqueue:

```python
    elif not channel_id.startswith("D") and not _extract_mentioned_user_ids(original_text):
        try:
            from app.worker.scheduler import get_redis_pool

            pool = await get_redis_pool()
            await pool.enqueue_job(
                "prefilter_triage_message",
                channel_id=channel_id,
                channel_type=event.get("channel_type", "channel"),
                sender_slack_id=user_id,
                message_ts=event.get("ts", ""),
                thread_ts=event.get("thread_ts"),
                event_type=event.get("type", "message"),
                bot_id=event.get("bot_id"),
                subtype=event.get("subtype"),
                authorizations=authorizations,
                message_text=event.get("text", ""),  # Transition: passed to old pipeline
            )
        except Exception:
            logger.exception("Failed to enqueue pre-filter job for channel message")
        return
```

- [ ] **Step 2: Replace DM/@mention triage routing**

In `backend/app/api/slack.py`, find lines 567-574 (DM/@mention path). Replace:

```python
    # Route to triage (DMs and @mentions)
    try:
        from app.worker.scheduler import get_redis_pool

        pool = await get_redis_pool()
        await pool.enqueue_job(
            "prefilter_triage_message",
            channel_id=channel_id,
            channel_type=event.get("channel_type", "im" if channel_id.startswith("D") else "channel"),
            sender_slack_id=user_id,
            message_ts=event.get("ts", ""),
            thread_ts=event.get("thread_ts"),
            event_type=event.get("type", "message"),
            bot_id=event.get("bot_id"),
            subtype=event.get("subtype"),
            authorizations=authorizations,
            message_text=event.get("text", ""),  # Transition: passed to old pipeline
        )
    except Exception:
        logger.exception("Failed to enqueue pre-filter job for DM/@mention")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/slack.py
git commit -m "feat(slack): replace TriageEventRouter with pre-filter job enqueue

Slack event handler now enqueues prefilter_triage_message job with
only message references (no content stored). The pre-filter worker
handles channel scoping, ignore rules, and user fan-out."
```

---

## Task 7: Deploy and Verify

- [ ] **Step 1: Run all tests**

```bash
cd backend && JWT_SECRET=test-secret DATABASE_URL=postgresql+asyncpg://alfred:alfred@localhost:5432/alfred uv run pytest tests/services/test_triage_cache.py tests/services/test_triage_prefilter.py -v
```

- [ ] **Step 2: Build frontend (check for type errors)**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Push and deploy**

```bash
git push origin slack-triage-refactor-3
```

Deploy to production:
```bash
gcloud compute ssh --zone "us-central1-c" "alfred-pa" --project "tyler-knotek-e1ltzltz-af40" --command "cd /opt/alfred && sudo git pull && sudo docker compose -f docker-compose.prod.yml up -d --build backend worker"
```

- [ ] **Step 4: Run migration on production**

The migration will run automatically via the `migrate` container on startup.

- [ ] **Step 5: Verify in production**

Check backend logs for pre-filter messages:
```bash
gcloud compute ssh --zone "us-central1-c" "alfred-pa" --command "sudo docker logs alfred-backend-1 --tail=50 2>&1 | grep -i prefilter"
```

Send a test message in a monitored Slack channel and verify:
1. Pre-filter job is enqueued (check worker logs)
2. Pre-filter fans out to process_triage_job for applicable users
3. Classification still works as before (existing pipeline handles it)

---

## Transition Notes

- The pre-filter replaces `TriageEventRouter` but still enqueues `process_triage_job` (the old pipeline)
- This means classification behavior is unchanged — only the routing layer is new
- Plan 2 will replace `process_triage_job` with the new triage agent
- `TriageEventRouter` can be removed in Plan 4 (cleanup) once Plan 2 is deployed
