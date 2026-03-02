"""Add todos table.

Revision ID: 016_add_todos_table
Revises: 015_add_github_app_configs
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_add_todos_table"
down_revision: str | None = "015_add_github_app_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create todos table."""
    op.create_table(
        "todos",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("users.id", name="fk_todos_user_id_users"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="2", nullable=False),
        sa.Column(
            "status", sa.String(20), server_default="open", nullable=False
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_starred", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "tags",
            sa.ARRAY(sa.String(100)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("recurrence_rule", sa.String(500), nullable=True),
        sa.Column(
            "recurrence_parent_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("todos.id", name="fk_todos_recurrence_parent_id_todos"),
            nullable=True,
        ),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_job_id", sa.String(100), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_todos"),
    )
    op.create_index("ix_todos_user_id", "todos", ["user_id"])
    op.create_index("ix_todos_user_id_status", "todos", ["user_id", "status"])
    op.create_index("ix_todos_user_id_due_at", "todos", ["user_id", "due_at"])
    op.create_index(
        "ix_todos_recurrence_parent_id", "todos", ["recurrence_parent_id"]
    )


def downgrade() -> None:
    """Drop todos table."""
    op.drop_index("ix_todos_recurrence_parent_id", table_name="todos")
    op.drop_index("ix_todos_user_id_due_at", table_name="todos")
    op.drop_index("ix_todos_user_id_status", table_name="todos")
    op.drop_index("ix_todos_user_id", table_name="todos")
    op.drop_table("todos")
