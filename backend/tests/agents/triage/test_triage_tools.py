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

        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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
        with patch(
            "app.services.slack_channel_client.SlackChannelClient.for_user",
            return_value=mock_client,
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

    def test_registry_has_all_action_tools(self):
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        expected = ["alert_now", "queue_for_digest", "link_messages"]
        for name in expected:
            assert registry.get(name) is not None, f"Missing tool: {name}"

    def test_registry_definitions(self):
        from app.agents.triage.tools import get_triage_tool_registry

        registry = get_triage_tool_registry()
        definitions = registry.get_definitions()
        assert len(definitions) >= 8  # 5 context + 3 action
        names = {d.name for d in definitions}
        assert "fetch_message" in names
        assert "get_queued_messages" in names
        assert "alert_now" in names
        assert "queue_for_digest" in names
        assert "link_messages" in names


# ---------------------------------------------------------------------------
# AlertNowTool
# ---------------------------------------------------------------------------


class TestAlertNowToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.alert_now import AlertNowTool

        tool = AlertNowTool()
        defn = tool.to_definition()
        assert defn.name == "alert_now"
        assert "abstract" in defn.parameters["properties"]
        assert "reason" in defn.parameters["properties"]
        assert "confidence" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestAlertNowToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.alert_now import AlertNowTool

        return AlertNowTool()

    @pytest.fixture
    def context(self):
        return ToolContext(
            db=AsyncMock(),
            user_id="user-123",
        )

    @pytest.fixture
    def agent_state(self):
        return {
            "sender_slack_id": "U_SENDER",
            "sender_name": "Alice",
            "channel_id": "C001",
            "channel_name": "engineering",
            "message_ts": "111.222",
            "thread_ts": None,
            "slack_permalink": "https://slack.com/archives/C001/p111222",
            "classification_path": "channel",
        }

    @pytest.mark.asyncio
    async def test_creates_classification_sends_dm_publishes_sse(
        self, tool, context, agent_state
    ):
        context["agent_state"] = agent_state

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OWNER"

        mock_classification = MagicMock()
        mock_classification.id = "cls-alert-1"

        mock_slack_client = AsyncMock()
        mock_slack_client.conversations_open.return_value = {
            "ok": True,
            "channel": {"id": "D_DM_CHANNEL"},
        }
        mock_slack_client.chat_postMessage.return_value = {"ok": True}
        mock_slack_service = MagicMock()
        mock_slack_service.client = mock_slack_client

        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create, patch(
            "app.services.slack.get_slack_service",
            return_value=mock_slack_service,
        ), patch(
            "app.services.notifications.NotificationService.publish",
            new_callable=AsyncMock,
        ) as mock_publish:
            result = await tool.execute(
                context=context,
                abstract="Server is down",
                reason="Production outage",
                confidence=0.95,
            )

        data = json.loads(result)
        assert data["status"] == "alerted"
        assert data["classification_id"] == "cls-alert-1"

        # Verify classification was created
        mock_create.assert_awaited_once()
        create_arg = mock_create.call_args[0][0]
        assert create_arg.action == "notify_now"
        assert create_arg.queued_for_digest is False
        assert create_arg.alert_count == 1
        assert create_arg.abstract == "Server is down"
        assert create_arg.confidence == 0.95

        # Verify Slack DM was sent
        mock_slack_client.conversations_open.assert_awaited_once_with(users="U_OWNER")
        mock_slack_client.chat_postMessage.assert_awaited_once()
        dm_call = mock_slack_client.chat_postMessage.call_args
        assert "P0" in dm_call.kwargs.get("text", dm_call[1].get("text", ""))

        # Verify SSE event was published
        mock_publish.assert_awaited_once()
        sse_call = mock_publish.call_args
        assert sse_call[0][0] == "user-123"
        assert sse_call[0][1] == "triage.urgent"

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(
            context=None, abstract="x", reason="y", confidence=0.9
        )
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_slack_dm_failure_still_returns_success(
        self, tool, context, agent_state
    ):
        """If Slack DM fails, classification is still stored and returned."""
        context["agent_state"] = agent_state

        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OWNER"

        mock_classification = MagicMock()
        mock_classification.id = "cls-alert-2"

        mock_slack_client = AsyncMock()
        mock_slack_client.conversations_open.side_effect = Exception("Slack down")
        mock_slack_service = MagicMock()
        mock_slack_service.client = mock_slack_client

        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ), patch(
            "app.services.slack.get_slack_service",
            return_value=mock_slack_service,
        ), patch(
            "app.services.notifications.NotificationService.publish",
            new_callable=AsyncMock,
        ):
            result = await tool.execute(
                context=context,
                abstract="Server down",
                reason="Outage",
                confidence=0.9,
            )

        data = json.loads(result)
        assert data["status"] == "alerted"
        assert data["classification_id"] == "cls-alert-2"


# ---------------------------------------------------------------------------
# QueueForDigestTool
# ---------------------------------------------------------------------------


class TestQueueForDigestToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.queue_for_digest import QueueForDigestTool

        tool = QueueForDigestTool()
        defn = tool.to_definition()
        assert defn.name == "queue_for_digest"
        assert "abstract" in defn.parameters["properties"]
        assert "reason" in defn.parameters["properties"]
        assert "confidence" in defn.parameters["properties"]
        assert "priority" in defn.parameters["properties"]
        assert defn.parameters["properties"]["priority"]["enum"] == [
            "P1",
            "P2",
            "P3",
        ]
        assert tool.max_iterations == 1


class TestQueueForDigestToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.queue_for_digest import QueueForDigestTool

        return QueueForDigestTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.fixture
    def agent_state(self):
        return {
            "sender_slack_id": "U_SENDER",
            "sender_name": "Bob",
            "channel_id": "C002",
            "channel_name": "alerts",
            "message_ts": "222.333",
            "thread_ts": None,
            "slack_permalink": "https://slack.com/link",
            "classification_path": "channel",
            "p1_max_wait_minutes": 30,
            "p1_settled_threshold_minutes": 5,
        }

    @pytest.mark.asyncio
    async def test_p1_sets_delivery_params(self, tool, context, agent_state):
        context["agent_state"] = agent_state

        mock_classification = MagicMock()
        mock_classification.id = "cls-q1"

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                abstract="Deploy approval needed",
                reason="Time-sensitive",
                confidence=0.85,
                priority="P1",
            )

        data = json.loads(result)
        assert data["status"] == "queued"
        assert data["priority"] == "P1"
        assert data["action"] == "summarize_next"
        assert data["deliver_by"] is not None

        create_arg = mock_create.call_args[0][0]
        assert create_arg.action == "summarize_next"
        assert create_arg.queued_for_digest is True
        assert create_arg.deliver_by is not None
        assert create_arg.settled_threshold is not None

    @pytest.mark.asyncio
    async def test_p2_eod_no_deliver_by(self, tool, context, agent_state):
        context["agent_state"] = agent_state

        mock_classification = MagicMock()
        mock_classification.id = "cls-q2"

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                abstract="FYI update",
                reason="Info only",
                confidence=0.7,
                priority="P2",
            )

        data = json.loads(result)
        assert data["status"] == "queued"
        assert data["priority"] == "P2"
        assert data["action"] == "summarize_eod"
        assert data["deliver_by"] is None

        create_arg = mock_create.call_args[0][0]
        assert create_arg.action == "summarize_eod"
        assert create_arg.queued_for_digest is True
        assert create_arg.deliver_by is None
        assert create_arg.settled_threshold is None

    @pytest.mark.asyncio
    async def test_p3_not_queued(self, tool, context, agent_state):
        context["agent_state"] = agent_state

        mock_classification = MagicMock()
        mock_classification.id = "cls-q3"

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                abstract="Random chatter",
                reason="Not relevant",
                confidence=0.6,
                priority="P3",
            )

        data = json.loads(result)
        assert data["status"] == "queued"
        assert data["priority"] == "P3"
        assert data["action"] == "ignore"

        create_arg = mock_create.call_args[0][0]
        assert create_arg.action == "ignore"
        assert create_arg.queued_for_digest is False

    @pytest.mark.asyncio
    async def test_uses_pending_group_id(self, tool, context, agent_state):
        """If agent_state has pending_group_id, uses it as group_id."""
        agent_state["pending_group_id"] = "grp-abc"
        context["agent_state"] = agent_state

        mock_classification = MagicMock()
        mock_classification.id = "cls-q4"

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                abstract="Related msg",
                reason="Part of group",
                confidence=0.8,
                priority="P1",
            )

        create_arg = mock_create.call_args[0][0]
        assert create_arg.group_id == "grp-abc"

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(
            context=None, abstract="x", reason="y", confidence=0.9, priority="P1"
        )
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# LinkMessagesTool
# ---------------------------------------------------------------------------


class TestLinkMessagesToolDefinition:
    def test_definition(self):
        from app.agents.triage.tools.link_messages import LinkMessagesTool

        tool = LinkMessagesTool()
        defn = tool.to_definition()
        assert defn.name == "link_messages"
        assert "existing_message_id" in defn.parameters["properties"]
        assert "priority" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestLinkMessagesToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.triage.tools.link_messages import LinkMessagesTool

        return LinkMessagesTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.fixture
    def agent_state(self):
        return {
            "sender_slack_id": "U_SENDER",
            "sender_name": "Carol",
            "channel_id": "C003",
            "channel_name": "ops",
            "message_ts": "333.444",
            "thread_ts": None,
            "slack_permalink": "https://slack.com/link2",
            "classification_path": "channel",
            "p1_max_wait_minutes": 30,
            "p1_settled_threshold_minutes": 5,
        }

    @pytest.mark.asyncio
    async def test_links_to_existing_creates_group(self, tool, context, agent_state):
        """When existing message has no group_id, creates new one and sets it."""
        context["agent_state"] = agent_state

        mock_existing = MagicMock()
        mock_existing.id = "cls-existing"
        mock_existing.group_id = None  # No existing group

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.get",
            new_callable=AsyncMock,
            return_value=mock_existing,
        ), patch(
            "app.db.repositories.triage.TriageClassificationRepository.update",
            new_callable=AsyncMock,
            return_value=mock_existing,
        ):
            # Mock the bulk update for group members
            mock_db = context["db"]
            mock_db.execute = AsyncMock()

            result = await tool.execute(
                context=context,
                existing_message_id="cls-existing",
                priority="P2",
            )

        data = json.loads(result)
        assert data["status"] == "linked"
        assert data["group_id"] is not None
        assert data["existing_message_id"] == "cls-existing"

        # Verify pending_group_id was set in agent_state
        assert agent_state["pending_group_id"] == data["group_id"]

    @pytest.mark.asyncio
    async def test_links_to_existing_with_group(self, tool, context, agent_state):
        """When existing message already has group_id, reuses it."""
        context["agent_state"] = agent_state

        mock_existing = MagicMock()
        mock_existing.id = "cls-existing"
        mock_existing.group_id = "grp-existing"

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.get",
            new_callable=AsyncMock,
            return_value=mock_existing,
        ):
            mock_db = context["db"]
            mock_db.execute = AsyncMock()

            result = await tool.execute(
                context=context,
                existing_message_id="cls-existing",
                priority="P2",
            )

        data = json.loads(result)
        assert data["status"] == "linked"
        assert data["group_id"] == "grp-existing"

    @pytest.mark.asyncio
    async def test_existing_not_found(self, tool, context, agent_state):
        context["agent_state"] = agent_state

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await tool.execute(
                context=context,
                existing_message_id="cls-nonexistent",
                priority="P2",
            )

        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(
            context=None, existing_message_id="x", priority="P1"
        )
        data = json.loads(result)
        assert "error" in data
