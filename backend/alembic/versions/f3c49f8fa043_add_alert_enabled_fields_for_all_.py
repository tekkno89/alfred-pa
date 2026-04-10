"""add_alert_enabled_fields_for_all_priorities

Revision ID: f3c49f8fa043
Revises: 7e5f8a6b6aa9
Create Date: 2026-04-09 21:40:33.036824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c49f8fa043'
down_revision: Union[str, None] = '7e5f8a6b6aa9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add alert enabled fields for P1, P2, P3
    op.add_column(
        'triage_user_settings',
        sa.Column('p1_alerts_enabled', sa.Boolean(), nullable=False, server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p2_alerts_enabled', sa.Boolean(), nullable=False, server_default='true')
    )
    op.add_column(
        'triage_user_settings',
        sa.Column('p3_alerts_enabled', sa.Boolean(), nullable=False, server_default='true')
    )


def downgrade() -> None:
    op.drop_column('triage_user_settings', 'p3_alerts_enabled')
    op.drop_column('triage_user_settings', 'p2_alerts_enabled')
    op.drop_column('triage_user_settings', 'p1_alerts_enabled')
