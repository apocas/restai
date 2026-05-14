"""Add ``options`` JSON blob column to teams.

NOT NULL with Python-side default — server_default on TEXT breaks
MySQL pre-8.0.13. Backfilled via UPDATE before the NOT NULL tighten.
Idempotent (has_column() guard) for re-runs after past silent failures.
"""
import sqlalchemy as sa
from alembic import op


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def _has_options_column() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("teams"):
        return False
    return any(c["name"] == "options" for c in inspector.get_columns("teams"))


def upgrade():
    if _has_options_column():
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("teams"):
        return

    # Add nullable → backfill → tighten to NOT NULL (avoids TEXT
    # server_default on MySQL pre-8.0.13).
    with op.batch_alter_table("teams") as batch:
        batch.add_column(sa.Column("options", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE teams SET options = '{}' WHERE options IS NULL"))
    with op.batch_alter_table("teams") as batch:
        batch.alter_column("options", existing_type=sa.Text(), nullable=False)


def downgrade():
    if not _has_options_column():
        return
    with op.batch_alter_table("teams") as batch:
        batch.drop_column("options")
