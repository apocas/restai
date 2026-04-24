"""Tests for the send_email + send_sms builtin tools.

Covers the happy path with mocked transports, plus precondition errors
(missing project context, missing config, missing recipient) so the
agent gets a clear ERROR string instead of an unhandled exception when
an admin forgets a field.

The tools do their `import smtplib` / `import requests` / `from
restai.database import get_db_wrapper` *inside* the function (so the
import cost is paid only when the tool is actually invoked). Tests
therefore patch the canonical module paths, not the tool module.
"""
from __future__ import annotations

import json
import smtplib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from restai.utils.crypto import encrypt_field


def _fake_project(opts: dict):
    """Stand-in for ProjectDatabase as the tools see it."""
    return SimpleNamespace(options=json.dumps(opts))


def _fake_db(project_obj):
    db = MagicMock()
    db.get_project_by_id.return_value = project_obj
    return db


# ─── send_email ─────────────────────────────────────────────────────────

def test_send_email_requires_project_context():
    from restai.llms.tools.send_email import send_email
    out = send_email("subject", "body")
    assert out.startswith("ERROR:")
    assert "project context" in out


def test_send_email_missing_smtp_config():
    from restai.llms.tools.send_email import send_email
    db = _fake_db(_fake_project({}))
    with patch("restai.database.get_db_wrapper", return_value=db):
        out = send_email("hello", "body", _brain=object(), _project_id=42)
    assert out.startswith("ERROR:")
    assert "not configured" in out


def test_send_email_missing_recipient():
    from restai.llms.tools.send_email import send_email
    db = _fake_db(_fake_project({"smtp_host": "smtp.example.com", "smtp_from": "bot@x"}))
    with patch("restai.database.get_db_wrapper", return_value=db):
        out = send_email("hi", "body", _brain=object(), _project_id=42)
    assert out.startswith("ERROR:")
    assert "recipient" in out


def test_send_email_happy_path():
    """STARTTLS path (port 587). Ensure smtplib.SMTP is constructed
    with host/port/timeout and send_message is called."""
    from restai.llms.tools.send_email import send_email
    opts = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "bot@example.com",
        "smtp_password": encrypt_field("hunter2"),
        "smtp_from": "bot@example.com",
        "email_default_to": "admin@example.com",
    }
    db = _fake_db(_fake_project(opts))

    sent = []
    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append({"host": host, "port": port, "timeout": timeout})
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self): sent.append({"starttls": True})
        def login(self, u, p): sent.append({"login": (u, p)})
        def send_message(self, msg): sent.append({"send": msg["To"]})

    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("smtplib.SMTP", _FakeSMTP):
        out = send_email("subj", "body", _brain=object(), _project_id=1)

    assert out.startswith("OK:"), out
    assert sent[0]["host"] == "smtp.example.com" and sent[0]["port"] == 587
    assert any("starttls" in s for s in sent)
    assert any("login" in s and s["login"] == ("bot@example.com", "hunter2") for s in sent)
    assert any("send" in s and s["send"] == "admin@example.com" for s in sent)


def test_send_email_implicit_tls_path():
    """Port 465 should use SMTP_SSL, not STARTTLS."""
    from restai.llms.tools.send_email import send_email
    opts = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "smtp_from": "bot@example.com",
        "email_default_to": "admin@example.com",
    }
    db = _fake_db(_fake_project(opts))

    used_ssl = {"flag": False}
    class _FakeSSL:
        def __init__(self, host, port, timeout=None):
            used_ssl["flag"] = True
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): pass
        def send_message(self, msg): pass

    class _FakePlainSMTP:
        def __init__(self, *a, **kw):
            raise AssertionError("plain SMTP must not be used on port 465")

    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("smtplib.SMTP_SSL", _FakeSSL), \
         patch("smtplib.SMTP", _FakePlainSMTP):
        out = send_email("subj", "body", _brain=object(), _project_id=1)

    assert out.startswith("OK:"), out
    assert used_ssl["flag"] is True


def test_send_email_smtp_failure_returns_error_string():
    from restai.llms.tools.send_email import send_email
    opts = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_from": "bot@example.com",
        "email_default_to": "admin@example.com",
    }
    db = _fake_db(_fake_project(opts))

    def _raise(*a, **kw):
        raise smtplib.SMTPException("relay refused")

    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("smtplib.SMTP", _raise):
        out = send_email("subj", "body", _brain=object(), _project_id=1)
    assert out.startswith("ERROR:"), out
    assert "relay refused" in out


# ─── send_sms ───────────────────────────────────────────────────────────

def test_send_sms_requires_project_context():
    from restai.llms.tools.send_sms import send_sms
    out = send_sms("hi")
    assert out.startswith("ERROR:")
    assert "project context" in out


def test_send_sms_missing_config():
    from restai.llms.tools.send_sms import send_sms
    db = _fake_db(_fake_project({}))
    with patch("restai.database.get_db_wrapper", return_value=db):
        out = send_sms("hi", _brain=object(), _project_id=1)
    assert out.startswith("ERROR:")
    assert "not configured" in out


def test_send_sms_missing_recipient():
    from restai.llms.tools.send_sms import send_sms
    db = _fake_db(_fake_project({
        "twilio_account_sid": "AC123",
        "twilio_auth_token": encrypt_field("tok"),
        "twilio_from_number": "+15551234567",
    }))
    with patch("restai.database.get_db_wrapper", return_value=db):
        out = send_sms("hi", _brain=object(), _project_id=1)
    assert out.startswith("ERROR:")
    assert "recipient" in out


def test_send_sms_happy_path():
    from restai.llms.tools.send_sms import send_sms
    db = _fake_db(_fake_project({
        "twilio_account_sid": "AC123",
        "twilio_auth_token": encrypt_field("tok_secret"),
        "twilio_from_number": "+15551234567",
        "sms_default_to": "+351912345678",
    }))

    captured = {}
    class _FakeResp:
        status_code = 201
        def json(self): return {"sid": "SMxxxx"}
    def fake_post(url, auth=None, data=None, timeout=None):
        captured.update({"url": url, "auth": auth, "data": data, "timeout": timeout})
        return _FakeResp()

    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("requests.post", fake_post):
        out = send_sms("hi from agent", _brain=object(), _project_id=1)

    assert out.startswith("OK:"), out
    assert "SMxxxx" in out
    assert "AC123/Messages.json" in captured["url"]
    assert captured["auth"] == ("AC123", "tok_secret")
    assert captured["data"] == {"From": "+15551234567", "To": "+351912345678", "Body": "hi from agent"}
    assert captured["timeout"] is not None


def test_send_sms_chunks_long_messages():
    from restai.llms.tools.send_sms import send_sms
    db = _fake_db(_fake_project({
        "twilio_account_sid": "AC123",
        "twilio_auth_token": encrypt_field("tok"),
        "twilio_from_number": "+15551234567",
        "sms_default_to": "+351912345678",
    }))

    calls = []
    class _FakeResp:
        status_code = 201
        def json(self): return {"sid": "SMxxxx"}
    def fake_post(url, auth=None, data=None, timeout=None):
        calls.append(len(data["Body"]))
        return _FakeResp()

    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("requests.post", fake_post):
        out = send_sms("x" * 3500, _brain=object(), _project_id=1)
    assert out.startswith("OK:")
    # 1600-char chunks → 3 parts (1600 + 1600 + 300).
    assert calls == [1600, 1600, 300]


def test_send_sms_twilio_error_surfaces():
    from restai.llms.tools.send_sms import send_sms
    db = _fake_db(_fake_project({
        "twilio_account_sid": "AC123",
        "twilio_auth_token": encrypt_field("tok"),
        "twilio_from_number": "+15551234567",
        "sms_default_to": "+351912345678",
    }))

    class _FakeResp:
        status_code = 400
        text = '{"message": "from number not owned"}'
        def json(self): return {"message": "from number not owned", "code": 21603}
    with patch("restai.database.get_db_wrapper", return_value=db), \
         patch("requests.post", lambda *a, **kw: _FakeResp()):
        out = send_sms("hi", _brain=object(), _project_id=1)
    assert out.startswith("ERROR:")
    assert "from number not owned" in out
