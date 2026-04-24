"""Tests for substance filter."""

import pytest

from app.db.models.triage import TriageClassification
from app.services.substance_filter import (
    ACKNOWLEDGMENT_PATTERNS,
    NON_SUBSTANTIVE_SUBTYPES,
    has_substantive_subtype,
    is_substantive,
    is_substantive_text,
)


def _make_classification(
    abstract: str = "Test message",
    sender_slack_id: str = "U123",
    channel_id: str = "C123",
) -> TriageClassification:
    return TriageClassification(
        user_id="test-user",
        sender_slack_id=sender_slack_id,
        channel_id=channel_id,
        message_ts="1234567890.001",
        priority_level="p2",
        classification_path="channel",
        abstract=abstract,
    )


class TestIsSubstantive:
    def test_normal_message_is_substantive(self):
        msg = _make_classification(
            abstract="Can you review the PR when you get a chance?"
        )
        assert is_substantive(msg) is True

    def test_message_with_trailing_thanks_is_substantive(self):
        msg = _make_classification(abstract="I pushed the fix, thanks!")
        assert is_substantive(msg) is True

    def test_emoji_only_is_non_substantive(self):
        msg = _make_classification(abstract="👍")
        assert is_substantive(msg) is False

    def test_multiple_emojis_is_non_substantive(self):
        msg = _make_classification(abstract="🎉 🚀 ✨")
        assert is_substantive(msg) is False

    def test_reaction_shorthand_is_non_substantive(self):
        msg = _make_classification(abstract=":+1:")
        assert is_substantive(msg) is False

    def test_thanks_is_non_substantive(self):
        msg = _make_classification(abstract="thanks")
        assert is_substantive(msg) is False

    def test_thx_is_non_substantive(self):
        msg = _make_classification(abstract="thx")
        assert is_substantive(msg) is False

    def test_ok_is_non_substantive(self):
        msg = _make_classification(abstract="ok")
        assert is_substantive(msg) is False

    def test_lgtm_is_non_substantive(self):
        msg = _make_classification(abstract="lgtm")
        assert is_substantive(msg) is False

    def test_sgtm_is_non_substantive(self):
        msg = _make_classification(abstract="sgtm")
        assert is_substantive(msg) is False

    def test_plus_one_is_non_substantive(self):
        msg = _make_classification(abstract="+1")
        assert is_substantive(msg) is False

    def test_got_it_is_non_substantive(self):
        msg = _make_classification(abstract="got it")
        assert is_substantive(msg) is False

    def test_sounds_good_is_non_substantive(self):
        msg = _make_classification(abstract="sounds good")
        assert is_substantive(msg) is False

    def test_empty_abstract_is_non_substantive(self):
        msg = _make_classification(abstract="")
        assert is_substantive(msg) is False

    def test_none_abstract_is_non_substantive(self):
        msg = _make_classification(abstract=None)
        msg.abstract = None
        assert is_substantive(msg) is False

    def test_short_alphanumeric_is_substantive(self):
        msg = _make_classification(abstract="Yes, do it")
        assert is_substantive(msg) is True

    def test_acknowledgment_with_punctuation_is_non_substantive(self):
        msg = _make_classification(abstract="thanks!")
        assert is_substantive(msg) is False

    def test_acknowledgment_with_emoji_is_non_substantive(self):
        msg = _make_classification(abstract="ok 👍")
        assert is_substantive(msg) is False


class TestIsSubstantiveText:
    def test_normal_text_is_substantive(self):
        assert is_substantive_text("This is a real message") is True

    def test_emoji_only_text_is_non_substantive(self):
        assert is_substantive_text("🎉") is False

    def test_thanks_text_is_non_substantive(self):
        assert is_substantive_text("thanks") is False

    def test_empty_text_is_non_substantive(self):
        assert is_substantive_text("") is False

    def test_none_text_is_non_substantive(self):
        assert is_substantive_text(None) is False


class TestHasSubstantiveSubtype:
    def test_no_subtype_is_substantive(self):
        assert has_substantive_subtype(None) is True

    def test_empty_subtype_is_substantive(self):
        assert has_substantive_subtype("") is True

    def test_channel_join_is_non_substantive(self):
        assert has_substantive_subtype("channel_join") is False

    def test_channel_leave_is_non_substantive(self):
        assert has_substantive_subtype("channel_leave") is False

    def test_bot_add_is_non_substantive(self):
        assert has_substantive_subtype("bot_add") is False

    def test_normal_message_is_substantive(self):
        assert has_substantive_subtype("bot_message") is True

    def test_reply_is_substantive(self):
        assert has_substantive_subtype(None) is True
