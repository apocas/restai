"""Add users.password_updated_at for stale-credential warnings (NULL = unknown, never warn)."""
import sqlalchemy as sa
from alembic import op


revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('users', sa.Column('password_updated_at', sa.DateTime(), nullable=True))
    except Exception:
        # Tolerate duplicate column on re-run; Postgres/MySQL raise, SQLite varies.
        pass


def downgrade():
    try:
        op.drop_column('users', 'password_updated_at')
    except Exception:
        pass
