"""Add context_secret column to widgets table for signed context injection."""
import sqlalchemy as sa
from alembic import op


revision = '030'
down_revision = '029'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('widgets', sa.Column('context_secret', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Error adding context_secret column: {e}")


def downgrade():
    try:
        op.drop_column('widgets', 'context_secret')
    except Exception as e:
        print(f"Error dropping context_secret column: {e}")
