"""SSRF protection on the MCP server host path.

`check_user_can_use_mcp_host` is a pure (user, host) function — it only reads
`user.is_admin` — so it tests directly without DB/network. All hosts are IP
literals or `.invalid` so `socket.getaddrinfo` parses/fails without real DNS.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from restai.auth import check_user_can_use_mcp_host
from restai.helper import is_blocked_network_host

ADMIN = SimpleNamespace(is_admin=True)
MEMBER = SimpleNamespace(is_admin=False)


def test_mcp_imds_host_blocked():
    with pytest.raises(HTTPException) as e:
        check_user_can_use_mcp_host(ADMIN, "http://169.254.169.254/latest/meta-data/")
    assert e.value.status_code == 400


def test_mcp_rfc1918_host_blocked():
    with pytest.raises(HTTPException) as e:
        check_user_can_use_mcp_host(MEMBER, "http://10.0.0.1:6333/")
    assert e.value.status_code == 400


def test_mcp_ipv4_mapped_imds_blocked():
    with pytest.raises(HTTPException) as e:
        check_user_can_use_mcp_host(MEMBER, "http://[::ffff:169.254.169.254]/")
    assert e.value.status_code == 400


def test_mcp_unresolvable_host_blocked_fail_closed():
    with pytest.raises(HTTPException) as e:
        check_user_can_use_mcp_host(MEMBER, "http://nonexistent.invalid/")
    assert e.value.status_code == 400


def test_mcp_public_host_allowed():
    # Public IP literal — no raise (accepted). Member is fine for network transport.
    check_user_can_use_mcp_host(MEMBER, "https://8.8.8.8/mcp")


def test_mcp_stdio_admin_only():
    # Non-network (stdio) host: admin-only, unchanged behavior.
    with pytest.raises(HTTPException) as e:
        check_user_can_use_mcp_host(MEMBER, "/usr/bin/some-mcp-server")
    assert e.value.status_code == 403
    check_user_can_use_mcp_host(ADMIN, "/usr/bin/some-mcp-server")  # admin allowed


@pytest.mark.parametrize("url,blocked", [
    ("http://169.254.169.254/", True),
    ("http://10.0.0.1:6333/", True),
    ("http://127.0.0.1/", True),
    ("http://[::ffff:169.254.169.254]/", True),
    ("sse://192.168.1.10/sse", True),
    ("http://nonexistent.invalid/", True),   # unresolvable -> fail closed
    ("not a url", True),                       # unparseable -> fail closed
    ("https://8.8.8.8/", False),
    ("https://1.1.1.1/mcp", False),
])
def test_is_blocked_network_host(url, blocked):
    assert is_blocked_network_host(url) is blocked
