"""Add system_prompt and context columns to output table."""
import sqlalchemy as sa
from alembic import op


revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('output', sa.Column('system_prompt', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Column system_prompt may already exist: {e}")

    try:
        op.add_column('output', sa.Column('context', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Column context may already exist: {e}")


def downgrade():
    try:
        op.drop_column('output', 'context')
    except Exception as e:
        print(f"Error dropping context column: {e}")

    try:
        op.drop_column('output', 'system_prompt')
    except Exception as e:
        print(f"Error dropping system_prompt column: {e}")
