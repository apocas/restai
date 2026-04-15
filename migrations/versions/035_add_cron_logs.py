"""Add cron_logs table for DB-based cron job logging."""
import sqlalchemy as sa
from alembic import op


revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'cron_logs',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('job', sa.String(100), nullable=False, index=True),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('message', sa.Text(), nullable=False, server_default=''),
            sa.Column('details', sa.Text(), nullable=True),
            sa.Column('items_processed', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('date', sa.DateTime(), nullable=False, index=True),
        )
    except Exception as e:
        print(f"Error creating cron_logs table: {e}")


def downgrade():
    try:
        op.drop_table('cron_logs')
    except Exception as e:
        print(f"Error dropping cron_logs table: {e}")
