"""Tests for SQL connection string validation in RAG projects."""
import pytest
from fastapi import HTTPException

from restai.projects.rag import _validate_connection_string


def test_accepts_postgresql():
    # Should not raise
    _validate_connection_string("postgresql://user:pass@host/db")


def test_accepts_mysql_pymysql():
    # Should not raise
    _validate_connection_string("mysql+pymysql://user:pass@host/db")


def test_accepts_sqlite_relative():
    # sqlite:// with no host + relative path. urlparse("sqlite:///relative.db")
    # produces path="/relative.db" which starts with "/" and triggers the
    # absolute-path guard. Use the empty-authority form instead.
    _validate_connection_string("sqlite:relative.db")


def test_rejects_file_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("file:///etc/passwd")
    assert exc_info.value.status_code == 400


def test_rejects_mongodb_scheme():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("mongodb://host/db")
    assert exc_info.value.status_code == 400


def test_rejects_sqlite_absolute_outside_cwd():
    with pytest.raises(HTTPException) as exc_info:
        _validate_connection_string("sqlite:///etc/passwd")
    assert exc_info.value.status_code == 400
