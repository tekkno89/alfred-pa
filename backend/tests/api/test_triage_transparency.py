"""Tests for the triage transparency API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dashboard import UserFeatureAccess
from app.db.models.triage import TopicAffinity
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
async def user_no_access(db_session: AsyncSession):
    """Create a test user without triage feature access."""
    user = UserFactory()
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_keywords(db_session: AsyncSession, test_user):
    """Create sample topic keywords for testing."""
    keywords = [
        TopicAffinity(
            user_id=test_user.id,
            keyword="urgent",
            weight=0.8,
            source_category="public",
        ),
        TopicAffinity(
            user_id=test_user.id,
            keyword="deadline",
            weight=0.5,
            source_category="sensitive",
        ),
        TopicAffinity(
            user_id=test_user.id,
            keyword="meeting",
            weight=-0.3,
            source_category="dm",
        ),
    ]
    for kw in keywords:
        db_session.add(kw)
    await db_session.commit()
    return keywords


class TestListKeywords:
    async def test_list_keywords_returns_all(
        self, client: AsyncClient, test_user, sample_keywords
    ):
        response = await client.get(
            "/api/triage/transparency/keywords",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert "keywords" in data
        assert len(data["keywords"]) == 3

    async def test_list_keywords_empty(self, client: AsyncClient, test_user):
        response = await client.get(
            "/api/triage/transparency/keywords",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["keywords"] == []

    async def test_list_keywords_includes_weight_and_category(
        self, client: AsyncClient, test_user, sample_keywords
    ):
        response = await client.get(
            "/api/triage/transparency/keywords",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        keywords = {k["keyword"]: k for k in data["keywords"]}

        assert keywords["urgent"]["weight"] == 0.8
        assert keywords["urgent"]["source_category"] == "public"
        assert keywords["deadline"]["weight"] == 0.5
        assert keywords["deadline"]["source_category"] == "sensitive"
        assert keywords["meeting"]["weight"] == -0.3
        assert keywords["meeting"]["source_category"] == "dm"

    async def test_list_keywords_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.get(
            "/api/triage/transparency/keywords",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403


class TestDeleteKeyword:
    async def test_delete_keyword_success(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/urgent",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        from sqlalchemy import select

        result = await db_session.execute(
            select(TopicAffinity).where(
                TopicAffinity.user_id == test_user.id,
                TopicAffinity.keyword == "urgent",
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_keyword_not_found(self, client: AsyncClient, test_user):
        response = await client.delete(
            "/api/triage/transparency/keywords/nonexistent",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 404

    async def test_delete_keyword_isolated_per_user(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        access = UserFeatureAccess(
            user_id=other_user.id,
            feature_key="card:triage",
            enabled=True,
            granted_by=other_user.id,
        )
        db_session.add(access)

        other_keyword = TopicAffinity(
            user_id=other_user.id,
            keyword="urgent",
            weight=0.9,
            source_category="public",
        )
        db_session.add(other_keyword)
        await db_session.commit()

        response = await client.delete(
            "/api/triage/transparency/keywords/urgent",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200

        from sqlalchemy import select

        result = await db_session.execute(
            select(TopicAffinity).where(
                TopicAffinity.user_id == other_user.id,
                TopicAffinity.keyword == "urgent",
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_delete_keyword_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/urgent",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403


class TestDeleteKeywordsByCategory:
    async def test_delete_by_category_public(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/category/public",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1

        from sqlalchemy import select

        result = await db_session.execute(
            select(TopicAffinity).where(TopicAffinity.user_id == test_user.id)
        )
        remaining = list(result.scalars().all())
        assert len(remaining) == 2
        remaining_keywords = {k.keyword for k in remaining}
        assert "urgent" not in remaining_keywords
        assert "deadline" in remaining_keywords
        assert "meeting" in remaining_keywords

    async def test_delete_by_category_sensitive(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/category/sensitive",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1

    async def test_delete_by_category_dm(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/category/dm",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1

    async def test_delete_by_category_invalid(self, client: AsyncClient, test_user):
        response = await client.delete(
            "/api/triage/transparency/keywords/category/invalid",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 400
        assert "Invalid category" in response.json()["detail"]

    async def test_delete_by_category_empty(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        await client.delete(
            "/api/triage/transparency/keywords/category/public",
            headers=auth_headers(test_user),
        )

        response = await client.delete(
            "/api/triage/transparency/keywords/category/public",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 0

    async def test_delete_by_category_isolated_per_user(
        self, client: AsyncClient, test_user, sample_keywords, db_session: AsyncSession
    ):
        other_user = UserFactory()
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        access = UserFeatureAccess(
            user_id=other_user.id,
            feature_key="card:triage",
            enabled=True,
            granted_by=other_user.id,
        )
        db_session.add(access)

        other_keyword = TopicAffinity(
            user_id=other_user.id,
            keyword="project",
            weight=0.7,
            source_category="public",
        )
        db_session.add(other_keyword)
        await db_session.commit()

        response = await client.delete(
            "/api/triage/transparency/keywords/category/public",
            headers=auth_headers(test_user),
        )
        assert response.status_code == 200

        from sqlalchemy import select

        result = await db_session.execute(
            select(TopicAffinity).where(
                TopicAffinity.user_id == other_user.id,
                TopicAffinity.source_category == "public",
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_delete_by_category_requires_feature_access(
        self, client: AsyncClient, user_no_access
    ):
        response = await client.delete(
            "/api/triage/transparency/keywords/category/public",
            headers=auth_headers(user_no_access),
        )
        assert response.status_code == 403
