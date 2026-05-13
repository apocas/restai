"""Add ``options`` JSON blob column to teams.

Mirrors ``projects.options``: a per-team generic settings bag. The first
consumer is SMTP overrides (`smtp_host`, `smtp_port`, `smtp_user`,
`smtp_password`, `smtp_from`, `email_default_to`) so a team can supply
its own mail relay; empty fields fall back to the platform-level
settings (see `restai.utils.email.send_email`).

NOT NULL with a Python-side default of ``"{}"``. We do NOT set a
``server_default`` because CLAUDE.md flags that as a MySQL pre-8.0.13
landmine on TEXT columns. Existing rows are backfilled by an explicit
UPDATE after the ADD COLUMN so the NOT NULL constraint is satisfiable
on every backend.

Idempotent: re-runs are no-ops because we gate on ``has_column()``.
This matters because migrations 035-038 silently advanced
``alembic_version`` on MySQL — we have to assume any structural op may
need to re-execute on previously-stamped DBs.
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
        # Pre-teams installs shouldn't exist this late in the migration
        # chain, but guard anyway so the migration is safe on truly
        # empty DBs.
        return

    # Two-step on every backend so MySQL pre-8.0.13 doesn't choke on a
    # TEXT server_default: (1) add NULLABLE, (2) backfill, (3) tighten
    # to NOT NULL. `op.batch_alter_table` gives SQLite a copy-rebuild
    # while MySQL/Postgres get native ALTER TABLE.
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
