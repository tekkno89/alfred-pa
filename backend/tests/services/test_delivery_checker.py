"""Tests for DeliveryChecker service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.delivery_checker import DeliveryChecker


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_classification(**overrides):
    """Create a mock TriageClassification with sensible defaults for delivery checking."""
    defaults = {
        "id": "class-1",
        "user_id": "user-1",
        "action": "summarize_next",
        "queued_for_digest": True,
        "deliver_by": datetime.now(UTC) + timedelta(hours=1),
        "last_related_activity_at": datetime.now(UTC) - timedelta(minutes=60),
        "settled_threshold": 30,
        "group_id": "group-1",
        "is_consolidated": False,
        "reviewed_at": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    m = MagicMock(**defaults)
    # Ensure attributes are comparable (not MagicMock proxies)
    for key in (
        "id",
        "user_id",
        "action",
        "queued_for_digest",
        "deliver_by",
        "last_related_activity_at",
        "settled_threshold",
        "group_id",
        "is_consolidated",
        "reviewed_at",
        "created_at",
    ):
        setattr(m, key, defaults[key])
    return m


def _setup_db_result(mock_db, items):
    """Configure mock_db.execute to return items via result.scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    mock_db.execute.return_value = mock_result
    return mock_result


def _setup_db_scalar(mock_db, value):
    """Configure mock_db.execute to return a scalar value (for count queries)."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    mock_db.execute.return_value = mock_result
    return mock_result


class TestGetUsersWithQueuedP1:
    async def test_returns_distinct_users(self, mock_db):
        _setup_db_result(mock_db, ["user-1", "user-2"])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_users_with_queued_p1()

        assert result == ["user-1", "user-2"]
        mock_db.execute.assert_called_once()

    async def test_returns_empty_list_when_no_users(self, mock_db):
        _setup_db_result(mock_db, [])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_users_with_queued_p1()

        assert result == []


class TestGetReadyP1Groups:
    async def test_settled_group_is_ready(self, mock_db):
        """Group with last_related_activity_at older than settled_threshold -> ready."""
        now = datetime.now(UTC)
        item = _make_classification(
            id="class-1",
            group_id="group-1",
            last_related_activity_at=now - timedelta(minutes=45),
            settled_threshold=30,
            deliver_by=now + timedelta(hours=1),  # future = not expired
        )
        _setup_db_result(mock_db, [item])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        assert len(result) == 1
        assert result[0]["group_id"] == "group-1"
        assert result[0]["reason"] == "settled"
        assert "class-1" in result[0]["message_ids"]

    async def test_expired_ttl_is_ready(self, mock_db):
        """Group with deliver_by in the past -> ready."""
        now = datetime.now(UTC)
        item = _make_classification(
            id="class-2",
            group_id="group-2",
            last_related_activity_at=now - timedelta(minutes=5),
            settled_threshold=30,  # not settled (5 < 30)
            deliver_by=now - timedelta(minutes=10),  # past = expired
        )
        _setup_db_result(mock_db, [item])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        assert len(result) == 1
        assert result[0]["group_id"] == "group-2"
        assert result[0]["reason"] == "expired"

    async def test_active_group_not_ready(self, mock_db):
        """Group with recent activity and future TTL -> not ready."""
        now = datetime.now(UTC)
        item = _make_classification(
            id="class-3",
            group_id="group-3",
            last_related_activity_at=now - timedelta(minutes=5),
            settled_threshold=30,  # not settled (5 < 30)
            deliver_by=now + timedelta(hours=1),  # future = not expired
        )
        _setup_db_result(mock_db, [item])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        assert len(result) == 0

    async def test_ungrouped_messages_are_individual_groups(self, mock_db):
        """Items with NULL group_id each form their own group."""
        now = datetime.now(UTC)
        item1 = _make_classification(
            id="class-a",
            group_id=None,
            last_related_activity_at=now - timedelta(minutes=60),
            settled_threshold=30,
            deliver_by=now + timedelta(hours=1),
        )
        item2 = _make_classification(
            id="class-b",
            group_id=None,
            last_related_activity_at=now - timedelta(minutes=5),
            settled_threshold=30,
            deliver_by=now + timedelta(hours=1),
        )
        _setup_db_result(mock_db, [item1, item2])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        # item1 should be ready (settled), item2 should not
        assert len(result) == 1
        assert result[0]["group_id"] == "class-a"  # Uses id as group key
        assert result[0]["reason"] == "settled"

    async def test_returns_empty_when_no_items(self, mock_db):
        """Returns empty list when no queued items."""
        _setup_db_result(mock_db, [])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        assert result == []

    async def test_multi_item_group_uses_min_threshold(self, mock_db):
        """When a group has multiple items, uses minimum settled_threshold."""
        now = datetime.now(UTC)
        item1 = _make_classification(
            id="class-x",
            group_id="group-multi",
            last_related_activity_at=now - timedelta(minutes=20),
            settled_threshold=30,  # not settled at 30
            deliver_by=now + timedelta(hours=1),
        )
        item2 = _make_classification(
            id="class-y",
            group_id="group-multi",
            last_related_activity_at=now - timedelta(minutes=25),
            settled_threshold=15,  # settled at 15 (20 > 15)
            deliver_by=now + timedelta(hours=1),
        )
        _setup_db_result(mock_db, [item1, item2])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        # The group uses min threshold=15, and max last_activity is 20 min ago
        # 20 >= 15 -> settled
        assert len(result) == 1
        assert result[0]["group_id"] == "group-multi"
        assert result[0]["reason"] == "settled"
        assert set(result[0]["message_ids"]) == {"class-x", "class-y"}

    async def test_settled_takes_priority_over_expired(self, mock_db):
        """When both settled and expired, reason is 'settled'."""
        now = datetime.now(UTC)
        item = _make_classification(
            id="class-both",
            group_id="group-both",
            last_related_activity_at=now - timedelta(minutes=60),
            settled_threshold=30,  # settled (60 >= 30)
            deliver_by=now - timedelta(minutes=10),  # also expired
        )
        _setup_db_result(mock_db, [item])

        checker = DeliveryChecker(mock_db)
        result = await checker.get_ready_p1_groups("user-1")

        assert len(result) == 1
        assert result[0]["reason"] == "settled"


class TestGetQueuedP2Messages:
    async def test_returns_queued_p2_messages(self, mock_db):
        items = [
            _make_classification(id="p2-1", action="summarize_eod"),
            _make_classification(id="p2-2", action="summarize_eod"),
        ]
        _setup_db_result(mock_db, items)

        checker = DeliveryChecker(mock_db)
        result = await checker.get_queued_p2_messages("user-1")

        assert len(result) == 2
        mock_db.execute.assert_called_once()


class TestCountP3Messages:
    async def test_returns_count(self, mock_db):
        _setup_db_scalar(mock_db, 7)

        checker = DeliveryChecker(mock_db)
        result = await checker.count_p3_messages("user-1")

        assert result == 7

    async def test_returns_zero_when_none(self, mock_db):
        _setup_db_scalar(mock_db, None)

        checker = DeliveryChecker(mock_db)
        result = await checker.count_p3_messages("user-1")

        assert result == 0


class TestIsEodTime:
    def test_matches_eod_time(self):
        checker = DeliveryChecker.__new__(DeliveryChecker)
        assert checker.is_eod_time("17:00", "17:00") is True

    def test_does_not_match(self):
        checker = DeliveryChecker.__new__(DeliveryChecker)
        assert checker.is_eod_time("17:00", "14:30") is False
