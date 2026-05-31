"""Add is_suspended flag to users.

A suspended user cannot log in and their API keys stop working — enforced
centrally in restai/auth.py (both the JWT-cookie and Bearer-API-key resolution
paths) plus every login / SSO / LDAP token-mint path.
"""
import sqlalchemy as sa
from alembic import op


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("users")]
    if "is_suspended" in cols:
        return
    # server_default on a Boolean/INT is portable across SQLite/MySQL/Postgres
    # (the no-server_default rule only applies to TEXT/BLOB). Existing rows
    # default to not-suspended.
    op.add_column(
        "users",
        sa.Column("is_suspended", sa.Boolean(), server_default="0", nullable=True),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("users")]
    if "is_suspended" not in cols:
        return
    # batch_alter_table so SQLite gets a copy-rebuild while MySQL/Postgres
    # get a native ALTER (SQLite can't DROP COLUMN directly on old versions).
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_suspended")
