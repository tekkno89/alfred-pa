"""add user_repos table

Revision ID: 032
Revises: 031
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_repos",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("alias", sa.String(100), nullable=True),
        sa.Column("github_account_label", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "owner", "repo_name", name="uq_user_repos_user_owner_repo"),
    )
    op.create_index("ix_user_repos_user_repo_name", "user_repos", ["user_id", "repo_name"])
    op.create_index("ix_user_repos_user_alias", "user_repos", ["user_id", "alias"])


def downgrade() -> None:
    op.drop_index("ix_user_repos_user_alias")
    op.drop_index("ix_user_repos_user_repo_name")
    op.drop_table("user_repos")
