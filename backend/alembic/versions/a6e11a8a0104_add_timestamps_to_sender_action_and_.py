"""add_timestamps_to_sender_action_and_feedback

Revision ID: a6e11a8a0104
Revises: 8ba4c1e5adea
Create Date: 2026-05-24 13:36:24.982202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6e11a8a0104'
down_revision: Union[str, None] = '8ba4c1e5adea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timestamps to sender_action_distributions
    op.add_column(
        "sender_action_distributions",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "sender_action_distributions",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add timestamps to feedback_embeddings
    op.add_column(
        "feedback_embeddings",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column(
        "feedback_embeddings",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Remove from feedback_embeddings
    op.drop_column("feedback_embeddings", "updated_at")
    op.drop_column("feedback_embeddings", "created_at")

    # Remove from sender_action_distributions
    op.drop_column("sender_action_distributions", "updated_at")
    op.drop_column("sender_action_distributions", "created_at")
