"""Tests for SQL connection string validation in RAG projects."""
import pytest
from fastapi import HTTPException

from restai.projects.rag import _validate_connection_string


def test_accepts_postgresql():
    _validate_connection_string("postgresql://user:pass@host/db")


def test_accepts_mysql_pymysql():
    _validate_connection_string("mysql+pymysql://user:pass@host/db")


def test_accepts_sqlite_relative_3_slash():
    # SQLAlchemy convention: sqlite:///<path> = RELATIVE under cwd
    # (3 slashes = empty netloc + relative path).
    _validate_connection_string("sqlite:///relative.db")


def test_accepts_sqlite_memory():
    _validate_connection_string("sqlite:///:memory:")


def test_accepts_sqlite_empty_path():
    # `sqlite:///` is a transient in-memory DB; SQLAlchemy accepts it.
    _validate_connection_string("sqlite:///")


def test_rejects_file_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("file:///etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_mongodb_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("mongodb://host/db")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_absolute_outside_cwd():
    # SQLAlchemy convention: sqlite:////<path> = ABSOLUTE
    # (4 slashes = empty netloc + absolute path).
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:////etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_traversal_via_dotdot_absolute():
    """Regression: literal prefix-match against cwd was bypassable via `..`
    segments. ``sqlite:////<cwd>/sub/../../../etc/passwd`` starts with cwd
    literally but resolves outside it."""
    import os
    cwd = os.path.realpath(os.getcwd())
    attack = f"sqlite:///{cwd}/sub/../../../etc/passwd"  # 4 slashes total since cwd starts with /
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string(attack)
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_traversal_via_dotdot_relative():
    """Regression: previous check only fired on absolute paths and missed
    relative paths that escape cwd via `..`."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:relative/../../etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_traversal_via_dotdot_three_slash():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:///relative/../../etc/passwd")
    assert exc_info.value.status_code == 400


def test_accepts_sqlite_absolute_inside_cwd():
    """Absolute path that resolves inside cwd is fine — e.g. the
    application's own restai.db."""
    import os
    cwd = os.path.realpath(os.getcwd())
    _validate_connection_string(f"sqlite:///{cwd}/restai.db")  # 4 slashes since cwd starts with /
