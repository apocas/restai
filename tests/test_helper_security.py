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
