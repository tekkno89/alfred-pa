"""Add summary cadence configuration to triage_user_settings

Revision ID: 034
Revises: 033
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P1 digest configuration
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_active_hours_start', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_active_hours_end', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_times', ARRAY(sa.String()), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )

    # P2 digest configuration
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_active_hours_start', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_active_hours_end', sa.String(10), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_times', ARRAY(sa.String()), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )

    # P3 digest configuration
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_digest_time', sa.String(10), nullable=True)
    )

    # Alert deduplication configuration
    op.add_column(
        'triage_user_settings',
        sa.Column('alert_dedup_window_minutes', sa.Integer(), nullable=False, server_default='30')
    )


def downgrade() -> None:
    # Remove alert deduplication config
    op.drop_column('triage_user_settings', 'alert_dedup_window_minutes')

    # Remove P3 digest config
    op.drop_column('triage_user_settings', 'p3_digest_time')

    # Remove P2 digest config
    op.drop_column('triage_user_settings', 'p2_digest_outside_hours_behavior')
    op.drop_column('triage_user_settings', 'p2_digest_times')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p2_digest_interval_minutes')

    # Remove P1 digest config
    op.drop_column('triage_user_settings', 'p1_digest_outside_hours_behavior')
    op.drop_column('triage_user_settings', 'p1_digest_times')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p1_digest_interval_minutes')