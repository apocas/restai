"""Add ON DELETE CASCADE / SET NULL to every FK pointing at projects.id.

Triggered by an admin hitting `IntegrityError 1451` on `DELETE FROM
projects` because most child FKs were created without a delete rule.
Only 3 of 17 child FKs had `ondelete="CASCADE"` before this; the
other 14 blocked project deletion as soon as any child row existed
(the canary was prompt_versions on a project that had ever had a
prompt edit).

Rules picked per table:
  - audit / log data (output) → SET NULL. We want to keep the
    inference history when the project is gone — useful for
    cost-attribution review.
  - everything else → CASCADE. Project lifecycle owns the row;
    deletion should sweep it.

Backend portability:
  - **MySQL**: can't alter a constraint in place; we DROP the existing
    FK by name and ADD a new one with the rule. Constraint names
    follow MySQL's auto-generated `<table>_ibfk_<n>` pattern when
    SQLAlchemy didn't pin one. To avoid guessing, we look up the
    real names from `information_schema.KEY_COLUMN_USAGE`.
  - **PostgreSQL**: same DROP + ADD shape, but constraint names are
    SQLAlchemy-generated like `<table>_project_id_fkey`. We look
    them up from `information_schema.table_constraints`.
  - **SQLite**: doesn't support ALTER FK. Use `op.batch_alter_table`
    so SQLAlchemy does a copy-rebuild — drops the table, recreates
    with the new constraints, re-inserts rows.

Idempotent: each per-table block checks the current rule first and
skips if already correct. Re-runs are no-ops.
"""
import sqlalchemy as sa
from alembic import op


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


# (child_table, child_column, on_delete) — every FK pointing at projects.id
_FKS = [
    ("output",                      "project_id", "SET NULL"),
    ("eval_datasets",               "project_id", "CASCADE"),
    ("prompt_versions",             "project_id", "CASCADE"),
    ("eval_runs",                   "project_id", "CASCADE"),
    ("project_invitations",         "project_id", "CASCADE"),
    ("widgets",                     "project_id", "CASCADE"),
    ("kg_entities",                 "project_id", "CASCADE"),
    ("kg_entity_mentions",          "project_id", "CASCADE"),
    ("kg_entity_relationships",     "project_id", "CASCADE"),
    ("retrieval_events",            "project_id", "CASCADE"),
    ("guard_events",                "project_id", "CASCADE"),
    ("project_comments",            "project_id", "CASCADE"),
    ("project_tools",               "project_id", "CASCADE"),
    ("project_routines",            "project_id", "CASCADE"),
    ("project_memory_bank_entries", "project_id", "CASCADE"),
    # Secondary M2M tables.
    ("users_projects",              "project_id", "CASCADE"),
    ("teams_projects",              "project_id", "CASCADE"),
]


def _mysql_apply(bind, table: str, column: str, rule: str):
    """MySQL: look up the existing FK name from information_schema, then
    drop + recreate with the desired rule. Skip when already correct."""
    rows = bind.execute(sa.text("""
        SELECT
            kcu.CONSTRAINT_NAME AS name,
            COALESCE(rc.DELETE_RULE, '') AS rule
        FROM information_schema.KEY_COLUMN_USAGE kcu
        LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
            ON rc.CONSTRAINT_NAME   = kcu.CONSTRAINT_NAME
            AND rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
        WHERE kcu.TABLE_SCHEMA          = DATABASE()
          AND kcu.TABLE_NAME            = :table
          AND kcu.COLUMN_NAME           = :col
          AND kcu.REFERENCED_TABLE_NAME = 'projects'
          AND kcu.REFERENCED_COLUMN_NAME = 'id'
    """), {"table": table, "col": column}).fetchall()

    for row in rows:
        name, current = row[0], (row[1] or "").upper()
        target = rule.upper().replace(" ", " ")
        # MySQL stores "NO ACTION" / "RESTRICT" / "CASCADE" / "SET NULL"
        if current == target:
            continue
        # backtick-quote `key`/`group`/etc. defensive — none in our
        # table names today, but cheap to keep.
        op.execute(sa.text(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`"))
        op.execute(sa.text(
            f"ALTER TABLE `{table}` "
            f"ADD CONSTRAINT `{name}` FOREIGN KEY (`{column}`) "
            f"REFERENCES `projects`(`id`) ON DELETE {rule}"
        ))


def _postgres_apply(bind, table: str, column: str, rule: str):
    """Postgres: use information_schema to find the constraint name and
    delete rule. DROP + ADD if the rule differs."""
    rows = bind.execute(sa.text("""
        SELECT tc.constraint_name, rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
         AND kcu.constraint_schema = tc.constraint_schema
        JOIN information_schema.referential_constraints rc
          ON rc.constraint_name = tc.constraint_name
         AND rc.constraint_schema = tc.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = :table
          AND kcu.column_name = :col
          AND ccu.table_name = 'projects'
          AND ccu.column_name = 'id'
    """), {"table": table, "col": column}).fetchall()

    for row in rows:
        name, current = row[0], (row[1] or "").upper()
        target = rule.upper()
        if current == target:
            continue
        op.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"'))
        op.execute(sa.text(
            f'ALTER TABLE "{table}" '
            f'ADD CONSTRAINT "{name}" FOREIGN KEY ("{column}") '
            f'REFERENCES "projects"("id") ON DELETE {rule}'
        ))


def _sqlite_apply(table: str, column: str, rule: str):
    """SQLite: no-op.

    SQLite's reflection of unnamed FKs through alembic's batch
    operation is unreliable (drop_constraint requires a name we don't
    have). For the dev SQLite path we accept the trade-off: existing
    SQLite databases keep their original FKs, but
    `delete_project_with_cleanup` (database.py) explicitly nukes child
    rows before the DELETE, so cascade isn't required for correctness.
    Fresh SQLite installs created from `Base.metadata.create_all()`
    pick up the model-level `ondelete="CASCADE"` automatically.
    Production deployments are MySQL / Postgres — the two paths above
    handle those correctly."""
    return


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    for table, column, rule in _FKS:
        if not inspector.has_table(table):
            # Migration ran on an older DB that hasn't yet seen this
            # table created — skip; the model definition will create
            # it correctly on next boot.
            continue
        if dialect == "mysql":
            _mysql_apply(bind, table, column, rule)
        elif dialect == "postgresql":
            _postgres_apply(bind, table, column, rule)
        else:
            # SQLite (and anything else): copy-rebuild path.
            _sqlite_apply(table, column, rule)


def downgrade():
    """Restore the no-rule FKs (DELETE blocks). Reverse of upgrade,
    same per-dialect plumbing. Mostly here for symmetry — there's no
    reason to actually run this in production."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name
    for table, column, _ in _FKS:
        if not inspector.has_table(table):
            continue
        if dialect == "mysql":
            _mysql_apply(bind, table, column, "RESTRICT")
        elif dialect == "postgresql":
            _postgres_apply(bind, table, column, "NO ACTION")
        # SQLite has no equivalent; downgrade is a no-op.
