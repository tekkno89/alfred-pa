"""add feedback embeddings

Revision ID: 040
Revises: 039
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "triage_feedback_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("triage_feedback.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "embedding_vector",
            postgresql.ARRAY(sa.Float(), dimensions=1),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_feedback_embeddings_feedback",
        "feedback_embeddings",
        ["triage_feedback_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_embeddings_feedback")
    op.drop_table("feedback_embeddings")
