from alembic import op
import sqlalchemy as sa

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('projects', sa.Column('sync_lock', sa.DateTime(), nullable=True))
    except Exception as e:
        print(f"Error adding sync_lock column: {e}")

def downgrade():
    try:
        op.drop_column('projects', 'sync_lock')
    except Exception as e:
        print(f"Error dropping sync_lock column: {e}")
