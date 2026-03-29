from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'guard_events',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('guard_project', sa.String(255), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('phase', sa.String(10), nullable=False),
            sa.Column('action', sa.String(10), nullable=False),
            sa.Column('mode', sa.String(10), nullable=False, server_default='block'),
            sa.Column('text_checked', sa.Text(), nullable=True),
            sa.Column('guard_response', sa.Text(), nullable=True),
            sa.Column('date', sa.DateTime(), nullable=False, index=True),
        )
    except Exception as e:
        print(f"Error creating guard_events: {e}")

def downgrade():
    try:
        op.drop_table('guard_events')
    except Exception as e:
        print(f"Error dropping guard_events: {e}")
