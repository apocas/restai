"""Project event webhook tests.

Covers the helper (`emit_event`) end-to-end with mocked HTTP, plus the
admin Test endpoint.

The HTTP POST happens in a daemon thread (so a flaky receiver can't
stall a cron / inference). Tests collect the request via a list shared
with the patched `requests.post`, then sleep briefly to let the thread
flush. Any test that depends on the request firing has a
``thread.join``-ish guard via a ``threading.Event``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from restai.utils.crypto import encrypt_field


# ─── helper ─────────────────────────────────────────────────────────────

def _wait_for(event: threading.Event, timeout: float = 2.0):
    assert event.wait(timeout), "background webhook thread did not run within timeout"


def test_emit_event_skips_when_no_url():
    from restai.webhooks import emit_event
    out = emit_event(1, "p", {}, "test", {"hi": True})
    assert out is False


def test_emit_event_skips_unknown_event_type():
    from restai.webhooks import emit_event
    opts = {"webhook_url": "https://hooks.example.com/x"}
    out = emit_event(1, "p", opts, "made_up_event", {})
    assert out is False


def test_emit_event_filters_by_subscription():
    from restai.webhooks import emit_event
    opts = {
        "webhook_url": "https://hooks.example.com/x",
        "webhook_events": "sync_completed",
    }
    fired = emit_event(1, "p", opts, "budget_exceeded", {})
    assert fired is False


def test_emit_event_refuses_private_url():
    from restai.webhooks import emit_event
    opts = {"webhook_url": "http://127.0.0.1:9999/hook"}
    out = emit_event(1, "p", opts, "test", {})
    assert out is False


def test_emit_event_refuses_non_http_scheme():
    from restai.webhooks import emit_event
    opts = {"webhook_url": "file:///etc/passwd"}
    out = emit_event(1, "p", opts, "test", {})
    assert out is False


def test_emit_event_signs_with_hmac():
    from restai.webhooks import emit_event
    secret = "super-shared-secret-123"
    opts = {
        "webhook_url": "https://hooks.example.com/x",
        "webhook_secret": encrypt_field(secret),
    }
    captured = {}
    done = threading.Event()

    class _FakeResp:
        status_code = 200
        text = ""

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update({"url": url, "data": data, "headers": dict(headers), "timeout": timeout})
        done.set()
        return _FakeResp()

    with patch("requests.post", fake_post), \
         patch("restai.webhooks._is_private_ip", lambda h: False):
        out = emit_event(42, "myproj", opts, "test", {"foo": "bar"})
        assert out is True
        _wait_for(done)

    assert captured["url"] == "https://hooks.example.com/x"
    assert captured["headers"]["X-RESTai-Event"] == "test"
    sig_header = captured["headers"]["X-RESTai-Signature"]
    assert sig_header.startswith("sha256=")
    expected = hmac.new(secret.encode(), captured["data"], hashlib.sha256).hexdigest()
    assert sig_header == f"sha256={expected}"
    payload = json.loads(captured["data"])
    assert payload["event"] == "test"
    assert payload["project_id"] == 42
    assert payload["project_name"] == "myproj"
    assert payload["data"] == {"foo": "bar"}


def test_emit_event_omits_signature_when_no_secret():
    from restai.webhooks import emit_event
    opts = {"webhook_url": "https://hooks.example.com/x"}
    captured = {}
    done = threading.Event()

    class _FakeResp:
        status_code = 200
        text = ""

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update({"headers": dict(headers)})
        done.set()
        return _FakeResp()

    with patch("requests.post", fake_post), \
         patch("restai.webhooks._is_private_ip", lambda h: False):
        emit_event(1, "p", opts, "test", {})
        _wait_for(done)

    assert "X-RESTai-Signature" not in captured["headers"]


def test_emit_event_swallows_post_failure():
    """A flaky receiver must not raise into the caller — we're called
    from inference / cron paths that can't be allowed to crash."""
    from restai.webhooks import emit_event
    opts = {"webhook_url": "https://hooks.example.com/x"}
    done = threading.Event()

    def fake_post(*a, **kw):
        done.set()
        raise RuntimeError("network is on fire")

    with patch("requests.post", fake_post), \
         patch("restai.webhooks._is_private_ip", lambda h: False):
        # Must return True (request was queued) even though the POST will fail.
        out = emit_event(1, "p", opts, "test", {})
        assert out is True
        _wait_for(done)
        # And no exception bubbles up — give the thread a moment to log.
        time.sleep(0.05)


# ─── /projects/{id}/webhooks/test endpoint ─────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from restai.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def project_id(client):
    """Reuse the same fixture pattern as test_whatsapp_webhook."""
    from restai.config import RESTAI_DEFAULT_PASSWORD
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    teams = client.get("/teams", auth=auth).json().get("teams", []) or []
    if not teams:
        pytest.skip("no team available")
    listing = client.get("/projects", auth=auth).json().get("projects", []) or []
    name = "webhook_test_project"
    existing = next((p for p in listing if p.get("name") == name), None)
    if existing:
        return existing["id"]
    info = client.get("/info", auth=auth).json()
    llms = info.get("llms") or []
    if not llms:
        pytest.skip("no LLMs configured")
    resp = client.post(
        "/projects",
        json={"name": name, "type": "agent", "llm": llms[0]["name"], "team_id": teams[0]["id"]},
        auth=auth,
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"could not create project: {resp.status_code}")
    return resp.json()["id"]


def test_webhook_test_endpoint_no_url_configured(client, project_id):
    """The fixture creates a fresh project on first run, but it persists
    across runs in the dev DB — a prior run of _fires_when_configured
    may have stamped webhook_url into the options. Clear it explicitly
    so this test asserts the precondition it actually depends on."""
    from restai.config import RESTAI_DEFAULT_PASSWORD
    from restai.database import get_db_wrapper
    from restai.models.databasemodels import ProjectDatabase

    db = get_db_wrapper()
    try:
        proj = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == project_id).first()
        opts = json.loads(proj.options or "{}")
        opts.pop("webhook_url", None)
        opts.pop("webhook_secret", None)
        proj.options = json.dumps(opts)
        db.db.commit()
    finally:
        db.db.close()

    r = client.post(
        f"/projects/{project_id}/webhooks/test", auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "no webhook_url" in body["reason"]


def test_webhook_test_endpoint_fires_when_configured(client, project_id):
    """Writing a webhook_url + flipping the test endpoint should queue
    a POST. We patch requests.post so no real network call happens."""
    from restai.config import RESTAI_DEFAULT_PASSWORD
    from restai.database import get_db_wrapper
    from restai.models.databasemodels import ProjectDatabase

    auth = ("admin", RESTAI_DEFAULT_PASSWORD)

    # Configure a webhook URL directly in the DB (bypasses model validation).
    db = get_db_wrapper()
    try:
        proj = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == project_id).first()
        opts = json.loads(proj.options or "{}")
        opts["webhook_url"] = "https://hooks.example.com/wh-test"
        opts["webhook_secret"] = encrypt_field("s3cret")
        proj.options = json.dumps(opts)
        db.db.commit()
    finally:
        db.db.close()

    captured = {}
    done = threading.Event()
    class _FakeResp:
        status_code = 202
        text = ""
    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update({"url": url, "headers": dict(headers)})
        done.set()
        return _FakeResp()

    with patch("requests.post", fake_post), \
         patch("restai.webhooks._is_private_ip", lambda h: False):
        r = client.post(f"/projects/{project_id}/webhooks/test", auth=auth)
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        _wait_for(done)

    assert captured["url"] == "https://hooks.example.com/wh-test"
    assert captured["headers"]["X-RESTai-Event"] == "test"
    assert captured["headers"]["X-RESTai-Signature"].startswith("sha256=")
