"""Add slack_user_id to users table.

Revision ID: 003_add_slack_user_id
Revises: 002_memory_vector_768
Create Date: 2026-02-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_slack_user_id"
down_revision: str | None = "002_memory_vector_768"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add slack_user_id column to users table."""
    op.add_column(
        "users",
        sa.Column("slack_user_id", sa.String(50), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_slack_user_id",
        "users",
        ["slack_user_id"],
    )


def downgrade() -> None:
    """Remove slack_user_id column from users table."""
    op.drop_constraint("uq_users_slack_user_id", "users", type_="unique")
    op.drop_column("users", "slack_user_id")
