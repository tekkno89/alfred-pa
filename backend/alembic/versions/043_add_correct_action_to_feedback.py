"""add correct_action to triage_feedback and fix embedding column

Revision ID: 043
Revises: 042
Create Date: 2026-05-11

This migration:
1. Adds correct_action field to triage_feedback table
2. Migrates existing correct_priority values to correct_action
3. Alters feedback_embeddings.embedding_vector from ARRAY to Vector type

"""

import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None

PRIORITY_TO_ACTION = {
    "p0": "notify_now",
    "p1": "summarize_next",
    "p2": "summarize_eod",
    "p3": "ignore",
    "review": "notify_now",
}


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "triage_feedback",
        sa.Column("correct_action", sa.String(20), nullable=True),
    )

    for old_val, new_val in PRIORITY_TO_ACTION.items():
        conn.execute(
            sa.text(
                "UPDATE triage_feedback SET correct_action = :new_val "
                "WHERE correct_priority = :old_val"
            ),
            {"new_val": new_val, "old_val": old_val},
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS feedback_embeddings_embedding_vector_idx "
        "ON feedback_embeddings USING ivfflat (embedding_vector vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_column("triage_feedback", "correct_action")
    op.execute(
        "DROP INDEX IF EXISTS feedback_embeddings_embedding_vector_idx"
    )
