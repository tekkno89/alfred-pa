"""Add is_starred column to sessions table.

Revision ID: 006
Revises: 005
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006_add_session_starred"
down_revision: str | None = "005_add_pomodoro_session_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "is_starred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_sessions_user_id_is_starred",
        "sessions",
        ["user_id", "is_starred"],
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_user_id_is_starred", table_name="sessions")
    op.drop_column("sessions", "is_starred")
