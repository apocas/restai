"""Rename routine_execution_log.manual → is_manual (MySQL 8.4 reserved word).

MySQL 8.4 promoted ``MANUAL`` to a reserved keyword; SQLAlchemy's
reserved-word list lags behind so the unquoted column name fails to
parse on fresh installs against MySQL 8.4 (``CREATE TABLE`` errors with
"You have an error in your SQL syntax […] near 'manual BOOL NOT NULL'").

Migration 045 has been corrected to use ``is_manual`` for fresh installs.
This heal-forward handles two pre-existing states that may need fixing:

1. The table EXISTS with the old ``manual`` column → rename it.
2. The table does NOT exist (because the old 045 silently advanced
   alembic_version on installs where its broken SQL was caught) →
   create it now with the right shape.

Healthy installs (created with the fixed 045 → ``is_manual`` already
present) → this migration is a no-op.
"""
import sqlalchemy as sa
from alembic import op


revision = '048'
down_revision = '047'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('routine_execution_log'):
        # Case 2: table never got created — rebuild from scratch with the
        # correct column name.
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
        return

    cols = {c['name'] for c in inspector.get_columns('routine_execution_log')}
    if 'is_manual' in cols:
        # Already correct (likely the fresh-install path of fixed 045).
        return
    if 'manual' not in cols:
        # Neither column present — schema is in an unexpected state; add
        # the column rather than guessing what to rename.
        with op.batch_alter_table('routine_execution_log') as batch:
            batch.add_column(sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='0'))
        return
    # Case 1: rename. `batch_alter_table` gives SQLite a copy-rebuild while
    # MySQL/Postgres get the native ALTER TABLE … CHANGE / RENAME COLUMN.
    with op.batch_alter_table('routine_execution_log') as batch:
        batch.alter_column(
            'manual',
            new_column_name='is_manual',
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default='0',
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('routine_execution_log'):
        return
    cols = {c['name'] for c in inspector.get_columns('routine_execution_log')}
    if 'is_manual' not in cols or 'manual' in cols:
        return
    with op.batch_alter_table('routine_execution_log') as batch:
        batch.alter_column(
            'is_manual',
            new_column_name='manual',
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default='0',
        )
