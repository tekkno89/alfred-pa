"""Refactor triage urgency levels to P0-P3 priority system.

Revision ID: 029_triage_prio
Revises: 028_reauth_dm
"""

from alembic import op
import sqlalchemy as sa

revision = "029_triage_prio"
down_revision = "028_reauth_dm"
branch_labels = None
depends_on = None

# Value mapping: old urgency -> new priority
URGENCY_TO_PRIORITY = {
    "urgent": "p0",
    "digest": "p2",
    "noise": "p3",
    "review": "review",
    "digest_summary": "digest_summary",
}

PRIORITY_TO_URGENCY = {v: k for k, v in URGENCY_TO_PRIORITY.items()}


def upgrade() -> None:
    # --- triage_classifications: rename urgency_level -> priority_level ---
    op.alter_column(
        "triage_classifications",
        "urgency_level",
        new_column_name="priority_level",
    )
    # Migrate values
    for old, new in URGENCY_TO_PRIORITY.items():
        op.execute(
            sa.text(
                "UPDATE triage_classifications SET priority_level = :new WHERE priority_level = :old"
            ).bindparams(old=old, new=new)
        )

    # --- channel_keyword_rules: rename urgency_override -> priority_override ---
    op.alter_column(
        "channel_keyword_rules",
        "urgency_override",
        new_column_name="priority_override",
    )
    for old, new in URGENCY_TO_PRIORITY.items():
        if old in ("urgent", "digest", "review"):
            op.execute(
                sa.text(
                    "UPDATE channel_keyword_rules SET priority_override = :new WHERE priority_override = :old"
                ).bindparams(old=old, new=new)
            )

    # --- triage_feedback: rename correct_urgency -> correct_priority, add feedback_text ---
    op.alter_column(
        "triage_feedback",
        "correct_urgency",
        new_column_name="correct_priority",
    )
    for old, new in URGENCY_TO_PRIORITY.items():
        if old in ("urgent", "digest", "noise", "review"):
            op.execute(
                sa.text(
                    "UPDATE triage_feedback SET correct_priority = :new WHERE correct_priority = :old"
                ).bindparams(old=old, new=new)
            )
    op.add_column(
        "triage_feedback",
        sa.Column("feedback_text", sa.Text(), nullable=True),
    )

    # --- triage_user_settings: add priority definition columns ---
    op.add_column(
        "triage_user_settings",
        sa.Column("p0_definition", sa.Text(), nullable=True),
    )
    op.add_column(
        "triage_user_settings",
        sa.Column("p1_definition", sa.Text(), nullable=True),
    )
    op.add_column(
        "triage_user_settings",
        sa.Column("p2_definition", sa.Text(), nullable=True),
    )
    op.add_column(
        "triage_user_settings",
        sa.Column("p3_definition", sa.Text(), nullable=True),
    )
    op.add_column(
        "triage_user_settings",
        sa.Column("digest_instructions", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # --- triage_user_settings: drop definition columns ---
    op.drop_column("triage_user_settings", "digest_instructions")
    op.drop_column("triage_user_settings", "p3_definition")
    op.drop_column("triage_user_settings", "p2_definition")
    op.drop_column("triage_user_settings", "p1_definition")
    op.drop_column("triage_user_settings", "p0_definition")

    # --- triage_feedback: drop feedback_text, rename back ---
    op.drop_column("triage_feedback", "feedback_text")
    for old, new in PRIORITY_TO_URGENCY.items():
        if old in ("p0", "p2", "p3", "review"):
            op.execute(
                sa.text(
                    "UPDATE triage_feedback SET correct_priority = :new WHERE correct_priority = :old"
                ).bindparams(old=old, new=new)
            )
    op.alter_column(
        "triage_feedback",
        "correct_priority",
        new_column_name="correct_urgency",
    )

    # --- channel_keyword_rules: rename back ---
    for old, new in PRIORITY_TO_URGENCY.items():
        if old in ("p0", "p2", "review"):
            op.execute(
                sa.text(
                    "UPDATE channel_keyword_rules SET priority_override = :new WHERE priority_override = :old"
                ).bindparams(old=old, new=new)
            )
    op.alter_column(
        "channel_keyword_rules",
        "priority_override",
        new_column_name="urgency_override",
    )

    # --- triage_classifications: rename back ---
    for old, new in PRIORITY_TO_URGENCY.items():
        op.execute(
            sa.text(
                "UPDATE triage_classifications SET priority_level = :new WHERE priority_level = :old"
            ).bindparams(old=old, new=new)
        )
    op.alter_column(
        "triage_classifications",
        "priority_level",
        new_column_name="urgency_level",
    )
