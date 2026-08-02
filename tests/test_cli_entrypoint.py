"""Unit tests for restai/cli.py — the `restai` CLI entrypoint.

Command dispatch is covered with uvicorn / alembic / script execution
fully mocked: no server ever starts, no migration ever runs.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import restai.cli as cli


# ─── _load_env ──────────────────────────────────────────────────────────

def test_load_env_none_is_noop():
    cli._load_env(None)  # must not raise


def test_load_env_missing_file_exits():
    with pytest.raises(SystemExit) as exc:
        cli._load_env("/nonexistent/definitely/not/here.env")
    assert exc.value.code == 1


def test_load_env_reads_values(tmp_path, monkeypatch):
    envfile = tmp_path / "test.env"
    envfile.write_text("# comment\n\nRESTAI_CLI_TEST_KEY='hello world'\n")
    monkeypatch.delenv("RESTAI_CLI_TEST_KEY", raising=False)
    cli._load_env(str(envfile))
    assert os.environ.get("RESTAI_CLI_TEST_KEY") == "hello world"
    monkeypatch.delenv("RESTAI_CLI_TEST_KEY", raising=False)


def test_load_env_manual_fallback_without_dotenv(tmp_path, monkeypatch):
    envfile = tmp_path / "test.env"
    envfile.write_text('RESTAI_CLI_FALLBACK_KEY="quoted"\nnot a kv line\n')
    monkeypatch.delenv("RESTAI_CLI_FALLBACK_KEY", raising=False)
    # Force the ImportError branch by hiding dotenv.
    monkeypatch.setitem(sys.modules, "dotenv", None)
    cli._load_env(str(envfile))
    assert os.environ.get("RESTAI_CLI_FALLBACK_KEY") == "quoted"
    monkeypatch.delenv("RESTAI_CLI_FALLBACK_KEY", raising=False)


# ─── serve ──────────────────────────────────────────────────────────────

def test_serve_dispatch_with_explicit_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai", "serve", "--port", "1234", "--workers", "2"])
    with patch("uvicorn.run") as run:
        cli.main()
    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == "restai.main:app"
    assert kwargs["port"] == 1234
    assert kwargs["workers"] == 2
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["reload"] is False
    # --port also exports RESTAI_PORT for the app process.
    assert os.environ.get("RESTAI_PORT") == "1234"
    monkeypatch.delenv("RESTAI_PORT", raising=False)


def test_no_command_defaults_to_serve(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai"])
    with patch("uvicorn.run") as run:
        cli.main()
    run.assert_called_once()
    kwargs = run.call_args.kwargs
    assert kwargs["workers"] == 4
    assert kwargs["host"] == "0.0.0.0"
    # No explicit port → falls back to RESTAI_PORT config (9000 in tests).
    assert kwargs["port"] == 9000


def test_serve_reload_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai", "serve", "--reload"])
    with patch("uvicorn.run") as run:
        cli.main()
    assert run.call_args.kwargs["reload"] is True
    monkeypatch.delenv("RESTAI_PORT", raising=False)


# ─── migrate ────────────────────────────────────────────────────────────

def test_migrate_upgrade_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai", "migrate"])
    with patch("alembic.command.upgrade") as up, patch("alembic.command.downgrade") as down:
        cli.main()
    up.assert_called_once()
    down.assert_not_called()
    cfg, target = up.call_args.args
    assert target == "head"
    # No POSTGRES/MYSQL host in the test env → sqlite URL.
    assert cfg.get_main_option("sqlalchemy.url") == "sqlite:///./restai.db"
    # script_location resolved to the repo's migrations dir.
    assert cfg.get_main_option("script_location").endswith("migrations")


def test_migrate_downgrade(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai", "migrate", "downgrade"])
    with patch("alembic.command.upgrade") as up, patch("alembic.command.downgrade") as down:
        cli.main()
    down.assert_called_once()
    up.assert_not_called()
    assert down.call_args.args[1] == "-1"


def test_migrate_rejects_bad_direction(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["restai", "migrate", "sideways"])
    with pytest.raises(SystemExit):
        cli.main()


# ─── init ───────────────────────────────────────────────────────────────

def test_init_imports_database_module(monkeypatch):
    sentinel = types.ModuleType("database")
    sentinel.touched = True
    monkeypatch.setitem(sys.modules, "database", sentinel)
    monkeypatch.setattr(sys, "argv", ["restai", "init"])
    cli.main()  # must not raise; the (stubbed) side-effect import is the whole job


# ─── cron-style subcommands dispatch through _run_script ────────────────

@pytest.mark.parametrize("command,script", [
    ("crons", "crons/runner.py"),
    ("sync", "crons/sync.py"),
    ("telegram", "crons/telegram.py"),
    ("slack", "crons/slack.py"),
    ("docker-cleanup", "crons/docker_cleanup.py"),
    ("routines", "crons/routines.py"),
])
def test_subcommand_dispatch(monkeypatch, command, script):
    monkeypatch.setattr(sys, "argv", ["restai", command])
    with patch.object(cli, "_run_script") as rs:
        cli.main()
    rs.assert_called_once()
    assert rs.call_args.args[1] == script


# ─── _run_script ────────────────────────────────────────────────────────

def test_run_script_executes_main(tmp_path):
    marker = tmp_path / "marker.txt"
    script = tmp_path / "job.py"
    script.write_text(
        "import pathlib\n"
        "def main():\n"
        f"    pathlib.Path({str(marker)!r}).write_text('ran')\n"
    )
    args = MagicMock(env_file=None)
    cli._run_script(args, str(script))
    assert marker.read_text() == "ran"


def test_run_script_without_main_is_noop(tmp_path):
    script = tmp_path / "nomain.py"
    script.write_text("X = 1\n")
    cli._run_script(MagicMock(env_file=None), str(script))  # must not raise


def test_run_script_unresolvable_exits():
    # A path with no .py extension yields no import spec anywhere → exit(1).
    with pytest.raises(SystemExit) as exc:
        cli._run_script(MagicMock(env_file=None), "definitely-not-a-script")
    assert exc.value.code == 1
