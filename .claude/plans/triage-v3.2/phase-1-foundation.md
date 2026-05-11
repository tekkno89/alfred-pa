# Phase 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish action-based classification, tiered message storage, engagement-gated delivery, and review flag infrastructure.

**Duration:** 3-4 weeks

**Architecture:** Rename `priority_level` to `action` throughout codebase. Implement `SlackMessageCache` for non-sensitive public channels only. Add `sensitive` flag to `MonitoredChannel`. Wire engagement check to gate `notify_now` delivery. Add `review` boolean flag for low-confidence classifications.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, Redis

---

## Requirements Covered

- **R1:** Action-based classification (notify_now, summarize_next, summarize_eod, ignore)
- **R-Cache:** Tiered message storage (cached for non-sensitive, on-demand fetch for sensitive)
- **R-ReviewState:** Orthogonal `review` flag
- **R2a:** Context fetching with walkback
- **R2b:** Engagement check gating all delivery paths
- **R-Reliability:** Backoff retry for classification and engagement failures

---

## File Structure

### Create

```
backend/app/services/slack_message_cache.py
backend/app/services/sensitive_content_fetcher.py
backend/alembic/versions/038_add_sensitive_to_monitored_channels.py
backend/alembic/versions/039_add_slack_message_cache.py
backend/alembic/versions/040_add_feedback_embeddings.py
backend/alembic/versions/041_add_sender_action_distributions.py
backend/alembic/versions/042_rename_priority_to_action.py
backend/alembic/versions/043_add_triage_classification_new_fields.py
backend/tests/unit/test_slack_message_cache.py
backend/tests/unit/test_sensitive_content_fetcher.py
```

### Modify

```
backend/app/db/models/triage.py
backend/app/db/models/__init__.py
backend/app/db/repositories/triage.py
backend/app/services/triage_classifier.py
backend/app/services/triage_pipeline.py
backend/app/services/triage_enrichment.py
backend/app/services/digest_response_checker.py
backend/app/schemas/triage.py
backend/app/api/triage.py
backend/worker/tasks.py
frontend/src/types/index.ts
frontend/src/pages/TriagePage.tsx
frontend/src/components/triage/ActionBadge.tsx
```

---

## Task 1: Add `sensitive` flag to MonitoredChannel

**Files:**
- Create: `backend/alembic/versions/038_add_sensitive_to_monitored_channels.py`
- Modify: `backend/app/db/models/triage.py:101-132`
- Modify: `backend/app/schemas/triage.py:103-145`

### Step 1: Write the migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/038_add_sensitive_to_monitored_channels.py
"""add sensitive to monitored channels

Revision ID: 038
Revises: 037_add_updated_at_to_conversation_summaries
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa

revision = '038'
down_revision = '037_add_updated_at_to_conversation_summaries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'monitored_channels',
        sa.Column('sensitive', sa.Boolean(), nullable=False, server_default='false')
    )
    # Set default: private channels are sensitive by default
    op.execute(
        "UPDATE monitored_channels SET sensitive = true WHERE channel_type = 'private'"
    )


def downgrade() -> None:
    op.drop_column('monitored_channels', 'sensitive')
```

- [ ] **Run migration**

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected: Migration applies successfully.

### Step 2: Update model

- [ ] **Modify MonitoredChannel model**

```python
# backend/app/db/models/triage.py
# Add after line 118 (after summary_behavior field):

    sensitive: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
```

### Step 3: Update schemas

- [ ] **Update MonitoredChannelCreate schema**

```python
# backend/app/schemas/triage.py
# Modify MonitoredChannelCreate class:

class MonitoredChannelCreate(BaseModel):
    """Request to add a monitored channel."""

    slack_channel_id: str = Field(..., min_length=1)
    channel_name: str = Field(..., min_length=1)
    channel_type: str = Field("public", pattern="^(public|private)$")
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")
    summary_behavior: str = Field("default", pattern="^(default|initial_only)$")
    sensitive: bool = Field(False, description="Mark channel as sensitive (no message caching)")
```

- [ ] **Update MonitoredChannelUpdate schema**

```python
# backend/app/schemas/triage.py
# Add to MonitoredChannelUpdate class:

    sensitive: bool | None = None
```

- [ ] **Update MonitoredChannelResponse schema**

```python
# backend/app/schemas/triage.py
# Add to MonitoredChannelResponse class:

    sensitive: bool = False
```

### Step 4: Update repository

- [ ] **Update MonitoredChannelRepository.create method**

```python
# backend/app/db/repositories/triage.py
# In MonitoredChannelRepository.create method, update to handle sensitive field:

    async def create(self, channel: MonitoredChannel) -> MonitoredChannel:
        # Set sensitive default based on channel_type if not specified
        if channel.sensitive is None:
            channel.sensitive = channel.channel_type == "private"
        self.db.add(channel)
        await self.db.commit()
        await self.db.refresh(channel)
        return channel
```

### Step 5: Write tests

- [ ] **Add test for sensitive flag default**

```python
# backend/tests/api/test_triage_settings.py
# Add test:

async def test_monitored_channel_sensitive_default(
    db_session: AsyncSession, test_user
):
    """Private channels should default to sensitive=true."""
    repo = MonitoredChannelRepository(db_session)
    
    # Public channel
    public = MonitoredChannel(
        user_id=test_user.id,
        slack_channel_id="C_PUBLIC",
        channel_name="public-channel",
        channel_type="public",
        priority="medium",
    )
    await repo.create(public)
    assert public.sensitive is False
    
    # Private channel
    private = MonitoredChannel(
        user_id=test_user.id,
        slack_channel_id="C_PRIVATE",
        channel_name="private-channel",
        channel_type="private",
        priority="medium",
    )
    await repo.create(private)
    assert private.sensitive is True
```

- [ ] **Run tests**

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/api/test_triage_settings.py -v -k sensitive
```

Expected: Tests pass.

### Step 6: Commit

```bash
git add backend/alembic/versions/038_add_sensitive_to_monitored_channels.py \
        backend/app/db/models/triage.py \
        backend/app/schemas/triage.py \
        backend/app/db/repositories/triage.py \
        backend/tests/api/test_triage_settings.py
git commit -m "feat(triage): add sensitive flag to MonitoredChannel"
```

---

## Task 2: Create SlackMessageCache model and service

**Files:**
- Create: `backend/alembic/versions/039_add_slack_message_cache.py`
- Create: `backend/app/db/models/slack_message_cache.py`
- Modify: `backend/app/db/models/__init__.py`
- Create: `backend/app/services/slack_message_cache.py`
- Create: `backend/tests/unit/test_slack_message_cache.py`

### Step 1: Write the migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/039_add_slack_message_cache.py
"""add slack message cache

Revision ID: 039
Revises: 038
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa

revision = '039'
down_revision = '038'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'slack_message_cache',
        sa.Column('workspace_id', sa.String(50), nullable=False),
        sa.Column('channel_id', sa.String(50), nullable=False),
        sa.Column('message_ts', sa.String(50), nullable=False),
        sa.Column('parent_thread_ts', sa.String(50), nullable=True),
        sa.Column('sender_slack_id', sa.String(50), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('is_bot', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cached_at', sa.DateTime(timezone=True), 
                  nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('workspace_id', 'channel_id', 'message_ts')
    )
    op.create_index('ix_slack_message_cache_thread', 'slack_message_cache', ['parent_thread_ts'])
    op.create_index('ix_slack_message_cache_cached_at', 'slack_message_cache', ['cached_at'])


def downgrade() -> None:
    op.drop_index('ix_slack_message_cache_cached_at')
    op.drop_index('ix_slack_message_cache_thread')
    op.drop_table('slack_message_cache')
```

- [ ] **Run migration**

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 2: Create the model

- [ ] **Create model file**

```python
# backend/app/db/models/slack_message_cache.py
"""Slack message cache for non-sensitive public channels."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SlackMessageCache(Base):
    """Workspace-scoped cache of raw message text for non-sensitive public channels.

    This is the ONLY place raw Slack message text is persisted.
    - Public non-sensitive channels: cached with 7-day TTL
    - Private channels: NOT cached (sensitive=true)
    - DMs: NOT cached (hardcoded, never stored)

    Multiple users monitoring the same channel share the same cache rows.
    """

    __tablename__ = "slack_message_cache"

    workspace_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    message_ts: Mapped[str] = mapped_column(String(50), primary_key=True)
    parent_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now(),
        index=True
    )

    def __repr__(self) -> str:
        return f"<SlackMessageCache({self.channel_id}/{self.message_ts})>"
```

- [ ] **Update models __init__.py**

```python
# backend/app/db/models/__init__.py
# Add to imports:

from app.db.models.slack_message_cache import SlackMessageCache

# Add to __all__:
    "SlackMessageCache",
```

### Step 3: Create the service

- [ ] **Create service file**

```python
# backend/app/services/slack_message_cache.py
"""Slack message cache service for non-sensitive public channels."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.slack_message_cache import SlackMessageCache
from app.db.models.triage import MonitoredChannel
from app.db.repositories.triage import MonitoredChannelRepository
from app.services.slack import SlackService

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7


class SlackMessageCacheService:
    """Manages the workspace-scoped message cache for non-sensitive public channels.

    Cache Rules:
    - Public channels with sensitive=false: CACHED (7-day TTL)
    - Public channels with sensitive=true: NOT cached
    - Private channels: NOT cached (sensitive defaults to true)
    - DMs: NOT cached (hardcoded, never stored)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.channel_repo = MonitoredChannelRepository(db)

    async def get_message(
        self,
        workspace_id: str,
        channel_id: str,
        message_ts: str,
    ) -> str | None:
        """Get cached message text, or None if not cached.

        Does NOT fetch from Slack - call fetch_and_cache() for that.
        """
        result = await self.db.execute(
            select(SlackMessageCache).where(
                SlackMessageCache.workspace_id == workspace_id,
                SlackMessageCache.channel_id == channel_id,
                SlackMessageCache.message_ts == message_ts,
            )
        )
        cached = result.scalar_one_or_none()
        return cached.text if cached else None

    async def get_thread_messages(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> list[tuple[str, str, str]]:
        """Get all cached messages in a thread.

        Returns list of (message_ts, sender_slack_id, text) tuples.
        """
        result = await self.db.execute(
            select(SlackMessageCache).where(
                SlackMessageCache.workspace_id == workspace_id,
                SlackMessageCache.channel_id == channel_id,
                SlackMessageCache.parent_thread_ts == thread_ts,
            ).order_by(SlackMessageCache.created_at)
        )
        messages = result.scalars().all()
        return [(m.message_ts, m.sender_slack_id, m.text) for m in messages]

    async def should_cache(
        self,
        user_id: str,
        channel_id: str,
    ) -> bool:
        """Check if messages from this channel should be cached.

        Returns True only for public non-sensitive channels.
        """
        mc = await self.channel_repo.get_by_user_and_channel(user_id, channel_id)
        if not mc:
            return False
        if mc.channel_type == "private":
            return False
        return not mc.sensitive

    async def fetch_and_cache(
        self,
        workspace_id: str,
        channel_id: str,
        message_ts: str,
        slack_service: SlackService,
    ) -> str | None:
        """Fetch message from Slack and cache if allowed.

        Returns message text or None if fetch failed.
        """
        try:
            response = await slack_service.client.conversations_history(
                channel=channel_id,
                latest=message_ts,
                limit=1,
                inclusive=True,
            )
            messages = response.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            text = msg.get("text", "")
            sender_id = msg.get("user", msg.get("bot_id", "unknown"))
            is_bot = msg.get("bot_id") is not None

            # Parse Slack timestamp to datetime
            created_at = None
            try:
                ts_float = float(message_ts)
                created_at = datetime.utcfromtimestamp(ts_float)
            except (ValueError, TypeError):
                pass

            # Check for thread parent
            parent_thread_ts = msg.get("thread_ts")
            if parent_thread_ts == message_ts:
                parent_thread_ts = None  # This IS the thread parent

            cached = SlackMessageCache(
                workspace_id=workspace_id,
                channel_id=channel_id,
                message_ts=message_ts,
                parent_thread_ts=parent_thread_ts,
                sender_slack_id=sender_id,
                text=text,
                is_bot=is_bot,
                created_at=created_at,
            )
            self.db.add(cached)
            await self.db.commit()

            logger.debug(f"Cached message {channel_id}/{message_ts}")
            return text

        except Exception as e:
            logger.warning(f"Failed to fetch/cache message {channel_id}/{message_ts}: {e}")
            return None

    async def cache_thread(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        slack_service: SlackService,
    ) -> list[tuple[str, str, str]]:
        """Fetch and cache all messages in a thread.

        Returns list of (message_ts, sender_slack_id, text) tuples.
        """
        try:
            response = await slack_service.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=100,
            )
            messages = response.get("messages", [])
            results = []

            for msg in messages:
                msg_ts = msg.get("ts")
                text = msg.get("text", "")
                sender_id = msg.get("user", msg.get("bot_id", "unknown"))
                is_bot = msg.get("bot_id") is not None

                created_at = None
                try:
                    ts_float = float(msg_ts)
                    created_at = datetime.utcfromtimestamp(ts_float)
                except (ValueError, TypeError):
                    pass

                # Check if already cached
                existing = await self.get_message(workspace_id, channel_id, msg_ts)
                if existing is None:
                    cached = SlackMessageCache(
                        workspace_id=workspace_id,
                        channel_id=channel_id,
                        message_ts=msg_ts,
                        parent_thread_ts=thread_ts if msg_ts != thread_ts else None,
                        sender_slack_id=sender_id,
                        text=text,
                        is_bot=is_bot,
                        created_at=created_at,
                    )
                    self.db.add(cached)

                results.append((msg_ts, sender_id, text))

            await self.db.commit()
            return results

        except Exception as e:
            logger.warning(f"Failed to cache thread {channel_id}/{thread_ts}: {e}")
            return []

    async def cleanup_expired(self) -> int:
        """Delete messages older than TTL. Called by nightly job.

        Returns count of deleted rows.
        """
        cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
        result = await self.db.execute(
            delete(SlackMessageCache).where(SlackMessageCache.cached_at < cutoff)
        )
        deleted = result.rowcount
        await self.db.commit()
        logger.info(f"Cleaned up {deleted} expired cache entries older than {CACHE_TTL_DAYS} days")
        return deleted
```

### Step 4: Write unit tests

- [ ] **Create test file**

```python
# backend/tests/unit/test_slack_message_cache.py
"""Unit tests for SlackMessageCacheService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.slack_message_cache import SlackMessageCacheService
from app.db.models.slack_message_cache import SlackMessageCache
from app.db.models.triage import MonitoredChannel


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def cache_service(mock_db):
    return SlackMessageCacheService(mock_db)


class TestSlackMessageCacheService:
    def test_cache_ttl_is_7_days(self):
        """Verify TTL constant."""
        from app.services.slack_message_cache import CACHE_TTL_DAYS
        assert CACHE_TTL_DAYS == 7

    @pytest.mark.asyncio
    async def test_get_message_returns_none_when_not_cached(self, cache_service, mock_db):
        """get_message returns None for cache miss."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        
        result = await cache_service.get_message("W123", "C123", "123.456")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_message_returns_text_when_cached(self, cache_service, mock_db):
        """get_message returns text for cache hit."""
        cached_msg = SlackMessageCache(
            workspace_id="W123",
            channel_id="C123",
            message_ts="123.456",
            sender_slack_id="U123",
            text="Hello world",
            cached_at=datetime.utcnow(),
        )
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=cached_msg)
        )
        
        result = await cache_service.get_message("W123", "C123", "123.456")
        
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_should_cache_returns_false_for_private_channel(self, cache_service):
        """Private channels should never be cached."""
        with patch.object(
            cache_service.channel_repo, 
            'get_by_user_and_channel',
            AsyncMock(return_value=MonitoredChannel(
                channel_type="private",
                sensitive=True,
            ))
        ):
            result = await cache_service.should_cache("user1", "C_PRIVATE")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_cache_returns_false_for_sensitive_public(self, cache_service):
        """Public channels marked sensitive should not be cached."""
        with patch.object(
            cache_service.channel_repo,
            'get_by_user_and_channel',
            AsyncMock(return_value=MonitoredChannel(
                channel_type="public",
                sensitive=True,
            ))
        ):
            result = await cache_service.should_cache("user1", "C_SENSITIVE")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_cache_returns_true_for_non_sensitive_public(self, cache_service):
        """Public non-sensitive channels should be cached."""
        with patch.object(
            cache_service.channel_repo,
            'get_by_user_and_channel',
            AsyncMock(return_value=MonitoredChannel(
                channel_type="public",
                sensitive=False,
            ))
        ):
            result = await cache_service.should_cache("user1", "C_PUBLIC")
            assert result is True

    @pytest.mark.asyncio
    async def test_should_cache_returns_false_for_unmonitored_channel(self, cache_service):
        """Unmonitored channels should not be cached."""
        with patch.object(
            cache_service.channel_repo,
            'get_by_user_and_channel',
            AsyncMock(return_value=None)
        ):
            result = await cache_service.should_cache("user1", "C_UNMONITORED")
            assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_deletes_old_messages(self, cache_service, mock_db):
        """Cleanup should delete messages older than TTL."""
        mock_result = MagicMock()
        mock_result.rowcount = 42
        mock_db.execute.return_value = mock_result
        
        result = await cache_service.cleanup_expired()
        
        assert result == 42
        mock_db.commit.assert_called_once()
```

- [ ] **Run tests**

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_slack_message_cache.py -v
```

Expected: All tests pass.

### Step 5: Commit

```bash
git add backend/alembic/versions/039_add_slack_message_cache.py \
        backend/app/db/models/slack_message_cache.py \
        backend/app/db/models/__init__.py \
        backend/app/services/slack_message_cache.py \
        backend/tests/unit/test_slack_message_cache.py
git commit -m "feat(triage): add SlackMessageCache for non-sensitive public channels"
```

---

## Task 3: Create SensitiveContentFetcher service

**Files:**
- Create: `backend/app/services/sensitive_content_fetcher.py`
- Create: `backend/tests/unit/test_sensitive_content_fetcher.py`

### Step 1: Create the service

- [ ] **Create service file**

```python
# backend/app/services/sensitive_content_fetcher.py
"""Fetcher for sensitive content that must be fetched on-demand from Slack.

Sensitive content (DMs, private channels, user-flagged channels) is never
cached in the database. This service provides a unified interface for
fetching such content with rate-limit handling.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from slack_sdk.errors import SlackApiError

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)


@dataclass
class FetchedMessage:
    """A message fetched from Slack API."""
    message_ts: str
    sender_slack_id: str
    text: str
    is_bot: bool
    created_at: datetime | None


class SensitiveContentFetcher:
    """Fetches sensitive content from Slack API with rate-limit handling.

    This service is used for:
    - DM conversation context
    - Private channel messages
    - User-flagged sensitive channels
    - Engagement checks on sensitive content
    - Escalation-time context fetch
    """

    def __init__(self, client: "AsyncWebClient") -> None:
        self.client = client

    async def fetch_message(
        self,
        channel_id: str,
        message_ts: str,
    ) -> FetchedMessage | None:
        """Fetch a single message from Slack.

        Returns None if message not found or rate-limited.
        """
        try:
            response = await self.client.conversations_history(
                channel=channel_id,
                latest=message_ts,
                limit=1,
                inclusive=True,
            )
            messages = response.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            return self._parse_message(msg)

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(f"Rate limited fetching message {channel_id}/{message_ts}")
                return None
            logger.exception(f"Slack API error fetching message: {e}")
            return None

    async def fetch_thread(
        self,
        channel_id: str,
        thread_ts: str,
        max_messages: int = 50,
    ) -> list[FetchedMessage]:
        """Fetch all messages in a thread.

        Returns empty list on failure (no fallback to cache).
        """
        try:
            response = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=max_messages,
            )
            messages = response.get("messages", [])
            return [self._parse_message(msg) for msg in messages]

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(f"Rate limited fetching thread {channel_id}/{thread_ts}")
            else:
                logger.exception(f"Slack API error fetching thread: {e}")
            return []

    async def fetch_dm_conversation(
        self,
        channel_id: str,
        max_messages: int = 20,
    ) -> list[FetchedMessage]:
        """Fetch recent DM conversation context.

        DMs are always fetched on-demand, never cached.
        """
        try:
            response = await self.client.conversations_history(
                channel=channel_id,
                limit=max_messages,
            )
            messages = response.get("messages", [])
            return [self._parse_message(msg) for msg in messages]

        except SlackApiError as e:
            if e.response.get("error") == "ratelimited":
                logger.warning(f"Rate limited fetching DM conversation {channel_id}")
            else:
                logger.exception(f"Slack API error fetching DM: {e}")
            return []

    async def check_engagement(
        self,
        channel_id: str,
        user_slack_id: str,
        after_ts: str,
        thread_ts: str | None = None,
    ) -> bool:
        """Check if user has engaged (reacted or replied) after a timestamp.

        Used for engagement checks on sensitive content.
        """
        try:
            if thread_ts:
                response = await self.client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=100,
                )
            else:
                response = await self.client.conversations_history(
                    channel=channel_id,
                    limit=50,
                )

            messages = response.get("messages", [])
            
            for msg in messages:
                msg_ts = msg.get("ts", "0")
                if msg_ts <= after_ts:
                    continue

                # Check if user posted a message
                if msg.get("user") == user_slack_id:
                    return True

                # Check if user reacted
                reactions = msg.get("reactions", [])
                for reaction in reactions:
                    if user_slack_id in reaction.get("users", []):
                        return True

            return False

        except SlackApiError as e:
            logger.warning(f"Failed to check engagement for {channel_id}: {e}")
            return False

    def _parse_message(self, msg: dict) -> FetchedMessage:
        """Parse a Slack message dict into FetchedMessage."""
        ts = msg.get("ts", "")
        created_at = None
        try:
            ts_float = float(ts)
            created_at = datetime.utcfromtimestamp(ts_float)
        except (ValueError, TypeError):
            pass

        return FetchedMessage(
            message_ts=ts,
            sender_slack_id=msg.get("user", msg.get("bot_id", "unknown")),
            text=msg.get("text", ""),
            is_bot=msg.get("bot_id") is not None,
            created_at=created_at,
        )
```

### Step 2: Write unit tests

- [ ] **Create test file**

```python
# backend/tests/unit/test_sensitive_content_fetcher.py
"""Unit tests for SensitiveContentFetcher."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from slack_sdk.errors import SlackApiError

from app.services.sensitive_content_fetcher import (
    SensitiveContentFetcher,
    FetchedMessage,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def fetcher(mock_client):
    return SensitiveContentFetcher(mock_client)


class TestSensitiveContentFetcher:
    @pytest.mark.asyncio
    async def test_fetch_message_returns_parsed_message(self, fetcher, mock_client):
        """fetch_message returns FetchedMessage on success."""
        mock_client.conversations_history.return_value = {
            "messages": [{
                "ts": "123.456",
                "user": "U123",
                "text": "Hello world",
            }]
        }

        result = await fetcher.fetch_message("C123", "123.456")

        assert result is not None
        assert result.message_ts == "123.456"
        assert result.sender_slack_id == "U123"
        assert result.text == "Hello world"
        assert result.is_bot is False

    @pytest.mark.asyncio
    async def test_fetch_message_returns_none_on_rate_limit(self, fetcher, mock_client):
        """fetch_message returns None on rate limit."""
        error = SlackApiError(message="ratelimited", response={"error": "ratelimited"})
        mock_client.conversations_history.side_effect = error

        result = await fetcher.fetch_message("C123", "123.456")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_thread_returns_messages(self, fetcher, mock_client):
        """fetch_thread returns list of FetchedMessage."""
        mock_client.conversations_replies.return_value = {
            "messages": [
                {"ts": "123.000", "user": "U1", "text": "First"},
                {"ts": "123.001", "user": "U2", "text": "Second"},
            ]
        }

        result = await fetcher.fetch_thread("C123", "123.000")

        assert len(result) == 2
        assert result[0].text == "First"
        assert result[1].text == "Second"

    @pytest.mark.asyncio
    async def test_fetch_thread_returns_empty_on_error(self, fetcher, mock_client):
        """fetch_thread returns empty list on error (no cache fallback)."""
        error = SlackApiError(message="error", response={"error": "channel_not_found"})
        mock_client.conversations_replies.side_effect = error

        result = await fetcher.fetch_thread("C123", "123.000")

        assert result == []

    @pytest.mark.asyncio
    async def test_check_engagement_detects_user_message(self, fetcher, mock_client):
        """check_engagement returns True if user posted after timestamp."""
        mock_client.conversations_history.return_value = {
            "messages": [
                {"ts": "123.010", "user": "U123", "text": "My reply"},
                {"ts": "123.005", "user": "U456", "text": "Original"},
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_engagement_detects_user_reaction(self, fetcher, mock_client):
        """check_engagement returns True if user reacted after timestamp."""
        mock_client.conversations_history.return_value = {
            "messages": [
                {
                    "ts": "123.005",
                    "user": "U456",
                    "text": "Original",
                    "reactions": [{"name": "thumbsup", "users": ["U123"]}],
                },
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_engagement_returns_false_no_engagement(self, fetcher, mock_client):
        """check_engagement returns False if no engagement found."""
        mock_client.conversations_history.return_value = {
            "messages": [
                {"ts": "123.005", "user": "U456", "text": "Message"},
            ]
        }

        result = await fetcher.check_engagement("C123", "U123", "123.000")

        assert result is False

    def test_parse_message_handles_bot_messages(self, fetcher):
        """_parse_message handles bot messages correctly."""
        result = fetcher._parse_message({
            "ts": "123.456",
            "bot_id": "B123",
            "text": "Bot message",
        })

        assert result.is_bot is True
        assert result.sender_slack_id == "B123"
```

- [ ] **Run tests**

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_sensitive_content_fetcher.py -v
```

### Step 3: Commit

```bash
git add backend/app/services/sensitive_content_fetcher.py \
        backend/tests/unit/test_sensitive_content_fetcher.py
git commit -m "feat(triage): add SensitiveContentFetcher for on-demand Slack fetches"
```

---

## Task 4: Add FeedbackEmbedding and SenderActionDistribution models

**Files:**
- Create: `backend/alembic/versions/040_add_feedback_embeddings.py`
- Create: `backend/alembic/versions/041_add_sender_action_distributions.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/db/models/__init__.py`

### Step 1: Create FeedbackEmbedding migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/040_add_feedback_embeddings.py
"""add feedback embeddings

Revision ID: 040
Revises: 039
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '040'
down_revision = '039'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feedback_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('triage_feedback_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('triage_feedback.id', ondelete='CASCADE'), nullable=False),
        sa.Column('embedding_vector', postgresql.ARRAY(sa.Float(), dimensions=1), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), 
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_feedback_embeddings_feedback', 'feedback_embeddings', ['triage_feedback_id'])


def downgrade() -> None:
    op.drop_index('ix_feedback_embeddings_feedback')
    op.drop_table('feedback_embeddings')
```

### Step 2: Create SenderActionDistribution migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/041_add_sender_action_distributions.py
"""add sender action distributions

Revision ID: 041
Revises: 040
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '041'
down_revision = '040'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sender_action_distributions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sender_slack_id', sa.String(50), nullable=False),
        sa.Column('channel_id', sa.String(50), nullable=False),
        sa.Column('action_distribution', postgresql.JSONB(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_computed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_sender_action_dist_unique',
        'sender_action_distributions',
        ['user_id', 'sender_slack_id', 'channel_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_sender_action_dist_unique')
    op.drop_table('sender_action_distributions')
```

### Step 3: Add models to triage.py

- [ ] **Add FeedbackEmbedding model**

```python
# backend/app/db/models/triage.py
# Add after TriageFeedback class:

class FeedbackEmbedding(Base, UUIDMixin, TimestampMixin):
    """Embedding of a corrected message for few-shot retrieval.

    Persists beyond R-Cache TTL since it's derived data (no raw text).
    Used by R3b to retrieve semantically similar past corrections.
    """

    __tablename__ = "feedback_embeddings"

    triage_feedback_id: Mapped[str] = mapped_column(
        ForeignKey("triage_feedback.id", ondelete="CASCADE"), nullable=False
    )
    embedding_vector: Mapped[list[float]] = mapped_column(
        ARRAY(Float, dimensions=1), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    feedback: Mapped["TriageFeedback"] = relationship(
        "TriageFeedback", back_populates="embedding"
    )

    def __repr__(self) -> str:
        return f"<FeedbackEmbedding(feedback={self.triage_feedback_id})>"
```

- [ ] **Add SenderActionDistribution model**

```python
# backend/app/db/models/triage.py
# Add after FeedbackEmbedding class:

class SenderActionDistribution(Base, UUIDMixin, TimestampMixin):
    """Per-(sender, channel) action distribution derived from corrections.

    Tracks the historical distribution of corrected actions for a sender
    in a specific channel, with 30-day half-life decay.
    Separate from SenderBehaviorModel which tracks response timing.
    """

    __tablename__ = "sender_action_distributions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_computed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        {"comment": "UNIQUE(user_id, sender_slack_id, channel_id) enforced via migration index"},
    )

    def __repr__(self) -> str:
        return f"<SenderActionDistribution(sender={self.sender_slack_id}, channel={self.channel_id})>"
```

- [ ] **Update TriageFeedback to add embedding relationship**

```python
# backend/app/db/models/triage.py
# Update TriageFeedback class:

class TriageFeedback(Base, UUIDMixin, TimestampMixin):
    """User feedback on a classification decision."""

    __tablename__ = "triage_feedback"

    classification_id: Mapped[str] = mapped_column(
        ForeignKey("triage_classifications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correct_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    classification: Mapped["TriageClassification"] = relationship(
        "TriageClassification", back_populates="feedback"
    )
    embedding: Mapped["FeedbackEmbedding | None"] = relationship(
        "FeedbackEmbedding", back_populates="feedback", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TriageFeedback(classification={self.classification_id}, correct={self.was_correct})>"
```

### Step 4: Update models __init__.py

- [ ] **Add exports**

```python
# backend/app/db/models/__init__.py
# Add to imports:

from app.db.models.triage import (
    FeedbackEmbedding,
    SenderActionDistribution,
)

# Add to __all__:
    "FeedbackEmbedding",
    "SenderActionDistribution",
```

### Step 5: Run migrations

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### Step 6: Commit

```bash
git add backend/alembic/versions/040_add_feedback_embeddings.py \
        backend/alembic/versions/041_add_sender_action_distributions.py \
        backend/app/db/models/triage.py \
        backend/app/db/models/__init__.py
git commit -m "feat(triage): add FeedbackEmbedding and SenderActionDistribution models"
```

---

## Task 5: Rename priority_level to action (Critical Work Stream)

**Files:**
- Create: `backend/alembic/versions/042_rename_priority_to_action.py`
- Modify: `backend/app/db/models/triage.py`
- Modify: `backend/app/db/repositories/triage.py`
- Modify: `backend/app/services/triage_classifier.py`
- Modify: `backend/app/services/triage_pipeline.py`
- Modify: `backend/app/services/triage_enrichment.py`
- Modify: `backend/app/services/digest_delivery.py`
- Modify: `backend/app/services/digest_grouper.py`
- Modify: `backend/app/schemas/triage.py`
- Modify: `backend/app/api/triage.py`
- Modify: `backend/worker/tasks.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/TriagePage.tsx`
- Modify: `frontend/src/components/triage/*`

### Step 1: Create migration

- [ ] **Create migration file**

```python
# backend/alembic/versions/042_rename_priority_to_action.py
"""rename priority to action

Revision ID: 042
Revises: 041
Create Date: 2024-01-15

This migration:
1. Renames priority_level column to action
2. Migrates existing values to new action labels
3. Updates related indexes

"""
from alembic import op
import sqlalchemy as sa

revision = '042'
down_revision = '041'
depends_on = None

# Mapping from old priority to new action
PRIORITY_TO_ACTION = {
    "p0": "notify_now",
    "p1": "summarize_next",
    "p2": "summarize_eod",
    "p3": "ignore",
    "review": "notify_now",  # review becomes action + review flag
    "digest_summary": "summarize_eod",  # digest_summary becomes action + is_consolidated flag
}


def upgrade() -> None:
    # Step 1: Add new column
    op.add_column(
        'triage_classifications',
        sa.Column('action', sa.String(20), nullable=True)
    )

    # Step 2: Migrate data
    conn = op.get_bind()
    for old_val, new_val in PRIORITY_TO_ACTION.items():
        conn.execute(
            sa.text(
                "UPDATE triage_classifications SET action = :new_val "
                "WHERE priority_level = :old_val"
            ),
            {"new_val": new_val, "old_val": old_val}
        )

    # Step 3: Set review flag for old 'review' priority
    op.add_column(
        'triage_classifications',
        sa.Column('review', sa.Boolean(), nullable=True, server_default='false')
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET review = true "
            "WHERE priority_level = 'review'"
        )
    )

    # Step 4: Set is_consolidated flag for old 'digest_summary' priority
    op.add_column(
        'triage_classifications',
        sa.Column('is_consolidated', sa.Boolean(), nullable=True, server_default='false')
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET is_consolidated = true "
            "WHERE priority_level = 'digest_summary'"
        )
    )

    # Step 5: Make action NOT NULL
    op.alter_column('triage_classifications', 'action', nullable=False)

    # Step 6: Drop old column
    op.drop_column('triage_classifications', 'priority_level')

    # Step 7: Create index on new column
    op.create_index('ix_triage_classifications_action', 'triage_classifications', ['action'])


def downgrade() -> None:
    # Re-add priority_level
    op.add_column(
        'triage_classifications',
        sa.Column('priority_level', sa.String(20), nullable=True)
    )

    conn = op.get_bind()
    ACTION_TO_PRIORITY = {
        "notify_now": "p0",
        "summarize_next": "p1",
        "summarize_eod": "p2",
        "ignore": "p3",
    }
    for new_val, old_val in ACTION_TO_PRIORITY.items():
        conn.execute(
            sa.text(
                "UPDATE triage_classifications SET priority_level = :old_val "
                "WHERE action = :new_val"
            ),
            {"new_val": new_val, "old_val": old_val}
        )

    # Restore review and digest_summary
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET priority_level = 'review' "
            "WHERE review = true"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET priority_level = 'digest_summary' "
            "WHERE is_consolidated = true"
        )
    )

    op.drop_index('ix_triage_classifications_action')
    op.drop_column('triage_classifications', 'action')
    op.drop_column('triage_classifications', 'review')
    op.drop_column('triage_classifications', 'is_consolidated')
```

### Step 2: Update TriageClassification model

- [ ] **Modify model**

```python
# backend/app/db/models/triage.py
# Update TriageClassification class - replace priority_level with action:

class TriageClassification(Base, UUIDMixin, TimestampMixin):
    """A classified Slack message (no raw text stored)."""

    __tablename__ = "triage_classifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    focus_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("focus_mode_state.id"), nullable=True
    )
    sender_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Action labels (notify_now, summarize_next, summarize_eod, ignore)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    
    # Orthogonal flags
    review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_path: Mapped[str] = mapped_column(String(10), nullable=False)
    escalated_by_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    surfaced_at_break: Mapped[bool] = mapped_column(Boolean, default=False)
    keyword_matches: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # New fields for R1/R2
    needs_more_context: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    message_type_id: Mapped[str | None] = mapped_column(
        ForeignKey("message_types.id"), nullable=True
    )
    
    # Digest consolidation
    digest_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("triage_classifications.id", ondelete="SET NULL"), nullable=True
    )
    child_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversation_summary_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation_summaries.id", ondelete="SET NULL"), nullable=True
    )

    # Alert tracking
    last_alerted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    alert_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Digest queue tracking
    queued_for_digest: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    digest_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    processed_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    feedback: Mapped["TriageFeedback | None"] = relationship(
        "TriageFeedback", back_populates="classification", uselist=False
    )
    conversation_summary: Mapped["ConversationSummary | None"] = relationship(
        "ConversationSummary",
        foreign_keys=[conversation_summary_id],
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<TriageClassification(user_id={self.user_id}, action={self.action})>"
```

### Step 3: Update TriageClassifier

- [ ] **Update ClassificationResult dataclass**

```python
# backend/app/services/triage_classifier.py
# Update ClassificationResult:

@dataclass
class ClassificationResult:
    """Result of classifying a message."""

    action: str  # notify_now | summarize_next | summarize_eod | ignore
    confidence: float
    reason: str
    abstract: str
    review: bool = False  # Orthogonal low-confidence flag
    needs_more_context: bool = False
    message_type: str | None = None
    keyword_matches: list[str] = field(default_factory=list)
```

- [ ] **Update default action definitions**

```python
# backend/app/services/triage_classifier.py
# Replace DEFAULT_P0-P3 with action definitions:

DEFAULT_NOTIFY_NOW = (
    "Needs immediate attention RIGHT NOW. Production incidents, emergencies, "
    "someone explicitly saying something is urgent/critical. Direct questions "
    "that require an immediate response."
)

DEFAULT_SUMMARIZE_NEXT = (
    "Time-sensitive requests that need action soon. Direct asks requiring a response, "
    "important questions needing input, meaningful requests with a deadline. "
    "Should be included in the next available digest window."
)

DEFAULT_SUMMARIZE_EOD = (
    "Noteworthy but not time-sensitive. Project updates, FYI items, relevant "
    "discussions, informational messages worth reviewing in the end-of-day digest."
)

DEFAULT_IGNORE = (
    "Low priority. General chatter, memes, social messages, non-work banter, "
    "automated notifications that need no action. @here, @channel, @everyone "
    "broadcasts that are not specifically relevant to the user."
)
```

- [ ] **Update classify methods to return action**

```python
# backend/app/services/triage_classifier.py
# Update _classify_channel method:

async def _classify_channel(
    self, payload: EnrichedTriagePayload
) -> ClassificationResult:
    """Classify a channel message."""
    # Critical channel priority auto-escalates
    if payload.channel_priority == "critical":
        return ClassificationResult(
            action="notify_now",
            confidence=0.9,
            reason=f"Channel #{payload.channel_name} is set to critical priority",
            abstract=f"Message in critical channel #{payload.channel_name}",
        )

    # Check for @here/@channel/@everyone - deterministic ignore
    text_lower = payload.message_text.lower()
    if any(mention in text_lower for mention in ["@here", "@channel", "@everyone"]):
        # Still classify for content, but note the broadcast
        # (PRD says these are deterministically classified as ignore)
        return ClassificationResult(
            action="ignore",
            confidence=0.95,
            reason="Broadcast mention (@here/@channel/@everyone) filtered",
            abstract="Broadcast message",
        )

    return await self._llm_classify(payload, path="channel")
```

- [ ] **Update _llm_classify to use action labels**

```python
# backend/app/services/triage_classifier.py
# Update system prompt in _llm_classify:

    system_prompt = f"""You are a message triage classifier. Classify a Slack message into one of the following ACTIONS.

Actions (what Alfred should DO with this message):
- notify_now: {self.notify_now_definition}
- summarize_next: {self.summarize_next_definition}
- summarize_eod: {self.summarize_eod_definition}
- ignore: {self.ignore_definition}

**Display Layer:** Users see P0/P1/P2/P3 in the UI where:
- P0 = notify_now
- P1 = summarize_next
- P2 = summarize_eod
- P3 = ignore

Do NOT use "review" as an action - instead set review=true if confidence is low.

DMs and @mentions raise the likelihood a message is notify_now or summarize_next — but still evaluate the actual message content before classifying.

... (rest of prompt remains similar) ...

Respond with valid JSON only:
{{"action": "notify_now|summarize_next|summarize_eod|ignore", "confidence": 0.0-1.0, "review": true|false, "needs_more_context": true|false, "reason": "brief explanation", "abstract": "1-sentence summary of the message topic without quoting the message"}}
```

### Step 4: Update triage_pipeline.py

- [ ] **Update process method**

```python
# backend/app/services/triage_pipeline.py
# Update classification creation:

        # 3. Store classification (no message text)
        classification = TriageClassification(
            user_id=user_id,
            focus_session_id=payload.focus_session_id,
            focus_started_at=payload.focus_started_at,
            sender_slack_id=sender_slack_id,
            sender_name=payload.sender_name or None,
            channel_id=channel_id,
            channel_name=payload.channel_name or None,
            message_ts=message_ts,
            thread_ts=thread_ts,
            slack_permalink=payload.slack_permalink,
            action=result.action,  # Changed from priority_level
            review=result.review,  # New field
            confidence=result.confidence,
            classification_reason=result.reason,
            abstract=result.abstract,
            classification_path=event_type,
            keyword_matches=result.keyword_matches if result.keyword_matches else None,
            needs_more_context=result.needs_more_context,  # New field
        )

        # Check if alerts are disabled for this action
        alerts_enabled = {
            "notify_now": settings.p0_alerts_enabled if settings else True,
            "summarize_next": settings.p1_alerts_enabled if settings else True,
            "summarize_eod": settings.p2_alerts_enabled if settings else True,
            "ignore": settings.p3_alerts_enabled if settings else True,
        }.get(result.action, True)
```

- [ ] **Update _deliver_urgent to check notify_now**

```python
# backend/app/services/triage_pipeline.py
# Update deliver check:

        # 4. Deliver notify_now notifications (with deduplication)
        if result.action == "notify_now":
```

### Step 5: Update frontend types

- [ ] **Update TriageClassification type**

```typescript
// frontend/src/types/index.ts
// Update TriageClassification interface:

export interface TriageClassification {
  id: string
  user_id: string
  sender_slack_id: string
  sender_name: string | null
  channel_id: string
  channel_name: string | null
  message_ts: string
  thread_ts: string | null
  slack_permalink: string | null
  action: 'notify_now' | 'summarize_next' | 'summarize_eod' | 'ignore'
  review: boolean
  is_consolidated: boolean
  confidence: number
  classification_reason: string | null
  abstract: string | null
  classification_path: 'dm' | 'channel'
  keyword_matches: Record<string, string[]> | null
  created_at: string | null
  reviewed_at: string | null
  needs_more_context: boolean
}

// Add helper function for UI display
export function actionToPriority(action: string): string {
  const mapping: Record<string, string> = {
    notify_now: 'P0',
    summarize_next: 'P1',
    summarize_eod: 'P2',
    ignore: 'P3',
  }
  return mapping[action] || action
}
```

### Step 6: Create ActionBadge component

- [ ] **Create component**

```tsx
// frontend/src/components/triage/ActionBadge.tsx
import { AlertTriangle, Clock, FileText, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Action = 'notify_now' | 'summarize_next' | 'summarize_eod' | 'ignore'

interface ActionBadgeProps {
  action: Action
  review?: boolean
  className?: string
}

const ACTION_CONFIG: Record<Action, {
  label: string
  icon: React.ElementType
  className: string
  priority: string
}> = {
  notify_now: {
    label: 'P0',
    icon: AlertTriangle,
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
    priority: 'Urgent',
  },
  summarize_next: {
    label: 'P1',
    icon: Clock,
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
    priority: 'Next',
  },
  summarize_eod: {
    label: 'P2',
    icon: FileText,
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
    priority: 'EOD',
  },
  ignore: {
    label: 'P3',
    icon: X,
    className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
    priority: 'Ignored',
  },
}

export function ActionBadge({ action, review, className }: ActionBadgeProps) {
  const config = ACTION_CONFIG[action] || ACTION_CONFIG.ignore
  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
        config.className,
        className
      )}
    >
      <Icon className="h-3 w-3" />
      {config.label}
      {review && (
        <span className="ml-1 text-yellow-600 dark:text-yellow-400" title="Needs review">
          ?
        </span>
      )}
    </span>
  )
}
```

### Step 7: Update TriagePage to use ActionBadge

- [ ] **Update P0AlertCard to use ActionBadge**

```tsx
// frontend/src/pages/TriagePage.tsx
// Replace priority badge with ActionBadge:

import { ActionBadge } from '@/components/triage/ActionBadge'

// In P0AlertCard component, replace the priority span with:
<ActionBadge action={item.action} review={item.review} />
```

### Step 8: Update schemas

- [ ] **Update schemas to use action**

```python
# backend/app/schemas/triage.py
# Update response schemas:

class TriageClassificationResponse(BaseModel):
    """Response with classification info."""

    model_config = {"from_attributes": True}

    id: str
    action: str  # notify_now | summarize_next | summarize_eod | ignore
    review: bool = False
    is_consolidated: bool = False
    confidence: float
    classification_reason: str | None
    abstract: str | None
    sender_slack_id: str
    sender_name: str | None
    channel_id: str
    channel_name: str | None
    message_ts: str
    thread_ts: str | None
    slack_permalink: str | None
    classification_path: str
    created_at: UTCDatetime = None
    reviewed_at: UTCDatetime = None
    needs_more_context: bool = False
```

### Step 9: Run migration and tests

```bash
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head
docker-compose -f docker-compose.dev.yml exec backend pytest tests/ -v -k triage
```

### Step 10: Commit

```bash
git add -A
git commit -m "feat(triage): rename priority to action labels

- Migrate priority_level to action column
- Add review and is_consolidated flags
- Update classifier to output actions
- Update frontend to use ActionBadge component
- Preserve P0-P3 display layer for UI"
```

---

## Task 6: Wire engagement check to gate notify_now delivery

**Files:**
- Modify: `backend/app/services/digest_response_checker.py`
- Modify: `backend/app/services/triage_pipeline.py`
- Create: `backend/tests/integration/test_engagement_gate.py`

### Step 1: Extend DigestResponseChecker

- [ ] **Add check_engagement method**

```python
# backend/app/services/digest_response_checker.py
# Add new method:

    async def check_engagement(
        self,
        user_id: str,
        user_slack_id: str,
        channel_id: str,
        message_ts: str,
        thread_ts: str | None = None,
        within_days: int = 3,
    ) -> bool:
        """Check if user has engaged with a message within the time window.

        Engagement includes:
        - Any reaction on the message
        - Substantive reply in thread/DM
        - Short acknowledgment reply (only marks that message ineligible)

        Args:
            user_id: Alfred user ID (for token lookup)
            user_slack_id: User's Slack ID
            channel_id: Channel ID
            message_ts: Message timestamp to check
            thread_ts: Thread timestamp if message is in a thread
            within_days: Time window for engagement check (default 3 days)

        Returns:
            True if user has engaged, False otherwise
        """
        client = await self._get_user_client(user_id)
        if not client:
            logger.warning(f"No user client for {user_id}, cannot check engagement")
            return False

        try:
            if thread_ts:
                # Check thread replies
                response = await client.conversations_replies(
                    channel=channel_id,
                    ts=thread_ts,
                    limit=100,
                )
            else:
                # Check channel history
                response = await client.conversations_history(
                    channel=channel_id,
                    limit=50,
                )

            messages = response.get("messages", [])
            cutoff_ts = self._get_cutoff_ts(within_days)

            for msg in messages:
                msg_ts = msg.get("ts", "0")
                if msg_ts < cutoff_ts:
                    continue

                # Check for reactions on the target message
                if msg_ts == message_ts:
                    reactions = msg.get("reactions", [])
                    for reaction in reactions:
                        if user_slack_id in reaction.get("users", []):
                            logger.debug(f"User {user_slack_id} reacted to message {message_ts}")
                            return True

                # Check for user replies after the message
                if msg.get("user") == user_slack_id and msg_ts > message_ts:
                    # Check if this is a short acknowledgment
                    if await self._is_short_ack(msg.get("text", "")):
                        logger.debug(f"User {user_slack_id} sent short ack after {message_ts}")
                        return True
                    # Substantive reply
                    logger.debug(f"User {user_slack_id} replied substantively after {message_ts}")
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error checking engagement: {e}")
            return False

    def _get_cutoff_ts(self, within_days: int) -> str:
        """Get timestamp cutoff for engagement window."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=within_days)
        return str(cutoff.timestamp())

    async def _is_short_ack(self, text: str) -> bool:
        """Check if text is a short acknowledgment.

        TODO: Extend substance_filter to handle user replies.
        For now, use simple heuristic.
        """
        text = text.strip().lower()
        short_acks = [
            "ok", "k", "thanks", "thx", "ty", "got it", "noted", "cool",
            "sure", "will do", "understood", "👍", "✓", "✅",
        ]
        return text in short_acks or len(text) < 10
```

### Step 2: Wire engagement check to notify_now delivery

- [ ] **Update triage_pipeline.py**

```python
# backend/app/services/triage_pipeline.py
# Update _deliver_urgent to check engagement first:

    async def _deliver_urgent(
        self,
        user_id: str,
        classification: TriageClassification,
        payload,
        result,
    ) -> None:
        """Send notify_now notification via Slack DM and SSE.

        ENGAGEMENT CHECK: Gate delivery on user engagement status.
        If user has already engaged (reacted or replied), skip delivery.
        """
        from app.db.repositories import UserRepository
        from app.services.digest_response_checker import DigestResponseChecker

        # Check engagement before delivering
        user_repo = UserRepository(self.db)
        user = await user_repo.get(user_id)
        
        if user and user.slack_user_id:
            checker = DigestResponseChecker(self.db)
            has_engaged = await checker.check_engagement(
                user_id=user_id,
                user_slack_id=user.slack_user_id,
                channel_id=classification.channel_id,
                message_ts=classification.message_ts,
                thread_ts=classification.thread_ts,
                within_days=3,
            )
            
            if has_engaged:
                logger.info(
                    f"Suppressing notify_now for {classification.id}: "
                    f"user already engaged"
                )
                # Record suppressed delivery for counterfactual review
                # (R8 implementation in Phase 2)
                return

        # Proceed with delivery...
        # (rest of existing implementation)
```

### Step 3: Write integration test

- [ ] **Create test file**

```python
# backend/tests/integration/test_engagement_gate.py
"""Integration tests for engagement-gated delivery."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.triage import TriageClassification, TriageUserSettings
from tests.conftest import auth_headers
from tests.factories import UserFactory


@pytest.fixture
async def test_user_with_slack(db_session: AsyncSession):
    user = UserFactory(slack_user_id="U_ENGAGED")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestEngagementGate:
    @pytest.mark.asyncio
    async def test_notify_now_suppressed_when_user_reacted(
        self,
        db_session: AsyncSession,
        test_user_with_slack,
    ):
        """notify_now should not be delivered if user already reacted."""
        # Create classification
        classification = TriageClassification(
            user_id=test_user_with_slack.id,
            sender_slack_id="U_SENDER",
            channel_id="C123",
            message_ts="123.456",
            action="notify_now",
            confidence=0.9,
            abstract="Test message",
            classification_path="channel",
        )
        db_session.add(classification)
        await db_session.commit()

        # Mock engagement checker to return True (user reacted)
        with patch(
            "app.services.digest_response_checker.DigestResponseChecker.check_engagement",
            AsyncMock(return_value=True)
        ):
            from app.services.triage_pipeline import TriagePipeline
            from app.services.triage_enrichment import EnrichedTriagePayload
            
            pipeline = TriagePipeline(db_session)
            
            # Mock notification service
            pipeline.notification_service.publish = AsyncMock()
            
            await pipeline._deliver_urgent(
                user_id=test_user_with_slack.id,
                classification=classification,
                payload=AsyncMock(),
                result=AsyncMock(abstract="Test"),
            )
            
            # Should NOT have called notification service
            pipeline.notification_service.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_now_delivered_when_no_engagement(
        self,
        db_session: AsyncSession,
        test_user_with_slack,
    ):
        """notify_now should be delivered if user has not engaged."""
        classification = TriageClassification(
            user_id=test_user_with_slack.id,
            sender_slack_id="U_SENDER",
            channel_id="C123",
            message_ts="123.456",
            action="notify_now",
            confidence=0.9,
            abstract="Test message",
            classification_path="channel",
        )
        db_session.add(classification)
        await db_session.commit()

        with patch(
            "app.services.digest_response_checker.DigestResponseChecker.check_engagement",
            AsyncMock(return_value=False)
        ):
            from app.services.triage_pipeline import TriagePipeline
            
            pipeline = TriagePipeline(db_session)
            pipeline.notification_service.publish = AsyncMock()
            
            await pipeline._deliver_urgent(
                user_id=test_user_with_slack.id,
                classification=classification,
                payload=AsyncMock(event_type="channel", channel_name="test", sender_name="Sender"),
                result=AsyncMock(abstract="Test"),
            )
            
            # Should have called notification service
            pipeline.notification_service.publish.assert_called()
```

### Step 4: Run tests

```bash
docker-compose -f docker-compose.dev.yml exec backend pytest tests/integration/test_engagement_gate.py -v
```

### Step 5: Commit

```bash
git add backend/app/services/digest_response_checker.py \
        backend/app/services/triage_pipeline.py \
        backend/tests/integration/test_engagement_gate.py
git commit -m "feat(triage): gate notify_now delivery with engagement check"
```

---

## Task 7: Add worker job for cache cleanup

**Files:**
- Modify: `backend/app/worker/tasks.py`
- Create: `backend/tests/unit/test_cache_cleanup.py`

### Step 1: Add cleanup job

- [ ] **Add to worker/tasks.py**

```python
# backend/app/worker/tasks.py
# Add new scheduled task:

@celery_app.task(name="cleanup_message_cache")
def cleanup_message_cache() -> dict:
    """Clean up expired Slack message cache entries.
    
    Runs nightly to delete messages older than 7-day TTL.
    This is the ONLY place raw message text is stored.
    
    Returns:
        Count of deleted entries
    """
    import asyncio
    from app.core.database import async_session_factory
    from app.services.slack_message_cache import SlackMessageCacheService
    
    async def _cleanup():
        async with async_session_factory() as db:
            service = SlackMessageCacheService(db)
            deleted = await service.cleanup_expired()
            return deleted
    
    deleted = asyncio.run(_cleanup())
    
    # TODO: Add alerting if cleanup fails or returns unexpected count
    return {"deleted": deleted}
```

### Step 2: Schedule the task

- [ ] **Add to celery beat schedule**

```python
# backend/app/worker/tasks.py
# Update celery_app configuration:

celery_app.conf.beat_schedule = {
    # ... existing schedules ...
    "cleanup-message-cache-daily": {
        "task": "cleanup_message_cache",
        "schedule": crontab(hour=3, minute=0),  # 3 AM UTC daily
    },
}
```

### Step 3: Write test

- [ ] **Create test file**

```python
# backend/tests/unit/test_cache_cleanup.py
"""Unit tests for cache cleanup task."""

import pytest
from unittest.mock import AsyncMock, patch


class TestCacheCleanup:
    def test_cleanup_task_calls_service(self):
        """Cleanup task should call SlackMessageCacheService.cleanup_expired."""
        from app.worker.tasks import cleanup_message_cache
        
        with patch(
            "app.worker.tasks.SlackMessageCacheService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.cleanup_expired = AsyncMock(return_value=42)
            mock_service_class.return_value = mock_service
            
            result = cleanup_message_cache()
            
            assert result == {"deleted": 42}
            mock_service.cleanup_expired.assert_called_once()
```

### Step 4: Commit

```bash
git add backend/app/worker/tasks.py \
        backend/tests/unit/test_cache_cleanup.py
git commit -m "feat(triage): add nightly cache cleanup worker job"
```

---

## Acceptance Criteria Checklist

After completing all tasks, verify:

- [ ] All classifier outputs use action labels internally; P0-P3 is UI-only display
- [ ] `priority` → `action` rename completes with regression tests passing
- [ ] `MonitoredChannel.sensitive` column added with correct defaults
- [ ] Public channels default to cached; private channels default to non-cached
- [ ] DM messages never persisted; always fetched on demand
- [ ] `SlackMessageCache` populated only for non-sensitive content
- [ ] Services query for text check `sensitive` flag first
- [ ] Nightly cleanup removes expired cache rows
- [ ] Engagement check gates `notify_now` delivery
- [ ] Low-confidence classifications get `review = true` with best-guess action
- [ ] Backend tests pass: `pytest tests/ -v -k triage`
- [ ] Frontend builds: `npm run build`

---

## Next Steps

After Phase 1 ships:
1. Monitor R-Cache size and TTL cleanup
2. Gather data on walkback cost/quality gates
3. Begin Phase 2: Closed-loop learning (R3)

---

*Phase 1 complete. Proceed to phase-2-trust.md for trust-building features.*
