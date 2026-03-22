"""Add reauth_dm_sent_at column to user_oauth_tokens.

Revision ID: 028_reauth_dm
Revises: 027_slack_ch_cache
"""

from alembic import op
import sqlalchemy as sa

revision = "028_reauth_dm"
down_revision = "027_slack_ch_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_oauth_tokens",
        sa.Column("reauth_dm_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_oauth_tokens", "reauth_dm_sent_at")
