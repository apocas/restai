"""Add ON DELETE CASCADE / SET NULL to every FK pointing at projects.id.

`output` keeps history (SET NULL); everything else CASCADEs with the
parent. MySQL/Postgres look up the live constraint name from
information_schema, then DROP + ADD. SQLite is a no-op (model-level
`ondelete` already covers fresh installs; legacy SQLite relies on the
app-side fallback in `delete_project`). Idempotent: skips when the
current rule already matches.
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
        target = rule.upper()
        if current == target:
            continue
        op.execute(sa.text(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`"))
        op.execute(sa.text(
            f"ALTER TABLE `{table}` "
            f"ADD CONSTRAINT `{name}` FOREIGN KEY (`{column}`) "
            f"REFERENCES `projects`(`id`) ON DELETE {rule}"
        ))


def _postgres_apply(bind, table: str, column: str, rule: str):
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
    # SQLite can't reflect unnamed FKs reliably; legacy installs lean on
    # the app-side fallback in database.delete_project. Fresh installs
    # pick up the model-level ondelete from Base.metadata.create_all().
    return


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    for table, column, rule in _FKS:
        if not inspector.has_table(table):
            continue
        if dialect == "mysql":
            _mysql_apply(bind, table, column, rule)
        elif dialect == "postgresql":
            _postgres_apply(bind, table, column, rule)
        else:
            _sqlite_apply(table, column, rule)


def downgrade():
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
