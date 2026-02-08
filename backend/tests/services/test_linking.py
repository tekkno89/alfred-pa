"""Tests for LinkingService."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.linking import LinkingService, CODE_PREFIX


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    return AsyncMock()


@pytest.fixture
def linking_service():
    """Create LinkingService instance."""
    return LinkingService()


class TestGenerateCode:
    """Tests for code generation."""

    def test_generate_code_length(self, linking_service):
        """Test that generated code is 6 characters."""
        code = linking_service._generate_code()
        assert len(code) == 6

    def test_generate_code_alphanumeric(self, linking_service):
        """Test that code contains only allowed characters."""
        # Characters that should NOT be in the code (confusing ones)
        forbidden = set("0OI1L")

        for _ in range(100):  # Generate many codes to test
            code = linking_service._generate_code()
            assert all(c not in forbidden for c in code)
            assert code.isupper() or code.isdigit() or all(
                c.isupper() or c.isdigit() for c in code
            )


class TestCreateCode:
    """Tests for create_code method."""

    async def test_create_code(self, linking_service, mock_redis):
        """Test creating a linking code."""
        mock_redis.exists.return_value = False

        with patch("app.services.linking.get_redis", return_value=mock_redis):
            code = await linking_service.create_code("U123456")

        assert len(code) == 6
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"{CODE_PREFIX}{code}"
        assert call_args[0][1] == 600  # TTL
        assert call_args[0][2] == "U123456"

    async def test_create_code_collision(self, linking_service, mock_redis):
        """Test code regeneration on collision."""
        # First code exists, second doesn't
        mock_redis.exists.side_effect = [True, False]

        with patch("app.services.linking.get_redis", return_value=mock_redis):
            code = await linking_service.create_code("U123456")

        assert len(code) == 6
        assert mock_redis.exists.call_count == 2


class TestValidateCode:
    """Tests for validate_code method."""

    async def test_validate_valid_code(self, linking_service, mock_redis):
        """Test validating a valid code."""
        mock_redis.getdel.return_value = "U123456"

        with patch("app.services.linking.get_redis", return_value=mock_redis):
            result = await linking_service.validate_code("ABC123")

        assert result == "U123456"
        mock_redis.getdel.assert_called_once_with(f"{CODE_PREFIX}ABC123")

    async def test_validate_invalid_code(self, linking_service, mock_redis):
        """Test validating an invalid/expired code."""
        mock_redis.getdel.return_value = None

        with patch("app.services.linking.get_redis", return_value=mock_redis):
            result = await linking_service.validate_code("INVALID")

        assert result is None

    async def test_validate_code_normalizes_input(self, linking_service, mock_redis):
        """Test that code is normalized (uppercase, stripped)."""
        mock_redis.getdel.return_value = "U123456"

        with patch("app.services.linking.get_redis", return_value=mock_redis):
            await linking_service.validate_code("  abc123  ")

        mock_redis.getdel.assert_called_once_with(f"{CODE_PREFIX}ABC123")
