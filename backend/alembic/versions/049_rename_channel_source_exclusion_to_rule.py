"""rename channel source exclusion to rule

Revision ID: 049
Revises: 048
"""

from alembic import op
import sqlalchemy as sa

revision = '049'
down_revision = '048'
depends_on = None


def upgrade() -> None:
    # Rename table
    op.rename_table('channel_source_exclusions', 'channel_source_rules')
    
    # Rename primary key constraint
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT pk_channel_source_exclusions TO pk_channel_source_rules"
    )
    
    # Rename unique constraint
    op.drop_constraint('uq_channel_source_exclusion_entity', 'channel_source_rules', type_='unique')
    op.create_unique_constraint('uq_channel_source_rule_entity', 'channel_source_rules', ['monitored_channel_id', 'slack_entity_id'])
    
    # Rename index
    op.drop_index('ix_channel_source_exclusions_channel_id', table_name='channel_source_rules')
    op.create_index('ix_channel_source_rules_channel_id', 'channel_source_rules', ['channel_id'])
    
    # Rename foreign key constraints
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT fk_channel_source_exclusions_monitored_channel_id_monit_e251 "
        "TO fk_channel_source_rules_monitored_channel_id"
    )
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT fk_channel_source_exclusions_user_id_users "
        "TO fk_channel_source_rules_user_id"
    )
    
    # Migrate action values: exclude → ignore, include → notify_now
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE channel_source_rules SET action = "
            "CASE WHEN action = 'exclude' THEN 'ignore' "
            "WHEN action = 'include' THEN 'notify_now' "
            "ELSE action END"
        )
    )


def downgrade() -> None:
    # Reverse action values
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE channel_source_rules SET action = "
            "CASE WHEN action = 'ignore' THEN 'exclude' "
            "WHEN action = 'notify_now' THEN 'include' "
            "ELSE action END"
        )
    )
    
    # Rename index back
    op.drop_index('ix_channel_source_rules_channel_id', table_name='channel_source_rules')
    op.create_index('ix_channel_source_exclusions_channel_id', 'channel_source_rules', ['channel_id'])
    
    # Rename unique constraint back
    op.drop_constraint('uq_channel_source_rule_entity', 'channel_source_rules', type_='unique')
    op.create_unique_constraint('uq_channel_source_exclusion_entity', 'channel_source_rules', ['monitored_channel_id', 'slack_entity_id'])
    
    # Rename foreign key constraints back
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT fk_channel_source_rules_monitored_channel_id "
        "TO fk_channel_source_exclusions_monitored_channel_id_monit_e251"
    )
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT fk_channel_source_rules_user_id "
        "TO fk_channel_source_exclusions_user_id_users"
    )
    
    # Rename primary key constraint back
    op.execute(
        "ALTER TABLE channel_source_rules "
        "RENAME CONSTRAINT pk_channel_source_rules TO pk_channel_source_exclusions"
    )
    
    # Rename table back
    op.rename_table('channel_source_rules', 'channel_source_exclusions')
