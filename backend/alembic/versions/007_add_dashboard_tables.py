"""Add dashboard tables: role column, user_dashboard_preferences, user_feature_access.

Revision ID: 007_add_dashboard_tables
Revises: 006_add_session_starred
Create Date: 2026-02-21

"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = "007_add_dashboard_tables"
down_revision: str | None = "006_add_session_starred"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add role column to users table
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="user",
        ),
    )

    # Create user_dashboard_preferences table
    op.create_table(
        "user_dashboard_preferences",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("card_type", sa.String(50), nullable=False),
        sa.Column("preferences", JSON, nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "card_type", name="uq_user_dashboard_preferences_user_card"),
    )

    # Create user_feature_access table
    op.create_table(
        "user_feature_access",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("feature_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("granted_by", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "feature_key", name="uq_user_feature_access_user_feature"),
    )

    # Bootstrap: set admin role for ADMIN_EMAIL if provided
    admin_email = os.environ.get("ADMIN_EMAIL")
    if admin_email:
        op.execute(
            sa.text("UPDATE users SET role = 'admin' WHERE email = :email").bindparams(
                email=admin_email
            )
        )


def downgrade() -> None:
    op.drop_table("user_feature_access")
    op.drop_table("user_dashboard_preferences")
    op.drop_column("users", "role")
