"""add suppressed deliveries

Revision ID: 045
Revises: 044
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '045'
down_revision = '044'
depends_on = None


def upgrade() -> None:
    # Drop existing table with different schema (if exists)
    op.execute('DROP TABLE IF EXISTS suppressed_deliveries CASCADE')
    
    op.create_table(
        'suppressed_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message_id', sa.String(50), nullable=False),
        sa.Column('original_action', sa.String(20), nullable=False),
        sa.Column('suppression_reason', sa.String(50), nullable=False),
        sa.Column('outcome_summary', sa.Text(), nullable=True),
        sa.Column('user_review_response', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_suppressed_deliveries_user_created',
        'suppressed_deliveries',
        ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_suppressed_deliveries_user_created')
    op.drop_table('suppressed_deliveries')
