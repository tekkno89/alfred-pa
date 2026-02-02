"""Change embedding vector dimension from 1536 to 768 for bge-base-en-v1.5

Revision ID: 002_memory_vector_768
Revises: 001_initial_schema
Create Date: 2024-02-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "002_memory_vector_768"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old embedding column and recreate with new dimension
    # Note: This will lose any existing embeddings - acceptable since we're changing models
    op.drop_column("memories", "embedding")
    op.add_column(
        "memories",
        sa.Column("embedding", Vector(768), nullable=True),
    )


def downgrade() -> None:
    # Revert to 1536 dimensions
    op.drop_column("memories", "embedding")
    op.add_column(
        "memories",
        sa.Column("embedding", Vector(1536), nullable=True),
    )
