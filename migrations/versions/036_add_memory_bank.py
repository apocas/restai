"""Add project_memory_bank_entries table for the per-project shared memory bank."""
import sqlalchemy as sa
from alembic import op


revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'project_memory_bank_entries',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('chat_id', sa.String(255), nullable=True, index=True),
            sa.Column('granularity', sa.String(20), nullable=False, index=True),
            sa.Column('period_key', sa.String(20), nullable=True, index=True),
            sa.Column('summary', sa.Text(), nullable=False, server_default=''),
            sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('source_message_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_source_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating project_memory_bank_entries table: {e}")


def downgrade():
    try:
        op.drop_table('project_memory_bank_entries')
    except Exception as e:
        print(f"Error dropping project_memory_bank_entries table: {e}")
