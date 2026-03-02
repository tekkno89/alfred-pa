"""Add github_app_configs table and FK on user_oauth_tokens.

Revision ID: 015_add_github_app_configs
Revises: 014_encrypt_existing_tokens
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_add_github_app_configs"
down_revision: str | None = "014_encrypt_existing_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create github_app_configs table and add FK to user_oauth_tokens."""
    op.create_table(
        "github_app_configs",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("encrypted_client_secret", sa.Text(), nullable=False),
        sa.Column(
            "encryption_key_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("encryption_keys.id"),
            nullable=False,
        ),
        sa.Column("github_app_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "label", name="uq_github_app_configs_user_label"
        ),
    )

    op.add_column(
        "user_oauth_tokens",
        sa.Column(
            "github_app_config_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("github_app_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop github_app_config_id from user_oauth_tokens and drop github_app_configs."""
    op.drop_column("user_oauth_tokens", "github_app_config_id")
    op.drop_table("github_app_configs")
