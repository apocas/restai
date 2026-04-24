"""Per-fire execution log for project routines.

Keeps a historical row per routine fire so admins can debug flaky
routines beyond the single-string `last_result` on
``project_routines``. Populated by ``crons/routines.py`` on every run
and by the admin-triggered `/retry` endpoint.
"""
import sqlalchemy as sa
from alembic import op


revision = '045'
down_revision = '044'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'routine_execution_log',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('routine_id', sa.Integer(), sa.ForeignKey('project_routines.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('status', sa.String(16), nullable=False, server_default='ok'),
            sa.Column('result', sa.Text(), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('manual', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
        )
    except Exception:
        pass


def downgrade():
    try:
        op.drop_table('routine_execution_log')
    except Exception:
        pass
