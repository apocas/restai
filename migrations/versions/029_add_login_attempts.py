"""Add login_attempts table for DB-backed rate limiting.

Replaces the in-memory login rate limiter so it works correctly across
multiple workers and survives process restarts.
"""
import sqlalchemy as sa
from alembic import op


revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'login_attempts',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('ip', sa.String(45), nullable=False, index=True),
            sa.Column('attempted_at', sa.DateTime(), nullable=False, index=True),
        )
    except Exception as e:
        print(f"Error creating login_attempts table: {e}")


def downgrade():
    try:
        op.drop_table('login_attempts')
    except Exception as e:
        print(f"Error dropping login_attempts table: {e}")
