"""add sensitive to monitored_channels

Revision ID: 038
Revises: 037
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='monitored_channels' AND column_name='sensitive'"
        )
    )
    if not result.fetchone():
        op.add_column(
            "monitored_channels",
            sa.Column(
                "sensitive",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        conn.execute(
            sa.text(
                "UPDATE monitored_channels SET sensitive = true WHERE channel_type = 'private'"
            )
        )


def downgrade() -> None:
    op.drop_column("monitored_channels", "sensitive")
