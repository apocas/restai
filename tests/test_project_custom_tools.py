"""Agent-created tools CRUD tests for restai/routers/projects/tools.py.

Tools are normally minted by the agent's `create_tool` builtin, so the
list/toggle/update/delete surface is seeded directly through
`DBWrapper.upsert_project_tool`. The Docker sandbox validation on PUT is
exercised in all three shapes: absent (warning), passing, and failing.
Also covers the block-workspace / system-prompt generators' 400 paths.
"""
import json
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"ctool_llm_{suffix}"
team_name = f"ctool_team_{suffix}"
agent_proj_name = f"ctool_agent_{suffix}"
block_proj_name = f"ctool_block_{suffix}"
tool_name = f"ctool_tool_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["llm_id"] = r.json()["id"]

    r = client.post("/teams", json={"name": team_name, "llms": [llm_name]}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": agent_proj_name, "llm": llm_name, "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["agent_id"] = r.json()["project"]

    r = client.post(
        "/projects",
        json={"name": block_proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["block_id"] = r.json()["project"]

    # Seed a tool the way the agent builtin would.
    db = open_db_wrapper()
    try:
        db.upsert_project_tool(
            project_id=state["agent_id"],
            name=tool_name,
            description="adds two numbers",
            parameters=json.dumps({"a": "int", "b": "int"}),
            code="print(1 + 2)",
        )
    finally:
        db.db.close()


def test_list_tools(client):
    r = client.get(f"/projects/{state['agent_id']}/custom-tools", auth=ADMIN)
    assert r.status_code == 200
    tools = r.json()["tools"]
    assert len(tools) == 1
    t = tools[0]
    assert t["name"] == tool_name
    assert t["description"] == "adds two numbers"
    assert t["enabled"] is True
    assert t["code"] == "print(1 + 2)"
    assert t["created_at"] is not None


def test_list_tools_empty_project(client):
    r = client.get(f"/projects/{state['block_id']}/custom-tools", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["tools"] == []


def test_toggle_tool(client):
    r = client.patch(f"/projects/{state['agent_id']}/custom-tools/{tool_name}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"name": tool_name, "enabled": False}

    r = client.patch(f"/projects/{state['agent_id']}/custom-tools/{tool_name}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_toggle_unknown_tool(client):
    r = client.patch(f"/projects/{state['agent_id']}/custom-tools/nope_{suffix}", auth=ADMIN)
    assert r.status_code == 404


def test_update_without_docker_warns(client):
    # Docker is disabled in the test env -> brain.docker_manager is None.
    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"code": "print(2 + 2)"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["code"] == "print(2 + 2)"
    assert data["description"] == "adds two numbers"  # untouched fields kept
    assert "warning" in data
    assert "Docker" in data["warning"]


def test_update_with_docker_validation_ok(client, monkeypatch):
    import restai.docker as docker_mod

    calls = []

    def fake_run_script(chat_id, script, stdin_data=""):
        calls.append((chat_id, script, stdin_data))
        return "4"

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(docker_mod, "run_script", fake_run_script)

    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"code": "print(int(args.get('a', 2)) * 2)", "description": "doubles a"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "warning" not in data
    assert data["description"] == "doubles a"
    assert len(calls) == 1
    assert calls[0][0] == "ephemeral"
    assert "print(int(args.get('a', 2)) * 2)" in calls[0][1]


def test_update_with_docker_validation_failure(client, monkeypatch):
    import restai.docker as docker_mod

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(docker_mod, "run_script", lambda *a, **k: "ERROR: NameError: nope")

    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"code": "nope()"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Code validation failed" in r.json()["detail"]

    # Failed validation must not overwrite the stored code.
    r = client.get(f"/projects/{state['agent_id']}/custom-tools", auth=ADMIN)
    assert r.json()["tools"][0]["code"] != "nope()"


def test_update_invalid_parameters_json(client):
    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"parameters": "{not json"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Invalid parameters JSON" in r.json()["detail"]


def test_update_empty_description_rejected(client):
    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"description": "   "},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Description is required" in r.json()["detail"]


def test_update_empty_code_rejected(client):
    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/{tool_name}",
        json={"code": "   "},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Code is required" in r.json()["detail"]


def test_update_unknown_tool(client):
    r = client.put(
        f"/projects/{state['agent_id']}/custom-tools/nope_{suffix}",
        json={"code": "print(1)"},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_delete_tool(client):
    r = client.delete(f"/projects/{state['agent_id']}/custom-tools/{tool_name}", auth=ADMIN)
    assert r.status_code == 200
    assert tool_name in r.json()["detail"]

    r = client.delete(f"/projects/{state['agent_id']}/custom-tools/{tool_name}", auth=ADMIN)
    assert r.status_code == 404

    r = client.get(f"/projects/{state['agent_id']}/custom-tools", auth=ADMIN)
    assert r.json()["tools"] == []


# ------------------------------------------------------- generators (400 paths)


def test_block_generate_rejects_non_block_project(client):
    r = client.post(
        f"/projects/{state['agent_id']}/block/generate",
        json={"description": "sum two numbers"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "block projects" in r.json()["detail"]


def test_block_generate_without_system_llm(client):
    # Force system_llm empty for this test, restore after.
    original = client.get("/settings", auth=ADMIN).json().get("system_llm", "")
    try:
        if original:
            client.patch("/settings", json={"system_llm": ""}, auth=ADMIN)
        r = client.post(
            f"/projects/{state['block_id']}/block/generate",
            json={"description": "sum two numbers"},
            auth=ADMIN,
        )
        assert r.status_code == 400
        assert "system LLM" in r.json()["detail"]
    finally:
        if original:
            client.patch("/settings", json={"system_llm": original}, auth=ADMIN)


def test_system_prompt_generate_without_system_llm(client):
    original = client.get("/settings", auth=ADMIN).json().get("system_llm", "")
    try:
        if original:
            client.patch("/settings", json={"system_llm": ""}, auth=ADMIN)
        r = client.post(
            f"/projects/{state['agent_id']}/system-prompt/generate",
            json={"description": "a friendly support bot"},
            auth=ADMIN,
        )
        assert r.status_code == 400
        assert "system LLM" in r.json()["detail"]
    finally:
        if original:
            client.patch("/settings", json={"system_llm": original}, auth=ADMIN)


def test_cleanup(client):
    client.delete(f"/projects/{state['agent_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['block_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
