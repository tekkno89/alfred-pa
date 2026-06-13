"""add delivery timing and grouping columns

Revision ID: 056
Revises: 055
Create Date: 2026-06-07

"""

from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TriageClassification columns
    op.add_column("triage_classifications", sa.Column("group_id", sa.String(36), nullable=True))
    op.add_column("triage_classifications", sa.Column("deliver_by", sa.DateTime(timezone=True), nullable=True))
    op.add_column("triage_classifications", sa.Column("last_related_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("triage_classifications", sa.Column("settled_threshold", sa.Integer(), nullable=True))
    op.add_column("triage_classifications", sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("triage_classifications", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))

    op.create_index("idx_tc_group_id", "triage_classifications", ["group_id"], postgresql_where=sa.text("group_id IS NOT NULL"))
    op.create_index("idx_tc_delivery", "triage_classifications", ["user_id", "deliver_by"], postgresql_where=sa.text("queued_for_digest = true AND deliver_by IS NOT NULL"))

    # TriageUserSettings columns
    op.add_column("triage_user_settings", sa.Column("p1_max_wait_minutes", sa.Integer(), server_default="60", nullable=False))
    op.add_column("triage_user_settings", sa.Column("p1_settled_threshold_minutes", sa.Integer(), server_default="30", nullable=False))


def downgrade() -> None:
    op.drop_column("triage_user_settings", "p1_settled_threshold_minutes")
    op.drop_column("triage_user_settings", "p1_max_wait_minutes")

    op.drop_index("idx_tc_delivery", table_name="triage_classifications")
    op.drop_index("idx_tc_group_id", table_name="triage_classifications")

    op.drop_column("triage_classifications", "retry_count")
    op.drop_column("triage_classifications", "needs_review")
    op.drop_column("triage_classifications", "settled_threshold")
    op.drop_column("triage_classifications", "last_related_activity_at")
    op.drop_column("triage_classifications", "deliver_by")
    op.drop_column("triage_classifications", "group_id")
