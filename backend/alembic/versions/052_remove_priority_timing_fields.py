"""remove priority-based timing fields

Revision ID: 052
Revises: 051
"""

from alembic import op
import sqlalchemy as sa

revision = '052'
down_revision = '051'
depends_on = None


def upgrade() -> None:
    # Remove alert enabled fields
    op.drop_column('triage_user_settings', 'p0_alerts_enabled')
    op.drop_column('triage_user_settings', 'p1_alerts_enabled')
    op.drop_column('triage_user_settings', 'p2_alerts_enabled')
    op.drop_column('triage_user_settings', 'p3_alerts_enabled')
    
    # Remove P1 digest fields
    op.drop_column('triage_user_settings', 'p1_digest_interval_minutes')
    op.drop_column('triage_user_settings', 'p1_digest_times')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p1_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p1_digest_outside_hours_behavior')
    
    # Remove P2 digest fields
    op.drop_column('triage_user_settings', 'p2_digest_interval_minutes')
    op.drop_column('triage_user_settings', 'p2_digest_times')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_start')
    op.drop_column('triage_user_settings', 'p2_digest_active_hours_end')
    op.drop_column('triage_user_settings', 'p2_digest_outside_hours_behavior')
    
    # Remove P3 digest field
    op.drop_column('triage_user_settings', 'p3_digest_time')


def downgrade() -> None:
    # Re-add alert enabled fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p0_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_alerts_enabled', sa.Boolean(), server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_alerts_enabled', sa.Boolean(), server_default='true')
    )
    
    # Re-add P1 digest fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_digest_times', sa.JSON(), nullable=True)
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
        sa.Column('p1_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )
    
    # Re-add P2 digest fields
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_interval_minutes', sa.Integer(), nullable=True)
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_digest_times', sa.JSON(), nullable=True)
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
        sa.Column('p2_digest_outside_hours_behavior', sa.String(20), nullable=True)
    )
    
    # Re-add P3 digest field
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_digest_time', sa.String(10), nullable=True)
    )
