from alembic import op
import sqlalchemy as sa

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.drop_column('projects', 'sync_lock')
    except Exception as e:
        print(f"Error dropping sync_lock: {e}")

def downgrade():
    try:
        op.add_column('projects', sa.Column('sync_lock', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Error adding sync_lock: {e}")
