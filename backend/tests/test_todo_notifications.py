"""Tests for TodoNotificationService and send_todo_reminder dedup lock."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.todo_notifications import TodoNotificationService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    with patch.object(TodoNotificationService, "__init__", lambda self, db: None):
        svc = TodoNotificationService.__new__(TodoNotificationService)
        svc.db = mock_db
        svc.todo_repo = AsyncMock()
        svc.user_repo = AsyncMock()
        svc.notification_service = AsyncMock()
        return svc


def _make_todo(
    todo_id="todo-1",
    status="open",
    title="Buy groceries",
    priority=2,
    description=None,
    user_id="user-1",
    slack_reminder_thread_ts=None,
    slack_reminder_channel=None,
):
    todo = MagicMock()
    todo.id = todo_id
    todo.status = status
    todo.title = title
    todo.priority = priority
    todo.description = description
    todo.user_id = user_id
    todo.slack_reminder_thread_ts = slack_reminder_thread_ts
    todo.slack_reminder_channel = slack_reminder_channel
    return todo


def _make_user(user_id="user-1", slack_user_id="U12345"):
    user = MagicMock()
    user.id = user_id
    user.slack_user_id = slack_user_id
    return user


class TestSendDueReminder:
    """Tests for TodoNotificationService.send_due_reminder()."""

    async def test_skips_completed_todo(self, service):
        """Should skip if todo is already completed."""
        service.todo_repo.get.return_value = _make_todo(status="completed")

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "not_open"
        service.notification_service.publish.assert_not_called()

    async def test_skips_missing_todo(self, service):
        """Should skip if todo doesn't exist."""
        service.todo_repo.get.return_value = None

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "not_open"

    async def test_skips_missing_user(self, service):
        """Should skip if user doesn't exist."""
        service.todo_repo.get.return_value = _make_todo()
        service.user_repo.get.return_value = None

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_user"

    @patch("app.services.slack.get_slack_service")
    @patch("app.core.config.get_settings")
    @patch("app.core.redis.get_redis", new_callable=AsyncMock)
    async def test_first_time_reminder_sends_dm_with_two_buttons(
        self, mock_redis, mock_settings, mock_slack, service
    ):
        """First-time reminder should send DM with Mark Done + Snooze buttons."""
        todo = _make_todo()
        user = _make_user()
        service.todo_repo.get.return_value = todo
        service.user_repo.get.return_value = user
        service.notification_service.publish.return_value = {
            "sse_clients_notified": 1,
            "webhooks_sent": 0,
            "webhook_results": [],
        }

        settings = MagicMock()
        settings.jwt_secret = "test-secret"
        settings.frontend_url = "http://localhost:3000"
        mock_settings.return_value = settings

        slack_service = MagicMock()
        slack_resp = MagicMock()
        slack_resp.__getitem__ = lambda self, key: {"ts": "123.456", "channel": "D999"}[key]
        slack_service.client.chat_postMessage = AsyncMock(return_value=slack_resp)
        mock_slack.return_value = slack_service

        redis_client = AsyncMock()
        mock_redis.return_value = redis_client

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "sent"
        assert "slack" in result["channels"]
        assert "sse_webhooks" in result["channels"]

        # Slack: main message + threaded action buttons
        assert slack_service.client.chat_postMessage.call_count == 2

        # Verify the threaded buttons message has exactly 2 buttons
        buttons_call = slack_service.client.chat_postMessage.call_args_list[1]
        action_blocks = buttons_call[1]["blocks"]
        elements = action_blocks[0]["elements"]
        assert len(elements) == 2
        assert elements[0]["action_id"] == "todo_complete"
        assert elements[1]["action_id"] == "todo_snooze"

        # Should save thread_ts and channel on the todo
        update_calls = service.todo_repo.update_todo.call_args_list
        # First call: persist thread location; second call: reminder_sent_at
        thread_update = update_calls[0]
        assert thread_update[1]["slack_reminder_thread_ts"] == "123.456"
        assert thread_update[1]["slack_reminder_channel"] == "D999"

        # NotificationService: todo_due event
        service.notification_service.publish.assert_called_once()
        call_args = service.notification_service.publish.call_args
        assert call_args[0][0] == "user-1"  # user_id
        assert call_args[0][1] == "todo_due"  # event_type
        assert call_args[0][2]["todo_id"] == "todo-1"

    @patch("app.services.slack.get_slack_service")
    @patch("app.services.todo_notifications.get_redis", new_callable=AsyncMock)
    async def test_refire_posts_in_existing_thread(
        self, mock_redis, mock_slack, service
    ):
        """Snoozed re-fire should post text-only in existing thread."""
        todo = _make_todo(
            slack_reminder_thread_ts="111.222",
            slack_reminder_channel="D999",
        )
        user = _make_user()
        service.todo_repo.get.return_value = todo
        service.user_repo.get.return_value = user
        service.notification_service.publish.return_value = {
            "sse_clients_notified": 0,
            "webhooks_sent": 0,
            "webhook_results": [],
        }

        slack_service = MagicMock()
        slack_service.client.chat_postMessage = AsyncMock()
        mock_slack.return_value = slack_service

        redis_client = AsyncMock()
        mock_redis.return_value = redis_client

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "sent"
        slack_result = result["channels"]["slack"]
        assert slack_result["refire"] is True
        assert slack_result["channel"] == "D999"
        assert slack_result["ts"] == "111.222"

        # Should post exactly one message (text-only in thread)
        assert slack_service.client.chat_postMessage.call_count == 1
        msg_call = slack_service.client.chat_postMessage.call_args
        assert msg_call[1]["thread_ts"] == "111.222"
        assert msg_call[1]["channel"] == "D999"
        assert "Buy groceries" in msg_call[1]["text"]

        # Should refresh the Redis mapping
        redis_client.set.assert_called_once()
        redis_key = redis_client.set.call_args[0][0]
        assert redis_key == "thread_todo:D999:111.222"

    async def test_skips_slack_when_no_slack_user_id(self, service):
        """Should skip Slack but still send SSE/webhooks when user has no Slack ID."""
        todo = _make_todo()
        user = _make_user(slack_user_id=None)
        service.todo_repo.get.return_value = todo
        service.user_repo.get.return_value = user
        service.notification_service.publish.return_value = {
            "sse_clients_notified": 0,
            "webhooks_sent": 0,
            "webhook_results": [],
        }

        result = await service.send_due_reminder("todo-1", "user-1")

        assert result["status"] == "sent"
        assert "slack" not in result["channels"]
        assert "sse_webhooks" in result["channels"]

        # NotificationService should still be called
        service.notification_service.publish.assert_called_once()

        # reminder_sent_at should still be set
        service.todo_repo.update_todo.assert_called_once()


class TestDedupLock:
    """Tests for the Redis dedup lock in send_todo_reminder worker task."""

    @patch("app.worker.tasks.get_db_session")
    @patch("app.core.redis.get_redis", new_callable=AsyncMock)
    async def test_acquires_lock_and_sends(self, mock_get_redis, mock_db_session):
        """Should acquire lock and delegate to TodoNotificationService."""
        from app.worker.tasks import send_todo_reminder

        redis_client = AsyncMock()
        redis_client.set.return_value = True  # Lock acquired
        mock_get_redis.return_value = redis_client

        mock_service = AsyncMock()
        mock_service.send_due_reminder.return_value = {"status": "sent", "todo_id": "todo-1"}

        mock_session = AsyncMock()
        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db_session.return_value = mock_db_ctx

        with patch(
            "app.services.todo_notifications.TodoNotificationService",
            return_value=mock_service,
        ):
            result = await send_todo_reminder({}, "todo-1", "user-1")

        assert result["status"] == "sent"
        redis_client.set.assert_called_once_with(
            "todo_reminder_lock:todo-1", "1", nx=True, ex=300
        )

    @patch("app.core.redis.get_redis", new_callable=AsyncMock)
    async def test_skips_when_lock_held(self, mock_get_redis):
        """Should skip when another process already holds the lock."""
        from app.worker.tasks import send_todo_reminder

        redis_client = AsyncMock()
        redis_client.set.return_value = False  # Lock NOT acquired
        mock_get_redis.return_value = redis_client

        result = await send_todo_reminder({}, "todo-1", "user-1")

        assert result["status"] == "skipped"
        assert result["reason"] == "dedup_lock"
