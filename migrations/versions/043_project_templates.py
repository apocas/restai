"""Project template library — reusable project snapshots.

Adds the ``project_templates`` table that lets users publish a
project's config (system prompt + options + Blockly workspace) as a
clonable "starter pack" with three-tier visibility (private / team /
public). Decouples sharing from the live project so an admin can share
a "Customer Support Bot" template without making the underlying
project public.
"""
import sqlalchemy as sa
from alembic import op


revision = '043'
down_revision = '042'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'project_templates',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('name', sa.String(255), nullable=False, index=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('project_type', sa.String(20), nullable=False),
            sa.Column('suggested_llm', sa.String(255), nullable=True),
            sa.Column('suggested_embeddings', sa.String(255), nullable=True),
            sa.Column('system_prompt', sa.Text(), nullable=True),
            sa.Column('options_json', sa.Text(), nullable=True),
            sa.Column('blockly_workspace', sa.Text(), nullable=True),
            sa.Column('visibility', sa.String(20), nullable=False, server_default='private'),
            sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        )
    except Exception:
        # Already created on a partial re-run.
        pass


def downgrade():
    try:
        op.drop_table('project_templates')
    except Exception:
        pass
