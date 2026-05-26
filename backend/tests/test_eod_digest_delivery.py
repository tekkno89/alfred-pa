"""Tests for EOD digest delivery cron job."""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager

from app.worker.tasks import deliver_eod_digests


class MockSession:
    """Mock session that tracks its closed state."""
    
    def __init__(self):
        self.is_closed = False
        self.calls_after_close = []
    
    def mark_closed(self):
        self.is_closed = True
    
    async def execute(self, *args, **kwargs):
        if self.is_closed:
            self.calls_after_close.append(("execute", args, kwargs))
            raise RuntimeError("Cannot use session after it is closed")
        return MagicMock()
    
    async def commit(self):
        if self.is_closed:
            raise RuntimeError("Cannot use session after it is closed")
    
    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_deliver_eod_digests_uses_fresh_session_for_timezone_lookup():
    """
    Test that deliver_eod_digests properly handles db session lifecycle.
    
    The bug: db session is closed before timezone lookup, causing silent failure.
    The fix: each user iteration should have its own db session or keep session alive.
    """
    sessions = []
    
    def create_mock_session():
        session = MockSession()
        sessions.append(session)
        return session
    
    @asynccontextmanager
    async def mock_get_db_session():
        session = create_mock_session()
        yield session
        session.mark_closed()
    
    mock_settings = MagicMock()
    mock_settings.user_id = "test-user-id"
    mock_settings.eod_review_time = "17:00"
    
    with patch("app.worker.tasks.get_db_session", side_effect=mock_get_db_session):
        with patch("app.worker.tasks.TriageUserSettingsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_all_always_on = AsyncMock(return_value=[mock_settings])
            MockRepo.return_value = mock_repo_instance
            
            with patch("app.services.timezone.get_user_timezone") as mock_get_tz:
                async def get_tz_with_session_check(db, user_id):
                    if hasattr(db, 'is_closed') and db.is_closed:
                        raise RuntimeError("Session is closed!")
                    return "America/Los_Angeles"
                mock_get_tz.side_effect = get_tz_with_session_check
                
                with patch("app.services.timezone.get_current_time_in_tz") as mock_time:
                    mock_time.return_value = datetime(2026, 5, 25, 17, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
                    
                    with patch("app.services.digest_delivery_orchestrator.DigestDeliveryOrchestrator") as MockOrchestrator:
                        mock_orch = AsyncMock()
                        mock_orch.deliver_eod_digest = AsyncMock(return_value={"status": "enqueued"})
                        MockOrchestrator.return_value = mock_orch
                        
                        result = await deliver_eod_digests({})
    
    assert result["delivered_count"] >= 1, "Digest should be delivered when time matches"
    assert len(sessions) == 2, f"Expected 2 sessions (initial + user loop), got {len(sessions)}"
    for i, session in enumerate(sessions):
        assert len(session.calls_after_close) == 0, \
            f"Session {i} was used after close: {session.calls_after_close}"


@pytest.mark.asyncio
async def test_deliver_eod_digests_respects_eod_review_time():
    """Test that digests are only delivered at the configured EOD review time."""
    mock_settings = MagicMock()
    mock_settings.user_id = "test-user-id"
    mock_settings.eod_review_time = "17:00"
    
    with patch("app.worker.tasks.TriageUserSettingsRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_all_always_on = AsyncMock(return_value=[mock_settings])
        MockRepo.return_value = mock_repo_instance
        
        with patch("app.services.timezone.get_user_timezone", return_value="America/Los_Angeles"):
            with patch("app.services.timezone.get_current_time_in_tz") as mock_time:
                mock_time.return_value = datetime(2026, 5, 25, 15, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
                
                result = await deliver_eod_digests({})
    
    assert result["delivered_count"] == 0, "Should not deliver when time doesn't match"


@pytest.mark.asyncio
async def test_deliver_eod_digests_integration(db_session, test_user):
    """
    Integration test that verifies the full flow with a real database session.
    
    This catches issues like the db session being closed before operations complete.
    """
    from app.db.models.triage import TriageUserSettings
    from app.worker.tasks import get_db_session
    from tests.conftest import TestSessionLocal
    
    triage_settings = TriageUserSettings(
        user_id=str(test_user.id),
        is_always_on=True,
        eod_review_time="17:00",
    )
    db_session.add(triage_settings)
    await db_session.commit()
    
    @asynccontextmanager
    async def mock_get_db_session():
        async with TestSessionLocal() as session:
            yield session
    
    with patch("app.worker.tasks.get_db_session", side_effect=mock_get_db_session):
        with patch("app.services.timezone.get_current_time_in_tz") as mock_time:
            mock_time.return_value = datetime(2026, 5, 25, 17, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
            
            with patch("app.services.digest_delivery_orchestrator.DigestDeliveryOrchestrator") as MockOrchestrator:
                mock_orch = AsyncMock()
                mock_orch.deliver_eod_digest = AsyncMock(return_value={"status": "enqueued"})
                MockOrchestrator.return_value = mock_orch
                
                result = await deliver_eod_digests({})
    
    assert result["delivered_count"] == 1
    mock_orch.deliver_eod_digest.assert_called_once_with(str(test_user.id))
