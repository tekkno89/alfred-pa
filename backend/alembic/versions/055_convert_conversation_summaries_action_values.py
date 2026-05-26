"""convert conversation_summaries action values from p1/p2/p3 to summarize_next/summarize_eod/ignore

Revision ID: 055
Revises: 054
Create Date: 2026-05-26

"""

from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE conversation_summaries
        SET action = CASE
            WHEN action = 'p1' THEN 'summarize_next'
            WHEN action = 'p2' THEN 'summarize_eod'
            WHEN action = 'p3' THEN 'ignore'
            ELSE action
        END
        WHERE action IN ('p1', 'p2', 'p3')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE conversation_summaries
        SET action = CASE
            WHEN action = 'summarize_next' THEN 'p1'
            WHEN action = 'summarize_eod' THEN 'p2'
            WHEN action = 'ignore' THEN 'p3'
            ELSE action
        END
        WHERE action IN ('summarize_next', 'summarize_eod', 'ignore')
    """)
