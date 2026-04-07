"""add runtime_type to coding_jobs

Revision ID: 031
Revises: 594a750883d8
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: str = "594a750883d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "coding_jobs",
        sa.Column(
            "runtime_type",
            sa.String(30),
            nullable=True,
            server_default="docker_sandbox",
        ),
    )


def downgrade() -> None:
    op.drop_column("coding_jobs", "runtime_type")
