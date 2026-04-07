"""add coding_jobs table

Revision ID: 594a750883d8
Revises: da7b92c29c9c
Create Date: 2026-04-04 05:59:21.342668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '594a750883d8'
down_revision: Union[str, None] = 'da7b92c29c9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('coding_jobs',
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('session_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('repo_full_name', sa.String(length=255), nullable=False),
    sa.Column('branch_name', sa.String(length=255), nullable=True),
    sa.Column('pr_url', sa.Text(), nullable=True),
    sa.Column('pr_number', sa.Integer(), nullable=True),
    sa.Column('task_description', sa.Text(), nullable=False),
    sa.Column('plan_content', sa.Text(), nullable=True),
    sa.Column('review_content', sa.Text(), nullable=True),
    sa.Column('revision_of_job_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('container_id', sa.String(length=100), nullable=True),
    sa.Column('error_details', sa.Text(), nullable=True),
    sa.Column('github_account_label', sa.String(length=100), nullable=True),
    sa.Column('conversation_log', sa.Text(), nullable=True),
    sa.Column('slack_channel_id', sa.String(length=100), nullable=True),
    sa.Column('slack_thread_ts', sa.String(length=50), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['revision_of_job_id'], ['coding_jobs.id'], name=op.f('fk_coding_jobs_revision_of_job_id_coding_jobs')),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_coding_jobs_session_id_sessions')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_coding_jobs_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coding_jobs'))
    )


def downgrade() -> None:
    op.drop_table('coding_jobs')
