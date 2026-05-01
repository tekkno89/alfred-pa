"""add updated_at to conversation_summaries

Revision ID: 037
Revises: 036
Create Date: 2026-05-01

"""

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='conversation_summaries' AND column_name='updated_at'"
        )
    )
    if not result.fetchone():
        op.add_column(
            "conversation_summaries",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("conversation_summaries", "updated_at")
