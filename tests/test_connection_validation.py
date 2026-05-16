"""Tests for SQL connection string validation in RAG projects.

SQLite is intentionally not allowed — see the comment in
`restai/projects/rag.py` for the security rationale (project admins
should not get a file-read primitive via NL→SQL).
"""
import pytest
from fastapi import HTTPException

from restai.projects.rag import _validate_connection_string


def test_accepts_postgresql():
    _validate_connection_string("postgresql://user:pass@host/db")


def test_accepts_postgresql_with_driver():
    _validate_connection_string("postgresql+psycopg2://user:pass@host/db")


def test_accepts_mysql():
    _validate_connection_string("mysql://user:pass@host/db")


def test_accepts_mysql_pymysql():
    _validate_connection_string("mysql+pymysql://user:pass@host/db")


def test_rejects_sqlite_relative():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:///relative.db")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_absolute():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:////etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_memory():
    """Even :memory: is rejected — admins should use a real DB."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:///:memory:")
    assert exc_info.value.status_code == 400


def test_rejects_file_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("file:///etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_mongodb_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("mongodb://host/db")
    assert exc_info.value.status_code == 400
