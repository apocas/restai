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


def upgrade():
    """Run database migrations to upgrade the database schema."""
    command.upgrade(_alembic_cfg(), "head")


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
