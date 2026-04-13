"""Add project_tools table for agent-created tools."""
import sqlalchemy as sa
from alembic import op


revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'project_tools',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('parameters', sa.Text(), nullable=False),
            sa.Column('code', sa.Text(), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating project_tools table: {e}")


def downgrade():
    try:
        op.drop_table('project_tools')
    except Exception as e:
        print(f"Error dropping project_tools table: {e}")
