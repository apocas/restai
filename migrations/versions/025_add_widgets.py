from alembic import op
import sqlalchemy as sa

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'widgets',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('creator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('key_hash', sa.String(64), nullable=False, unique=True, index=True),
            sa.Column('encrypted_key', sa.String(4096), nullable=False),
            sa.Column('key_prefix', sa.String(12), nullable=False),
            sa.Column('name', sa.String(255), nullable=False, server_default='Chat Widget'),
            sa.Column('config', sa.Text(), nullable=False),
            sa.Column('allowed_domains', sa.Text(), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
    except Exception as e:
        print(f"Error creating widgets table: {e}")

def downgrade():
    try:
        op.drop_table('widgets')
    except Exception as e:
        print(f"Error dropping widgets table: {e}")
