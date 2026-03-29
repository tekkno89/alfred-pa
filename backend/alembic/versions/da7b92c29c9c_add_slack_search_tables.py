"""add slack search tables

Revision ID: da7b92c29c9c
Revises: 030_always_on_min_prio
Create Date: 2026-03-29 19:57:20.974628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'da7b92c29c9c'
down_revision: Union[str, None] = '030_always_on_min_prio'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('slack_channel_summaries',
    sa.Column('channel_id', sa.String(length=50), nullable=False),
    sa.Column('channel_name', sa.String(length=255), nullable=False),
    sa.Column('channel_type', sa.String(length=10), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('member_count', sa.Integer(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('generated_by_user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('last_summarized_at', sa.DateTime(), nullable=False),
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['generated_by_user_id'], ['users.id'], name=op.f('fk_slack_channel_summaries_generated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_slack_channel_summaries')),
    sa.UniqueConstraint('channel_id', name=op.f('uq_slack_channel_summaries_channel_id'))
    )
    op.create_table('user_channel_participation',
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('channel_id', sa.String(length=50), nullable=False),
    sa.Column('channel_name', sa.String(length=255), nullable=False),
    sa.Column('channel_type', sa.String(length=10), nullable=False),
    sa.Column('participation_rank', sa.Integer(), nullable=False),
    sa.Column('is_member', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('member_count', sa.Integer(), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_channel_participation_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_channel_participation')),
    sa.UniqueConstraint('user_id', 'channel_id', name='uq_user_channel_participation')
    )
    op.create_index(op.f('ix_user_channel_participation_user_id'), 'user_channel_participation', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_channel_participation_user_id'), table_name='user_channel_participation')
    op.drop_table('user_channel_participation')
    op.drop_table('slack_channel_summaries')
