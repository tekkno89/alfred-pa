"""Tests for TriageEnrichmentService."""

import pytest

from app.services.triage_enrichment import generate_slack_permalink


class TestGenerateSlackPermalink:
    def test_basic_permalink(self):
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
        )
        assert result == "https://myworkspace.slack.com/archives/C12345/p1234567890123456"

    def test_permalink_with_thread(self):
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
            thread_ts="1234567890.000001",
        )
        assert "thread_ts=1234567890000001" in result
        assert "cid=C12345" in result

    def test_permalink_same_thread_ts(self):
        """When thread_ts == message_ts, no thread param needed."""
        result = generate_slack_permalink(
            workspace_domain="myworkspace",
            channel_id="C12345",
            message_ts="1234567890.123456",
            thread_ts="1234567890.123456",
        )
        assert "thread_ts" not in result

    def test_permalink_no_workspace(self):
        result = generate_slack_permalink(
            workspace_domain=None,
            channel_id="C12345",
            message_ts="1234567890.123456",
        )
        assert result is None
