import factory
from uuid import uuid4
from datetime import datetime, timezone

from app.db.models import User, Session, Message, Memory
from app.db.models.triage import TriageClassification


class UserFactory(factory.Factory):
    """Factory for User model."""

    class Meta:
        model = User

    id = factory.LazyFunction(lambda: str(uuid4()))
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password_hash = factory.LazyFunction(
        lambda: (
            "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYMNpGNQGK6"
        )  # "password"
    )
    oauth_provider = None
    oauth_id = None


class SessionFactory(factory.Factory):
    """Factory for Session model."""

    class Meta:
        model = Session

    id = factory.LazyFunction(lambda: str(uuid4()))
    user_id = factory.LazyFunction(lambda: str(uuid4()))
    title = factory.Sequence(lambda n: f"Conversation {n}")
    source = "webapp"
    slack_channel_id = None
    slack_thread_ts = None


class SlackSessionFactory(SessionFactory):
    """Factory for Slack-originated sessions."""

    source = "slack"
    slack_channel_id = factory.Sequence(lambda n: f"C{n:010d}")
    slack_thread_ts = factory.Sequence(lambda n: f"1234567890.{n:06d}")


class MessageFactory(factory.Factory):
    """Factory for Message model."""

    class Meta:
        model = Message

    id = factory.LazyFunction(lambda: str(uuid4()))
    session_id = factory.LazyFunction(lambda: str(uuid4()))
    role = "user"
    content = factory.Sequence(lambda n: f"Test message {n}")
    metadata_ = None


class AssistantMessageFactory(MessageFactory):
    """Factory for assistant messages."""

    role = "assistant"
    content = factory.Sequence(lambda n: f"Assistant response {n}")


class MemoryFactory(factory.Factory):
    """Factory for Memory model."""

    class Meta:
        model = Memory

    id = factory.LazyFunction(lambda: str(uuid4()))
    user_id = factory.LazyFunction(lambda: str(uuid4()))
    type = "knowledge"
    content = factory.Sequence(lambda n: f"Memory content {n}")
    embedding = None
    source_session_id = None


class PreferenceMemoryFactory(MemoryFactory):
    """Factory for preference memories."""

    type = "preference"
    content = factory.Sequence(lambda n: f"User preference {n}")


class SummaryMemoryFactory(MemoryFactory):
    """Factory for summary memories."""

    type = "summary"
    content = factory.Sequence(lambda n: f"Conversation summary {n}")


class TriageClassificationFactory(factory.Factory):
    """Factory for TriageClassification model."""

    class Meta:
        model = TriageClassification

    id = factory.LazyFunction(lambda: str(uuid4()))
    user_id = factory.LazyFunction(lambda: str(uuid4()))
    sender_slack_id = factory.Sequence(lambda n: f"U{n:08d}")
    sender_name = factory.Sequence(lambda n: f"User {n}")
    channel_id = factory.Sequence(lambda n: f"C{n:08d}")
    channel_name = factory.Sequence(lambda n: f"channel-{n}")
    message_ts = factory.LazyFunction(
        lambda: f"{int(datetime.now(timezone.utc).timestamp())}.000001"
    )
    thread_ts = None
    slack_permalink = None
    priority_level = "p1"
    confidence = 0.9
    classification_path = "channel"
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    queued_for_digest = True


class ThreadTriageClassificationFactory(TriageClassificationFactory):
    """Factory for thread-based triage classifications."""

    thread_ts = factory.LazyAttribute(lambda obj: obj.message_ts)
    classification_path = "channel"


class DMTriageClassificationFactory(TriageClassificationFactory):
    """Factory for DM-based triage classifications."""

    channel_id = factory.Sequence(lambda n: f"D{n:08d}")
    classification_path = "dm"
