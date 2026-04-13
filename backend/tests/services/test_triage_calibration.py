"""Unit tests for triage calibration service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.triage_calibration import parse_slack_permalink


class TestParseSlackPermalink:
    def test_basic_permalink(self):
        result = parse_slack_permalink(
            "https://myworkspace.slack.com/archives/C12345/p1234567890123456"
        )
        assert result is not None
        assert result["channel_id"] == "C12345"
        assert result["message_ts"] == "1234567890.123456"

    def test_permalink_with_thread(self):
        result = parse_slack_permalink(
            "https://myworkspace.slack.com/archives/C12345/p1234567890123456?thread_ts=1234567890111111&cid=C12345"
        )
        assert result is not None
        assert result["channel_id"] == "C12345"
        assert result["message_ts"] == "1234567890.123456"
        assert result["thread_ts"] == "1234567890.111111"

    def test_permalink_private_channel(self):
        result = parse_slack_permalink(
            "https://workspace.slack.com/archives/GABCDE12/p9876543210123456"
        )
        assert result is not None
        assert result["channel_id"] == "GABCDE12"
        assert result["message_ts"] == "9876543210.123456"

    def test_permalink_dm_channel(self):
        result = parse_slack_permalink(
            "https://workspace.slack.com/archives/D12345/p1700000000000000"
        )
        assert result is not None
        assert result["channel_id"] == "D12345"
        assert result["message_ts"] == "1700000000.000000"

    def test_invalid_permalink_no_channel(self):
        result = parse_slack_permalink(
            "https://workspace.slack.com/archives/p1234567890123456"
        )
        assert result is None

    def test_invalid_permalink_no_ts(self):
        result = parse_slack_permalink("https://workspace.slack.com/archives/C12345/")
        assert result is None

    def test_invalid_permalink_wrong_format(self):
        result = parse_slack_permalink("https://not-slack.com/something/else")
        assert result is None

    def test_invalid_permalink_short_ts(self):
        result = parse_slack_permalink(
            "https://workspace.slack.com/archives/C12345/p12345"
        )
        assert result is None

    def test_permalink_with_http(self):
        result = parse_slack_permalink(
            "http://workspace.slack.com/archives/C12345/p1234567890123456"
        )
        assert result is not None
        assert result["channel_id"] == "C12345"

    def test_permalink_with_subdomain_hyphen(self):
        result = parse_slack_permalink(
            "https://my-workspace.slack.com/archives/C12345/p1234567890123456"
        )
        assert result is not None
        assert result["channel_id"] == "C12345"
