"""Tests for digest subagent tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.base import ToolContext


# ---------------------------------------------------------------------------
# DigestFetchThreadTool
# ---------------------------------------------------------------------------


class TestDigestFetchThreadToolDefinition:
    def test_definition(self):
        from app.agents.digest.tools.fetch_thread import DigestFetchThreadTool

        tool = DigestFetchThreadTool()
        defn = tool.to_definition()
        assert defn.name == "digest_fetch_thread"
        assert "channel_id" in defn.parameters["properties"]
        assert "thread_ts" in defn.parameters["properties"]
        assert tool.max_iterations == 2


class TestDigestFetchThreadToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.digest.tools.fetch_thread import DigestFetchThreadTool

        return DigestFetchThreadTool()

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
# DigestFetchChannelHistoryTool
# ---------------------------------------------------------------------------


class TestDigestFetchChannelHistoryToolDefinition:
    def test_definition(self):
        from app.agents.digest.tools.fetch_channel_history import (
            DigestFetchChannelHistoryTool,
        )

        tool = DigestFetchChannelHistoryTool()
        defn = tool.to_definition()
        assert defn.name == "digest_fetch_channel_history"
        assert "channel_id" in defn.parameters["properties"]
        assert tool.max_iterations == 2


class TestDigestFetchChannelHistoryToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.digest.tools.fetch_channel_history import (
            DigestFetchChannelHistoryTool,
        )

        return DigestFetchChannelHistoryTool()

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
# SendDigestDmTool
# ---------------------------------------------------------------------------


class TestSendDigestDmToolDefinition:
    def test_definition(self):
        from app.agents.digest.tools.send_digest_dm import SendDigestDmTool

        tool = SendDigestDmTool()
        defn = tool.to_definition()
        assert defn.name == "send_digest_dm"
        assert "digest_text" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestSendDigestDmToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.digest.tools.send_digest_dm import SendDigestDmTool

        return SendDigestDmTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_sends_dm_to_user(self, tool, context):
        """Sends digest to user's Slack DM via their slack_user_id."""
        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OWNER"

        mock_slack_service = MagicMock()
        mock_slack_service.send_message = AsyncMock(return_value={"ok": True})

        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.agents.digest.tools.send_digest_dm.get_slack_service",
            return_value=mock_slack_service,
        ):
            result = await tool.execute(
                context=context,
                digest_text="*Your Daily Digest*\n- Item 1\n- Item 2",
            )

        data = json.loads(result)
        assert data["status"] == "sent"

        mock_slack_service.send_message.assert_awaited_once_with(
            channel="U_OWNER",
            text="*Your Daily Digest*\n- Item 1\n- Item 2",
        )

    @pytest.mark.asyncio
    async def test_handles_missing_slack_user_id(self, tool, context):
        """Returns error when user has no slack_user_id."""
        mock_user = MagicMock()
        mock_user.slack_user_id = None

        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            result = await tool.execute(
                context=context,
                digest_text="Some digest",
            )

        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_handles_user_not_found(self, tool, context):
        """Returns error when user is not found."""
        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await tool.execute(
                context=context,
                digest_text="Some digest",
            )

        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_handles_slack_error(self, tool, context):
        """Returns error when Slack API fails."""
        mock_user = MagicMock()
        mock_user.slack_user_id = "U_OWNER"

        mock_slack_service = MagicMock()
        mock_slack_service.send_message = AsyncMock(
            side_effect=Exception("Slack API error")
        )

        with patch(
            "app.db.repositories.user.UserRepository.get",
            new_callable=AsyncMock,
            return_value=mock_user,
        ), patch(
            "app.agents.digest.tools.send_digest_dm.get_slack_service",
            return_value=mock_slack_service,
        ):
            result = await tool.execute(
                context=context,
                digest_text="Some digest",
            )

        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        """Returns error if context is missing."""
        result = await tool.execute(context=None, digest_text="Some digest")
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# SaveDigestRecordTool
# ---------------------------------------------------------------------------


class TestSaveDigestRecordToolDefinition:
    def test_definition(self):
        from app.agents.digest.tools.save_digest_record import SaveDigestRecordTool

        tool = SaveDigestRecordTool()
        defn = tool.to_definition()
        assert defn.name == "save_digest_record"
        assert "summary_text" in defn.parameters["properties"]
        assert "message_ids" in defn.parameters["properties"]
        assert "digest_type" in defn.parameters["properties"]
        assert defn.parameters["properties"]["digest_type"]["enum"] == ["p1", "eod"]
        assert tool.max_iterations == 1


class TestSaveDigestRecordToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.digest.tools.save_digest_record import SaveDigestRecordTool

        return SaveDigestRecordTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_creates_consolidated_record(self, tool, context):
        """Creates a consolidated TriageClassification record and links children."""
        mock_classification = MagicMock()
        mock_classification.id = "digest-record-1"

        mock_db = context["db"]
        mock_db.execute = AsyncMock()

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                summary_text="Summary of 3 messages",
                message_ids=["cls-1", "cls-2", "cls-3"],
                digest_type="p1",
            )

        data = json.loads(result)
        assert data["status"] == "saved"
        assert data["digest_record_id"] == "digest-record-1"

        # Verify classification was created with correct fields
        mock_create.assert_awaited_once()
        create_arg = mock_create.call_args[0][0]
        assert create_arg.is_consolidated is True
        assert create_arg.action == "summarize_next"
        assert create_arg.abstract == "Summary of 3 messages"
        assert create_arg.child_count == 3
        assert create_arg.digest_type == "scheduled"
        assert create_arg.queued_for_digest is False

        # Verify child messages were linked via SQL update
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_eod_digest_type(self, tool, context):
        """EOD digest type sets action to summarize_eod."""
        mock_classification = MagicMock()
        mock_classification.id = "digest-record-2"

        mock_db = context["db"]
        mock_db.execute = AsyncMock()

        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            return_value=mock_classification,
        ) as mock_create:
            result = await tool.execute(
                context=context,
                summary_text="EOD summary",
                message_ids=["cls-1"],
                digest_type="eod",
            )

        data = json.loads(result)
        assert data["status"] == "saved"

        create_arg = mock_create.call_args[0][0]
        assert create_arg.action == "summarize_eod"

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(
            context=None,
            summary_text="x",
            message_ids=["1"],
            digest_type="p1",
        )
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        with patch(
            "app.db.repositories.triage.TriageClassificationRepository.create",
            new_callable=AsyncMock,
            side_effect=Exception("DB error"),
        ):
            result = await tool.execute(
                context=context,
                summary_text="x",
                message_ids=["1"],
                digest_type="p1",
            )

        data = json.loads(result)
        assert "error" in data
        assert "DB error" in data["error"]


# ---------------------------------------------------------------------------
# MarkDeliveredTool
# ---------------------------------------------------------------------------


class TestMarkDeliveredToolDefinition:
    def test_definition(self):
        from app.agents.digest.tools.mark_delivered import MarkDeliveredTool

        tool = MarkDeliveredTool()
        defn = tool.to_definition()
        assert defn.name == "mark_delivered"
        assert "message_ids" in defn.parameters["properties"]
        assert tool.max_iterations == 1


class TestMarkDeliveredToolExecute:
    @pytest.fixture
    def tool(self):
        from app.agents.digest.tools.mark_delivered import MarkDeliveredTool

        return MarkDeliveredTool()

    @pytest.fixture
    def context(self):
        return ToolContext(db=AsyncMock(), user_id="user-123")

    @pytest.mark.asyncio
    async def test_marks_messages_delivered(self, tool, context):
        """Updates queued_for_digest=False and processed_reason='summarized'."""
        mock_db = context["db"]
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await tool.execute(
            context=context,
            message_ids=["cls-1", "cls-2", "cls-3"],
        )

        data = json.loads(result)
        assert data["status"] == "marked"
        assert data["count"] == 3

        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_message_ids(self, tool, context):
        """Handles empty message_ids list."""
        mock_db = context["db"]
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await tool.execute(
            context=context,
            message_ids=[],
        )

        data = json.loads(result)
        assert data["status"] == "marked"
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_missing_context(self, tool):
        result = await tool.execute(context=None, message_ids=["1"])
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, context):
        mock_db = context["db"]
        mock_db.execute = AsyncMock(side_effect=Exception("DB error"))

        result = await tool.execute(
            context=context,
            message_ids=["cls-1"],
        )

        data = json.loads(result)
        assert "error" in data
        assert "DB error" in data["error"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestDigestToolRegistry:
    def test_registry_has_all_tools(self):
        from app.agents.digest.tools import get_digest_tool_registry

        registry = get_digest_tool_registry()
        expected = [
            "digest_fetch_thread",
            "digest_fetch_channel_history",
            "send_digest_dm",
            "save_digest_record",
            "mark_delivered",
        ]
        for name in expected:
            assert registry.get(name) is not None, f"Missing tool: {name}"

    def test_registry_definitions(self):
        from app.agents.digest.tools import get_digest_tool_registry

        registry = get_digest_tool_registry()
        definitions = registry.get_definitions()
        assert len(definitions) == 5
        names = {d.name for d in definitions}
        assert "digest_fetch_thread" in names
        assert "digest_fetch_channel_history" in names
        assert "send_digest_dm" in names
        assert "save_digest_record" in names
        assert "mark_delivered" in names
