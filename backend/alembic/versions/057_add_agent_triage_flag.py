"""add agent triage feature flag

Revision ID: 057
Revises: 056
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("triage_user_settings", sa.Column("use_agent_triage", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("triage_user_settings", "use_agent_triage")
