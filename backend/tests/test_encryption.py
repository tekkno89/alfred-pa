"""Tests for the envelope encryption layer."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.core.encryption.kek_provider import LocalKEKProvider
from app.core.encryption.service import (
    EncryptionService,
    _dek_cache,
    _DEK_CACHE_TTL_SECONDS,
)


class TestLocalKEKProvider:
    """Tests for LocalKEKProvider."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """DEK encrypted and decrypted with local key should match."""
        key = Fernet.generate_key().decode()
        provider = LocalKEKProvider(key=key)

        plaintext_dek = Fernet.generate_key()
        encrypted = provider.encrypt_dek(plaintext_dek)

        assert encrypted != plaintext_dek
        decrypted = provider.decrypt_dek(encrypted)
        assert decrypted == plaintext_dek

    def test_key_from_string(self) -> None:
        """Provider should accept key as string."""
        key = Fernet.generate_key().decode()
        provider = LocalKEKProvider(key=key)
        dek = b"test-data-to-encrypt-with-fernet"
        # Should not raise
        encrypted = provider.encrypt_dek(Fernet.generate_key())
        assert encrypted is not None

    def test_key_from_file(self, tmp_path) -> None:
        """Provider should accept key from file."""
        key = Fernet.generate_key().decode()
        key_file = tmp_path / "kek.key"
        key_file.write_text(key)

        provider = LocalKEKProvider(key_file=str(key_file))
        dek = Fernet.generate_key()
        encrypted = provider.encrypt_dek(dek)
        decrypted = provider.decrypt_dek(encrypted)
        assert decrypted == dek

    def test_no_key_generates_ephemeral(self) -> None:
        """Provider should auto-generate an ephemeral key when none provided."""
        provider = LocalKEKProvider()
        # Should work - encrypts with auto-generated key
        dek = Fernet.generate_key()
        encrypted = provider.encrypt_dek(dek)
        decrypted = provider.decrypt_dek(encrypted)
        assert decrypted == dek


class TestEncryptionService:
    """Tests for EncryptionService."""

    def setup_method(self) -> None:
        """Clear DEK cache before each test."""
        _dek_cache.clear()

    def _make_service(self) -> EncryptionService:
        key = Fernet.generate_key().decode()
        provider = LocalKEKProvider(key=key)
        return EncryptionService(provider)

    def test_generate_dek(self) -> None:
        """generate_dek should return encrypted_dek and cache the plaintext."""
        svc = self._make_service()
        encrypted_dek, plaintext_dek = svc.generate_dek()

        assert encrypted_dek is not None
        assert plaintext_dek is not None
        assert encrypted_dek != plaintext_dek
        # Should be cached
        assert encrypted_dek in _dek_cache

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Encrypting then decrypting should return the original plaintext."""
        svc = self._make_service()
        encrypted_dek, _ = svc.generate_dek()

        plaintext = "my-secret-token-value"
        ciphertext = svc.encrypt(plaintext, encrypted_dek)

        assert ciphertext != plaintext
        result = svc.decrypt(ciphertext, encrypted_dek)
        assert result == plaintext

    def test_encrypt_different_plaintexts(self) -> None:
        """Different plaintexts should produce different ciphertexts."""
        svc = self._make_service()
        encrypted_dek, _ = svc.generate_dek()

        ct1 = svc.encrypt("token-a", encrypted_dek)
        ct2 = svc.encrypt("token-b", encrypted_dek)
        assert ct1 != ct2

    def test_dek_cache_hit(self) -> None:
        """Subsequent operations should use cached DEK, not re-decrypt."""
        key = Fernet.generate_key().decode()
        provider = LocalKEKProvider(key=key)
        svc = EncryptionService(provider)

        encrypted_dek, _ = svc.generate_dek()

        # Spy on decrypt_dek
        original_decrypt = provider.decrypt_dek
        call_count = 0

        def counting_decrypt(data: bytes) -> bytes:
            nonlocal call_count
            call_count += 1
            return original_decrypt(data)

        provider.decrypt_dek = counting_decrypt

        # First encrypt uses cache from generate_dek
        svc.encrypt("test", encrypted_dek)
        assert call_count == 0  # Should use cache, not call decrypt_dek

    def test_dek_cache_expiry(self) -> None:
        """Expired cache entries should trigger re-decryption."""
        key = Fernet.generate_key().decode()
        provider = LocalKEKProvider(key=key)
        svc = EncryptionService(provider)

        encrypted_dek, plaintext_dek = svc.generate_dek()

        # Manually expire the cache entry
        _dek_cache[encrypted_dek] = (plaintext_dek, time.monotonic() - _DEK_CACHE_TTL_SECONDS - 1)

        # Should still work (re-decrypts via provider)
        result = svc.encrypt("test-after-expiry", encrypted_dek)
        decrypted = svc.decrypt(result, encrypted_dek)
        assert decrypted == "test-after-expiry"

    def test_unicode_plaintext(self) -> None:
        """Should handle unicode strings correctly."""
        svc = self._make_service()
        encrypted_dek, _ = svc.generate_dek()

        plaintext = "token-with-unicode-\u2603-\U0001f600"
        ciphertext = svc.encrypt(plaintext, encrypted_dek)
        result = svc.decrypt(ciphertext, encrypted_dek)
        assert result == plaintext


class TestTokenEncryptionService:
    """Tests for TokenEncryptionService (integration-level, mocked DB)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def encryption_key(self) -> Fernet:
        return Fernet.generate_key()

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, mock_db) -> None:
        """store_encrypted_token and get_decrypted_access_token should roundtrip."""
        from app.services.token_encryption import TokenEncryptionService

        kek_key = Fernet.generate_key().decode()

        with (
            patch("app.services.token_encryption.get_encryption_service") as mock_enc,
            patch.object(
                TokenEncryptionService, "__init__", lambda self, db: None
            ),
        ):
            # Set up a real encryption service with local KEK
            from app.core.encryption.kek_provider import LocalKEKProvider
            from app.core.encryption.service import EncryptionService

            provider = LocalKEKProvider(key=kek_key)
            real_svc = EncryptionService(provider)

            svc = TokenEncryptionService.__new__(TokenEncryptionService)
            svc.db = mock_db
            svc.token_repo = AsyncMock()
            svc.key_repo = AsyncMock()
            svc._encryption = real_svc

            # Mock: no existing DEK
            svc.key_repo.get_active_by_name.return_value = None
            mock_key = MagicMock()
            mock_key.id = "test-key-id"

            # Capture the actual encrypted_dek so the mock returns real bytes
            async def capture_create_key(**kwargs):
                mock_key.encrypted_dek = kwargs["encrypted_dek"]
                return mock_key

            svc.key_repo.create_key.side_effect = capture_create_key

            # Capture what gets stored
            stored_token = MagicMock()
            svc.token_repo.upsert.return_value = stored_token

            await svc.store_encrypted_token(
                user_id="user-1",
                provider="github",
                access_token="ghp_test123",
                refresh_token="ghr_refresh456",
            )

            # Verify upsert was called with encrypted values
            call_args = svc.token_repo.upsert.call_args
            assert call_args.kwargs["access_token"] == "encrypted"
            assert call_args.kwargs["encrypted_access_token"] is not None
            assert call_args.kwargs["encrypted_refresh_token"] is not None
            assert call_args.kwargs["encryption_key_id"] == "test-key-id"

            # Now test decryption
            encrypted_dek = svc.key_repo.create_key.call_args.kwargs["encrypted_dek"]
            enc_access = call_args.kwargs["encrypted_access_token"]

            # Mock the key lookup for decryption
            mock_enc_key = MagicMock()
            mock_enc_key.encrypted_dek = encrypted_dek
            svc.key_repo.get.return_value = mock_enc_key

            mock_token = MagicMock()
            mock_token.encrypted_access_token = enc_access
            mock_token.encryption_key_id = "test-key-id"
            mock_token.access_token = "encrypted"

            result = await svc.get_decrypted_access_token(mock_token)
            assert result == "ghp_test123"

    @pytest.mark.asyncio
    async def test_fallback_to_plaintext(self, mock_db) -> None:
        """Should fallback to plaintext for tokens without encryption."""
        from app.services.token_encryption import TokenEncryptionService

        with patch.object(
            TokenEncryptionService, "__init__", lambda self, db: None
        ):
            svc = TokenEncryptionService.__new__(TokenEncryptionService)
            svc.db = mock_db
            svc.token_repo = AsyncMock()
            svc.key_repo = AsyncMock()

            mock_token = MagicMock()
            mock_token.encrypted_access_token = None
            mock_token.encryption_key_id = None
            mock_token.access_token = "xoxp-plaintext-token"

            result = await svc.get_decrypted_access_token(mock_token)
            assert result == "xoxp-plaintext-token"
