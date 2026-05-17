"""add updated_at to message_types and channel_type_rules

Revision ID: 048
Revises: 047
"""

from alembic import op
import sqlalchemy as sa

revision = "048"
down_revision = "047"
depends_on = None


def upgrade() -> None:
    op.add_column(
        "message_types",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.add_column(
        "channel_type_rules",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_column("channel_type_rules", "updated_at")
    op.drop_column("message_types", "updated_at")
