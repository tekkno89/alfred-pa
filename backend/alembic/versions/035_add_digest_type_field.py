"""add digest_type field

Revision ID: 035
Revises: b6f791ab3552
Create Date: 2026-04-12

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "035"
down_revision = "b6f791ab3552"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add digest_type field to distinguish focus session vs scheduled digests
    op.add_column(
        "triage_classifications", sa.Column("digest_type", sa.String(20), nullable=True)
    )

    # Create index for efficient filtering
    op.create_index(
        "ix_triage_classifications_digest_type",
        "triage_classifications",
        ["digest_type"],
        postgresql_where=sa.text("digest_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_triage_classifications_digest_type", table_name="triage_classifications"
    )
    op.drop_column("triage_classifications", "digest_type")
