"""Extended WhatsApp webhook tests (restai/routers/whatsapp_webhook.py).

Complements tests/test_whatsapp_webhook.py (which covers the handshake
happy/403 paths, bad-signature 401, unknown phone id, allowlist reject
and the non-text notice). This file covers the branches it skips:

* GET handshake with wrong hub.mode.
* POST with non-JSON body / wrong `object` / entry without phone id.
* POST with a valid signature but MISSING signature header → 401.
* Empty text body and missing `from` → silently dropped.
* Project with app_secret but no access_token → skipped, still 200.
* Empty allowlist = open access (any sender reaches the agent).
* Agent raising → no reply sent, handler survives.
* POST /projects/{id}/whatsapp/test (unconfigured / configured / 404).
* _parse_allowlist unit behavior.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import DBWrapper
from restai.main import app
from restai.utils.crypto import encrypt_field

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
team_name = f"waext_team_{suffix}"
proj_name = f"waext_proj_{suffix}"

PHONE_ID = f"waext_phone_{suffix}"
APP_SECRET = f"waext_secret_{suffix}"
ACCESS_TOKEN = f"waext_token_{suffix}"
SENDER = "351911111111"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _set_options(opts: dict):
    """Overwrite the test project's WhatsApp options directly in the DB."""
    from restai.models.databasemodels import ProjectDatabase

    db = DBWrapper()
    try:
        proj = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == state["project_id"]).first()
        current = json.loads(proj.options or "{}")
        # Drop any previous whatsapp_* keys, then apply the new set.
        current = {k: v for k, v in current.items() if not k.startswith("whatsapp_")}
        current.update(opts)
        proj.options = json.dumps(current)
        db.db.commit()
    finally:
        db.db.close()


def _default_options(**overrides):
    opts = {
        "whatsapp_phone_number_id": PHONE_ID,
        "whatsapp_access_token": encrypt_field(ACCESS_TOKEN),
        "whatsapp_app_secret": encrypt_field(APP_SECRET),
        "whatsapp_verify_token": encrypt_field(f"waext_verify_{suffix}"),
    }
    opts.update(overrides)
    return opts


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _payload(message: dict | None, phone_id: str = PHONE_ID) -> bytes:
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": phone_id},
    }
    if message is not None:
        value["messages"] = [message]
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": value}]}],
    }).encode()


def _post(client, body: bytes, sig: str | None):
    headers = {"content-type": "application/json"}
    if sig is not None:
        headers["X-Hub-Signature-256"] = sig
    return client.post("/webhooks/whatsapp", content=body, headers=headers)


@pytest.fixture()
def outbound(monkeypatch):
    """Capture outbound sends + agent dispatches."""
    sent = []
    agent_calls = []

    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda token, pid, to, text: sent.append((token, pid, to, text)) or {"ok": True},
    )

    async def fake_run_agent(project_id, text, from_phone):
        agent_calls.append((project_id, text, from_phone))
        return f"reply to {text}"

    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", fake_run_agent)
    return sent, agent_calls


def test_setup(client):
    r = client.post("/teams", json={"name": team_name}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["project_id"] = r.json()["project"]
    _set_options(_default_options())


# ---------------------------------------------------------------- handshake


def test_handshake_wrong_mode(client):
    r = client.get("/webhooks/whatsapp", params={
        "hub.mode": "unsubscribe",
        "hub.challenge": "abc",
        "hub.verify_token": f"waext_verify_{suffix}",
    })
    assert r.status_code == 400


# ---------------------------------------------------------------- body parsing


def test_post_non_json_body(client, outbound):
    sent, agent_calls = outbound
    r = _post(client, b"this is not json{{", sig="sha256=whatever")
    assert r.status_code == 200
    assert r.json() == {"status": "ignored", "reason": "invalid json"}
    assert sent == [] and agent_calls == []


def test_post_wrong_object(client, outbound):
    sent, agent_calls = outbound
    body = json.dumps({"object": "page", "entry": []}).encode()
    r = _post(client, body, sig="sha256=whatever")
    assert r.status_code == 200
    assert r.json() == {"status": "ignored", "reason": "unexpected object"}
    assert sent == [] and agent_calls == []


def test_post_entry_without_phone_id(client, outbound):
    sent, agent_calls = outbound
    body = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"metadata": {}}}]}],
    }).encode()
    r = _post(client, body, sig="sha256=whatever")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert sent == [] and agent_calls == []


# ---------------------------------------------------------------- signature


def test_post_missing_signature_header(client, outbound):
    sent, agent_calls = outbound
    body = _payload({"from": SENDER, "type": "text", "text": {"body": "hi"}})
    r = _post(client, body, sig=None)
    assert r.status_code == 401
    assert sent == [] and agent_calls == []


# ---------------------------------------------------------------- message edge cases


def test_post_message_without_sender_dropped(client, outbound):
    sent, agent_calls = outbound
    body = _payload({"type": "text", "text": {"body": "hi"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200
    assert sent == [] and agent_calls == []


def test_post_empty_text_dropped(client, outbound):
    sent, agent_calls = outbound
    body = _payload({"from": SENDER, "type": "text", "text": {"body": "   "}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200
    assert sent == [] and agent_calls == []


def test_post_no_access_token_skipped(client, outbound):
    sent, agent_calls = outbound
    _set_options(_default_options(whatsapp_access_token=""))
    body = _payload({"from": SENDER, "type": "text", "text": {"body": "hello"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert sent == [] and agent_calls == []
    _set_options(_default_options())


def test_post_open_allowlist_dispatches_any_sender(client, outbound):
    sent, agent_calls = outbound
    # No whatsapp_allowed_phone_numbers key at all → open access.
    body = _payload({"from": "1555000999", "type": "text", "text": {"body": "open door"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200
    assert agent_calls == [(state["project_id"], "open door", "1555000999")]
    assert len(sent) == 1
    token, pid, to, text = sent[0]
    assert token == ACCESS_TOKEN
    assert pid == PHONE_ID
    assert to == "1555000999"
    assert text == "reply to open door"


def test_post_agent_failure_sends_nothing(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda *a, **kw: sent.append(a) or {"ok": True},
    )

    async def broken_agent(project_id, text, from_phone):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", broken_agent)

    body = _payload({"from": SENDER, "type": "text", "text": {"body": "boom"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200  # ack regardless; failure stays server-side
    assert sent == []


def test_post_agent_empty_answer_sends_nothing(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda *a, **kw: sent.append(a) or {"ok": True},
    )

    async def empty_agent(project_id, text, from_phone):
        return ""

    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", empty_agent)

    body = _payload({"from": SENDER, "type": "text", "text": {"body": "hello?"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200
    assert sent == []


def test_post_send_failure_swallowed(client, monkeypatch):
    """send_message raising must never bubble out of the background task."""

    def broken_send(*a, **kw):
        raise RuntimeError("meta is down")

    monkeypatch.setattr("restai.routers.whatsapp_webhook.send_message", broken_send)

    async def ok_agent(project_id, text, from_phone):
        return "fine"

    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", ok_agent)

    body = _payload({"from": SENDER, "type": "text", "text": {"body": "hi"}})
    r = _post(client, body, sig=_sign(body))
    assert r.status_code == 200


# ---------------------------------------------------------------- connection test endpoint


def test_whatsapp_test_unknown_project(client):
    r = client.post("/projects/99999999/whatsapp/test", auth=ADMIN)
    assert r.status_code == 404


def test_whatsapp_test_unconfigured(client):
    _set_options({})  # strip whatsapp_* keys
    r = client.post(f"/projects/{state['project_id']}/whatsapp/test", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "not configured" in data["error"]
    _set_options(_default_options())


def test_whatsapp_test_configured(client, monkeypatch):
    captured = {}

    def fake_validate(token, phone_id):
        captured["token"] = token
        captured["phone_id"] = phone_id
        return {"ok": True, "display_phone_number": "+351 000 000 000"}

    monkeypatch.setattr("restai.routers.whatsapp_webhook.validate_token", fake_validate)

    r = client.post(f"/projects/{state['project_id']}/whatsapp/test", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Credentials are decrypted before hitting Meta.
    assert captured["token"] == ACCESS_TOKEN
    assert captured["phone_id"] == PHONE_ID


# ---------------------------------------------------------------- allowlist parsing


def test_parse_allowlist_variants():
    from restai.routers.whatsapp_webhook import _parse_allowlist

    assert _parse_allowlist("") == set()
    assert _parse_allowlist("+351911111111") == {"351911111111"}
    assert _parse_allowlist("111,222;333 , +444") == {"111", "222", "333", "444"}
    assert _parse_allowlist(" , ; ") == set()


# ---------------------------------------------------------------- cleanup


def test_cleanup(client):
    client.delete(f"/projects/{state['project_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
