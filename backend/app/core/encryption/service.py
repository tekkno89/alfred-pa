"""Encryption service with DEK generation, encrypt/decrypt, and caching."""

import logging
import time
from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.encryption.kek_provider import (
    AWSKMSKEKProvider,
    GCPKMSKEKProvider,
    KEKProvider,
    LocalKEKProvider,
)

logger = logging.getLogger(__name__)

# DEK cache: maps encrypted_dek bytes -> (plaintext_dek, cached_at)
_dek_cache: dict[bytes, tuple[bytes, float]] = {}
_DEK_CACHE_TTL_SECONDS = 300  # 5 minutes


class EncryptionService:
    """Service for envelope encryption using DEK/KEK pattern.

    DEKs (Data Encryption Keys) encrypt the actual data using Fernet.
    The KEK (Key Encryption Key) encrypts the DEKs for storage.
    """

    def __init__(self, kek_provider: KEKProvider):
        self._kek_provider = kek_provider

    def generate_dek(self) -> tuple[bytes, bytes]:
        """Generate a new DEK and return (encrypted_dek, plaintext_dek).

        The encrypted_dek should be stored in the database.
        The plaintext_dek is used for encryption operations and cached in memory.
        """
        plaintext_dek = Fernet.generate_key()
        encrypted_dek = self._kek_provider.encrypt_dek(plaintext_dek)
        # Cache the DEK
        _dek_cache[encrypted_dek] = (plaintext_dek, time.monotonic())
        return encrypted_dek, plaintext_dek

    def _get_plaintext_dek(self, encrypted_dek: bytes) -> bytes:
        """Get the plaintext DEK, using cache if available."""
        cached = _dek_cache.get(encrypted_dek)
        if cached:
            plaintext_dek, cached_at = cached
            if time.monotonic() - cached_at < _DEK_CACHE_TTL_SECONDS:
                return plaintext_dek
            # Cache expired
            del _dek_cache[encrypted_dek]

        # Decrypt DEK using KEK provider
        plaintext_dek = self._kek_provider.decrypt_dek(encrypted_dek)
        _dek_cache[encrypted_dek] = (plaintext_dek, time.monotonic())
        return plaintext_dek

    def encrypt(self, plaintext: str, encrypted_dek: bytes) -> str:
        """Encrypt plaintext using the given encrypted DEK.

        Returns base64-encoded ciphertext (Fernet token).
        """
        plaintext_dek = self._get_plaintext_dek(encrypted_dek)
        f = Fernet(plaintext_dek)
        ciphertext = f.encrypt(plaintext.encode("utf-8"))
        return ciphertext.decode("utf-8")

    def decrypt(self, ciphertext: str, encrypted_dek: bytes) -> str:
        """Decrypt ciphertext using the given encrypted DEK.

        Returns the original plaintext string.
        """
        plaintext_dek = self._get_plaintext_dek(encrypted_dek)
        f = Fernet(plaintext_dek)
        plaintext = f.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")


def _create_kek_provider() -> KEKProvider:
    """Create the appropriate KEK provider based on configuration."""
    from app.core.config import get_settings

    settings = get_settings()
    provider = settings.encryption_kek_provider

    if provider == "local":
        return LocalKEKProvider(
            key=settings.encryption_kek_local_key or None,
            key_file=settings.encryption_kek_local_key_file or None,
        )
    elif provider == "gcp_kms":
        if not settings.encryption_gcp_kms_key_name:
            raise ValueError("ENCRYPTION_GCP_KMS_KEY_NAME required for gcp_kms provider")
        return GCPKMSKEKProvider(key_name=settings.encryption_gcp_kms_key_name)
    elif provider == "aws_kms":
        if not settings.encryption_aws_kms_key_id:
            raise ValueError("ENCRYPTION_AWS_KMS_KEY_ID required for aws_kms provider")
        return AWSKMSKEKProvider(key_id=settings.encryption_aws_kms_key_id)
    else:
        raise ValueError(f"Unknown encryption KEK provider: {provider}")


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get cached EncryptionService instance."""
    kek_provider = _create_kek_provider()
    return EncryptionService(kek_provider)
