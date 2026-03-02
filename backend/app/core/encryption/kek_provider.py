"""KEK (Key Encryption Key) provider interface and implementations."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class KEKProvider(ABC):
    """Abstract base class for Key Encryption Key providers."""

    @abstractmethod
    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypt a DEK using the KEK."""
        ...

    @abstractmethod
    def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt a DEK using the KEK."""
        ...


class LocalKEKProvider(KEKProvider):
    """KEK provider using a local Fernet key.

    Suitable for development and single-server deployments.
    For production multi-server deployments, use GCP KMS or AWS KMS.
    """

    def __init__(self, key: str | None = None, key_file: str | None = None):
        if key:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        elif key_file:
            key_data = Path(key_file).read_text().strip()
            self._fernet = Fernet(key_data.encode())
        else:
            raise ValueError(
                "ENCRYPTION_KEK_LOCAL_KEY or ENCRYPTION_KEK_LOCAL_KEY_FILE must be set. "
                "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypt a DEK using the local Fernet key."""
        return self._fernet.encrypt(plaintext_dek)

    def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt a DEK using the local Fernet key."""
        return self._fernet.decrypt(encrypted_dek)


class GCPKMSKEKProvider(KEKProvider):
    """KEK provider using Google Cloud KMS.

    Requires google-cloud-kms package and appropriate credentials.
    """

    def __init__(self, key_name: str):
        self._key_name = key_name

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypt a DEK using GCP KMS."""
        try:
            from google.cloud import kms  # type: ignore[attr-defined]

            client = kms.KeyManagementServiceClient()
            response = client.encrypt(
                request={"name": self._key_name, "plaintext": plaintext_dek}
            )
            return response.ciphertext
        except ImportError:
            raise RuntimeError(
                "google-cloud-kms package required for GCP KMS provider. "
                "Install with: pip install google-cloud-kms"
            )

    def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt a DEK using GCP KMS."""
        try:
            from google.cloud import kms  # type: ignore[attr-defined]

            client = kms.KeyManagementServiceClient()
            response = client.decrypt(
                request={"name": self._key_name, "ciphertext": encrypted_dek}
            )
            return response.plaintext
        except ImportError:
            raise RuntimeError(
                "google-cloud-kms package required for GCP KMS provider. "
                "Install with: pip install google-cloud-kms"
            )


class AWSKMSKEKProvider(KEKProvider):
    """KEK provider using AWS KMS.

    Requires boto3 package and appropriate credentials.
    """

    def __init__(self, key_id: str):
        self._key_id = key_id

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypt a DEK using AWS KMS."""
        try:
            import boto3  # type: ignore[import-untyped]

            client = boto3.client("kms")
            response = client.encrypt(
                KeyId=self._key_id,
                Plaintext=plaintext_dek,
            )
            return response["CiphertextBlob"]
        except ImportError:
            raise RuntimeError(
                "boto3 package required for AWS KMS provider. "
                "Install with: pip install boto3"
            )

    def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt a DEK using AWS KMS."""
        try:
            import boto3  # type: ignore[import-untyped]

            client = boto3.client("kms")
            response = client.decrypt(
                CiphertextBlob=encrypted_dek,
            )
            return response["Plaintext"]
        except ImportError:
            raise RuntimeError(
                "boto3 package required for AWS KMS provider. "
                "Install with: pip install boto3"
            )
