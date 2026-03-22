"""Add digest consolidation columns and rename review_at_break to review.

Revision ID: 026_digest_consol
Revises: 025_custom_class_rules
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "026_digest_consol"
down_revision = "025_custom_class_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add session-scoping and digest consolidation columns
    op.add_column(
        "triage_classifications",
        sa.Column("focus_started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "triage_classifications",
        sa.Column(
            "digest_summary_id",
            UUID(as_uuid=False),
            sa.ForeignKey("triage_classifications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "triage_classifications",
        sa.Column("child_count", sa.Integer(), nullable=True),
    )

    # Rename review_at_break -> review in existing data
    op.execute(
        "UPDATE triage_classifications SET urgency_level = 'review' "
        "WHERE urgency_level = 'review_at_break'"
    )
    op.execute(
        "UPDATE triage_feedback SET correct_urgency = 'review' "
        "WHERE correct_urgency = 'review_at_break'"
    )


def downgrade() -> None:
    # Rename review -> review_at_break
    op.execute(
        "UPDATE triage_classifications SET urgency_level = 'review_at_break' "
        "WHERE urgency_level = 'review'"
    )
    op.execute(
        "UPDATE triage_feedback SET correct_urgency = 'review_at_break' "
        "WHERE correct_urgency = 'review'"
    )

    op.drop_column("triage_classifications", "child_count")
    op.drop_column("triage_classifications", "digest_summary_id")
    op.drop_column("triage_classifications", "focus_started_at")
