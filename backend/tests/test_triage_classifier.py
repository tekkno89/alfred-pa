"""Unit tests for the triage classifier."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.triage_classifier import TriageClassifier
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
                "urgency": "digest",
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
                "urgency": "review",
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
                "urgency": "digest",
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


class TestTightenedUrgentDefinition:
    """Verify the tightened urgent definition is in the prompt."""

    @patch("app.services.triage_classifier.get_llm_provider")
    @patch("app.services.triage_classifier.get_settings")
    async def test_urgent_definition_mentions_production_incidents(
        self, mock_settings, mock_provider_fn
    ):
        mock_settings.return_value.triage_classification_model = "test-model"
        mock_settings.return_value.triage_vertex_location = None
        provider = AsyncMock()
        provider.generate.return_value = json.dumps(
            {
                "urgency": "review",
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
        assert "Casual requests or favors" in system_content
        assert "NOT urgent" in system_content
