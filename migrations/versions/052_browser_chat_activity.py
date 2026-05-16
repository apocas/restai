"""Track per-chat browser container activity in DB.

Mirror of 051 for the agentic-browser container. Same reason: the
`browser_cleanup` cron was evicting purely by container creation age
(`restai.created_at` label), which kills a busy browser session at
`browser_timeout` seconds regardless of whether the agent just made a
`browser_*` call. Heartbeat per `runtime.call()` lets the cron see
real idle time.

Separate table from `docker_chat_activity` so docker terminal and
browser containers in the same chat don't overwrite each other's
heartbeat (composite (chat_id, kind) would also work but means
breaking PK on MySQL — sibling table avoids that headache).
"""
import sqlalchemy as sa
from alembic import op


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("browser_chat_activity"):
        return
    op.create_table(
        "browser_chat_activity",
        sa.Column("chat_id", sa.String(255), primary_key=True),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_browser_chat_activity_last_activity",
        "browser_chat_activity",
        ["last_activity"],
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("browser_chat_activity"):
        return
    try:
        op.drop_index("ix_browser_chat_activity_last_activity", "browser_chat_activity")
    except Exception:
        pass
    op.drop_table("browser_chat_activity")
