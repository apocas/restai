"""RESTai CLI — run the platform from a pip install."""

import argparse
import os
import sys


def _load_env(env_file):
    """Load environment variables from a .env file."""
    if not env_file:
        return
    if not os.path.isfile(env_file):
        print(f"Error: env file '{env_file}' not found.", file=sys.stderr)
        sys.exit(1)
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)
    except ImportError:
        # Manual fallback
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    os.environ[key] = value


def cmd_serve(args):
    """Start the RESTai server."""
    _load_env(args.env_file)

    # Set port from args or env
    if args.port:
        os.environ["RESTAI_PORT"] = str(args.port)

    import uvicorn
    from restai.config import RESTAI_PORT

    port = int(args.port or RESTAI_PORT or 9000)
    workers = args.workers

    print(f"Starting RESTai on port {port} with {workers} worker(s)")
    uvicorn.run(
        "restai.main:app",
        host=args.host,
        port=port,
        workers=workers,
        reload=args.reload,
    )


def cmd_migrate(args):
    """Run database migrations."""
    _load_env(args.env_file)

    from alembic.config import Config
    from alembic import command
    from restai.config import POSTGRES_URL, MYSQL_URL, POSTGRES_HOST, MYSQL_HOST

    if POSTGRES_HOST:
        db_url = POSTGRES_URL
    elif MYSQL_HOST:
        db_url = MYSQL_URL
    else:
        db_url = "sqlite:///./restai.db"

    # Find alembic.ini and migrations — check repo root first, then site-packages
    import sysconfig
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    site_packages = sysconfig.get_path("purelib")

    alembic_ini = os.path.join(package_root, "alembic.ini")
    if not os.path.isfile(alembic_ini):
        alembic_ini = os.path.join(site_packages, "alembic.ini")
    if not os.path.isfile(alembic_ini):
        print("Error: alembic.ini not found", file=sys.stderr)
        sys.exit(1)

    migrations_dir = os.path.join(package_root, "migrations")
    if not os.path.isdir(migrations_dir):
        migrations_dir = os.path.join(site_packages, "migrations")

    alembic_cfg = Config(alembic_ini)
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", migrations_dir)

    if args.direction == "upgrade":
        command.upgrade(alembic_cfg, "head")
        print("Database migrated successfully.")
    else:
        command.downgrade(alembic_cfg, "-1")
        print("Database downgraded.")


def cmd_init(args):
    """Initialize the database with tables, admin user, and default models."""
    _load_env(args.env_file)

    # The root database.py script creates tables and seeds data on import
    import importlib
    import database  # noqa: F401 — side-effect import that creates tables
    print("Database initialized.")


def _run_script(args, script_path):
    """Run a standalone script."""
    _load_env(args.env_file)
    import importlib.util
    spec = importlib.util.spec_from_file_location("script", script_path)
    if spec is None:
        # Try relative to package
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(package_root, script_path)
        spec = importlib.util.spec_from_file_location("script", script_path)
    if spec is None:
        print(f"Error: script not found: {script_path}", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()


def main():
    parser = argparse.ArgumentParser(
        prog="restai",
        description="RESTai — AI as a Service Platform",
    )
    parser.add_argument("--env-file", "-e", default=None, help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the RESTai server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", "-p", type=int, default=None, help="Port (default: 9000 or RESTAI_PORT)")
    serve_parser.add_argument("--workers", "-w", type=int, default=4, help="Number of workers (default: 4)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    serve_parser.set_defaults(func=cmd_serve)

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("direction", nargs="?", default="upgrade", choices=["upgrade", "downgrade"])
    migrate_parser.set_defaults(func=cmd_migrate)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize database schema and admin user")
    init_parser.set_defaults(func=cmd_init)

    # sync
    sync_parser = subparsers.add_parser("sync", help="Run knowledge base sync (cron-friendly)")
    sync_parser.set_defaults(func=lambda args: _run_script(args, "scripts/sync.py"))

    # telegram
    telegram_parser = subparsers.add_parser("telegram", help="Poll Telegram for updates (cron-friendly)")
    telegram_parser.set_defaults(func=lambda args: _run_script(args, "scripts/telegram.py"))

    # slack
    slack_parser = subparsers.add_parser("slack", help="Start Slack bot daemon (long-running)")
    slack_parser.set_defaults(func=lambda args: _run_script(args, "scripts/slack.py"))

    args = parser.parse_args()
    if not args.command:
        # Default to serve
        args.command = "serve"
        args.host = "0.0.0.0"
        args.port = None
        args.workers = 4
        args.reload = False
        args.func = cmd_serve

    args.func(args)


if __name__ == "__main__":
    main()
