"""Add team_id to api_keys + backfill existing keys.

API keys now carry the team whose budget is billed for the key's
direct-access usage (`/direct`, `/image`, `/audio`, `/embeddings`). This
makes team attribution deterministic for users who belong to more than one
team — previously the direct-access path billed the *first* team that
granted model access, which is order-dependent.

The column is nullable at the DB level (pre-existing rows and the legacy
`users.api_key` fallback have none) but required for keys minted through
the API after this migration. Existing keys are backfilled to the owner's
team — the single team for single-team users, else the lowest-id team
(matching the prior first-granting-team default).

Portable across SQLite / MySQL / PostgreSQL:
- the column is added without an inline constraint (plain ADD COLUMN works
  on all three; SQLite can't ALTER-ADD a column carrying a FK constraint).
- the FK + index are created with `ALTER ADD` only on MySQL/Postgres; on
  SQLite the column stays plain (SQLite doesn't enforce FKs anyway, and a
  fresh install builds the FK from the model via create_all).
- the backfill uses a correlated scalar subquery with LIMIT, valid on all
  three backends.
- downgrade drops the FK first on MySQL/Postgres, then drops the column via
  batch so SQLite gets a copy-rebuild instead of an unsupported DROP COLUMN.
"""
import sqlalchemy as sa
from alembic import op


revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None

_FK_NAME = "fk_api_keys_team_id"
_IX_NAME = "ix_api_keys_team_id"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("api_keys")}
    if "team_id" not in cols:
        op.add_column("api_keys", sa.Column("team_id", sa.Integer(), nullable=True))
        op.create_index(_IX_NAME, "api_keys", ["team_id"])
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                _FK_NAME, "api_keys", "teams", ["team_id"], ["id"]
            )

    # Backfill: assign each key to its owner's team. teams_users mirrors the
    # member set used by get_teams_for_user; lowest team id = "first like before".
    op.execute(
        sa.text(
            """
            UPDATE api_keys SET team_id = (
                SELECT tu.team_id FROM teams_users tu
                WHERE tu.user_id = api_keys.user_id
                ORDER BY tu.team_id ASC LIMIT 1
            )
            WHERE team_id IS NULL
            """
        )
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        try:
            op.drop_constraint(_FK_NAME, "api_keys", type_="foreignkey")
        except Exception:
            pass
    with op.batch_alter_table("api_keys") as batch:
        try:
            batch.drop_index(_IX_NAME)
        except Exception:
            pass
        batch.drop_column("team_id")
