"""add_is_hidden_to_monitored_channels

Revision ID: b6f791ab3552
Revises: 88dc8958a993
Create Date: 2026-04-11 14:20:48.333760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6f791ab3552'
down_revision: Union[str, None] = '88dc8958a993'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('monitored_channels', sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('monitored_channels', 'is_hidden')
