"""Unit tests for SuppressedDeliveryService."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.suppressed_delivery_service import (
    SuppressedDeliveryService,
    CANONICAL_CAP,
    RETENTION_DAYS,
)
from app.db.models.triage import SuppressedDelivery


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service with mock db."""
    return SuppressedDeliveryService(mock_db)


class TestRecordSuppression:
    async def test_record_suppression_creates_record(self, service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_count_result

        result = await service.record_suppression(
            user_id="user-123",
            message_id="msg-456",
            original_action="p1",
            suppression_reason="low_engagement",
            outcome_summary="User was away for 2 hours",
        )

        assert result is not None
        assert result.user_id == "user-123"
        assert result.message_id == "msg-456"
        assert result.original_action == "p1"
        assert result.suppression_reason == "low_engagement"
        assert result.outcome_summary == "User was away for 2 hours"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_record_suppression_respects_cap(self, service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = CANONICAL_CAP
        mock_db.execute.return_value = mock_count_result

        result = await service.record_suppression(
            user_id="user-123",
            message_id="msg-456",
            original_action="p1",
            suppression_reason="low_engagement",
        )

        assert result is None
        mock_db.add.assert_not_called()

    async def test_record_suppression_cap_boundary(self, service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = CANONICAL_CAP - 1
        mock_db.execute.return_value = mock_count_result

        result = await service.record_suppression(
            user_id="user-123",
            message_id="msg-456",
            original_action="p1",
            suppression_reason="low_engagement",
        )

        assert result is not None
        mock_db.add.assert_called_once()

    async def test_record_suppression_without_outcome_summary(self, service, mock_db):
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_count_result

        result = await service.record_suppression(
            user_id="user-123",
            message_id="msg-456",
            original_action="p2",
            suppression_reason="focus_mode",
        )

        assert result is not None
        assert result.outcome_summary is None


class TestGetForReview:
    async def test_get_for_review_returns_unreviewed(self, service, mock_db):
        suppressed1 = SuppressedDelivery(
            user_id="user-123",
            message_id="msg-1",
            original_action="p1",
            suppression_reason="low_engagement",
        )
        suppressed2 = SuppressedDelivery(
            user_id="user-123",
            message_id="msg-2",
            original_action="p2",
            suppression_reason="focus_mode",
            user_review_response="yes",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [suppressed1]
        mock_db.execute.return_value = mock_result

        results = await service.get_for_review("user-123")

        assert len(results) == 1
        assert results[0].message_id == "msg-1"

    async def test_get_for_review_respects_limit(self, service, mock_db):
        items = [
            SuppressedDelivery(
                user_id="user-123",
                message_id=f"msg-{i}",
                original_action="p1",
                suppression_reason="low_engagement",
            )
            for i in range(20)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = items[:CANONICAL_CAP]
        mock_db.execute.return_value = mock_result

        results = await service.get_for_review("user-123", limit=5)

        assert len(results) <= CANONICAL_CAP

    async def test_get_for_review_empty(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        results = await service.get_for_review("user-123")

        assert results == []


class TestRecordReviewResponse:
    async def test_record_review_response_success(self, service, mock_db):
        suppressed = SuppressedDelivery(
            id="suppressed-123",
            user_id="user-123",
            message_id="msg-456",
            original_action="p1",
            suppression_reason="low_engagement",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = suppressed
        mock_db.execute.return_value = mock_result

        success = await service.record_review_response(
            suppressed_id="suppressed-123",
            user_id="user-123",
            response="yes",
        )

        assert success is True
        assert suppressed.user_review_response == "yes"
        mock_db.commit.assert_called_once()

    async def test_record_review_response_not_found(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success = await service.record_review_response(
            suppressed_id="nonexistent",
            user_id="user-123",
            response="yes",
        )

        assert success is False

    async def test_record_review_response_wrong_user(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        success = await service.record_review_response(
            suppressed_id="suppressed-123",
            user_id="different-user",
            response="yes",
        )

        assert success is False

    async def test_record_review_response_different_responses(self, service, mock_db):
        for response in ["yes", "no", "maybe"]:
            suppressed = SuppressedDelivery(
                id="suppressed-123",
                user_id="user-123",
                message_id="msg-456",
                original_action="p1",
                suppression_reason="low_engagement",
            )

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = suppressed
            mock_db.execute.return_value = mock_result

            success = await service.record_review_response(
                suppressed_id="suppressed-123",
                user_id="user-123",
                response=response,
            )

            assert success is True
            assert suppressed.user_review_response == response


class TestCleanupExpired:
    async def test_cleanup_expired_deletes_old_records(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        count = await service.cleanup_expired()

        assert count == 5
        mock_db.commit.assert_called_once()

    async def test_cleanup_expired_no_records(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await service.cleanup_expired()

        assert count == 0


class TestConstants:
    def test_canonical_cap_value(self):
        assert CANONICAL_CAP == 10

    def test_retention_days_value(self):
        assert RETENTION_DAYS == 90
