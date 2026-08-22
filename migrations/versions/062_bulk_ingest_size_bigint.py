"""Widen `bulk_ingest_jobs.size_bytes` to 64-bit.

`size_bytes` was a 32-bit INTEGER, which caps at 2,147,483,647 (~2 GB). Now
that the per-file upload ceiling is an admin setting with no hard maximum, a
large staged file would overflow the column on MySQL/Postgres (SQLite is
dynamically typed and would have stored it fine, which is exactly how this
would have reached production unnoticed).

Portable across SQLite / MySQL / Postgres: `batch_alter_table` gives SQLite a
copy-rebuild while the others get a native ALTER. Guarded by schema inspection
rather than a broad try/except, per the migration rules in CLAUDE.md.
"""
import sqlalchemy as sa
from alembic import op


revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if "bulk_ingest_jobs" not in inspector.get_table_names():
        return False
    return any(c["name"] == "size_bytes" for c in inspector.get_columns("bulk_ingest_jobs"))


def upgrade():
    if not _has_column():
        return
    with op.batch_alter_table("bulk_ingest_jobs") as batch:
        batch.alter_column(
            "size_bytes",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            existing_server_default=sa.text("'0'"),
        )


def downgrade():
    if not _has_column():
        return
    with op.batch_alter_table("bulk_ingest_jobs") as batch:
        batch.alter_column(
            "size_bytes",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
            existing_server_default=sa.text("'0'"),
        )
