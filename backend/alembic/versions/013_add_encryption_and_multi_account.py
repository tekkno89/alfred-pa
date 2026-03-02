"""Add encryption keys table and multi-account support for oauth tokens.

Revision ID: 013_add_encryption_multi
Revises: 012_add_slack_status_custom
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_add_encryption_multi"
down_revision: str | None = "012_add_slack_status_custom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add encryption_keys table and multi-account columns to user_oauth_tokens."""
    # 1. Create encryption_keys table
    op.create_table(
        "encryption_keys",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("key_name", sa.String(100), unique=True, nullable=False),
        sa.Column("encrypted_dek", sa.LargeBinary, nullable=False),
        sa.Column("kek_provider", sa.String(50), nullable=False),
        sa.Column("kek_reference", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    # 2. Add new columns to user_oauth_tokens
    op.add_column(
        "user_oauth_tokens",
        sa.Column("encrypted_access_token", sa.Text, nullable=True),
    )
    op.add_column(
        "user_oauth_tokens",
        sa.Column("encrypted_refresh_token", sa.Text, nullable=True),
    )
    op.add_column(
        "user_oauth_tokens",
        sa.Column(
            "encryption_key_id",
            UUID(as_uuid=False),
            sa.ForeignKey("encryption_keys.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "user_oauth_tokens",
        sa.Column(
            "account_label",
            sa.String(100),
            nullable=False,
            server_default="default",
        ),
    )
    op.add_column(
        "user_oauth_tokens",
        sa.Column("external_account_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "user_oauth_tokens",
        sa.Column(
            "token_type",
            sa.String(20),
            nullable=False,
            server_default="oauth",
        ),
    )

    # 3. Drop old unique constraint and create new one
    op.drop_constraint(
        "uq_user_oauth_tokens_user_provider",
        "user_oauth_tokens",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_oauth_tokens_user_provider_label",
        "user_oauth_tokens",
        ["user_id", "provider", "account_label"],
    )


def downgrade() -> None:
    """Reverse encryption and multi-account changes."""
    # Drop new unique constraint and restore old one
    op.drop_constraint(
        "uq_user_oauth_tokens_user_provider_label",
        "user_oauth_tokens",
        type_="unique",
    )
    # Note: the original constraint name followed the naming convention
    op.create_unique_constraint(
        "uq_user_oauth_tokens_user_provider",
        "user_oauth_tokens",
        ["user_id", "provider"],
    )

    # Drop new columns from user_oauth_tokens
    op.drop_column("user_oauth_tokens", "token_type")
    op.drop_column("user_oauth_tokens", "external_account_id")
    op.drop_column("user_oauth_tokens", "account_label")
    op.drop_column("user_oauth_tokens", "encryption_key_id")
    op.drop_column("user_oauth_tokens", "encrypted_refresh_token")
    op.drop_column("user_oauth_tokens", "encrypted_access_token")

    # Drop encryption_keys table
    op.drop_table("encryption_keys")
