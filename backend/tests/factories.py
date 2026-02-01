import factory
from uuid import uuid4

from app.db.models import User, Session, Message, Memory


class UserFactory(factory.Factory):
    """Factory for User model."""

    class Meta:
        model = User

    id = factory.LazyFunction(lambda: str(uuid4()))
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password_hash = factory.LazyFunction(
        lambda: "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYMNpGNQGK6"  # "password"
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
