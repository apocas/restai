"""WhatsApp Business Cloud API webhook tests.

Covers:
* GET subscription handshake — happy path + bad verify_token → 403.
* POST signature verification — bad sig → 401.
* POST routing by phone_number_id — unknown id → 200 ack, no agent run.
* Allowlist gate — sender outside allowlist → 200 ack, "not authorized"
  reply queued.
* Non-text message → 200 ack, polite "text only" reply queued.

The agent dispatch is patched out in every test that exercises a
project-bound message because we don't want to spin up a real LLM, and
because TestClient's BackgroundTasks runs synchronously after the
response — letting the real chat pipeline run would either blow up on
missing LLM config or take seconds.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import get_db_wrapper
from restai.main import app
from restai.utils.crypto import encrypt_field


AUTH = ("admin", RESTAI_DEFAULT_PASSWORD)

# Constants used in the fake project we set up. These are intentionally
# distinctive so a stale row from a prior run is easy to spot in the DB.
PHONE_NUMBER_ID = "wa_test_phone_999000111"
ACCESS_TOKEN = "wa_test_access_token_xyz"
APP_SECRET = "wa_test_app_secret_super_random"
VERIFY_TOKEN = "wa_test_verify_token_abc"
ALLOWED_SENDER = "351900000001"
BLOCKED_SENDER = "999999999999"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def project_id(client):
    """Create (or find) an agent project, then write WhatsApp options
    directly into the DB so we don't depend on the project create API
    accepting our new keys (it does, but bypassing keeps the test
    hermetic to model-validator changes)."""
    teams = client.get("/teams", auth=AUTH).json().get("teams", []) or []
    if not teams:
        pytest.skip("no team available to bootstrap project")
    team_id = teams[0]["id"]

    name = "whatsapp_webhook_test_project"
    # Find existing by name via the list endpoint (per-id GET requires int).
    listing = client.get("/projects", auth=AUTH).json().get("projects", []) or []
    existing = next((p for p in listing if p.get("name") == name), None)
    if existing:
        pid = existing["id"]
    else:
        # Pick whatever LLM is registered. In CI / fresh dev DB the
        # default seed includes one; if not, skip cleanly.
        info = client.get("/info", auth=AUTH).json()
        llms = info.get("llms") or []
        llm_name = llms[0].get("name") if llms else None
        if not llm_name:
            pytest.skip("no LLMs configured — cannot bootstrap project")
        resp = client.post(
            "/projects",
            json={"name": name, "type": "agent", "llm": llm_name, "team_id": team_id},
            auth=AUTH,
        )
        if resp.status_code not in (200, 201):
            pytest.skip(f"could not create test project: {resp.status_code} {resp.text}")
        pid = resp.json()["id"]

    # Write WhatsApp options directly: secrets must be encrypted at rest
    # because the webhook handler decrypts them on the way out.
    db = get_db_wrapper()
    try:
        from restai.models.databasemodels import ProjectDatabase
        proj = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == pid).first()
        opts = json.loads(proj.options or "{}")
        opts.update({
            "whatsapp_phone_number_id": PHONE_NUMBER_ID,
            "whatsapp_access_token": encrypt_field(ACCESS_TOKEN),
            "whatsapp_app_secret": encrypt_field(APP_SECRET),
            "whatsapp_verify_token": encrypt_field(VERIFY_TOKEN),
            "whatsapp_allowed_phone_numbers": ALLOWED_SENDER,
        })
        proj.options = json.dumps(opts)
        db.db.commit()
    finally:
        db.db.close()

    return pid


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_payload(from_phone: str = ALLOWED_SENDER, msg_type: str = "text",
                   text: str = "hello bot") -> bytes:
    msg = {"from": from_phone, "id": "wamid.test", "type": msg_type}
    if msg_type == "text":
        msg["text"] = {"body": text}
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "biz_account_id",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                    "messages": [msg],
                },
            }],
        }],
    }).encode()


# ─── GET handshake ──────────────────────────────────────────────────────

def test_verify_handshake_ok(client, project_id):
    r = client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.challenge": "challenge_value_42",
        "hub.verify_token": VERIFY_TOKEN,
    })
    assert r.status_code == 200, r.text
    assert r.text == "challenge_value_42"


def test_verify_handshake_bad_token(client, project_id):
    r = client.get("/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.challenge": "challenge_value_42",
        "hub.verify_token": "definitely_wrong_token",
    })
    assert r.status_code == 403


def test_verify_handshake_missing_params(client):
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe"})
    assert r.status_code == 400


# ─── POST routing & signature ───────────────────────────────────────────

def test_post_unknown_phone_number_id_acks_silently(client):
    """If no project owns the phone_number_id, signature is never checked
    (we don't have a secret to check it with). Still ack 200 so Meta
    doesn't retry — it's an inbound for a project that was deleted."""
    body = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": "phone_id_we_do_not_know"},
            "messages": [{"from": ALLOWED_SENDER, "type": "text", "text": {"body": "hi"}}],
        }}]}],
    }).encode()
    r = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=00", "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_post_bad_signature_returns_401(client, project_id, monkeypatch):
    body = _make_payload()
    sent_messages = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda *a, **kw: sent_messages.append(a) or {"ok": True},
    )

    r = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=tampered_sig", "content-type": "application/json"},
    )
    assert r.status_code == 401
    assert sent_messages == [], "no outbound on bad sig"


def test_post_text_message_dispatches_agent(client, project_id, monkeypatch):
    """Valid signature + allowlisted sender + text → agent runs and
    reply is sent. We mock both the agent dispatch and the outbound
    send so the test stays hermetic."""
    sent_messages = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda token, pid, to, text: sent_messages.append((token, pid, to, text)) or {"ok": True},
    )

    async def fake_run_agent(project_id, text, from_phone):
        return f"echo: {text}"
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook._run_agent",
        fake_run_agent,
    )

    body = _make_payload(text="hello bot")
    sig = _sign(body)
    r = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert sent_messages, "agent reply should have been queued"
    token, pid, to, reply = sent_messages[-1]
    assert token == ACCESS_TOKEN
    assert pid == PHONE_NUMBER_ID
    assert to == ALLOWED_SENDER
    assert reply == "echo: hello bot"


def test_post_blocked_sender_replies_unauthorized(client, project_id, monkeypatch):
    sent_messages = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda token, pid, to, text: sent_messages.append((to, text)) or {"ok": True},
    )
    agent_called = []
    async def fake_run_agent(project_id, text, from_phone):
        agent_called.append(from_phone)
        return "should not happen"
    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", fake_run_agent)

    body = _make_payload(from_phone=BLOCKED_SENDER, text="hello")
    sig = _sign(body)
    r = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert agent_called == [], "agent must not run for blocked senders"
    assert sent_messages, "polite reject should be queued"
    to, reply = sent_messages[-1]
    assert to == BLOCKED_SENDER
    assert "not authorized" in reply.lower()


def test_post_non_text_message_replies_text_only_notice(client, project_id, monkeypatch):
    sent_messages = []
    monkeypatch.setattr(
        "restai.routers.whatsapp_webhook.send_message",
        lambda token, pid, to, text: sent_messages.append((to, text)) or {"ok": True},
    )
    agent_called = []
    async def fake_run_agent(project_id, text, from_phone):
        agent_called.append(from_phone)
        return "should not happen"
    monkeypatch.setattr("restai.routers.whatsapp_webhook._run_agent", fake_run_agent)

    body = _make_payload(msg_type="image")
    sig = _sign(body)
    r = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert agent_called == [], "agent must not run for non-text messages"
    assert sent_messages, "text-only notice should be queued"
    to, reply = sent_messages[-1]
    assert to == ALLOWED_SENDER
    assert "text" in reply.lower()


# ─── verify_signature unit tests (no network) ──────────────────────────

def test_verify_signature_rejects_missing_header():
    from restai.whatsapp import verify_signature
    assert verify_signature(b"body", None, "secret") is False
    assert verify_signature(b"body", "", "secret") is False


def test_verify_signature_rejects_bad_prefix():
    from restai.whatsapp import verify_signature
    assert verify_signature(b"body", "md5=abcd", "secret") is False


def test_verify_signature_accepts_valid_hmac():
    from restai.whatsapp import verify_signature
    body = b'{"hello":"world"}'
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, "secret") is True


def test_verify_signature_constant_time_mismatch():
    from restai.whatsapp import verify_signature
    body = b'{"hello":"world"}'
    sig = "sha256=" + hmac.new(b"different_key", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, "secret") is False
