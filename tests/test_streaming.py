"""Tests for streaming vs non-streaming chat paths across ALL project types.

Verifies that every project type (block, app, agent) correctly returns:
  - Non-streaming: a JSON dict with the answer.
  - Streaming: SSE events (data: lines + event: close).

Block uses a passthrough workspace (output = input), app returns a
builder hint, and agent needs an LLM (may skip if none configured).
"""

import json
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = random.randint(0, 999999)
user_name = f"stream_user_{suffix}"
user_pass = "stream_pass_123"
team_name = f"stream_team_{suffix}"

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
USER = (user_name, user_pass)

block_project_id = None
app_project_id = None
agent_project_id = None
team_id = None
llm_name = None

PASSTHROUGH_WORKSPACE = {
    "blocks": {
        "blocks": [
            {
                "type": "restai_set_output",
                "inputs": {
                    "VALUE": {
                        "block": {"type": "restai_get_input"}
                    }
                },
            }
        ]
    },
    "variables": [],
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create user, team, and all three project types."""
    global block_project_id, app_project_id, agent_project_id, team_id, llm_name

    llms = client.get("/llms", auth=ADMIN)
    if llms.status_code != 200 or not llms.json():
        pytest.skip("No LLMs configured")
    llm_name = llms.json()[0]["name"]

    client.post("/users", json={"username": user_name, "password": user_pass}, auth=ADMIN)

    r = client.post(
        "/teams",
        json={"name": team_name, "users": [user_name], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201
    team_id = r.json()["id"]

    # Block project
    r = client.post(
        "/projects",
        json={"name": f"stream-block-{suffix}", "llm": llm_name, "type": "block", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code == 201
    block_project_id = r.json()["project"]
    r = client.patch(
        f"/projects/{block_project_id}",
        json={"users": [user_name], "options": {"blockly_workspace": PASSTHROUGH_WORKSPACE}},
        auth=ADMIN,
    )
    assert r.status_code == 200

    # App project
    r = client.post(
        "/projects",
        json={"name": f"stream-app-{suffix}", "llm": llm_name, "type": "app", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code == 201
    app_project_id = r.json()["project"]
    client.patch(f"/projects/{app_project_id}", json={"users": [user_name]}, auth=ADMIN)

    # Agent project
    r = client.post(
        "/projects",
        json={"name": f"stream-agent-{suffix}", "llm": llm_name, "type": "agent", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code == 201
    agent_project_id = r.json()["project"]
    client.patch(f"/projects/{agent_project_id}", json={"users": [user_name]}, auth=ADMIN)


# ── Block project ──────────────────────────────────────────────────────

def test_block_non_streaming(client):
    r = client.post(
        f"/projects/{block_project_id}/chat",
        json={"question": "echo block"},
        auth=USER,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict), f"Expected dict, got {type(data)}: {data}"
    assert data.get("answer") == "echo block"
    assert data.get("type") == "block"


def test_block_streaming(client):
    r = client.post(
        f"/projects/{block_project_id}/chat",
        json={"question": "echo block stream", "stream": True},
        auth=USER,
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200
    _assert_sse_has_answer(r.text, "echo block stream", "block")


# ── App project ────────────────────────────────────────────────────────

def test_app_non_streaming(client):
    r = client.post(
        f"/projects/{app_project_id}/chat",
        json={"question": "hello app"},
        auth=USER,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict), f"Expected dict, got {type(data)}: {data}"
    assert "app-builder project" in data.get("answer", "").lower()
    assert data.get("type") == "app"


def test_app_streaming(client):
    r = client.post(
        f"/projects/{app_project_id}/chat",
        json={"question": "hello app stream", "stream": True},
        auth=USER,
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200
    final = _parse_final_sse(r.text)
    assert final is not None, f"No final answer in SSE: {r.text}"
    assert "app-builder project" in final["answer"].lower()
    assert final["type"] == "app"


# ── Agent project ──────────────────────────────────────────────────────

def test_agent_non_streaming(client):
    """Agent non-streaming must return a dict, not SSE strings."""
    r = client.post(
        f"/projects/{agent_project_id}/chat",
        json={"question": "say hello"},
        auth=USER,
    )
    # Agent needs a working LLM; if the LLM fails, we still get a dict
    # (with an error message as the answer), never a raw string.
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict), f"Expected dict, got {type(data)}: {r.text[:500]}"
    assert "answer" in data, f"Missing 'answer' key in: {list(data.keys())}"


def test_agent_streaming(client):
    """Agent streaming must return SSE events, not a raw dict."""
    r = client.post(
        f"/projects/{agent_project_id}/chat",
        json={"question": "say hello", "stream": True},
        auth=USER,
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200
    body = r.text
    data_lines = [l for l in body.split("\n") if l.startswith("data:")]
    assert len(data_lines) >= 1, f"No SSE data lines in agent response: {body[:500]}"

    final = _parse_final_sse(body)
    assert final is not None, f"No final answer SSE event: {body[:500]}"
    assert "answer" in final


# ── /question shim (block) ─────────────────────────────────────────────

def test_question_shim_non_streaming(client):
    r = client.post(
        f"/projects/{block_project_id}/question",
        json={"question": "echo question"},
        auth=USER,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert data.get("answer") == "echo question"


def test_question_shim_streaming(client):
    r = client.post(
        f"/projects/{block_project_id}/question",
        json={"question": "echo q-stream", "stream": True},
        auth=USER,
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 200
    final = _parse_final_sse(r.text)
    assert final is not None
    assert final["answer"] == "echo q-stream"


# ── Helpers ────────────────────────────────────────────────────────────

def _parse_final_sse(body: str):
    for line in body.split("\n"):
        if line.startswith("data:"):
            try:
                payload = json.loads(line.removeprefix("data:").strip())
                if "answer" in payload:
                    return payload
            except (json.JSONDecodeError, ValueError):
                pass
    return None


def _assert_sse_has_answer(body: str, expected_answer: str, expected_type: str):
    lines = [l for l in body.split("\n") if l.strip()]
    data_lines = [l for l in lines if l.startswith("data:")]
    assert len(data_lines) >= 1, f"No data lines in: {lines}"

    has_text = False
    has_final = False
    for dl in data_lines:
        payload = json.loads(dl.removeprefix("data:").strip())
        if "text" in payload and "answer" not in payload:
            has_text = True
        if "answer" in payload:
            has_final = True
            assert payload["answer"] == expected_answer
            assert payload["type"] == expected_type

    assert has_text, f"No text delta SSE event in: {lines}"
    assert has_final, f"No final answer SSE event in: {lines}"

    close_lines = [l for l in lines if l.startswith("event:") and "close" in l]
    assert len(close_lines) >= 1, f"No event: close in: {lines}"


# ── Cleanup ────────────────────────────────────────────────────────────

def test_cleanup(client):
    for pid in [block_project_id, app_project_id, agent_project_id]:
        if pid:
            client.delete(f"/projects/{pid}", auth=ADMIN)
    client.delete(f"/teams/{team_name}", auth=ADMIN)
    client.delete(f"/users/{user_name}", auth=ADMIN)
