"""Add project_routines table for scheduled messages."""
import sqlalchemy as sa
from alembic import op


revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'project_routines',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('schedule_minutes', sa.Integer(), nullable=False, server_default='60'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('last_run', sa.DateTime(), nullable=True),
            sa.Column('last_result', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating project_routines table: {e}")


def downgrade():
    try:
        op.drop_table('project_routines')
    except Exception as e:
        print(f"Error dropping project_routines table: {e}")
