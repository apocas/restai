"""Tests for helper security functions (SSRF protection)."""
import socket
import threading
import http.server
import socketserver

import pytest

from restai.helper import (
    _is_private_ip, _resolve_validated_ip, _pin_url_and_host, _pinned_get, _safe_get,
)


def test_loopback_is_private():
    assert _is_private_ip("127.0.0.1") is True


def test_10_range_is_private():
    assert _is_private_ip("10.0.0.1") is True


def test_172_16_range_is_private():
    assert _is_private_ip("172.16.0.1") is True


def test_192_168_range_is_private():
    assert _is_private_ip("192.168.1.1") is True


def test_aws_metadata_is_private():
    assert _is_private_ip("169.254.169.254") is True


def test_google_dns_is_public():
    assert _is_private_ip("8.8.8.8") is False


def test_cloudflare_dns_is_public():
    assert _is_private_ip("1.1.1.1") is False


# --- IPv6 / IPv4-mapped / IPv4-compatible coverage (SSRF bypass guards) ---

def test_ipv4_mapped_imds_is_private():
    # ::ffff:169.254.169.254 — IPv4-mapped IMDS; the original bypass (PR #178).
    assert _is_private_ip("::ffff:169.254.169.254") is True


def test_ipv4_mapped_loopback_is_private():
    assert _is_private_ip("::ffff:127.0.0.1") is True


def test_ipv4_mapped_rfc1918_is_private():
    assert _is_private_ip("::ffff:10.0.0.1") is True


def test_ipv4_compatible_imds_is_private():
    # ::169.254.169.254 — deprecated IPv4-compatible form (no .ipv4_mapped).
    assert _is_private_ip("::169.254.169.254") is True


def test_ipv6_loopback_is_private():
    assert _is_private_ip("::1") is True


def test_ipv6_link_local_is_private():
    assert _is_private_ip("fe80::1") is True


def test_public_ipv6_is_public():
    assert _is_private_ip("2001:4860:4860::8888") is False


# --- Category-based coverage: 0.0.0.0, unspecified, broadcast, multicast, reserved ---

@pytest.mark.parametrize("host", [
    "0.0.0.0",          # unspecified — reaches localhost on Linux
    "0.1.2.3",          # 0.0.0.0/8 "this network"
    "::",               # IPv6 unspecified
    "255.255.255.255",  # broadcast / reserved
    "224.0.0.1",        # multicast
    "240.0.0.1",        # reserved (Class E)
    "::ffff:0.0.0.0",   # IPv4-mapped unspecified
])
def test_category_blocked(host):
    assert _is_private_ip(host) is True


@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
def test_public_hosts_allowed(host):
    assert _is_private_ip(host) is False


# --- _resolve_validated_ip (resolve-once + fail-closed) ---

def test_resolve_validated_ip_public_literal():
    assert _resolve_validated_ip("8.8.8.8") == "8.8.8.8"


@pytest.mark.parametrize("host", ["10.0.0.1", "0.0.0.0", "127.0.0.1", "nonexistent.invalid"])
def test_resolve_validated_ip_rejects(host):
    with pytest.raises(ValueError):
        _resolve_validated_ip(host)


def test_resolve_validated_ip_rejects_mixed_records(monkeypatch):
    # A host that resolves to BOTH a public and a private address is refused
    # entirely (defeats picking the public A-record then rebinding to private).
    def fake_getaddrinfo(host, *a, **kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        _resolve_validated_ip("rebind.example")


# --- _pin_url_and_host ---

def test_pin_url_and_host_ipv4():
    assert _pin_url_and_host("https://example.com/a?b=1", "93.184.216.34") == (
        "https://93.184.216.34/a?b=1", "example.com")


def test_pin_url_and_host_preserves_port_and_brackets_ipv6():
    assert _pin_url_and_host("http://h:8080/x", "2001:db8::1") == (
        "http://[2001:db8::1]:8080/x", "h:8080")


# --- End-to-end against a loopback server (the reporter's PoC shape) ---

@pytest.fixture
def loopback_server():
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"SECRET host=" + (self.headers.get("Host", "") or "").encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port
    srv.shutdown()


@pytest.mark.parametrize("tmpl", [
    "http://127.0.0.1:{p}/",
    "http://0.0.0.0:{p}/",
    "http://[::ffff:127.0.0.1]:{p}/",
])
def test_safe_get_blocks_internal(loopback_server, tmpl):
    with pytest.raises(ValueError):
        _safe_get(tmpl.format(p=loopback_server), timeout=5)


def test_pinned_get_connects_to_ip_preserving_host(loopback_server):
    # Pin to the loopback IP but present a different hostname — proves the connection
    # targets the pinned IP while the original host rides in the Host header.
    r = _pinned_get(f"http://some-host.test:{loopback_server}/p", "127.0.0.1", timeout=5)
    assert r.status_code == 200
    assert f"host=some-host.test:{loopback_server}" in r.text
