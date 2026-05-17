"""add channel type rules

Revision ID: 047
Revises: 046
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "047"
down_revision = "046"
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_type_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column(
            "message_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message_types.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_channel_type_rules_unique",
        "channel_type_rules",
        ["user_id", "channel_id", "message_type_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_channel_type_rules_unique")
    op.drop_table("channel_type_rules")
