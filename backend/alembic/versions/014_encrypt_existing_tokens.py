"""Encrypt existing plaintext OAuth tokens.

Revision ID: 014_encrypt_existing_tokens
Revises: 013_add_encryption_multi
Create Date: 2026-03-01
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet

# revision identifiers, used by Alembic.
revision: str = "014_encrypt_existing_tokens"
down_revision: str | None = "013_add_encryption_multi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Encrypt all existing plaintext tokens in user_oauth_tokens."""
    conn = op.get_bind()

    # Check if there are any tokens to migrate
    result = conn.execute(
        sa.text(
            "SELECT id, access_token, refresh_token FROM user_oauth_tokens "
            "WHERE encrypted_access_token IS NULL AND access_token != 'encrypted'"
        )
    )
    rows = result.fetchall()

    if not rows:
        return  # Nothing to migrate

    # Import encryption service (needs settings to be configured)
    try:
        from app.core.encryption.service import get_encryption_service

        enc = get_encryption_service()
        encrypted_dek, _ = enc.generate_dek()

        # Store the DEK
        key_id = str(uuid4())
        from app.core.config import get_settings

        settings = get_settings()
        conn.execute(
            sa.text(
                "INSERT INTO encryption_keys (id, key_name, encrypted_dek, kek_provider, is_active, created_at, updated_at) "
                "VALUES (:id, :key_name, :encrypted_dek, :kek_provider, true, now(), now())"
            ),
            {
                "id": key_id,
                "key_name": "oauth_tokens_dek_v1",
                "encrypted_dek": encrypted_dek,
                "kek_provider": settings.encryption_kek_provider,
            },
        )

        # Encrypt each token
        for row in rows:
            token_id = row[0]
            access_token = row[1]
            refresh_token = row[2]

            encrypted_access = enc.encrypt(access_token, encrypted_dek)
            encrypted_refresh = (
                enc.encrypt(refresh_token, encrypted_dek)
                if refresh_token
                else None
            )

            conn.execute(
                sa.text(
                    "UPDATE user_oauth_tokens SET "
                    "encrypted_access_token = :enc_access, "
                    "encrypted_refresh_token = :enc_refresh, "
                    "encryption_key_id = :key_id "
                    "WHERE id = :id"
                ),
                {
                    "id": token_id,
                    "enc_access": encrypted_access,
                    "enc_refresh": encrypted_refresh,
                    "key_id": key_id,
                },
            )
    except Exception:
        # If encryption is not configured, skip migration
        # Tokens will be encrypted on next write
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "Skipping token encryption migration: encryption not configured. "
            "Tokens will be encrypted on next write."
        )


def downgrade() -> None:
    """Clear encrypted token fields (plaintext tokens remain intact)."""
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE user_oauth_tokens SET "
            "encrypted_access_token = NULL, "
            "encrypted_refresh_token = NULL, "
            "encryption_key_id = NULL"
        )
    )
    conn.execute(sa.text("DELETE FROM encryption_keys WHERE key_name = 'oauth_tokens_dek_v1'"))
