"""Tests for GET /projects/{id}/logs/conversation/{chat_id}/details — the
full conversation inspector behind the log viewer's Details button."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from restai.main import app
from restai.config import RESTAI_DEFAULT_PASSWORD
from starlette.testclient import TestClient

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = uuid.uuid4().hex[:8]
llm_name = f"cd_llm_{suffix}"
team_name = f"cd-team-{suffix}"
project_name = f"cd-proj-{suffix}"
chat_id = f"cd-chat-{suffix}"

project_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def setup(client):
    """LLM + team + project via the API, then OutputDatabase rows directly."""
    global project_id
    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": '{"model": "gpt-4o-mini", "api_key": "sk-fake"}',
            "privacy": "private",
            "type": "chat",
        },
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/teams",
        json={"name": team_name, "users": ["admin"], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    team_id = r.json()["id"]
    r = client.post(
        "/projects",
        json={"name": project_name, "llm": llm_name, "type": "agent", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    project_id = r.json()["project"]

    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase

    base = datetime.now(timezone.utc)
    trace1 = json.dumps([
        {"tool": "llm_turn", "args": '{"turn": 1, "llm": "%s"}' % llm_name,
         "latency_ms": 900, "status": "ok", "error": None},
        {"tool": "search", "args": "{}", "latency_ms": 120, "status": "ok", "error": None},
    ])
    trace2 = json.dumps([
        {"tool": "llm_turn", "args": '{"turn": 1, "llm": "%s"}' % llm_name,
         "latency_ms": 700, "status": "ok", "error": None},
        {"tool": "search", "args": "{}", "latency_ms": 300, "status": "error", "error": "boom"},
        {"tool": "llm_fallback", "args": '{"from": "a", "to": "b"}',
         "latency_ms": None, "status": "ok", "error": "429"},
    ])
    db = DBWrapper()
    try:
        for i, (trace, status, stop) in enumerate([
            (trace1, "success", None),
            (trace2, "error", "max_time"),
        ]):
            db.db.add(OutputDatabase(
                project_id=project_id,
                chat_id=chat_id,
                question=f"q{i}",
                answer=f"a{i}",
                llm=llm_name,
                date=base + timedelta(seconds=i),
                input_tokens=100 + i,
                output_tokens=10 + i,
                input_cost=0.001,
                output_cost=0.0005,
                latency_ms=1000 + i * 500,
                status=status,
                stop_reason=stop,
                retries=i,
                fallbacks=1 if i else None,
                token_accuracy="high",
                tool_trace=trace,
            ))
        db.db.commit()
    finally:
        db.db.close()
    yield


def test_details_returns_turns_and_rollups(client):
    r = client.get(
        f"/projects/{project_id}/logs/conversation/{chat_id}/details", auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()

    s = data["summary"]
    assert s["turns"] == 2
    assert s["input_tokens"] == 201
    assert s["output_tokens"] == 21
    assert s["total_tokens"] == 222
    assert s["error_turns"] == 1
    assert s["models"] == [llm_name]
    assert s["avg_latency_ms"] == 1250
    assert s["started_at"] <= s["last_at"]

    turns = data["turns"]
    assert [t["question"] for t in turns] == ["q0", "q1"]
    assert turns[1]["stop_reason"] == "max_time"
    assert turns[1]["retries"] == 1
    assert turns[1]["fallbacks"] == 1
    assert turns[1]["token_accuracy"] == "high"
    assert isinstance(turns[0]["tool_trace"], list)
    assert turns[0]["tool_trace"][0]["tool"] == "llm_turn"

    tools = data["tools"]
    by_name = {t["tool"]: t for t in tools["tools"]}
    assert by_name["search"]["calls"] == 2
    assert by_name["search"]["errors"] == 1
    assert tools["llm_turns"]["count"] == 2
    assert tools["fallbacks"] == 1


def test_details_unknown_chat_404(client):
    r = client.get(
        f"/projects/{project_id}/logs/conversation/nope-{suffix}/details", auth=ADMIN,
    )
    assert r.status_code == 404


def test_details_requires_project_access(client):
    r = client.get(
        f"/projects/{project_id}/logs/conversation/{chat_id}/details",
    )
    assert r.status_code in (401, 403)
