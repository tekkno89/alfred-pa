"""add topic affinities

Revision ID: 044
Revises: 043
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '044'
down_revision = '043'
depends_on = None


def upgrade() -> None:
    op.create_table(
        'topic_affinities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('keyword', sa.String(100), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('source_category', sa.String(50), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_topic_affinities_unique',
        'topic_affinities',
        ['user_id', 'keyword'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_topic_affinities_unique')
    op.drop_table('topic_affinities')
