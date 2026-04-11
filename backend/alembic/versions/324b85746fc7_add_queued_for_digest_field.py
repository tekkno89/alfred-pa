"""add_queued_for_digest_field

Revision ID: 324b85746fc7
Revises: be2ebf7ee839
Create Date: 2026-04-10 22:40:53.128915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '324b85746fc7'
down_revision: Union[str, None] = 'be2ebf7ee839'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add queued_for_digest field to track which messages should be digested
    op.add_column(
        'triage_classifications',
        sa.Column('queued_for_digest', sa.Boolean(), nullable=False, server_default='true')
    )

    # Create index for digest queries
    op.create_index(
        'idx_triage_queued_digest',
        'triage_classifications',
        ['user_id', 'priority_level', 'queued_for_digest'],
        postgresql_where=sa.text('queued_for_digest = true')
    )


def downgrade() -> None:
    op.drop_index('idx_triage_queued_digest', table_name='triage_classifications')
    op.drop_column('triage_user_settings', 'queued_for_digest')
