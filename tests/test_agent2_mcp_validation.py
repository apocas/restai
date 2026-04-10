"""Tests for MCP client security validation."""
import pytest

from restai.agent2.mcp_client import (
    _is_http_host,
    _validate_stdio_args,
)


def test_validate_stdio_args_rejects_shell_metacharacters():
    with pytest.raises(ValueError):
        _validate_stdio_args(args=["$(evil)"])


def test_validate_stdio_args_rejects_semicolons():
    with pytest.raises(ValueError):
        _validate_stdio_args(args=["foo;bar"])


def test_validate_stdio_args_rejects_pipes():
    with pytest.raises(ValueError):
        _validate_stdio_args(args=["foo|bar"])


def test_validate_stdio_args_rejects_backticks():
    with pytest.raises(ValueError):
        _validate_stdio_args(args=["`whoami`"])


def test_validate_stdio_args_accepts_safe_args():
    _validate_stdio_args(args=["--server", "my-mcp-server", "--port", "3000"])


def test_validate_stdio_args_accepts_none():
    _validate_stdio_args(args=None)


def test_is_http_host_returns_true_for_http():
    assert _is_http_host("http://example.com") is True


def test_is_http_host_returns_true_for_https():
    assert _is_http_host("https://example.com") is True


def test_is_http_host_returns_false_for_npx():
    assert _is_http_host("npx") is False


def test_is_http_host_returns_false_for_empty_string():
    assert _is_http_host("") is False
