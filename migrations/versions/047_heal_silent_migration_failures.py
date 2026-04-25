"""Self-heal deployments where migrations 035-039 silently failed.

Background:
- Migrations 035, 036, 038, 039 originally wrapped `op.create_table` in a
  broad try/except that printed the error and continued. On MySQL those
  `create_table` calls failed (TEXT columns can't carry a `server_default`,
  and 038 also used the unquoted reserved word `key` in a DELETE), but
  alembic still advanced `alembic_version` past them.
- Result: deployments running MySQL ended up at 046 with four tables
  missing (`cron_logs`, `project_memory_bank_entries`, `image_generators`,
  `speech_to_text`) and runtime errors every time those tables were
  queried.
- The four migrations are now fixed for fresh installs, but already-broken
  DBs won't re-run them. This migration inspects the live schema and
  creates only the tables that are actually missing.

Healthy installs (created with the fixed 035-039) → all four tables
already exist → this migration is a no-op.

Broken installs (stuck at 046 with missing tables) → exactly the missing
ones get created with the same shape the originals would have produced
(minus the MySQL-incompatible `server_default` on TEXT columns).
"""
import sqlalchemy as sa
from alembic import op


revision = '047'
down_revision = '046'
branch_labels = None
depends_on = None


def _ensure_cron_logs(inspector):
    if inspector.has_table('cron_logs'):
        return
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


def _ensure_project_memory_bank_entries(inspector):
    if inspector.has_table('project_memory_bank_entries'):
        return
    op.create_table(
        'project_memory_bank_entries',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('chat_id', sa.String(255), nullable=True, index=True),
        sa.Column('granularity', sa.String(20), nullable=False, index=True),
        sa.Column('period_key', sa.String(20), nullable=True, index=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_source_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def _ensure_image_generators(inspector):
    if inspector.has_table('image_generators'):
        return
    op.create_table(
        'image_generators',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('class_name', sa.String(64), nullable=False),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('privacy', sa.String(32), nullable=False, server_default='public'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def _ensure_speech_to_text(inspector):
    if inspector.has_table('speech_to_text'):
        return
    op.create_table(
        'speech_to_text',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('class_name', sa.String(64), nullable=False),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('privacy', sa.String(32), nullable=False, server_default='public'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def upgrade():
    inspector = sa.inspect(op.get_bind())
    _ensure_cron_logs(inspector)
    _ensure_project_memory_bank_entries(inspector)
    _ensure_image_generators(inspector)
    _ensure_speech_to_text(inspector)


def downgrade():
    # Pure heal-forward: dropping these on downgrade would also blow away
    # tables that legitimately belong to revisions 035/036/038/039. Leave
    # the originals' downgrades to do that work.
    pass
