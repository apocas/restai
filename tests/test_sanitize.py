"""Tests for filename sanitization and name validation utilities."""

import pytest

from restai.models.models import sanitize_filename, validate_safe_name


def test_sanitize_strips_path():
    """sanitize_filename should strip directory traversal components."""
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_sanitize_removes_null():
    """sanitize_filename should remove null bytes."""
    assert sanitize_filename("file\x00name.txt") == "filename.txt"


def test_sanitize_empty():
    """sanitize_filename should return 'unnamed_file' for empty input."""
    assert sanitize_filename("") == "unnamed_file"


def test_validate_safe_name_rejects_special():
    """validate_safe_name should raise ValueError for names with special characters."""
    with pytest.raises(ValueError):
        validate_safe_name("test<script>")


def test_validate_safe_name_accepts_valid():
    """validate_safe_name should accept names with allowed characters and return them."""
    result = validate_safe_name("my-project_v2.0")
    assert result == "my-project_v2.0"
