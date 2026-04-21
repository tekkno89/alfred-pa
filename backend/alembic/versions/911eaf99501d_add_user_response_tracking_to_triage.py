"""add_user_response_tracking_to_triage

Revision ID: 911eaf99501d
Revises: e2e7b4b0e858
Create Date: 2026-04-21 22:06:02.016722

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "911eaf99501d"
down_revision: Union[str, None] = "e2e7b4b0e858"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "triage_classifications",
        sa.Column("user_reacted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "triage_classifications",
        sa.Column("user_responded_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("triage_classifications", "user_responded_at")
    op.drop_column("triage_classifications", "user_reacted_at")
