"""Tests for MCP client security validation."""
import pytest

from restai.agent2.mcp_client import (
    ALLOWED_MCP_STDIO_COMMANDS,
    _is_http_host,
    _validate_stdio_host,
)


def test_allowed_commands_contains_expected_entries():
    expected = {"npx", "uvx", "python", "python3", "node", "deno", "bun"}
    for cmd in expected:
        assert cmd in ALLOWED_MCP_STDIO_COMMANDS, f"{cmd} missing from ALLOWED_MCP_STDIO_COMMANDS"


def test_validate_stdio_host_accepts_npx():
    # Should not raise
    _validate_stdio_host("npx")


def test_validate_stdio_host_accepts_python3():
    # Should not raise
    _validate_stdio_host("python3")


def test_validate_stdio_host_rejects_bin_sh():
    with pytest.raises((ValueError, NameError)):
        _validate_stdio_host("/bin/sh")


def test_validate_stdio_host_rejects_bin_bash():
    with pytest.raises((ValueError, NameError)):
        _validate_stdio_host("/bin/bash")


def test_validate_stdio_host_rejects_shell_metacharacters_in_args():
    with pytest.raises((ValueError, NameError)):
        _validate_stdio_host("npx", args=["$(evil)"])


def test_is_http_host_returns_true_for_http():
    assert _is_http_host("http://example.com") is True


def test_is_http_host_returns_true_for_https():
    assert _is_http_host("https://example.com") is True


def test_is_http_host_returns_false_for_npx():
    assert _is_http_host("npx") is False


def test_is_http_host_returns_false_for_empty_string():
    assert _is_http_host("") is False
