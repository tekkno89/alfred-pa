"""Tests for TriageClassifier."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.triage_classifier import TriageClassifier, ClassificationResult
from app.services.triage_enrichment import EnrichedTriagePayload


def _make_payload(**overrides) -> EnrichedTriagePayload:
    defaults = dict(
        user_id="user-1",
        event_type="dm",
        channel_id="D12345",
        sender_slack_id="U99999",
        message_ts="1234567890.123456",
        thread_ts=None,
        message_text="Hello, are you available?",
        sender_name="Alice",
        is_vip=False,
        focus_session_id="session-1",
        is_in_focus=True,
        channel_priority="medium",
        channel_name="",
        slack_permalink=None,
        sensitivity="medium",
        keyword_rules=[],
    )
    defaults.update(overrides)
    return EnrichedTriagePayload(**defaults)


class TestClassifyDM:
    async def test_vip_sender_always_p0(self):
        classifier = TriageClassifier(sensitivity="medium")
        payload = _make_payload(is_vip=True)

        result = await classifier.classify(payload)

        assert result.priority == "p0"
        assert result.confidence == 1.0
        assert "VIP" in result.reason

    async def test_non_vip_dm_calls_llm(self):
        classifier = TriageClassifier(sensitivity="medium")
        payload = _make_payload(is_vip=False)

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = (
            '{"priority": "review", "confidence": 0.8, '
            '"reason": "casual message", "abstract": "Asking about availability"}'
        )

        with patch(
            "app.services.triage_classifier.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await classifier.classify(payload)

        assert result.priority == "review"
        assert result.confidence == 0.8
        mock_provider.generate.assert_called_once()


class TestClassifyChannel:
    async def test_keyword_match_overrides_llm(self):
        classifier = TriageClassifier(sensitivity="medium")

        rule = MagicMock()
        rule.keyword_pattern = "deploy"
        rule.match_type = "contains"
        rule.priority_override = "p0"

        payload = _make_payload(
            event_type="channel",
            channel_id="C12345",
            message_text="Starting deploy to production now",
            keyword_rules=[rule],
        )

        result = await classifier.classify(payload)

        assert result.priority == "p0"
        assert result.confidence == 1.0
        assert "deploy" in result.reason.lower()

    async def test_exact_keyword_match(self):
        classifier = TriageClassifier()

        rule = MagicMock()
        rule.keyword_pattern = "outage"
        rule.match_type = "exact"
        rule.priority_override = "p0"

        payload = _make_payload(
            event_type="channel",
            message_text="We have an outage right now",
            keyword_rules=[rule],
        )

        result = await classifier.classify(payload)

        assert result.priority == "p0"

    async def test_exact_keyword_no_match_substring(self):
        """'outage' should not match 'outages' in exact mode."""
        classifier = TriageClassifier()

        rule = MagicMock()
        rule.keyword_pattern = "outage"
        rule.match_type = "exact"
        rule.priority_override = "p0"

        payload = _make_payload(
            event_type="channel",
            message_text="Looking at past outages",
            keyword_rules=[rule],
        )

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = (
            '{"priority": "p2", "confidence": 0.7, '
            '"reason": "historical discussion", "abstract": "Discussing past incidents"}'
        )

        with patch(
            "app.services.triage_classifier.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await classifier.classify(payload)

        # Should NOT match exact "outage" in "outages" -> falls through to LLM
        assert result.priority == "p2"

    async def test_critical_channel_auto_escalates(self):
        classifier = TriageClassifier()
        payload = _make_payload(
            event_type="channel",
            channel_id="C12345",
            channel_priority="critical",
            channel_name="incidents",
            keyword_rules=[],
        )

        result = await classifier.classify(payload)

        assert result.priority == "p0"
        assert result.confidence == 0.9

    async def test_llm_fallback_on_error(self):
        classifier = TriageClassifier()
        payload = _make_payload(event_type="channel", keyword_rules=[])

        mock_provider = AsyncMock()
        mock_provider.generate.side_effect = Exception("LLM error")

        with patch(
            "app.services.triage_classifier.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await classifier.classify(payload)

        assert result.priority == "review"
        assert result.confidence == 0.3


class TestSensitivity:
    async def test_sensitivity_passed_to_prompt(self):
        classifier = TriageClassifier(sensitivity="high")
        payload = _make_payload()

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = (
            '{"priority": "p0", "confidence": 0.9, '
            '"reason": "high sensitivity", "abstract": "A question"}'
        )

        with patch(
            "app.services.triage_classifier.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await classifier.classify(payload)

        # Verify the system prompt contains the sensitivity
        call_args = mock_provider.generate.call_args
        messages = call_args[1].get("messages") or call_args[0][0]
        system_msg = next(m for m in messages if m.role == "system")
        assert "high" in system_msg.content


class TestCustomDefinitions:
    async def test_custom_definitions_in_prompt(self):
        classifier = TriageClassifier(
            sensitivity="medium",
            p0_definition="Only production fires",
            p1_definition="Direct asks from my manager",
        )
        payload = _make_payload()

        mock_provider = AsyncMock()
        mock_provider.generate.return_value = (
            '{"priority": "p1", "confidence": 0.8, '
            '"reason": "manager ask", "abstract": "Question from manager"}'
        )

        with patch(
            "app.services.triage_classifier.get_llm_provider",
            return_value=mock_provider,
        ):
            result = await classifier.classify(payload)

        call_args = mock_provider.generate.call_args
        messages = call_args[1].get("messages") or call_args[0][0]
        system_msg = next(m for m in messages if m.role == "system")
        assert "Only production fires" in system_msg.content
        assert "Direct asks from my manager" in system_msg.content
        assert result.priority == "p1"
