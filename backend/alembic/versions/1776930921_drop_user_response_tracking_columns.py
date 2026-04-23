"""drop_user_response_tracking_columns

Revision ID: drop_response_tracking
Revises: 911eaf99501d
Create Date: 2026-04-23

Response tracking is now done at digest-time via Slack API using user tokens,
not via event-driven updates to these columns.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "drop_response_tracking"
down_revision: Union[str, None] = "911eaf99501d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("triage_classifications", "user_responded_at")
    op.drop_column("triage_classifications", "user_reacted_at")


def downgrade() -> None:
    op.add_column(
        "triage_classifications",
        sa.Column("user_reacted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "triage_classifications",
        sa.Column("user_responded_at", sa.DateTime(), nullable=True),
    )
