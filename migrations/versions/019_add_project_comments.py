from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'project_comments',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, index=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating project_comments: {e}")

def downgrade():
    try:
        op.drop_table('project_comments')
    except Exception as e:
        print(f"Error dropping project_comments: {e}")
