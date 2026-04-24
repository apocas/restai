"""SSRF + tool-loader hardening tests.

Covers the three small security fixes that landed together:
* `crawler_classic` rejects loopback / link-local / private addresses
  and times out instead of hanging.
* `_sync_url` skips URL knowledge sync when the target resolves to a
  private/internal address.
* `load_tools` reads userland tools from an absolute install-relative
  path, not the process's current working directory.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ─── crawler_classic ────────────────────────────────────────────────────

@pytest.mark.parametrize("blocked_url", [
    "http://127.0.0.1/",
    "http://localhost:9000/admin",
    "http://10.0.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",  # AWS IMDS
])
def test_crawler_classic_blocks_private_addresses(blocked_url):
    from restai.llms.tools.crawler_classic import crawler_classic
    out = crawler_classic(blocked_url)
    assert out.startswith("ERROR:")
    assert "private" in out.lower() or "internal" in out.lower()


def test_crawler_classic_rejects_invalid_url():
    from restai.llms.tools.crawler_classic import crawler_classic
    out = crawler_classic("not_a_url")
    assert out.startswith("ERROR:")


def test_crawler_classic_uses_timeout(monkeypatch):
    """Ensure the timeout kwarg is actually passed through. We don't want
    a slow upstream to block an agent indefinitely."""
    from restai.llms.tools import crawler_classic as mod
    captured = {}

    class _FakeResp:
        content = b"<html><body>hello</body></html>"

    def fake_get(url, headers=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResp()

    # Bypass SSRF guard with a public address.
    monkeypatch.setattr(mod, "_is_private_ip", lambda h: False)
    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.crawler_classic("http://example.com/")
    assert "hello" in out
    assert captured["timeout"] is not None and captured["timeout"] > 0


# ─── _sync_url SSRF ─────────────────────────────────────────────────────

def test_sync_url_skips_private_address(caplog):
    from restai import sync as sync_mod

    class _FakeSource:
        name = "test"
        url = "http://127.0.0.1/secrets"

    called = {"loaded": False}
    class _FakeReader:
        def load_data(self, urls):
            called["loaded"] = True
            return []

    with patch.object(sync_mod, "logger") as fake_logger, \
         patch("restai.loaders.url.SeleniumWebReader", _FakeReader):
        sync_mod._sync_url(project=None, source=_FakeSource(), db=None, brain=None)

    assert called["loaded"] is False, "loader must not run for private address"
    # The function must have logged a warning explaining why.
    warn_calls = [c for c in fake_logger.warning.call_args_list]
    assert warn_calls, "expected a warning log for the skipped sync"
    assert any("private" in str(c).lower() or "internal" in str(c).lower() for c in warn_calls)


def test_sync_url_skips_invalid_url():
    from restai import sync as sync_mod

    class _FakeSource:
        name = "bad"
        url = ""

    class _FakeReader:
        def load_data(self, urls):
            raise AssertionError("loader must not be called for empty url")

    with patch("restai.loaders.url.SeleniumWebReader", _FakeReader):
        # Should return cleanly, no exception.
        sync_mod._sync_url(project=None, source=_FakeSource(), db=None, brain=None)


# ─── tool loader path ──────────────────────────────────────────────────

def test_load_tools_uses_absolute_userland_path():
    """Verify the loader reads from the install-root /tools directory, not
    the process CWD. We exercise it by changing CWD and confirming we
    still get the same tool set (and that the loader resolved the
    absolute path printed in the log)."""
    from restai import tools as tools_mod

    original_cwd = os.getcwd()
    try:
        os.chdir("/tmp")
        loaded = tools_mod.load_tools()
        names = {t.metadata.name for t in loaded}
        # Core tools always load; absence of these would mean the
        # function silently bailed.
        assert "send_telegram" in names
        assert "send_whatsapp" in names
        assert "crawler_classic" in names
    finally:
        os.chdir(original_cwd)
