"""Tests for triage agent context-gathering tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.base import ToolContext


# ---------------------------------------------------------------------------
# FetchMessageTool
# ---------------------------------------------------------------------------


class TestFetchMessageToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.fetch_message import FetchMessageTool

        tool = FetchMessageTool()
        defn = tool.to_definition()
        assert defn.name == "fetch_message"
        assert "channel_id" in defn.parameters["properties"]
        assert "message_ts" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestFetchMessageToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.fetch_message import FetchMessageTool

        return FetchMessageTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_success(self, tool, context):
        mock_client = AsyncMock()
        mock_client.conversations_history.return_value = {
            "ok": True,
            "messages": [
                {
                    "text": "Hello world",
                    "user": "U123",
                    "ts": "1234567890.123456",
                    "thread_ts": "1234567890.000001",
                }
            ],
        }
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_message.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(
                context=context,
                channel_id="C001",
                message_ts="1234567890.123456",
            )

        data = json.loads(result)
        assert data["text"] == "Hello world"
        assert data["user"] == "U123"
        assert data["ts"] == "1234567890.123456"
        assert data["thread_ts"] == "1234567890.000001"

        mock_client.conversations_history.assert_awaited_once_with(
            channel="C001",
            oldest="1234567890.123456",
            inclusive=True,
            limit=1,
        )

    @pytest.mark.asyncio
    async def test_success_no_thread(self, tool, context):
        """Message without thread_ts returns null."""
        mock_client = AsyncMock()
        mock_client.conversations_history.return_value = {
            "ok": True,
            "messages": [
                {
                    "text": "Top-level message",
                    "user": "U456",
                    "ts": "1111111111.111111",
                }
            ],
        }
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_message.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(
                context=context,
                channel_id="C001",
                message_ts="1111111111.111111",
            )

        data = json.loads(result)
        assert data["thread_ts"] is None

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        mock_client = AsyncMock()
        mock_client.conversations_history.side_effect = Exception("API error")
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_message.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(
                context=context,
                channel_id="C001",
                message_ts="1234567890.123456",
            )

        data = json.loads(result)
        assert "error" in data
        assert "API error" in data["error"]


# ---------------------------------------------------------------------------
# GetQueuedMessagesTool
# ---------------------------------------------------------------------------


class TestGetQueuedMessagesToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.get_queued_messages import GetQueuedMessagesTool

        tool = GetQueuedMessagesTool()
        defn = tool.to_definition()
        assert defn.name == "get_queued_messages"
        assert "channel_id" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestGetQueuedMessagesToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.get_queued_messages import GetQueuedMessagesTool

        return GetQueuedMessagesTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_success(self, tool, context):
        mock_classification = MagicMock()
        mock_classification.id = "cls-1"
        mock_classification.sender_name = "Alice"
        mock_classification.abstract = "Needs approval"
        mock_classification.action = "summarize_next"
        mock_classification.group_id = "grp-1"
        mock_classification.message_ts = "111.222"
        mock_classification.channel_name = "engineering"

        mock_classification.queued_for_digest = True

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.get_recent",
            new_callable=AsyncMock,
            return_value=[mock_classification],
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert data["count"] == 1
        assert len(data["messages"]) == 1
        msg = data["messages"][0]
        assert msg["id"] == "cls-1"
        assert msg["sender_name"] == "Alice"
        assert msg["abstract"] == "Needs approval"
        assert msg["action"] == "summarize_next"
        assert msg["group_id"] == "grp-1"
        assert msg["message_ts"] == "111.222"
        assert msg["channel_name"] == "engineering"

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        """Returns error if db or user_id missing."""
        result = await tool.execute(context=None, channel_id="C001")
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.get_recent",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert "error" in data
        assert "DB error" in data["error"]


# ---------------------------------------------------------------------------
# FetchThreadTool
# ---------------------------------------------------------------------------


class TestFetchThreadToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.fetch_thread import FetchThreadTool

        tool = FetchThreadTool()
        defn = tool.to_definition()
        assert defn.name == "fetch_thread"
        assert "channel_id" in defn.parameters["properties"]
        assert "thread_ts" in defn.parameters["properties"]
        assert tool.max_iterations == 2


class TestFetchThreadToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.fetch_thread import FetchThreadTool

        return FetchThreadTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_success(self, tool, context):
        mock_client = AsyncMock()
        mock_client.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {"user": "U1", "text": "Thread parent", "ts": "111.000"},
                {"user": "U2", "text": "Reply", "ts": "111.001"},
            ],
        }
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_thread.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(
                context=context, channel_id="C001", thread_ts="111.000"
            )

        data = json.loads(result)
        assert data["count"] == 2
        assert len(data["messages"]) == 2
        assert data["messages"][0]["text"] == "Thread parent"

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        mock_client = AsyncMock()
        mock_client.conversations_replies.side_effect = Exception("Thread error")
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_thread.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(
                context=context, channel_id="C001", thread_ts="111.000"
            )

        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# FetchChannelHistoryTool
# ---------------------------------------------------------------------------


class TestFetchChannelHistoryToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.fetch_channel_history import (
            FetchChannelHistoryTool,
        )

        tool = FetchChannelHistoryTool()
        defn = tool.to_definition()
        assert defn.name == "fetch_channel_history"
        assert "channel_id" in defn.parameters["properties"]
        assert tool.max_iterations == 2


class TestFetchChannelHistoryToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.fetch_channel_history import (
            FetchChannelHistoryTool,
        )

        return FetchChannelHistoryTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_filters_thread_replies(self, tool, context):
        """Thread replies (where thread_ts != ts) are excluded."""
        mock_client = AsyncMock()
        mock_client.conversations_history.return_value = {
            "ok": True,
            "messages": [
                {
                    "user": "U1",
                    "text": "Top-level",
                    "ts": "100.000",
                },
                {
                    "user": "U2",
                    "text": "Reply in thread",
                    "ts": "100.001",
                    "thread_ts": "100.000",
                },
                {
                    "user": "U3",
                    "text": "Another top-level",
                    "ts": "200.000",
                    "thread_ts": "200.000",
                },
            ],
        }
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_channel_history.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        # The reply where thread_ts != ts should be filtered out
        assert data["count"] == 2
        texts = [m["text"] for m in data["messages"]]
        assert "Reply in thread" not in texts

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        mock_client = AsyncMock()
        mock_client.conversations_history.side_effect = Exception("Channel error")
        mock_service = MagicMock()
        mock_service.client = mock_client

        with patch(
            "app.agents.triage.tools.fetch_channel_history.get_slack_service",
            return_value=mock_service,
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# GetUserChannelRulesTool
# ---------------------------------------------------------------------------


class TestGetUserChannelRulesToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.get_user_channel_rules import (
            GetUserChannelRulesTool,
        )

        tool = GetUserChannelRulesTool()
        defn = tool.to_definition()
        assert defn.name == "get_user_channel_rules"
        assert "channel_id" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestGetUserChannelRulesToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.get_user_channel_rules import (
            GetUserChannelRulesTool,
        )

        return GetUserChannelRulesTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_cache_hit(self, tool, context):
        """Returns cached rules without hitting DB."""
        cached = {
            "priority": "high",
            "triage_instructions": "Flag all prod alerts",
            "summary_behavior": "detailed",
        }

        with patch(
            "app.services.triage_cache.TriageCacheService.get_channel_rules",
            new_callable=AsyncMock,
            return_value=cached,
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert data["priority"] == "high"
        assert data["triage_instructions"] == "Flag all prod alerts"
        assert data["summary_behavior"] == "detailed"

    @pytest.mark.asyncio
    async def test_cache_miss_falls_back_to_db(self, tool, context):
        """On cache miss, queries MonitoredChannelRepository and caches result."""
        mock_channel = MagicMock()
        mock_channel.priority = "medium"
        mock_channel.triage_instructions = None
        mock_channel.summary_behavior = "default"

        with patch(
            "app.services.triage_cache.TriageCacheService.get_channel_rules",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.triage_cache.TriageCacheService.set_channel_rules",
            new_callable=AsyncMock,
        ) as mock_set, patch(
            "app.db.repositories.triage.MonitoredChannelRepository.get_by_user_and_channel",
            new_callable=AsyncMock,
            return_value=mock_channel,
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert data["priority"] == "medium"
        assert data["triage_instructions"] == ""
        assert data["summary_behavior"] == "default"
        # Verify it cached the result
        mock_set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(context=None, channel_id="C001")
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        with patch(
            "app.services.triage_cache.TriageCacheService.get_channel_rules",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            result = await tool.execute(context=context, channel_id="C001")

        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestTriageToolRegistry:
    def test_registry_has_all_context_tools(self):
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        expected = [
            "fetch_message",
            "fetch_thread",
            "fetch_channel_history",
            "get_queued_messages",
            "get_user_channel_rules",
        ]
        for name in expected:
            assert registry.get(name) is not None, f"Missing tool: {name}"

    def test_registry_definitions(self):
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        definitions = registry.get_definitions()
        assert len(definitions) >= 5
        names = {d.name for d in definitions}
        assert "fetch_message" in names
        assert "get_queued_messages" in names
