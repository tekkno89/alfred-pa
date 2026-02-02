from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from tests.factories import UserFactory


class TestRegister:
    """Tests for POST /api/auth/register."""

    async def test_register_success(self, client: AsyncClient):
        """Should register a new user successfully."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "securepassword123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should reject registration with existing email."""
        # Create existing user
        user = UserFactory(email="existing@example.com")
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/api/auth/register",
            json={"email": "existing@example.com", "password": "securepassword123"},
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    async def test_register_invalid_email(self, client: AsyncClient):
        """Should reject registration with invalid email."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "securepassword123"},
        )

        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        """Should reject registration with password less than 8 characters."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )

        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/auth/login."""

    async def test_login_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should login with correct credentials."""
        # Create user with known password
        password_hash = hash_password("correctpassword")
        user = UserFactory(email="login@example.com", password_hash=password_hash)
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "correctpassword"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should reject login with wrong password."""
        password_hash = hash_password("correctpassword")
        user = UserFactory(email="wrongpass@example.com", password_hash=password_hash)
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/api/auth/login",
            json={"email": "wrongpass@example.com", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Should reject login for non-existent user."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "nouser@example.com", "password": "anypassword"},
        )

        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    async def test_login_oauth_user_no_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should reject login for OAuth user without password."""
        # OAuth users have no password_hash
        user = UserFactory(
            email="oauth@example.com",
            password_hash=None,
            oauth_provider="google",
            oauth_id="12345",
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/api/auth/login",
            json={"email": "oauth@example.com", "password": "anypassword"},
        )

        assert response.status_code == 401


class TestGetCurrentUser:
    """Tests for GET /api/auth/me."""

    async def test_get_me_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should return current user profile with valid token."""
        user = UserFactory(email="me@example.com")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(user.id)

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["email"] == "me@example.com"
        assert "created_at" in data

    async def test_get_me_no_token(self, client: AsyncClient):
        """Should return 401 without token."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        """Should return 401 with invalid token."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401

    async def test_get_me_nonexistent_user(self, client: AsyncClient):
        """Should return 401 if user in token doesn't exist."""
        # Create token for non-existent user
        token = create_access_token("00000000-0000-0000-0000-000000000000")

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 401


class TestProtectedEndpoints:
    """Tests for protected endpoints using JWT auth."""

    async def test_sessions_with_jwt(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should access sessions endpoint with valid JWT."""
        user = UserFactory()
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(user.id)

        response = await client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    async def test_sessions_without_token(self, client: AsyncClient):
        """Should reject sessions access without token."""
        response = await client.get("/api/sessions")

        assert response.status_code == 401

    async def test_create_session_with_jwt(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should create session with valid JWT."""
        user = UserFactory()
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        token = create_access_token(user.id)

        response = await client.post(
            "/api/sessions",
            json={"title": "Test Session"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
