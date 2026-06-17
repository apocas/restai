"""Payment system — Stripe/PayPal top-ups of the team prepaid wallet.

Two new tables:

- `payment_transactions`: one row per real-money payment toward a team wallet.
  Audit trail + idempotency — `(provider, provider_ref)` is unique, and crediting
  only fires on the atomic pending->completed claim, so a webhook + a return-page
  finalize for the same payment can never double-credit.
- `team_payment_config`: per-team saved payment method (for auto-recharge) + the
  auto-recharge rule (threshold/amount). One row per team.

Portable across SQLite / MySQL / PostgreSQL: brand-new tables, so FKs are INLINE in
CREATE TABLE (the SQLite landmine is only *adding* an FK column to an existing
table). No `server_default` on TEXT (MySQL rule). Guarded with has_table.
"""
import sqlalchemy as sa
from alembic import op


revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("payment_transactions"):
        op.create_table(
            "payment_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("provider_ref", sa.String(255), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("balance_transaction_id", sa.Integer(), sa.ForeignKey("team_balance_transactions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("provider", "provider_ref", name="uq_payment_provider_ref"),
        )
        op.create_index("ix_payment_tx_team_id", "payment_transactions", ["team_id"])
        op.create_index("ix_payment_tx_team_status", "payment_transactions", ["team_id", "status"])
        op.create_index("ix_payment_tx_created_at", "payment_transactions", ["created_at"])

    if not insp.has_table("team_payment_config"):
        op.create_table(
            "team_payment_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(32), nullable=True),
            sa.Column("customer_ref", sa.String(255), nullable=True),
            sa.Column("method_ref", sa.String(255), nullable=True),
            sa.Column("brand", sa.String(32), nullable=True),
            sa.Column("last4", sa.String(8), nullable=True),
            sa.Column("auto_recharge_enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("auto_recharge_threshold", sa.Float(), nullable=True),
            sa.Column("auto_recharge_amount", sa.Float(), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("team_id", name="uq_team_payment_config_team"),
        )
        op.create_index("ix_team_payment_config_team_id", "team_payment_config", ["team_id"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("team_payment_config"):
        op.drop_table("team_payment_config")
    if insp.has_table("payment_transactions"):
        op.drop_table("payment_transactions")
