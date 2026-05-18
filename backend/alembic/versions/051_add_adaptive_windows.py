"""add adaptive windows

Revision ID: 051
Revises: 050
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "051"
down_revision = "050"
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adaptive_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "message_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message_types.id"),
            nullable=False,
        ),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_adaptive_windows_unique",
        "adaptive_windows",
        ["user_id", "message_type_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_adaptive_windows_unique")
    op.drop_table("adaptive_windows")
