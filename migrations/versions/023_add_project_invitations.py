from alembic import op
import sqlalchemy as sa

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'project_invitations',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('username', sa.String(255), nullable=False, index=True),
            sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating project_invitations: {e}")

def downgrade():
    try:
        op.drop_table('project_invitations')
    except Exception as e:
        print(f"Error dropping project_invitations: {e}")
