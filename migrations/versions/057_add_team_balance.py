"""Add teams.balance — the prepaid wallet (hard stop) alongside the soft budget.

`balance` is a real-money wallet, distinct from `budget` (the soft monthly cap):
decremented as cost is spent, and when it hits 0 all team usage hard-stops.
NULL = no wallet / disabled, so existing teams are unaffected (back-compat).

Portable across SQLite / MySQL / PostgreSQL: a plain nullable Float column needs
no FK / index / server_default. Downgrade drops it via batch so SQLite gets a
copy-rebuild instead of an unsupported DROP COLUMN.
"""
import sqlalchemy as sa
from alembic import op


revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("teams")}
    if "balance" not in cols:
        op.add_column("teams", sa.Column("balance", sa.Float(), nullable=True))


def downgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("teams")}
    if "balance" in cols:
        with op.batch_alter_table("teams") as batch:
            batch.drop_column("balance")
