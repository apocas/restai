"""Tests for helper security functions (SSRF protection)."""
from restai.helper import _is_private_ip


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
