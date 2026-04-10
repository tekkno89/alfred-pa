"""Add alert tracking fields to triage_classifications

Revision ID: 033
Revises: 032
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add alert tracking columns
    op.add_column(
        'triage_classifications',
        sa.Column('last_alerted_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'triage_classifications',
        sa.Column('alert_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Add indexes for deduplication queries
    op.create_index(
        'idx_triage_last_alerted_thread',
        'triage_classifications',
        ['user_id', 'thread_ts', 'last_alerted_at'],
        postgresql_where=sa.text('thread_ts IS NOT NULL')
    )
    op.create_index(
        'idx_triage_last_alerted_sender',
        'triage_classifications',
        ['user_id', 'sender_slack_id', 'last_alerted_at']
    )


def downgrade() -> None:
    op.drop_index('idx_triage_last_alerted_sender', 'triage_classifications')
    op.drop_index('idx_triage_last_alerted_thread', 'triage_classifications')
    op.drop_column('triage_classifications', 'alert_count')
    op.drop_column('triage_classifications', 'last_alerted_at')