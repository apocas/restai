"""Re-embed a RAG project's knowledge base into a new embeddings model.

Changing `projects.embeddings` used to leave the vector store full of vectors
computed by the OLD model — an opaque 500 when the dimension changed, and
silently meaningless similarity scores when it didn't. The source files are
deleted after ingest, so there was no way back. `reembed_jobs` drives a
snapshot → reset → rebuild migration that re-embeds the chunk text already
held in the vector store.

Three changes:
- `reembed_jobs` — the job queue, drained by `crons/reembed.py`.
- `projects.embeddings_indexed` — which model the store's vectors were
  ACTUALLY built with, as opposed to the one the project asks for. NULL means
  "never stamped" (every pre-upgrade project) and must be read as unknown, not
  stale, so upgrading doesn't mass-flag the installed base.
- `embeddings.input_cost` — per-1M-token rate. Embedding models carried no
  pricing at all, so re-embedding could not be billed. Defaults to 0.0 so
  existing installs migrate for free until an admin sets a rate.

Portable across SQLite / MySQL / Postgres: creates are gated on schema
inspection rather than a broad try/except (the pattern that let 035-039
silently advance `alembic_version` on MySQL), column adds go through
`batch_alter_table`, and no TEXT column carries a `server_default`.
"""
import sqlalchemy as sa
from alembic import op


revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if not inspector.has_table(table):
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade():
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("reembed_jobs"):
        op.create_table(
            "reembed_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("from_embeddings", sa.String(255), nullable=True),
            sa.Column("to_embeddings", sa.String(255), nullable=False),
            # queued / processing / done / error — same vocabulary as bulk_ingest_jobs.
            sa.Column("status", sa.String(16), nullable=False, server_default="queued", index=True),
            # snapshotting / resetting / rebuilding. Meaningful only while
            # `processing`; this is what a resumed job keys off, because
            # re-running the reset would wipe rows already rebuilt.
            sa.Column("phase", sa.String(16), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("snapshot_path", sa.String(1024), nullable=True),
            sa.Column("chunks_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunks_done", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tokens_embedded", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    # Plain `add_column`, NOT `batch_alter_table`: adding a column is portable
    # everywhere, whereas batch mode makes SQLite do a full DROP/CREATE/RENAME
    # rebuild — and `projects` is the most FK-referenced table in the schema,
    # so that is real risk for no benefit. `batch_alter_table` is for the ops
    # SQLite genuinely cannot do natively (DROP/ALTER COLUMN), which is why the
    # downgrade below uses it and this does not. Same precedent as
    # `061_output_run_metadata.py:39-44`.
    if inspector.has_table("projects") and not _has_column(inspector, "projects", "embeddings_indexed"):
        op.add_column("projects", sa.Column("embeddings_indexed", sa.String(255), nullable=True))

    if inspector.has_table("embeddings") and not _has_column(inspector, "embeddings", "input_cost"):
        op.add_column("embeddings", sa.Column("input_cost", sa.Float(), nullable=True, server_default="0"))


def downgrade():
    inspector = sa.inspect(op.get_bind())

    if _has_column(inspector, "embeddings", "input_cost"):
        with op.batch_alter_table("embeddings") as batch:
            batch.drop_column("input_cost")

    if _has_column(inspector, "projects", "embeddings_indexed"):
        with op.batch_alter_table("projects") as batch:
            batch.drop_column("embeddings_indexed")

    if inspector.has_table("reembed_jobs"):
        op.drop_table("reembed_jobs")
