"""Integration tests for triage classification endpoints."""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
from app.db.models.focus import FocusModeState
from app.db.models.triage import TriageClassification
from tests.conftest import auth_headers
from tests.factories import UserFactory


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user with triage feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:triage",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession):
    """Create another user with triage access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    access = UserFeatureAccess(
        user_id=user.id,
        feature_key="card:triage",
        enabled=True,
        granted_by=user.id,
    )
    db_session.add(access)
    await db_session.commit()
    return user


@pytest.fixture
async def classifications(db_session: AsyncSession, test_user):
    """Create sample classifications with different review states."""
    now = datetime.utcnow()
    items = []
    for i, (urgency, reviewed) in enumerate([
        ("urgent", True),
        ("review", False),
        ("digest", False),
        ("urgent", False),
        ("digest", True),
    ]):
        c = TriageClassification(
            user_id=test_user.id,
            sender_slack_id=f"U{i:05d}",
            sender_name=f"User {i}",
            channel_id="C12345",
            channel_name="general",
            message_ts=f"1700000{i}.000000",
            urgency_level=urgency,
            confidence=0.9,
            classification_reason="test",
            abstract=f"Message {i}",
            classification_path="channel",
            reviewed_at=now if reviewed else None,
        )
        db_session.add(c)
        items.append(c)

    await db_session.commit()
    for item in items:
        await db_session.refresh(item)
    return items


@pytest.fixture
async def active_focus_session(db_session: AsyncSession, test_user):
    """Create an active focus session."""
    session = FocusModeState(
        user_id=test_user.id,
        is_active=True,
        mode="simple",
        started_at=datetime.utcnow(),
        ends_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def ended_focus_session(db_session: AsyncSession, test_user):
    """Create an ended focus session."""
    session = FocusModeState(
        user_id=test_user.id,
        is_active=False,
        mode="simple",
        started_at=datetime.utcnow() - timedelta(hours=2),
        ends_at=datetime.utcnow() - timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def digest_in_active_session(
    db_session: AsyncSession, test_user, active_focus_session
):
    """Create digest classifications linked to an active focus session."""
    items = []
    for i in range(3):
        c = TriageClassification(
            user_id=test_user.id,
            focus_session_id=active_focus_session.id,
            sender_slack_id=f"UA{i:04d}",
            sender_name=f"Active Sender {i}",
            channel_id="C12345",
            channel_name="general",
            message_ts=f"1700100{i}.000000",
            urgency_level="digest",
            confidence=0.8,
            abstract=f"Active digest {i}",
            classification_path="channel",
        )
        db_session.add(c)
        items.append(c)
    await db_session.commit()
    for item in items:
        await db_session.refresh(item)
    return items


@pytest.fixture
async def digest_in_ended_session(
    db_session: AsyncSession, test_user, ended_focus_session
):
    """Create digest classifications linked to an ended focus session."""
    items = []
    for i in range(2):
        c = TriageClassification(
            user_id=test_user.id,
            focus_session_id=ended_focus_session.id,
            sender_slack_id=f"UE{i:04d}",
            sender_name=f"Ended Sender {i}",
            channel_id="C12345",
            channel_name="general",
            message_ts=f"1700200{i}.000000",
            urgency_level="digest",
            confidence=0.7,
            abstract=f"Ended digest {i}",
            classification_path="channel",
        )
        db_session.add(c)
        items.append(c)
    await db_session.commit()
    for item in items:
        await db_session.refresh(item)
    return items


class TestClassificationsReviewedFilter:
    """Test reviewed query param on GET /classifications."""

    @pytest.mark.asyncio
    async def test_filter_unreviewed(
        self, client: AsyncClient, test_user, classifications
    ):
        resp = await client.get(
            "/api/triage/classifications",
            params={"reviewed": "false", "hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 3 unreviewed items
        assert data["total"] == 3
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["reviewed_at"] is None

    @pytest.mark.asyncio
    async def test_filter_reviewed(
        self, client: AsyncClient, test_user, classifications
    ):
        resp = await client.get(
            "/api/triage/classifications",
            params={"reviewed": "true", "hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        for item in data["items"]:
            assert item["reviewed_at"] is not None

    @pytest.mark.asyncio
    async def test_filter_all(
        self, client: AsyncClient, test_user, classifications
    ):
        resp = await client.get(
            "/api/triage/classifications",
            params={"hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5


class TestActiveSessionDigestExclusion:
    """Test hide_active_digest filtering."""

    @pytest.mark.asyncio
    async def test_hides_active_session_digest(
        self,
        client: AsyncClient,
        test_user,
        digest_in_active_session,
        digest_in_ended_session,
    ):
        resp = await client.get(
            "/api/triage/classifications",
            params={"hide_active_digest": "true"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only ended session digests should appear (active ones excluded)
        active_ids = {d.id for d in digest_in_active_session}
        for item in data["items"]:
            assert item["id"] not in active_ids
        # Ended session digests should be present
        ended_ids = {d.id for d in digest_in_ended_session}
        returned_ids = {item["id"] for item in data["items"]}
        assert ended_ids.issubset(returned_ids)

    @pytest.mark.asyncio
    async def test_shows_all_when_disabled(
        self,
        client: AsyncClient,
        test_user,
        digest_in_active_session,
        digest_in_ended_session,
    ):
        resp = await client.get(
            "/api/triage/classifications",
            params={"hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        all_ids = {d.id for d in digest_in_active_session + digest_in_ended_session}
        returned_ids = {item["id"] for item in data["items"]}
        assert all_ids.issubset(returned_ids)


class TestMarkReviewed:
    """Test PATCH /classifications/reviewed."""

    @pytest.mark.asyncio
    async def test_mark_reviewed(
        self, client: AsyncClient, test_user, classifications
    ):
        unreviewed_id = classifications[1].id  # review, unreviewed
        resp = await client.patch(
            "/api/triage/classifications/reviewed",
            json={
                "classification_ids": [unreviewed_id],
                "reviewed": True,
            },
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        # Verify it's now reviewed
        resp2 = await client.get(
            "/api/triage/classifications",
            params={"reviewed": "true", "hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        reviewed_ids = {item["id"] for item in resp2.json()["items"]}
        assert unreviewed_id in reviewed_ids

    @pytest.mark.asyncio
    async def test_mark_unreviewed(
        self, client: AsyncClient, test_user, classifications
    ):
        reviewed_id = classifications[0].id  # urgent, reviewed
        resp = await client.patch(
            "/api/triage/classifications/reviewed",
            json={
                "classification_ids": [reviewed_id],
                "reviewed": False,
            },
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

    @pytest.mark.asyncio
    async def test_ownership_check(
        self, client: AsyncClient, test_user, other_user, classifications
    ):
        """Other user can't mark test_user's classifications."""
        target_id = classifications[1].id
        resp = await client.patch(
            "/api/triage/classifications/reviewed",
            json={
                "classification_ids": [target_id],
                "reviewed": True,
            },
            headers=auth_headers(other_user),
        )
        assert resp.status_code == 200
        # Should update 0 rows because ownership doesn't match
        assert resp.json()["updated"] == 0


class TestDigestChildren:
    """Test GET /classifications/{id}/digest-children."""

    @pytest.mark.asyncio
    async def test_get_digest_children(
        self,
        client: AsyncClient,
        test_user,
        db_session: AsyncSession,
        digest_in_ended_session,
    ):
        # Create a digest_summary row and link children to it
        summary = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="SYSTEM",
            sender_name="Digest Summary",
            channel_id="C12345",
            channel_name=None,
            message_ts="1700200999.000000",
            urgency_level="digest_summary",
            confidence=1.0,
            classification_reason="Consolidated 2 digest items",
            abstract="2 noteworthy messages",
            classification_path="channel",
            child_count=2,
        )
        db_session.add(summary)
        await db_session.commit()
        await db_session.refresh(summary)

        # Link children
        for child in digest_in_ended_session:
            child.digest_summary_id = summary.id
        await db_session.commit()

        resp = await client.get(
            f"/api/triage/classifications/{summary.id}/digest-children",
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        children = resp.json()
        assert len(children) == 2

    @pytest.mark.asyncio
    async def test_not_found_for_other_user(
        self,
        client: AsyncClient,
        other_user,
        db_session: AsyncSession,
        test_user,
    ):
        summary = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="SYSTEM",
            sender_name="Digest Summary",
            channel_id="C12345",
            message_ts="1700300000.000000",
            urgency_level="digest_summary",
            confidence=1.0,
            abstract="Summary",
            classification_path="channel",
        )
        db_session.add(summary)
        await db_session.commit()
        await db_session.refresh(summary)

        resp = await client.get(
            f"/api/triage/classifications/{summary.id}/digest-children",
            headers=auth_headers(other_user),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_summary_returns_empty(
        self,
        client: AsyncClient,
        test_user,
        classifications,
    ):
        # Regular classification (not digest_summary) should return empty
        target = classifications[2]  # digest, not a summary
        resp = await client.get(
            f"/api/triage/classifications/{target.id}/digest-children",
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestReviewableFilter:
    """Test the 'reviewable' pseudo-filter returns urgent + review + digest_summary."""

    @pytest.mark.asyncio
    async def test_reviewable_returns_correct_levels(
        self, client: AsyncClient, test_user, classifications, db_session: AsyncSession
    ):
        # Add a digest_summary item
        summary = TriageClassification(
            user_id=test_user.id,
            sender_slack_id="SYSTEM",
            sender_name=None,
            channel_id="C12345",
            channel_name=None,
            message_ts="1700099999.000000",
            urgency_level="digest_summary",
            confidence=1.0,
            classification_reason="Consolidated 2 digest items",
            abstract="2 noteworthy messages",
            classification_path="simple",
            child_count=2,
        )
        db_session.add(summary)
        await db_session.commit()

        resp = await client.get(
            "/api/triage/classifications",
            params={"urgency": "reviewable", "hide_active_digest": "false"},
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        # From fixtures: 2 urgent + 1 review + 1 digest_summary = 4
        assert data["total"] == 4
        returned_levels = {item["urgency_level"] for item in data["items"]}
        assert returned_levels <= {"urgent", "review", "digest_summary"}
        # Ensure no digest or noise items
        assert "digest" not in returned_levels
        assert "noise" not in returned_levels


class TestTotalCountAccuracy:
    """Verify total count reflects active filters."""

    @pytest.mark.asyncio
    async def test_total_matches_filtered_count(
        self, client: AsyncClient, test_user, classifications
    ):
        # Filter by urgency=urgent and unreviewed
        resp = await client.get(
            "/api/triage/classifications",
            params={
                "urgency": "urgent",
                "reviewed": "false",
                "hide_active_digest": "false",
            },
            headers=auth_headers(test_user),
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only 1 urgent + unreviewed (index 3)
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["urgency_level"] == "urgent"
        assert data["items"][0]["reviewed_at"] is None
