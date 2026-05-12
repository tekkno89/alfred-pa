"""rename priority to action

Revision ID: 042
Revises: 041
Create Date: 2026-05-11

This migration:
1. Renames priority_level column to action
2. Migrates existing values to new action labels
3. Adds review and is_consolidated flags

"""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None

PRIORITY_TO_ACTION = {
    "p0": "notify_now",
    "p1": "summarize_next",
    "p2": "summarize_eod",
    "p3": "ignore",
    "review": "notify_now",
    "digest_summary": "summarize_eod",
}


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "triage_classifications",
        sa.Column("action", sa.String(20), nullable=True),
    )

    for old_val, new_val in PRIORITY_TO_ACTION.items():
        conn.execute(
            sa.text(
                "UPDATE triage_classifications SET action = :new_val "
                "WHERE priority_level = :old_val"
            ),
            {"new_val": new_val, "old_val": old_val},
        )

    op.add_column(
        "triage_classifications",
        sa.Column("review", sa.Boolean(), nullable=True, server_default="false"),
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET review = true "
            "WHERE priority_level = 'review'"
        )
    )

    op.add_column(
        "triage_classifications",
        sa.Column(
            "is_consolidated", sa.Boolean(), nullable=True, server_default="false"
        ),
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET is_consolidated = true "
            "WHERE priority_level = 'digest_summary'"
        )
    )

    op.alter_column("triage_classifications", "action", nullable=False)

    op.drop_column("triage_classifications", "priority_level")

    op.create_index(
        "ix_triage_classifications_action",
        "triage_classifications",
        ["action"],
    )


def downgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "triage_classifications",
        sa.Column("priority_level", sa.String(20), nullable=True),
    )

    ACTION_TO_PRIORITY = {
        "notify_now": "p0",
        "summarize_next": "p1",
        "summarize_eod": "p2",
        "ignore": "p3",
    }
    for new_val, old_val in ACTION_TO_PRIORITY.items():
        conn.execute(
            sa.text(
                "UPDATE triage_classifications SET priority_level = :old_val "
                "WHERE action = :new_val"
            ),
            {"new_val": new_val, "old_val": old_val},
        )

    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET priority_level = 'review' "
            "WHERE review = true"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE triage_classifications SET priority_level = 'digest_summary' "
            "WHERE is_consolidated = true"
        )
    )

    op.drop_index("ix_triage_classifications_action")
    op.drop_column("triage_classifications", "action")
    op.drop_column("triage_classifications", "review")
    op.drop_column("triage_classifications", "is_consolidated")
