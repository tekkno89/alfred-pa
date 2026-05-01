"""add conversation_summaries table

Revision ID: 036
Revises: de9e5c6ca05a
Create Date: 2026-04-30

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "036"
down_revision = "de9e5c6ca05a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        
        sa.Column("conversation_type", sa.String(20), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("channel_name", sa.String(255), nullable=True),
        sa.Column("thread_ts", sa.String(50), nullable=True),
        
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("participants", JSONB, nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("priority_level", sa.String(20), nullable=False),
        
        sa.Column("first_message_ts", sa.String(50), nullable=False),
        sa.Column("slack_permalink", sa.Text(), nullable=True),
        
        sa.Column("digest_summary_id", sa.UUID(), sa.ForeignKey("triage_classifications.id"), nullable=True),
        
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_reacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    op.create_index("idx_cs_user_digest", "conversation_summaries", ["user_id", "digest_summary_id"])
    op.create_index("idx_cs_thread", "conversation_summaries", ["channel_id", "thread_ts"])
    op.create_index("idx_cs_user_created", "conversation_summaries", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_cs_digest_summary", "conversation_summaries", ["digest_summary_id"])
    
    op.add_column(
        "triage_classifications",
        sa.Column("conversation_summary_id", sa.UUID(), sa.ForeignKey("conversation_summaries.id"), nullable=True)
    )
    
    op.create_index(
        "idx_tc_conversation_summary_id",
        "triage_classifications",
        ["conversation_summary_id"],
        postgresql_where=sa.text("conversation_summary_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tc_conversation_summary_id", table_name="triage_classifications")
    op.drop_column("triage_classifications", "conversation_summary_id")
    
    op.drop_index("idx_cs_digest_summary", table_name="conversation_summaries")
    op.drop_index("idx_cs_user_created", table_name="conversation_summaries")
    op.drop_index("idx_cs_thread", table_name="conversation_summaries")
    op.drop_index("idx_cs_user_digest", table_name="conversation_summaries")
    
    op.drop_table("conversation_summaries")
