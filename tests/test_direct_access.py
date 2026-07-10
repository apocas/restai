import random
import types
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


# ── stub LLM helpers (drive the translated path without a real provider) ──
class _FakeMsg:
    def __init__(self, content):
        self.content = content
        self.additional_kwargs = {}


class _FakeResp:
    def __init__(self, content, usage=True, finish="stop"):
        self.message = _FakeMsg(content)
        self.raw = {"choices": [{"finish_reason": finish}]}
        if usage:
            self.raw["usage"] = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


class _FakeLLM:
    def chat(self, messages, **kw):
        return _FakeResp("Hello from stub")

    def stream_chat(self, messages, **kw):
        for i, d in enumerate(["Hel", "lo"]):
            raw = {"choices": [{"finish_reason": "stop" if i == 1 else None}]}
            if i == 1:
                raw["usage"] = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
            yield types.SimpleNamespace(delta=d, message=_FakeMsg(""), raw=raw)


def _stub_llm_obj(class_name="Ollama"):
    props = types.SimpleNamespace(class_name=class_name, input_cost=1.0, output_cost=2.0, options={})
    return types.SimpleNamespace(llm=_FakeLLM(), props=props)


class _FakeEmbedding:
    def get_text_embedding_batch(self, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def _patch_llm(monkeypatch, class_name="Ollama"):
    monkeypatch.setattr(app.state.brain, "get_llm", lambda name, db: _stub_llm_obj(class_name))


def _patch_embedding(monkeypatch):
    monkeypatch.setattr(app.state.brain, "get_embedding", lambda name, db: types.SimpleNamespace(embedding=_FakeEmbedding()))

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
team_name = f"direct_team_{_suffix}"
llm_name = f"direct_llm_{_suffix}"
test_username = f"direct_user_{_suffix}"
test_password = "direct_test_pass"
team_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, LLM, user, and wire them together."""
    global team_id
    resp = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)

    resp = client.post(
        "/users",
        json={"username": test_username, "password": test_password, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)

    resp = client.post(
        "/teams",
        json={"name": team_name, "users": [test_username], "admins": [], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]


def test_list_models_admin(client):
    """Admin should see all models including the test LLM."""
    resp = client.get("/direct/models", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "llms" in data
    assert isinstance(data["llms"], list)
    names = [l["name"] for l in data["llms"]]
    assert llm_name in names


def test_list_models_user(client):
    """Non-admin user should see LLMs filtered by team membership."""
    resp = client.get("/direct/models", auth=(test_username, test_password))
    assert resp.status_code == 200
    data = resp.json()
    assert "llms" in data
    assert isinstance(data["llms"], list)
    names = [l["name"] for l in data["llms"]]
    assert llm_name in names


def test_chat_completions_no_model_openai_error_envelope(client):
    """Unknown model → 404 in OpenAI's error envelope (not RESTai's {detail})."""
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "nonexistent_model_xyz", "messages": [{"role": "user", "content": "hi"}]},
        auth=ADMIN,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body and "detail" not in body
    assert body["error"]["type"] == "invalid_request_error"
    assert body["error"]["code"] == "model_not_found"


def test_chat_completion_success(client, monkeypatch):
    """Translated-path non-stream completion returns OpenAI shape + real usage."""
    _patch_llm(monkeypatch)
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "stub", "messages": [{"role": "user", "content": "hi"}]},
        auth=ADMIN,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "Hello from stub"
    assert body["choices"][0]["finish_reason"] == "stop"
    # real usage came from the (stub) provider raw.usage, not the estimate
    assert body["usage"]["prompt_tokens"] == 11
    assert body["usage"]["completion_tokens"] == 7
    assert body["usage"]["total_tokens"] == 18
    assert body["system_fingerprint"].startswith("restai")


def test_chat_completion_stream(client, monkeypatch):
    """Streaming emits a leading role chunk, content deltas, and [DONE]."""
    _patch_llm(monkeypatch)
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "stub", "messages": [{"role": "user", "content": "hi"}],
              "stream": True, "stream_options": {"include_usage": True}},
        auth=ADMIN,
    )
    assert resp.status_code == 200
    text = resp.text
    assert '"role": "assistant"' in text     # leading role chunk
    assert '"content": "Hel"' in text and '"content": "lo"' in text
    assert '"chat.completion.chunk"' in text
    assert '"usage"' in text                  # include_usage honored
    assert "data: [DONE]" in text


def test_completions_legacy(client, monkeypatch):
    """Legacy /v1/completions returns text_completion shape."""
    _patch_llm(monkeypatch)
    resp = client.post(
        "/v1/completions",
        json={"model": "stub", "prompt": "hello"},
        auth=ADMIN,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "text_completion"
    assert body["choices"][0]["text"] == "Hello from stub"


def test_v1_models_list_and_retrieve(client):
    """GET /v1/models lists LLMs; GET /v1/models/{id} retrieves one; unknown → 404 envelope."""
    resp = client.get("/v1/models", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert llm_name in [m["id"] for m in data["data"]]

    resp = client.get(f"/v1/models/{llm_name}", auth=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["id"] == llm_name

    resp = client.get("/v1/models/does_not_exist_xyz", auth=ADMIN)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "model_not_found"


def test_embeddings_float_and_base64(client, monkeypatch):
    """/v1/embeddings returns float vectors, and base64 strings when asked."""
    _patch_embedding(monkeypatch)
    resp = client.post("/v1/embeddings", json={"model": "stub-emb", "input": ["a", "b"]}, auth=ADMIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list" and len(body["data"]) == 2
    assert isinstance(body["data"][0]["embedding"], list)

    resp = client.post(
        "/v1/embeddings",
        json={"model": "stub-emb", "input": "a", "encoding_format": "base64", "dimensions": 2},
        auth=ADMIN,
    )
    assert resp.status_code == 200
    emb = resp.json()["data"][0]["embedding"]
    assert isinstance(emb, str)  # base64 packed


def test_moderations(client):
    """/v1/moderations flags PII, passes clean text."""
    resp = client.post("/v1/moderations", json={"input": "just a normal sentence"}, auth=ADMIN)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["flagged"] is False

    resp = client.post("/v1/moderations", json={"input": "email me at a@b.com"}, auth=ADMIN)
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["flagged"] is True
    assert result["categories"]["pii"] is True


def test_cleanup(client):
    client.delete(f"/users/{test_username}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
    client.delete(f"/teams/{team_id}", auth=ADMIN)
