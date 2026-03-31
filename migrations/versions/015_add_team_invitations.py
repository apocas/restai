from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'team_invitations',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False, index=True),
            sa.Column('username', sa.String(255), nullable=False, index=True),
            sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating team_invitations: {e}")

def downgrade():
    try:
        op.drop_table('team_invitations')
    except Exception as e:
        print(f"Error dropping team_invitations: {e}")
