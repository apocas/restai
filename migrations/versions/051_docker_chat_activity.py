"""Track per-chat Docker container activity in DB.

Multi-server safe replacement for the cron's prior label-based age
check. Each `DockerManager.exec_command` UPSERTs `last_activity`; the
cleanup cron reads from this table so eviction is driven by real
"time since last terminal exec", not container lifetime.

Single shared Docker daemon assumed (no `docker_host` column).
Idempotent: `has_table` guard for re-runs after past silent failures.
"""
import sqlalchemy as sa
from alembic import op


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("docker_chat_activity"):
        return
    op.create_table(
        "docker_chat_activity",
        sa.Column("chat_id", sa.String(255), primary_key=True),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_docker_chat_activity_last_activity",
        "docker_chat_activity",
        ["last_activity"],
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("docker_chat_activity"):
        return
    try:
        op.drop_index("ix_docker_chat_activity_last_activity", "docker_chat_activity")
    except Exception:
        pass
    op.drop_table("docker_chat_activity")
