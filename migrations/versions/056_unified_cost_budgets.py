"""Unified cost-budget model.

Three additive, back-compat schema changes that underpin one coherent cost-budget
model enforced at four scopes (team, user-in-team, project, api-key):

1. `output.api_key_id` — attribute each inference row to the authenticating API
   key, so per-key cost can be aggregated (and analytics attributed). NULL for
   cookie/basic auth and all historical rows.
2. `team_user_budgets` — per-(user, team) monthly cost cap. A user may belong to
   multiple teams, so the cap is per membership. `budget` -1 = uncapped.
3. `api_keys.cost_budget_monthly` — per-key monthly COST cap (currency), distinct
   from the existing token quota. NULL = uncapped.

Portable across SQLite / MySQL / PostgreSQL, following migration 055: plain
nullable ADD COLUMN everywhere; index always; FK only on backends that support
ALTER ADD CONSTRAINT (SQLite gets the FK from create_all on fresh installs); the
downgrade drops the FK first then the column via batch so SQLite copy-rebuilds.
"""
import sqlalchemy as sa
from alembic import op


revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None

_FK_OUTPUT_KEY = "fk_output_api_key_id"
_IX_OUTPUT_KEY = "ix_output_api_key_id"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. output.api_key_id
    out_cols = {c["name"] for c in insp.get_columns("output")}
    if "api_key_id" not in out_cols:
        op.add_column("output", sa.Column("api_key_id", sa.Integer(), nullable=True))
        op.create_index(_IX_OUTPUT_KEY, "output", ["api_key_id"])
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(_FK_OUTPUT_KEY, "output", "api_keys", ["api_key_id"], ["id"])

    # 2. team_user_budgets
    if not insp.has_table("team_user_budgets"):
        op.create_table(
            "team_user_budgets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("budget", sa.Float(), nullable=False, server_default="-1.0"),
            sa.UniqueConstraint("team_id", "user_id", name="uq_team_user_budget"),
        )
        op.create_index("ix_team_user_budgets_team_id", "team_user_budgets", ["team_id"])
        op.create_index("ix_team_user_budgets_user_id", "team_user_budgets", ["user_id"])

    # 3. api_keys.cost_budget_monthly
    key_cols = {c["name"] for c in insp.get_columns("api_keys")}
    if "cost_budget_monthly" not in key_cols:
        op.add_column("api_keys", sa.Column("cost_budget_monthly", sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    key_cols = {c["name"] for c in insp.get_columns("api_keys")}
    if "cost_budget_monthly" in key_cols:
        with op.batch_alter_table("api_keys") as batch:
            batch.drop_column("cost_budget_monthly")

    if insp.has_table("team_user_budgets"):
        op.drop_table("team_user_budgets")

    out_cols = {c["name"] for c in insp.get_columns("output")}
    if "api_key_id" in out_cols:
        if bind.dialect.name != "sqlite":
            try:
                op.drop_constraint(_FK_OUTPUT_KEY, "output", type_="foreignkey")
            except Exception:
                pass
        with op.batch_alter_table("output") as batch:
            try:
                batch.drop_index(_IX_OUTPUT_KEY)
            except Exception:
                pass
            batch.drop_column("api_key_id")
