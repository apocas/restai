"""Agentic browser — project_secrets vault (per-project encrypted credentials)."""
import sqlalchemy as sa
from alembic import op


revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'project_secrets',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('value', sa.Text(), nullable=False),  # encrypted at rest
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('project_id', 'name', name='uq_project_secret_name'),
        )
    except Exception as e:
        print(f"Error creating project_secrets table: {e}")


def downgrade():
    try:
        op.drop_table('project_secrets')
    except Exception as e:
        print(f"Error dropping project_secrets table: {e}")
