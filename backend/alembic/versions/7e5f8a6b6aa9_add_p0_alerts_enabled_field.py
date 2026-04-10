"""add_p0_alerts_enabled_field

Revision ID: 7e5f8a6b6aa9
Revises: 034
Create Date: 2026-04-09 21:02:21.298764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e5f8a6b6aa9'
down_revision: Union[str, None] = '034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add p0_alerts_enabled field to triage_user_settings
    op.add_column(
        'triage_user_settings',
        sa.Column('p0_alerts_enabled', sa.Boolean(), nullable=False, server_default='true')
    )


def downgrade() -> None:
    op.drop_column('triage_user_settings', 'p0_alerts_enabled')
