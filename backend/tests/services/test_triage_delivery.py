"""Tests for TriageDeliveryService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_delivery import TriageDeliveryService


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_classification(**overrides):
    from datetime import datetime

    defaults = {
        "id": "class-1",
        "sender_slack_id": "U_SENDER",
        "sender_name": "Sender",
        "channel_id": "C12345",
        "channel_name": "general",
        "priority_level": "p2",
        "abstract": "Test message",
        "slack_permalink": "https://workspace.slack.com/archives/C12345/p123",
        "surfaced_at_break": False,
        "classification_path": "channel",
        "message_ts": "1234567890.123456",
        "confidence": 0.8,
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock(**defaults)
    # Make confidence and created_at comparable
    m.confidence = defaults["confidence"]
    m.created_at = defaults["created_at"]
    return m


class TestDeliverSessionDigest:
    async def test_delivers_items_and_creates_summary(self, mock_db):
        """Should create a digest summary and send Slack DM."""
        items = [_make_classification(id=f"class-{i}") for i in range(3)]
        mock_user = MagicMock()
        mock_user.slack_user_id = "U_SELF"

        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = items
            # _create_digest_summary needs to work — mock the create and link
            mock_summary = MagicMock(id="summary-1")
            service.class_repo.create.return_value = mock_summary
            service.class_repo.link_to_summary = AsyncMock()
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                count = await service.deliver_session_digest("user-1", "session-1")

        assert count == 3
        service.class_repo.mark_surfaced_at_break.assert_called_once()
        mock_slack.send_message.assert_called_once()

    async def test_returns_zero_when_no_items(self, mock_db):
        """Should return 0 when there are no unsurfaced items."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.notification_service = AsyncMock()

            count = await service.deliver_session_digest("user-1", "session-1")

        assert count == 0
        service.class_repo.mark_surfaced_at_break.assert_not_called()

    async def test_publishes_sse_event(self, mock_db):
        """Should publish triage.break_check_slack SSE event."""
        items = [_make_classification()]
        mock_user = MagicMock(slack_user_id="U_SELF")

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_unsurfaced_digest_items.return_value = items
            mock_summary = MagicMock(id="summary-1")
            service.class_repo.create.return_value = mock_summary
            service.class_repo.link_to_summary = AsyncMock()
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=AsyncMock(),
            ):
                await service.deliver_session_digest("user-1", "session-1")

        service.notification_service.publish.assert_called_once()
        sse_call = service.notification_service.publish.call_args
        assert sse_call[0][1] == "triage.break_check_slack"
        assert sse_call[0][2]["count"] == 1


class TestClearBreakNotification:
    async def test_publishes_clear_event(self, mock_db):
        """Should publish triage.break_notification_clear SSE event."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.notification_service = AsyncMock()

            await service.clear_break_notification("user-1")

        service.notification_service.publish.assert_called_once_with(
            "user-1", "triage.break_notification_clear", {}
        )


class TestGenerateAndSendDigest:
    async def test_sends_digest_dm(self, mock_db):
        """Should send a Slack DM with digest grouped by priority."""
        from datetime import datetime

        items = [
            _make_classification(
                priority_level="p0", abstract="Server down", confidence=0.9
            ),
            _make_classification(
                priority_level="p1", abstract="Meeting notes", confidence=0.8
            ),
            _make_classification(
                priority_level="p3", abstract="Newsletter", confidence=0.6
            ),
        ]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = items
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                await service.generate_and_send_digest("user-1", "session-1")

        mock_slack.send_message.assert_called_once()
        text = mock_slack.send_message.call_args[1]["text"]
        assert "Focus Session Triage Digest" in text
        # P0 should not appear in digest (instantly notified during focus)
        assert "P0: 1" not in text
        assert "P1: 1" in text
        assert "P2: 0" in text

    async def test_shows_top_3_by_confidence(self, mock_db):
        """Should show top 3 items sorted by confidence score."""
        from datetime import datetime

        items = [
            _make_classification(
                id="p1-low",
                priority_level="p1",
                abstract="Low priority",
                confidence=0.5,
            ),
            _make_classification(
                id="p1-high",
                priority_level="p1",
                abstract="High priority",
                confidence=0.95,
            ),
            _make_classification(
                id="p1-mid",
                priority_level="p1",
                abstract="Mid priority",
                confidence=0.75,
            ),
            _make_classification(
                id="p1-vlow", priority_level="p1", abstract="Very low", confidence=0.3
            ),
            _make_classification(
                id="p1-vhigh",
                priority_level="p1",
                abstract="Very high",
                confidence=0.85,
            ),
        ]
        mock_user = MagicMock(slack_user_id="U_SELF")
        mock_slack = AsyncMock()

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = items
            service.class_repo.get_unsurfaced_digest_items.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.user_repo.get.return_value = mock_user
            service.notification_service = AsyncMock()

            with patch(
                "app.services.triage_delivery.SlackService",
                return_value=mock_slack,
            ):
                await service.generate_and_send_digest("user-1", "session-1")

        text = mock_slack.send_message.call_args[1]["text"]
        # Should show top 3 (high 0.95, vhigh 0.85, mid 0.75)
        assert "High priority" in text
        assert "Very high" in text
        assert "Mid priority" in text
        # Should not show lower confidence items
        assert "Low priority" not in text
        assert "Very low" not in text
        # Should show remaining count
        assert "2 more P1 messages" in text
        assert "Check Alfred Triage" in text

    async def test_no_digest_when_no_items(self, mock_db):
        """Should not send anything when there are no classifications."""
        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.get_by_session.return_value = []
            service.settings_repo = AsyncMock()
            service.user_repo = AsyncMock()
            service.notification_service = AsyncMock()

            await service.generate_and_send_digest("user-1", "session-1")

        service.user_repo.get.assert_not_called()


class TestTwoModeSummarizer:
    """Tests for thread_incremental vs full summarization modes."""

    @pytest.mark.asyncio
    async def test_thread_incremental_mode_includes_context_new(self, mock_db):
        """thread_incremental mode should include CONTEXT/NEW distinction in prompt."""
        from app.services.digest_grouper import ConversationGroup, ThreadContext

        msg = _make_classification(
            id="msg-1",
            sender_slack_id="U1",
            sender_name="Alice",
            abstract="I agree with the proposal",
            message_ts="100.2",
        )

        thread_ctx = ThreadContext(
            thread_ts="100.0",
            channel_id="C123",
            context_messages=[
                {"user": "U2", "text": "Bob: Here is the proposal", "ts": "100.0"},
                {"user": "U3", "text": "Carol: Looks good to me", "ts": "100.1"},
            ],
            new_messages=[msg],
            is_first_run=False,
        )

        conv = ConversationGroup(
            id="thread:100.0",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            thread_ts="100.0",
            summarization_mode="thread_incremental",
            thread_context=thread_ctx,
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()

            with patch("app.core.llm.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.generate = AsyncMock(return_value="Summary result")
                mock_llm.return_value = mock_provider

                with patch("app.core.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(
                        web_search_synthesis_model="gemini-2.5-flash-lite"
                    )

                    await service.create_conversation_summary(conv)

        call_prompt = mock_provider.generate.call_args[1]["messages"][0].content
        assert "CONTEXT" in call_prompt
        assert "NEW" in call_prompt

    @pytest.mark.asyncio
    async def test_full_mode_summarizes_all_messages(self, mock_db):
        """full mode should summarize all messages without CONTEXT/NEW distinction."""
        from app.services.digest_grouper import ConversationGroup

        messages = [
            _make_classification(
                id=f"msg-{i}",
                sender_slack_id=f"U{i}",
                sender_name=f"User{i}",
                abstract=f"Message {i}",
                message_ts=f"100.{i}",
            )
            for i in range(3)
        ]

        conv = ConversationGroup(
            id="channel:C123",
            messages=messages,
            conversation_type="channel",
            channel_id="C123",
            summarization_mode="full",
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()

            with patch("app.core.llm.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.generate = AsyncMock(return_value="Summary result")
                mock_llm.return_value = mock_provider

                with patch("app.core.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(
                        web_search_synthesis_model="gemini-2.5-flash-lite"
                    )

                    await service.create_conversation_summary(conv)

        call_prompt = mock_provider.generate.call_args[1]["messages"][0].content
        assert "CONTEXT" not in call_prompt or "NEW" not in call_prompt

    @pytest.mark.asyncio
    async def test_first_run_thread_uses_full_mode(self, mock_db):
        """First-run thread should use 'full' summarization mode."""
        from app.services.digest_grouper import ConversationGroup, ThreadContext

        msg = _make_classification(
            id="msg-1",
            sender_slack_id="U1",
            sender_name="Alice",
            abstract="Starting the discussion",
            message_ts="100.1",
        )

        thread_ctx = ThreadContext(
            thread_ts="100.1",
            channel_id="C123",
            context_messages=[],
            new_messages=[msg],
            is_first_run=True,
        )

        conv = ConversationGroup(
            id="thread:100.1",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            thread_ts="100.1",
            summarization_mode="full",
            thread_context=thread_ctx,
        )

        assert conv.summarization_mode == "full"


class TestSummaryQuality:
    """Tests for summary quality requirements."""

    @pytest.mark.asyncio
    async def test_summary_contains_participant_names(self, mock_db):
        """Summary should name participants by display name."""
        from app.services.digest_grouper import ConversationGroup

        messages = [
            _make_classification(
                id="msg-1",
                sender_slack_id="U1",
                sender_name="Mike",
                abstract="The build is broken on main branch",
                message_ts="100.1",
            ),
            _make_classification(
                id="msg-2",
                sender_slack_id="U2",
                sender_name="Sara",
                abstract="Should we roll back the release?",
                message_ts="100.2",
            ),
        ]

        conv = ConversationGroup(
            id="channel:C123",
            messages=messages,
            conversation_type="channel",
            channel_id="C123",
            summarization_mode="full",
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()

            with patch("app.core.llm.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.generate = AsyncMock(
                    return_value="Mike reported the build is broken. Sara asked about rolling back the release."
                )
                mock_llm.return_value = mock_provider

                with patch("app.core.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(
                        web_search_synthesis_model="gemini-2.5-flash-lite"
                    )

                    summary = await service.create_conversation_summary(conv)

        assert "Mike" in summary
        assert "Sara" in summary

    @pytest.mark.asyncio
    async def test_summary_avoids_user_literal(self, mock_db):
        """Summary should not use 'user' or 'a user' - should use actual names."""
        from app.services.digest_grouper import ConversationGroup

        messages = [
            _make_classification(
                id="msg-1",
                sender_slack_id="U1",
                sender_name="Raj",
                abstract="Shared the Q3 planning doc for feedback",
                message_ts="100.1",
            ),
        ]

        conv = ConversationGroup(
            id="channel:C123",
            messages=messages,
            conversation_type="channel",
            channel_id="C123",
            summarization_mode="full",
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()

            with patch("app.core.llm.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.generate = AsyncMock(
                    return_value="Raj shared the Q3 planning doc and requested feedback from the platform team."
                )
                mock_llm.return_value = mock_provider

                with patch("app.core.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(
                        web_search_synthesis_model="gemini-2.5-flash-lite"
                    )

                    summary = await service.create_conversation_summary(conv)

        assert "user" not in summary.lower() or "Raj" in summary

    @pytest.mark.asyncio
    async def test_prompt_includes_few_shot_examples(self, mock_db):
        """Prompt should include BAD/GOOD few-shot examples for quality."""
        from app.services.digest_grouper import ConversationGroup

        messages = [
            _make_classification(
                id="msg-1",
                sender_slack_id="U1",
                sender_name="Alice",
                abstract="Test message",
                message_ts="100.1",
            ),
        ]

        conv = ConversationGroup(
            id="channel:C123",
            messages=messages,
            conversation_type="channel",
            channel_id="C123",
            summarization_mode="full",
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()

            with patch("app.core.llm.get_llm_provider") as mock_llm:
                mock_provider = AsyncMock()
                mock_provider.generate = AsyncMock(return_value="Summary")
                mock_llm.return_value = mock_provider

                with patch("app.core.config.get_settings") as mock_settings:
                    mock_settings.return_value = MagicMock(
                        web_search_synthesis_model="gemini-2.5-flash-lite"
                    )

                    await service.create_conversation_summary(conv)

        call_prompt = mock_provider.generate.call_args[1]["messages"][0].content
        assert "BAD:" in call_prompt
        assert "GOOD:" in call_prompt
        assert "Caitlin" in call_prompt or "Sara" in call_prompt or "Raj" in call_prompt


class TestPrepareConversationDigest:
    """Tests for prepare_conversation_digest with thin update detection."""

    @pytest.mark.asyncio
    async def test_skips_thin_thread_update(self, mock_db):
        """Thread with all non-substantive NEW messages should be skipped."""
        from app.services.digest_grouper import ConversationGroup, ThreadContext

        msg = _make_classification(
            id="msg-1",
            sender_slack_id="U1",
            sender_name="Alice",
            abstract="ok",
            message_ts="100.2",
        )

        thread_ctx = ThreadContext(
            thread_ts="100.0",
            channel_id="C123",
            context_messages=[
                {"user": "U2", "text": "Here's the proposal", "ts": "100.0"},
                {"user": "U3", "text": "Looks good", "ts": "100.1"},
            ],
            new_messages=[msg],
            is_first_run=False,
        )

        conv = ConversationGroup(
            id="thread:100.0",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            thread_ts="100.0",
            summarization_mode="thread_incremental",
            thread_context=thread_ctx,
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.mark_processed = AsyncMock()

            mock_grouper = AsyncMock()
            mock_grouper.group_messages_with_context = AsyncMock(return_value=[conv])

            mock_checker = AsyncMock()
            mock_checker.filter_unresponded_conversations = AsyncMock(
                return_value=[conv]
            )

            with patch(
                "app.services.digest_grouper.DigestGrouper",
                return_value=mock_grouper,
            ):
                with patch(
                    "app.services.digest_response_checker.DigestResponseChecker",
                    return_value=mock_checker,
                ):
                    result = await service.prepare_conversation_digest(
                        "user-1", "U_SELF", [msg]
                    )

        service.class_repo.mark_processed.assert_called()
        call_args = service.class_repo.mark_processed.call_args
        assert call_args[0][1] == "skipped_thin_update"

    @pytest.mark.asyncio
    async def test_includes_thread_with_substantive_new(self, mock_db):
        """Thread with substantive NEW messages should be included."""
        from app.services.digest_grouper import ConversationGroup, ThreadContext

        msg = _make_classification(
            id="msg-1",
            sender_slack_id="U1",
            sender_name="Alice",
            abstract="I think we should proceed with option A for the following reasons...",
            message_ts="100.2",
        )

        thread_ctx = ThreadContext(
            thread_ts="100.0",
            channel_id="C123",
            context_messages=[
                {"user": "U2", "text": "Which option should we pick?", "ts": "100.0"},
            ],
            new_messages=[msg],
            is_first_run=False,
        )

        conv = ConversationGroup(
            id="thread:100.0",
            messages=[msg],
            conversation_type="thread",
            channel_id="C123",
            thread_ts="100.0",
            summarization_mode="thread_incremental",
            thread_context=thread_ctx,
        )

        with patch.object(TriageDeliveryService, "__init__", lambda self, db: None):
            service = TriageDeliveryService.__new__(TriageDeliveryService)
            service.db = mock_db
            service.class_repo = AsyncMock()
            service.class_repo.mark_processed = AsyncMock()

            mock_grouper = AsyncMock()
            mock_grouper.group_messages_with_context = AsyncMock(return_value=[conv])

            mock_checker = AsyncMock()
            mock_checker.filter_unresponded_conversations = AsyncMock(
                return_value=[conv]
            )

            with patch(
                "app.services.digest_grouper.DigestGrouper",
                return_value=mock_grouper,
            ):
                with patch(
                    "app.services.digest_response_checker.DigestResponseChecker",
                    return_value=mock_checker,
                ):
                    result = await service.prepare_conversation_digest(
                        "user-1", "U_SELF", [msg]
                    )

        assert len(result) == 1
