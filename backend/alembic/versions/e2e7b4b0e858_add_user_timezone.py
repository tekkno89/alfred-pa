"""add_user_timezone

Revision ID: e2e7b4b0e858
Revises: f3c49f8fa043
Create Date: 2026-04-14 05:01:59.920777

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2e7b4b0e858"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "timezone")
