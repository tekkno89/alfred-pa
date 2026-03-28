"""Unit tests for the triage classifier."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.triage_classifier import (
    TriageClassifier,
    _parse_json_response,
)
from app.services.triage_enrichment import EnrichedTriagePayload


def _make_payload(**overrides) -> EnrichedTriagePayload:
    defaults = dict(
        user_id="u1",
        event_type="dm",
        channel_id="C1",
        sender_slack_id="U99",
        message_ts="1234.5678",
        thread_ts=None,
        message_text="hello",
    )
    defaults.update(overrides)
    return EnrichedTriagePayload(**defaults)


class TestCustomClassificationRules:
    """Verify custom rules are injected into the LLM prompt."""

    @patch("app.services.triage_classifier.get_llm_provider")
    @patch("app.services.triage_classifier.get_settings")
    async def test_custom_rules_appear_in_prompt(
        self, mock_settings, mock_provider_fn
    ):
        mock_settings.return_value.triage_classification_model = "test-model"
        mock_settings.return_value.triage_vertex_location = None
        provider = AsyncMock()
        provider.generate.return_value = json.dumps(
            {
                "priority": "p2",
                "confidence": 0.9,
                "reason": "test",
                "abstract": "test msg",
            }
        )
        mock_provider_fn.return_value = provider

        classifier = TriageClassifier(
            sensitivity="medium",
            custom_classification_rules="Charger requests are never urgent",
        )
        payload = _make_payload(message_text="Can I borrow your charger?")
        await classifier.classify(payload)

        # Verify the system prompt contains the custom rules
        call_args = provider.generate.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_content = messages[0].content
        assert "User-defined classification rules (follow these):" in system_content
        assert "Charger requests are never urgent" in system_content

    @patch("app.services.triage_classifier.get_llm_provider")
    @patch("app.services.triage_classifier.get_settings")
    async def test_no_custom_rules_section_when_none(
        self, mock_settings, mock_provider_fn
    ):
        mock_settings.return_value.triage_classification_model = "test-model"
        mock_settings.return_value.triage_vertex_location = None
        provider = AsyncMock()
        provider.generate.return_value = json.dumps(
            {
                "priority": "review",
                "confidence": 0.8,
                "reason": "test",
                "abstract": "test msg",
            }
        )
        mock_provider_fn.return_value = provider

        classifier = TriageClassifier(sensitivity="medium")
        payload = _make_payload(message_text="Hello there")
        await classifier.classify(payload)

        call_args = provider.generate.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_content = messages[0].content
        assert "User-defined classification rules" not in system_content

    @patch("app.services.triage_classifier.get_llm_provider")
    @patch("app.services.triage_classifier.get_settings")
    async def test_no_custom_rules_section_when_empty(
        self, mock_settings, mock_provider_fn
    ):
        mock_settings.return_value.triage_classification_model = "test-model"
        mock_settings.return_value.triage_vertex_location = None
        provider = AsyncMock()
        provider.generate.return_value = json.dumps(
            {
                "priority": "p2",
                "confidence": 0.7,
                "reason": "test",
                "abstract": "test msg",
            }
        )
        mock_provider_fn.return_value = provider

        classifier = TriageClassifier(
            sensitivity="medium", custom_classification_rules=""
        )
        payload = _make_payload(message_text="Hey")
        await classifier.classify(payload)

        call_args = provider.generate.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_content = messages[0].content
        assert "User-defined classification rules" not in system_content


class TestParseJsonResponse:
    """Test JSON parsing including truncated / code-fenced responses."""

    def test_plain_json(self):
        result = _parse_json_response('{"priority": "p2", "confidence": 0.9}')
        assert result["priority"] == "p2"

    def test_code_fenced_json(self):
        raw = '```json\n{"priority": "p0", "confidence": 0.85, "reason": "test", "abstract": "summary"}\n```'
        result = _parse_json_response(raw)
        assert result["priority"] == "p0"
        assert result["confidence"] == 0.85

    def test_truncated_code_fenced_json(self):
        """Simulates gemini-2.5-flash exhausting token budget mid-response."""
        raw = (
            '```json\n{\n  "priority": "p2",\n  "confidence": 0.9,\n'
            '  "reason": "The message discusses significant risks associated with '
            'production database writes",\n  "abstract": "A discussion about prod DB'
        )
        result = _parse_json_response(raw)
        assert result["priority"] == "p2"
        assert result["confidence"] == 0.9
        assert "production database" in result["reason"]

    def test_truncated_mid_reason(self):
        """Response truncated before abstract field even starts."""
        raw = (
            '```json\n{\n  "priority": "p0",\n  "confidence": 0.85,\n'
            '  "reason": "The message reports a failing Storybook deploy due to a'
        )
        result = _parse_json_response(raw)
        assert result["priority"] == "p0"
        assert result["confidence"] == 0.85

    def test_preamble_before_json(self):
        """Model writes text before the JSON block."""
        raw = (
            'I cannot classify because the content was not provided.\n\n'
            '```json\n{"priority": "review", "confidence": 0.5, "reason": "no content", '
            '"abstract": "unclassifiable"}\n```'
        )
        result = _parse_json_response(raw)
        assert result["priority"] == "review"

    def test_no_json_at_all_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("This is just plain text with no JSON.")


class TestP0Definition:
    """Verify the P0 definition mentions key terms."""

    @patch("app.services.triage_classifier.get_llm_provider")
    @patch("app.services.triage_classifier.get_settings")
    async def test_p0_definition_mentions_production_incidents(
        self, mock_settings, mock_provider_fn
    ):
        mock_settings.return_value.triage_classification_model = "test-model"
        mock_settings.return_value.triage_vertex_location = None
        provider = AsyncMock()
        provider.generate.return_value = json.dumps(
            {
                "priority": "review",
                "confidence": 0.8,
                "reason": "test",
                "abstract": "test msg",
            }
        )
        mock_provider_fn.return_value = provider

        classifier = TriageClassifier(sensitivity="medium")
        payload = _make_payload()
        await classifier.classify(payload)

        call_args = provider.generate.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        system_content = messages[0].content
        assert "Production incidents" in system_content
        assert "NOT P0" in system_content
