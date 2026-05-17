"""add message types

Revision ID: 046
Revises: 045
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "046"
down_revision = "045"
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("type_name", sa.String(100), nullable=False),
        sa.Column("type_definition", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("is_archived", sa.Boolean(), default=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_message_types_unique",
        "message_types",
        ["user_id", "type_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_message_types_unique")
    op.drop_table("message_types")
