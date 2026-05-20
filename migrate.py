"""Alembic migration runner.

Stdlib-only on purpose: this file runs as the very first step of
`make update`, before `uv sync` has had a chance to install anything
new from `pyproject.toml`. Adding a third-party CLI dep here means an
old instance whose .venv is missing that dep can't even reach the
migrations to fix the upgrade. argparse keeps this script bootable
under any Python 3 install.
"""
import argparse

from alembic.config import Config
from alembic import command

from restai.config import POSTGRES_URL, MYSQL_URL, POSTGRES_HOST, MYSQL_HOST, SQLITE_PATH


def get_database_url():
    if POSTGRES_HOST:
        return POSTGRES_URL
    elif MYSQL_HOST:
        return MYSQL_URL
    else:
        # Honor SQLITE_PATH so K8s deployments using a PVC mount end up
        # operating on the *same* file that database.py just initialized.
        # Hardcoding `./restai.db` here meant alembic ran against an
        # empty file in the cwd while database.py wrote to the PVC, and
        # migration 027's batch_alter_table('llms') exploded.
        return f"sqlite:///{SQLITE_PATH or './restai.db'}"


def _alembic_cfg():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def _autostamp_if_provisioned_but_unstamped(cfg):
    """If the schema already looks provisioned (key tables exist) but
    Alembic has no record of a baseline, stamp HEAD instead of letting
    the upgrade replay every revision from 001 against the existing
    schema (which dies with "Duplicate column" / "Table already exists"
    the moment it hits the first additive migration).

    Triggered by the case where `make database` was run by an older
    revision of this codebase that didn't call `_stamp_alembic_head()`
    after `create_all()` — the schema is at HEAD, but `alembic_version`
    is empty or missing. Also covers schema-only dump restores.

    Returns True when we stamped (caller should skip the upgrade).
    """
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(get_database_url())
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        # `users` is the canonical sentinel — every install since 001
        # has it and database.py keys its own bootstrap on the same
        # table. Without it, we treat this as a fresh DB and let alembic
        # run from scratch.
        if "users" not in tables:
            return False
        if "alembic_version" in tables:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).fetchone()
                if row and row[0]:
                    return False  # already stamped, normal upgrade path
    finally:
        engine.dispose()

    print(
        "migrate: schema is already provisioned but alembic_version is empty — "
        "stamping HEAD instead of replaying migrations from 001."
    )
    command.stamp(cfg, "head")
    return True


def upgrade():
    """Run database migrations to upgrade the database schema."""
    cfg = _alembic_cfg()
    if _autostamp_if_provisioned_but_unstamped(cfg):
        return
    command.upgrade(cfg, "head")


def downgrade():
    """Run database migrations to downgrade the database schema."""
    command.downgrade(_alembic_cfg(), "-1")


def main():
    parser = argparse.ArgumentParser(
        description="Run Alembic migrations against the configured database.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("upgrade", help="Upgrade to the latest revision (alembic head).")
    sub.add_parser("downgrade", help="Downgrade by one revision (alembic -1).")
    args = parser.parse_args()

    if args.cmd == "upgrade":
        upgrade()
    elif args.cmd == "downgrade":
        downgrade()


if __name__ == "__main__":
    main()
