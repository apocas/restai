"""Add cron_logs table for DB-based cron job logging.

MySQL-safety notes:
- TEXT/BLOB columns must NOT carry a `server_default` — pre-8.0.13 MySQL
  rejects them outright (`ER_BLOB_CANT_HAVE_DEFAULT`). Defaults for those
  columns belong in the application layer (CronLogger always writes a
  value, so NOT NULL is enough).
- Earlier revisions of this file wrapped `create_table` in a broad
  try/except that printed the error and continued. That made alembic
  advance `alembic_version` even when the table was never created,
  silently breaking later migrations and runtime code. Don't reintroduce
  that pattern.
"""
import sqlalchemy as sa
from alembic import op


revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cron_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('job', sa.String(100), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('items_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=False, index=True),
    )


def downgrade():
    op.drop_table('cron_logs')
