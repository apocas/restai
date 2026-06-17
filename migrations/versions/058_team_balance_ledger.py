"""Team balance ledger — a transaction log of every prepaid-wallet movement.

`teams.balance` (migration 057) is a single float with no history, so a team
admin can't see where the money went or when it was topped up. This adds an
authoritative ledger: one row per applied movement, storing the signed `amount`
(negative = usage debit OUT, positive = top-up IN) and the resulting
`balance_after` — so the running balance always reconciles with `teams.balance`,
even across clamp-at-0 overspend.

Portable across SQLite / MySQL / PostgreSQL: a brand-new table, so the FKs are
INLINE in CREATE TABLE (only *adding* an FK column to an existing table is the
SQLite landmine). No `server_default` on the TEXT `description` (MySQL rule);
`created_at` is always set app-side. Guarded with has_table for idempotency.
"""
import sqlalchemy as sa
from alembic import op


revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("team_balance_transactions"):
        op.create_table(
            "team_balance_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("balance_after", sa.Float(), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_team_balance_tx_team_id", "team_balance_transactions", ["team_id"])
        op.create_index("ix_team_balance_tx_created_at", "team_balance_transactions", ["created_at"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("team_balance_transactions"):
        op.drop_table("team_balance_transactions")
