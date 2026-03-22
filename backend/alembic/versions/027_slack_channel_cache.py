"""Add slack_channel_cache table.

Revision ID: 027_slack_ch_cache
Revises: 026_digest_consol
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "027_slack_ch_cache"
down_revision = "026_digest_consol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_channel_cache",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("slack_channel_id", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("num_members", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("slack_channel_cache")
