"""Substance filter — identify non-substantive messages for digest filtering."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.triage import TriageClassification

ACKNOWLEDGMENT_PATTERNS = [
    "ok",
    "okay",
    "k",
    "thanks",
    "thx",
    "ty",
    "np",
    "lgtm",
    "sgtm",
    "shipit",
    "got it",
    "sounds good",
    "will do",
    "done",
    "yep",
    "yup",
    "nope",
    "+1",
    "-1",
]

NON_SUBSTANTIVE_SUBTYPES = {
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "channel_archive",
    "channel_unarchive",
    "bot_add",
    "bot_remove",
    "file_share",
    "file_comment",
    "file_mention",
    "pinned_item",
    "unpinned_item",
    "reminder_add",
    "slackbot_response",
    "thread_broadcast",
}

_ack_pattern = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in ACKNOWLEDGMENT_PATTERNS) + r")"
    r"[\s\.\!\!\?\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]*$",
    re.IGNORECASE | re.UNICODE,
)

_emoji_shorthand_pattern = re.compile(r"^:[\w\-\+]+:$")

_emoji_only_pattern = re.compile(
    r"^[\s"
    r"\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F700-\U0001F77F"
    r"\U0001F780-\U0001F7FF"
    r"\U0001F800-\U0001F8FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA00-\U0001FA6F"
    r"\U0001FA70-\U0001FAFF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U0001F004"
    r"\U0001F0CF"
    r"]+$",
    re.UNICODE,
)


def _is_emoji_only(text: str) -> bool:
    """Check if text contains only emojis (unicode or shorthand like :thumbsup:)."""
    if _emoji_only_pattern.match(text):
        return True
    if _emoji_shorthand_pattern.match(text):
        return True
    parts = text.split()
    if all(
        _emoji_shorthand_pattern.match(p.strip())
        or _emoji_only_pattern.match(p.strip())
        for p in parts
    ):
        return True
    return False


def is_substantive(message: "TriageClassification") -> bool:
    """Check if a message has substantive content worth summarizing.

    Args:
        message: TriageClassification to check

    Returns:
        True if the message is substantive, False if it should be filtered
    """
    abstract = message.abstract or ""
    text = abstract.strip()

    if not text:
        return False

    if len(text) < 10:
        if not any(c.isalnum() for c in text):
            return False

    if _ack_pattern.match(text):
        return False

    if _is_emoji_only(text):
        return False

    return True


def is_substantive_text(text: str | None) -> bool:
    """Check if raw text has substantive content.

    Args:
        text: Raw message text to check

    Returns:
        True if the text is substantive, False if it should be filtered
    """
    if not text:
        return False

    text = text.strip()

    if not text:
        return False

    if len(text) < 10:
        if not any(c.isalnum() for c in text):
            return False

    if _ack_pattern.match(text):
        return False

    if _is_emoji_only(text):
        return False

    return True


def has_substantive_subtype(subtype: str | None) -> bool:
    """Check if a Slack message subtype is substantive.

    Args:
        subtype: Slack message subtype (e.g., 'channel_join', 'bot_message')

    Returns:
        True if the subtype is substantive, False if it's a system notification
    """
    if not subtype:
        return True

    return subtype not in NON_SUBSTANTIVE_SUBTYPES
