"""Add agent run-outcome metadata to `output`.

Four nullable columns persisted by `log_inference` for every inference row
(NULL for non-agent rows and history):

- stop_reason: how the run ended ("max_turns", "max_time", "error";
  NULL = completed normally)
- retries: transient provider retries performed during the run
- fallbacks: fallback-LLM switches during the run
- token_accuracy: provenance of the token counts ("high"/"medium"/"low")

Portable across SQLite / MySQL / Postgres: plain nullable ADD COLUMN, no
server_default, no TEXT defaults. Idempotency via schema inspection (NOT a
broad try/except — see CLAUDE.md migration rules), so a partially applied
run resumes cleanly.
"""
import sqlalchemy as sa
from alembic import op


revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("stop_reason", sa.String(32)),
    ("retries", sa.Integer()),
    ("fallbacks", sa.Integer()),
    ("token_accuracy", sa.String(16)),
]


def _existing_columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("output")}


def upgrade():
    existing = _existing_columns()
    for name, col_type in _COLUMNS:
        if name not in existing:
            op.add_column("output", sa.Column(name, col_type, nullable=True))


def downgrade():
    existing = _existing_columns()
    # batch_alter_table so SQLite gets a copy-rebuild while MySQL/Postgres
    # run native ALTERs (older SQLite rejects DROP COLUMN).
    to_drop = [name for name, _ in _COLUMNS if name in existing]
    if not to_drop:
        return
    with op.batch_alter_table("output") as batch:
        for name in to_drop:
            batch.drop_column(name)
