"""remove_always_on_min_priority_field

Revision ID: be2ebf7ee839
Revises: f3c49f8fa043
Create Date: 2026-04-10 18:02:21.092951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be2ebf7ee839'
down_revision: Union[str, None] = 'f3c49f8fa043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove always_on_min_priority field (replaced by priority-level toggles)
    op.drop_column('triage_user_settings', 'always_on_min_priority')


def downgrade() -> None:
    op.add_column(
        'triage_user_settings',
        sa.Column('always_on_min_priority', sa.String(2), nullable=True)
    )
    # Set default value for existing rows
    op.execute("UPDATE triage_user_settings SET always_on_min_priority = 'p3'")
    op.alter_column('triage_user_settings', 'always_on_min_priority', nullable=False)
