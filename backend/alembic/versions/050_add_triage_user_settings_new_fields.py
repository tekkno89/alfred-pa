"""add triage user settings new fields

Revision ID: 050
Revises: 049
"""

import sqlalchemy as sa

from alembic import op

revision = '050'
down_revision = '049'
depends_on = None


def upgrade() -> None:
    op.add_column(
        'triage_user_settings',
        sa.Column('eod_review_time', sa.String(10), server_default='17:30')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('notify_now_degrade_minutes', sa.Integer, server_default='240')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('away_mode_enabled', sa.Boolean, server_default='false')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('away_mode_notify_now_behavior', sa.String(20), server_default='push_immediately')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('product_mode', sa.String(20), server_default='always_on')
    )


def downgrade() -> None:
    op.drop_column('triage_user_settings', 'product_mode')
    op.drop_column('triage_user_settings', 'away_mode_notify_now_behavior')
    op.drop_column('triage_user_settings', 'away_mode_enabled')
    op.drop_column('triage_user_settings', 'notify_now_degrade_minutes')
    op.drop_column('triage_user_settings', 'eod_review_time')
