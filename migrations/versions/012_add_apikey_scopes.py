from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('api_keys', sa.Column('allowed_projects', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Error adding allowed_projects: {e}")
    try:
        op.add_column('api_keys', sa.Column('read_only', sa.Boolean(), nullable=False, server_default='0'))
    except Exception as e:
        print(f"Error adding read_only: {e}")

def downgrade():
    try:
        op.drop_column('api_keys', 'allowed_projects')
    except Exception as e:
        print(f"Error dropping allowed_projects: {e}")
    try:
        op.drop_column('api_keys', 'read_only')
    except Exception as e:
        print(f"Error dropping read_only: {e}")
