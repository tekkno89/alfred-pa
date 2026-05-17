"""Test that focus mode works identically with bot filter changes.

This test ensures:
1. Bot messages skip LLM classification (short-circuit)
2. Bot messages with explicit rules use that action
3. Focus mode continues to work correctly with bot messages
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.models.triage import (
    MonitoredChannel,
    ChannelSourceRule,
    TriageClassification,
    TriageUserSettings,
)
from app.services.triage_enrichment import EnrichedTriagePayload
from app.services.triage_classifier import ClassificationResult
from tests.factories import UserFactory


class TestBotFilterFocusModeParity:
    """Tests for bot filter behavior with focus mode."""

    @pytest.mark.asyncio
    async def test_bot_filter_short_circuits_before_llm(
        self, db_session: AsyncSession, test_user: User
    ):
        """Bot message should not trigger LLM call - short-circuit to 'ignore'.

        This test verifies that bot rules are checked BEFORE LLM classification.
        Bot messages should never reach the LLM classifier.
        """
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id=test_user.id,
            event_type="channel",
            channel_id="C12345",
            sender_slack_id="B99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="PagerDuty alert triggered",
            sensitivity="medium",
            is_bot=True,
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="notify_now",
            confidence=1.0,
            reason="Should not be called",
            abstract="Should not be called",
        )

        mock_class_repo = AsyncMock()
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)
        mock_exclusion_repo = AsyncMock()
        mock_exclusion_repo.get_bot_rule.return_value = None

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.ChannelSourceRuleRepository",
                return_value=mock_exclusion_repo,
            ),
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(db_session)
            await pipeline.process(
                user_id=test_user.id,
                event_type="channel",
                channel_id="C12345",
                sender_slack_id="B99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="PagerDuty alert triggered",
                bot_id="B99999",
            )

        mock_classifier.classify.assert_not_called()
        mock_class_repo.create.assert_called_once()
        created = mock_class_repo.create.call_args[0][0]
        assert created.action == "ignore"
        assert created.sender_slack_id == "B99999"

    @pytest.mark.asyncio
    async def test_focus_mode_behavior_with_bot_messages(
        self, db_session: AsyncSession, test_user: User
    ):
        """Focus mode should handle bot messages correctly.

        This test ensures focus mode continues to work correctly with bot messages.
        Bot messages should be short-circuited (ignored by default) without
        affecting the normal focus mode flow for human messages.
        """
        mock_enrichment = AsyncMock()

        async def enrich_side_effect(*args, **kwargs):
            is_bot = kwargs.get("bot_id") is not None
            return EnrichedTriagePayload(
                user_id=test_user.id,
                event_type="channel",
                channel_id="C12345",
                sender_slack_id=kwargs["sender_slack_id"],
                message_ts=kwargs["message_ts"],
                thread_ts=None,
                message_text=kwargs["message_text"],
                sensitivity="medium",
                is_bot=is_bot,
            )

        mock_enrichment.enrich.side_effect = enrich_side_effect

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="notify_now",
            confidence=0.9,
            reason="Urgent human message",
            abstract="Urgent message",
        )

        mock_class_repo = AsyncMock()
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(
            debug_mode=False, p0_alerts_enabled=False
        )
        mock_exclusion_repo = AsyncMock()
        mock_exclusion_repo.get_bot_rule.return_value = None

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.ChannelSourceRuleRepository",
                return_value=mock_exclusion_repo,
            ),
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(db_session)

            # Process bot message - should be ignored, no LLM call
            await pipeline.process(
                user_id=test_user.id,
                event_type="channel",
                channel_id="C12345",
                sender_slack_id="B99999",
                message_ts="1234567890.111111",
                thread_ts=None,
                message_text="Bot message",
                bot_id="B99999",
            )

            # Process human message - should go to LLM
            await pipeline.process(
                user_id=test_user.id,
                event_type="channel",
                channel_id="C12345",
                sender_slack_id="U88888",
                message_ts="1234567890.222222",
                thread_ts=None,
                message_text="Human message",
                bot_id=None,
            )

        # Bot message: no LLM call
        # Human message: LLM call made
        mock_classifier.classify.assert_called_once()

        # Both classifications should be created
        assert mock_class_repo.create.call_count == 2
        bot_class = mock_class_repo.create.call_args_list[0][0][0]
        human_class = mock_class_repo.create.call_args_list[1][0][0]

        assert bot_class.action == "ignore"
        assert human_class.action == "notify_now"

    @pytest.mark.asyncio
    async def test_bot_with_explicit_rule_uses_rule_action(
        self, db_session: AsyncSession, test_user: User
    ):
        """Bot with an explicit rule should use that action, not default 'ignore'."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id=test_user.id,
            event_type="channel",
            channel_id="C12345",
            sender_slack_id="B99999",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="PagerDuty alert: High CPU",
            sensitivity="medium",
            is_bot=True,
        )

        mock_classifier = AsyncMock()
        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(
            debug_mode=False, p0_alerts_enabled=False
        )
        mock_class_repo = AsyncMock()
        mock_exclusion_repo = AsyncMock()
        mock_exclusion_repo.get_bot_rule.return_value = MagicMock(action="notify_now")

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.ChannelSourceRuleRepository",
                return_value=mock_exclusion_repo,
            ),
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(db_session)
            await pipeline.process(
                user_id=test_user.id,
                event_type="channel",
                channel_id="C12345",
                sender_slack_id="B99999",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="PagerDuty alert: High CPU",
                bot_id="B99999",
            )

        mock_classifier.classify.assert_not_called()
        mock_class_repo.create.assert_called_once()
        created = mock_class_repo.create.call_args[0][0]
        assert created.action == "notify_now"

    @pytest.mark.asyncio
    async def test_non_bot_message_proceeds_to_llm(
        self, db_session: AsyncSession, test_user: User
    ):
        """Non-bot message should proceed to LLM classification."""
        mock_enrichment = AsyncMock()
        mock_enrichment.enrich.return_value = EnrichedTriagePayload(
            user_id=test_user.id,
            event_type="dm",
            channel_id="D12345",
            sender_slack_id="U88888",
            message_ts="1234567890.123456",
            thread_ts=None,
            message_text="Hello from a real user",
            sensitivity="medium",
            is_bot=False,
        )

        mock_classifier = AsyncMock()
        mock_classifier.classify.return_value = ClassificationResult(
            action="summarize_next",
            confidence=0.8,
            reason="casual DM",
            abstract="Hello message",
        )

        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_by_user_id.return_value = MagicMock(debug_mode=False)
        mock_class_repo = AsyncMock()
        mock_exclusion_repo = AsyncMock()

        with (
            patch(
                "app.services.triage_pipeline.TriageEnrichmentService",
                return_value=mock_enrichment,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassifier",
                return_value=mock_classifier,
            ),
            patch(
                "app.services.triage_pipeline.TriageClassificationRepository",
                return_value=mock_class_repo,
            ),
            patch(
                "app.services.triage_pipeline.TriageUserSettingsRepository",
                return_value=mock_settings_repo,
            ),
            patch(
                "app.services.triage_pipeline.ChannelSourceRuleRepository",
                return_value=mock_exclusion_repo,
            ),
            patch("app.services.triage_pipeline.NotificationService"),
        ):
            from app.services.triage_pipeline import TriagePipeline

            pipeline = TriagePipeline(db_session)
            await pipeline.process(
                user_id=test_user.id,
                event_type="dm",
                channel_id="D12345",
                sender_slack_id="U88888",
                message_ts="1234567890.123456",
                thread_ts=None,
                message_text="Hello from a real user",
            )

        mock_classifier.classify.assert_called_once()
        mock_class_repo.create.assert_called_once()
        created = mock_class_repo.create.call_args[0][0]
        assert created.action == "summarize_next"


class TestChannelSourceRuleBotRules:
    """Tests for ChannelSourceRuleRepository bot rule lookup."""

    @pytest.mark.asyncio
    async def test_get_bot_rule_returns_rule_for_bot_entity(
        self, db_session: AsyncSession, test_user: User
    ):
        """Repository should find bot rules by slack_entity_id and entity_type='bot'."""
        from app.db.repositories.triage import ChannelSourceRuleRepository

        monitored = MonitoredChannel(
            user_id=test_user.id,
            slack_channel_id="C12345",
            channel_name="alerts",
            channel_type="public",
        )
        db_session.add(monitored)
        await db_session.commit()
        await db_session.refresh(monitored)

        bot_rule = ChannelSourceRule(
            monitored_channel_id=monitored.id,
            user_id=test_user.id,
            slack_entity_id="B99999",
            entity_type="bot",
            action="notify_now",
            display_name="PagerDuty Bot",
        )
        db_session.add(bot_rule)
        await db_session.commit()

        repo = ChannelSourceRuleRepository(db_session)
        result = await repo.get_bot_rule(
            user_id=test_user.id,
            channel_id="C12345",
            bot_id="B99999",
        )

        assert result is not None
        assert result.action == "notify_now"
        assert result.slack_entity_id == "B99999"
        assert result.entity_type == "bot"

    @pytest.mark.asyncio
    async def test_get_bot_rule_returns_none_for_nonexistent_bot(
        self, db_session: AsyncSession, test_user: User
    ):
        """Repository should return None if no bot rule exists."""
        from app.db.repositories.triage import ChannelSourceRuleRepository

        repo = ChannelSourceRuleRepository(db_session)
        result = await repo.get_bot_rule(
            user_id=test_user.id,
            channel_id="C12345",
            bot_id="B_NONEXISTENT",
        )

        assert result is None


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = UserFactory(slack_user_id="U12345678")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
