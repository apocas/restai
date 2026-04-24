"""Password-age tracking for stale-credential warnings.

Adds `users.password_updated_at` (nullable DateTime). Set on every
password write (create_user / update_user). The login endpoint compares
this against the optional `password_max_age_days` setting and surfaces a
soft warning when exceeded — passwords stay valid (no forced rotation),
but the admin gets a nudge to rotate.

Existing rows are left with NULL: there's no honest way to backfill the
age of a password we never tracked, and assuming "old" or "today" both
have failure modes (forces unnecessary churn vs. silently ignores
genuinely stale creds). NULL means "unknown — don't warn", which is the
right default until each user next changes their password.
"""
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
        # Column already present — re-running on a partially-migrated DB
        # is harmless. Postgres + MySQL both raise on duplicate columns;
        # SQLite varies by version.
        pass


def downgrade():
    try:
        op.drop_column('users', 'password_updated_at')
    except Exception:
        pass
