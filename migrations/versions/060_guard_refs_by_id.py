"""Convert guard references from project NAME to project ID.

`projects.guard` (input guard) and the `guard_output` key inside `projects.options`
(output guard) historically stored the guard project's *name*, which breaks the
moment that project is renamed. This migration rewrites both to store the project
*id* instead. Data-only (no DDL) — the `guard` column stays `String` and holds the
id as a string; `guard_output` stays inside the options JSON as the id.

Portable across SQLite / MySQL / Postgres: all work is done in Python through the
bound connection with parameter-bound SQL, so there are no backend-specific DDL
quirks. Idempotent — values that are already numeric ids are left untouched, and a
name that doesn't resolve to a live project is left as-is (Guard resolution falls
back to name lookup, so nothing breaks).
"""
import json

import sqlalchemy as sa
from alembic import op


revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def _load_projects(bind):
    rows = bind.execute(sa.text("SELECT id, name, guard, options FROM projects")).fetchall()
    name_to_id = {r[1]: r[0] for r in rows if r[1] is not None}
    return rows, name_to_id


def _remap(rows, translate):
    """Yield (id, new_guard, new_options) for rows whose guard / guard_output
    changed under `translate` (a value -> new-value-or-None function)."""
    for pid, _name, guard, options in rows:
        new_guard = translate(guard)
        guard_changed = new_guard is not None and new_guard != guard

        new_options = None
        try:
            opts = json.loads(options) if options else {}
        except Exception:
            opts = {}
        if isinstance(opts, dict) and opts.get("guard_output") is not None:
            mapped = translate(opts.get("guard_output"))
            if mapped is not None and mapped != opts.get("guard_output"):
                opts["guard_output"] = mapped
                new_options = json.dumps(opts)

        if guard_changed or new_options is not None:
            yield pid, (new_guard if guard_changed else guard), new_options


def _apply(bind, rows, translate):
    for pid, new_guard, new_options in _remap(rows, translate):
        bind.execute(
            sa.text("UPDATE projects SET guard = :g WHERE id = :id"),
            {"g": new_guard, "id": pid},
        )
        if new_options is not None:
            bind.execute(
                sa.text("UPDATE projects SET options = :o WHERE id = :id"),
                {"o": new_options, "id": pid},
            )


def upgrade():
    bind = op.get_bind()
    rows, name_to_id = _load_projects(bind)

    def name_to_id_fn(value):
        if value is None:
            return None
        s = str(value)
        if s.isdigit():
            return s  # already an id
        mapped = name_to_id.get(s)
        return str(mapped) if mapped is not None else None

    _apply(bind, rows, name_to_id_fn)


def downgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name FROM projects")).fetchall()
    id_to_name = {str(r[0]): r[1] for r in rows}
    all_rows = bind.execute(sa.text("SELECT id, name, guard, options FROM projects")).fetchall()

    def id_to_name_fn(value):
        if value is None:
            return None
        s = str(value)
        if not s.isdigit():
            return None  # already a name
        return id_to_name.get(s)

    _apply(bind, all_rows, id_to_name_fn)
