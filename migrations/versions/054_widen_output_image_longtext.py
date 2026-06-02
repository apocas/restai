"""Widen output.image to LONGTEXT on MySQL.

A user-attached image is stored as a base64 data-URI in `output.image`.
MySQL `TEXT` caps at 64KB, but a single screenshot/scan data-URI already
runs ~140KB, so the inference-log INSERT fails with
`(1406, "Data too long for column 'image' at row 1")`. Postgres and SQLite
`TEXT` are unbounded, so this is a MySQL-only widening — gated by dialect
so the migration is a clean no-op on the other two backends (SQLite can't
ALTER COLUMN type anyway).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "output",
        "image",
        existing_type=mysql.TEXT(),
        type_=mysql.LONGTEXT(),
        existing_nullable=True,
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "output",
        "image",
        existing_type=mysql.LONGTEXT(),
        type_=mysql.TEXT(),
        existing_nullable=True,
    )
