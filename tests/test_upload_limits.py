"""Upload-ceiling tests: the body-size middleware, the `max_upload_size_mb`
setting round-trip, and the chat-attachment cap.

The point of the middleware is that an oversized body is refused *before* it
is read into memory, so these assert on the response the client gets rather
than on RSS — measuring memory in-process is unreliable and the property that
actually matters (no `.read()` before the check) is structural.
"""
from __future__ import annotations

import base64
import uuid

import pytest
from fastapi.testclient import TestClient

from restai import config
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.middleware import (
    _JSON_BODY_LIMIT_BYTES,
    _MULTIPART_SLACK_BYTES,
    _limit_for_path,
)

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── path → limit resolution ───────────────────────────────────────────────

def test_upload_paths_get_the_configured_ceiling(monkeypatch):
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 7 * 1024 * 1024)
    expected = 7 * 1024 * 1024 + _MULTIPART_SLACK_BYTES
    for path in (
        "/projects/1/embeddings/ingest/upload",
        "/projects/1/ingest-bulk",
        "/projects/1/attachments",
        "/v1/audio/transcriptions",
    ):
        assert _limit_for_path(path) == expected, path


def test_non_upload_paths_get_the_json_ceiling(monkeypatch):
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 7 * 1024 * 1024)
    for path in ("/projects/1/chat", "/v1/chat/completions", "/settings"):
        assert _limit_for_path(path) == _JSON_BODY_LIMIT_BYTES, path


def test_multipart_slack_admits_a_file_exactly_at_the_ceiling(monkeypatch):
    """The multipart envelope (boundaries + sibling fields) is bigger than the
    file, so the ceiling has to allow some slack or an exactly-max file 413s."""
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 5 * 1024 * 1024)
    assert _limit_for_path("/projects/1/ingest-bulk") > config.max_upload_bytes()


# ── middleware enforcement ────────────────────────────────────────────────

def test_oversized_json_body_is_rejected_with_413(client, monkeypatch):
    import restai.middleware as mw

    monkeypatch.setattr(mw, "_JSON_BODY_LIMIT_BYTES", 4096)
    r = client.post(
        "/projects/1/chat",
        json={"question": "x" * 20000},
        auth=ADMIN,
    )
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower()


def test_v1_paths_keep_the_openai_error_envelope(client, monkeypatch):
    """OpenAI SDKs parse `error.type`; a bare `detail` breaks them."""
    import restai.middleware as mw

    monkeypatch.setattr(mw, "_JSON_BODY_LIMIT_BYTES", 4096)
    r = client.post(
        "/v1/chat/completions",
        json={"model": "nope", "messages": [{"role": "user", "content": "x" * 20000}]},
        auth=ADMIN,
    )
    assert r.status_code == 413, r.text
    body = r.json()
    assert "error" in body and "detail" not in body
    # Not `api_error` — that reads as retryable and clients would re-upload.
    assert body["error"]["type"] == "invalid_request_error"


def test_body_under_the_ceiling_reaches_the_app(client, monkeypatch):
    """The guard must not intercept normal traffic: a small body still gets
    the app's own response (404 for a missing project), not a 413."""
    import restai.middleware as mw

    monkeypatch.setattr(mw, "_JSON_BODY_LIMIT_BYTES", 1024 * 1024)
    r = client.post("/projects/99999999/chat", json={"question": "hi"}, auth=ADMIN)
    assert r.status_code != 413
    assert r.status_code in (401, 403, 404, 422, 500)


def test_get_requests_are_never_body_checked(client, monkeypatch):
    import restai.middleware as mw

    monkeypatch.setattr(mw, "_JSON_BODY_LIMIT_BYTES", 1)
    r = client.get("/info", auth=ADMIN)
    assert r.status_code == 200


# ── setting round-trip ────────────────────────────────────────────────────

def test_max_upload_size_setting_round_trip(client):
    original = client.get("/settings", auth=ADMIN).json().get("max_upload_size_mb")
    try:
        r = client.patch("/settings", json={"max_upload_size_mb": 321}, auth=ADMIN)
        assert r.status_code == 200, r.text

        # Read back through the settings API...
        assert client.get("/settings", auth=ADMIN).json()["max_upload_size_mb"] == 321
        # ...through /info, which is what clients pre-validate against...
        assert client.get("/info", auth=ADMIN).json()["max_upload_size_mb"] == 321
        # ...and through config's DB read-through, which is what a *second*
        # uvicorn worker would see. There is no in-process mirror by design.
        assert config.MAX_UPLOAD_SIZE_MB == 321
        assert config.max_upload_bytes() == 321 * 1024 * 1024
    finally:
        if original is not None:
            client.patch("/settings", json={"max_upload_size_mb": original}, auth=ADMIN)


def test_max_upload_size_rejects_non_positive(client):
    r = client.patch("/settings", json={"max_upload_size_mb": 0}, auth=ADMIN)
    assert r.status_code == 422


# ── chat attachment cap ───────────────────────────────────────────────────

def test_b64_decoded_size_is_exact():
    from restai.helper import _b64_decoded_size

    for n in (0, 1, 2, 3, 100, 3000, 4097):
        payload = base64.b64encode(b"x" * n).decode()
        assert _b64_decoded_size(payload) == n, n


def test_attachment_over_ceiling_is_refused(monkeypatch):
    from fastapi import HTTPException

    from restai.helper import enforce_attachment_limits
    from restai.models.models import ChatModel, FileAttachment

    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1024)
    big = base64.b64encode(b"z" * 5000).decode()
    chat = ChatModel(
        question="q",
        files=[FileAttachment(name="big.bin", content=big, mime_type="application/octet-stream")],
    )
    with pytest.raises(HTTPException) as exc:
        enforce_attachment_limits(chat)
    assert exc.value.status_code == 413


def test_attachment_under_ceiling_passes(monkeypatch):
    from restai.helper import enforce_attachment_limits
    from restai.models.models import ChatModel, FileAttachment

    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1024 * 1024)
    small = base64.b64encode(b"z" * 500).decode()
    chat = ChatModel(
        question=f"q-{uuid.uuid4().hex[:6]}",
        files=[FileAttachment(name="ok.bin", content=small, mime_type="application/octet-stream")],
    )
    enforce_attachment_limits(chat)  # must not raise


def test_oversized_inline_image_is_refused(monkeypatch):
    """`ChatModel.image` carries no length bound of its own — the ceiling is
    the only thing standing between a base64 image and the worker's heap."""
    from fastapi import HTTPException

    from restai.helper import enforce_attachment_limits
    from restai.models.models import ChatModel

    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1024)
    chat = ChatModel(question="q", image=base64.b64encode(b"i" * 5000).decode())
    with pytest.raises(HTTPException) as exc:
        enforce_attachment_limits(chat)
    assert exc.value.status_code == 413


def test_image_url_is_not_size_checked(monkeypatch):
    """A URL in `.image` is fetched later behind the SSRF guard; measuring the
    URL string as if it were base64 would reject perfectly ordinary links."""
    from restai.helper import enforce_attachment_limits
    from restai.models.models import ChatModel

    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1)
    chat = ChatModel(question="q", image="https://example.com/a-fairly-long-image-url.png")
    enforce_attachment_limits(chat)  # must not raise
