"""add_triage_instructions_and_remove_keyword_rules

Revision ID: 88dc8958a993
Revises: 324b85746fc7
Create Date: 2026-04-11 12:30:27.984164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88dc8958a993'
down_revision: Union[str, None] = '324b85746fc7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add triage_instructions column to monitored_channels
    op.add_column('monitored_channels', sa.Column('triage_instructions', sa.Text(), nullable=True))

    # Drop channel_keyword_rules table
    op.drop_table('channel_keyword_rules')


def downgrade() -> None:
    # Recreate channel_keyword_rules table
    op.create_table(
        'channel_keyword_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('monitored_channel_id', sa.String(36), sa.ForeignKey('monitored_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('keyword_pattern', sa.String(255), nullable=False),
        sa.Column('match_type', sa.String(20), default='contains'),
        sa.Column('priority_override', sa.String(20), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Remove triage_instructions column
    op.drop_column('monitored_channels', 'triage_instructions')
