"""Per-fire execution log for project routines.

Keeps a historical row per routine fire so admins can debug flaky
routines beyond the single-string `last_result` on
``project_routines``. Populated by ``crons/routines.py`` on every run
and by the admin-triggered `/retry` endpoint.

History notes:
- An earlier version named the boolean column ``manual``. MySQL 8.4
  promoted ``MANUAL`` to a reserved keyword (SQLAlchemy's reserved-word
  list lags behind, so the column wasn't auto-quoted) and ``CREATE TABLE``
  fails on those servers. The column is now ``is_manual``; migration
  048 renames any pre-existing ``manual`` column for installs that
  managed to create the table on older MySQL.
- The earlier version also used ``sa.false()`` (which renders as the
  literal keyword ``false``, rejected by some MySQL configurations as a
  DEFAULT for BOOL) and wrapped ``op.create_table`` in a broad
  ``try/except``. Both anti-patterns are removed.
"""
import sqlalchemy as sa
from alembic import op


revision = '045'
down_revision = '044'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('routine_execution_log'):
        return
    op.create_table(
        'routine_execution_log',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('routine_id', sa.Integer(), sa.ForeignKey('project_routines.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='ok'),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
    )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('routine_execution_log'):
        op.drop_table('routine_execution_log')
