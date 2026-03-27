from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'prompt_versions',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('system_prompt', sa.Text(), nullable=False),
            sa.Column('description', sa.String(500), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('is_active', sa.Boolean(), default=False),
        )
    except Exception as e:
        print(f"Error creating prompt_versions: {e}")

    try:
        op.add_column('eval_runs', sa.Column('prompt_version_id', sa.Integer(), nullable=True))
    except Exception as e:
        print(f"Error adding prompt_version_id: {e}")

def downgrade():
    try:
        op.drop_column('eval_runs', 'prompt_version_id')
    except Exception as e:
        print(f"Error dropping prompt_version_id: {e}")
    try:
        op.drop_table('prompt_versions')
    except Exception as e:
        print(f"Error dropping prompt_versions: {e}")
