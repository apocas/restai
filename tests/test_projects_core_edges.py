"""Edge-path tests for restai/routers/projects/core.py.

Covers paths untouched by test_projects.py / test_project_clone.py:
create-validation failures (team/LLM/embedding access, duplicate name,
empty name), PATCH validation failures, guard name resolution
(guard_name / guard_output_name), /projects/health, non-RAG 400s on the
knowledge endpoints, the agent tools endpoint, chat/question input
validation and chat/stop, plus project-invitation edge branches.
"""
import base64
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"core_llm_{suffix}"
llm_outside_name = f"core_llm_out_{suffix}"
emb_name = f"core_emb_{suffix}"
emb_outside_name = f"core_emb_out_{suffix}"
team_name = f"core_team_{suffix}"
team2_name = f"core_team2_{suffix}"
member_user = f"core_member_{suffix}"
member_pass = "core_member_pass"
guard_proj_name = f"core_guard_{suffix}"
agent_proj_name = f"core_agent_{suffix}"
block_proj_name = f"core_block_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    state["llm_ids"] = []
    for name in (llm_name, llm_outside_name):
        r = client.post(
            "/llms",
            json={
                "name": name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
            },
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text
        state["llm_ids"].append(r.json()["id"])

    state["emb_ids"] = []
    for name in (emb_name, emb_outside_name):
        r = client.post(
            "/embeddings",
            json={
                "name": name,
                "class_name": "Ollama",
                "options": '{"model_name": "test-emb"}',
                "privacy": "public",
                "dimension": 768,
            },
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text
        state["emb_ids"].append(r.json()["id"])

    r = client.post(
        "/users",
        json={"username": member_user, "password": member_pass, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text

    # Team 1 has the LLM + embedding + member; team 2 has neither.
    r = client.post(
        "/teams",
        json={
            "name": team_name,
            "users": [member_user],
            "llms": [llm_name],
            "embeddings": [emb_name],
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post("/teams", json={"name": team2_name}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team2_id"] = r.json()["id"]

    # Guard project + main agent project + block project.
    r = client.post(
        "/projects",
        json={"name": guard_proj_name, "llm": llm_name, "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["guard_id"] = r.json()["project"]

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

    # Give the member access to the agent project (for permission tests).
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"users": [member_user, "admin"]},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- create


def test_create_project_name_sanitized_to_empty(client):
    # ":" passes the Pydantic safe-name check but is stripped by the
    # route's sanitizer, leaving an empty name.
    r = client.post(
        "/projects",
        json={"name": ":", "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Invalid project name" in r.json()["detail"]


def test_create_project_team_zero_rejected(client):
    r = client.post(
        "/projects",
        json={"name": f"core_x_{suffix}", "type": "block", "team_id": 0},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Team" in r.json()["detail"]


def test_create_project_unknown_team(client):
    r = client.post(
        "/projects",
        json={"name": f"core_x2_{suffix}", "type": "block", "team_id": 99999999},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_create_project_non_member_team(client):
    # member_user is not in team2.
    r = client.post(
        "/projects",
        json={"name": f"core_x3_{suffix}", "type": "block", "team_id": state["team2_id"]},
        auth=(member_user, member_pass),
    )
    assert r.status_code == 403


def test_create_project_unknown_llm(client):
    r = client.post(
        "/projects",
        json={"name": f"core_x4_{suffix}", "llm": "no_such_llm_ever", "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 404
    assert "LLM" in r.json()["detail"]


def test_create_project_llm_not_in_team(client):
    r = client.post(
        "/projects",
        json={"name": f"core_x5_{suffix}", "llm": llm_outside_name, "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 403
    assert "does not have access" in r.json()["detail"]


def test_create_rag_project_unknown_embeddings(client):
    r = client.post(
        "/projects",
        json={
            "name": f"core_x6_{suffix}",
            "llm": llm_name,
            "embeddings": "no_such_embedding_ever",
            "type": "rag",
            "team_id": state["team_id"],
        },
        auth=ADMIN,
    )
    assert r.status_code == 404
    assert "Embeddings" in r.json()["detail"]


def test_create_rag_project_embedding_not_in_team(client):
    r = client.post(
        "/projects",
        json={
            "name": f"core_x7_{suffix}",
            "llm": llm_name,
            "embeddings": emb_outside_name,
            "type": "rag",
            "team_id": state["team_id"],
        },
        auth=ADMIN,
    )
    assert r.status_code == 403
    assert "embedding" in r.json()["detail"].lower()


def test_create_project_duplicate_name(client):
    r = client.post(
        "/projects",
        json={"name": agent_proj_name, "llm": llm_name, "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 403
    assert "already exists" in r.json()["detail"]


# ---------------------------------------------------------------- health


def test_projects_health_admin(client):
    r = client.get("/projects/health", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = {row["project_id"] for row in data}
    assert state["agent_id"] in ids
    row = next(row for row in data if row["project_id"] == state["agent_id"])
    for key in ("health", "requests_7d", "avg_latency", "guard_block_rate", "eval_score"):
        assert key in row
    assert 0 <= row["health"] <= 100


def test_projects_health_member(client):
    r = client.get("/projects/health", auth=(member_user, member_pass))
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Member only sees assigned projects.
    ids = {row["project_id"] for row in data}
    assert ids <= {state["agent_id"]}


# ---------------------------------------------------------------- guard names


def test_guard_names_resolved(client):
    gid = str(state["guard_id"])
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"guard": gid, "options": {"guard_output": gid}},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/projects/{state['agent_id']}", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["guard_name"] == guard_proj_name
    assert data["guard_output_name"] == guard_proj_name


def test_guard_ref_to_unknown_project_rejected(client):
    """Guard refs are validated on write now — an unresolvable id is refused
    rather than stored. Previously any project id was accepted, which let a
    tenant point `guard` at another tenant's project and run inference on it."""
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"guard": "99999999"},
        auth=ADMIN,
    )
    assert r.status_code == 400, r.text

    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"options": {"guard_output": "99999999"}},
        auth=ADMIN,
    )
    assert r.status_code == 400, r.text


def test_guard_names_tolerate_dangling_ref():
    """The *display* path stays lenient: a ref left dangling by a deleted guard
    project must render as no-name rather than blowing up the project GET."""
    from restai.database import DBWrapper
    from restai.routers.projects.core import _attach_guard_names

    db = DBWrapper()
    try:
        payload = {"guard": "99999999", "options": {"guard_output": "99999999"}}
        _attach_guard_names(payload, db)
        assert payload["guard_name"] is None
        assert payload["guard_output_name"] is None
    finally:
        db.db.close()


# ---------------------------------------------------------------- patch


def test_patch_unknown_project(client):
    r = client.patch("/projects/99999999", json={"human_name": "x"}, auth=ADMIN)
    assert r.status_code == 404


def test_patch_unknown_llm(client):
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"llm": "no_such_llm_ever"},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_patch_llm_not_in_current_team(client):
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"llm": llm_outside_name},
        auth=ADMIN,
    )
    assert r.status_code == 403
    assert "does not have access" in r.json()["detail"]


def test_patch_unknown_team(client):
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"team_id": 99999999},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_patch_team_without_llm_access(client):
    # Moving to team2 (which has no LLMs) must fail the LLM access gate.
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"team_id": state["team2_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 403


def test_patch_team_as_non_member(client):
    # member_user has project access but is not in team2.
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"team_id": state["team2_id"]},
        auth=(member_user, member_pass),
    )
    assert r.status_code == 403


def test_patch_search_knowledge_project_unknown(client):
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"options": {"search_knowledge_project": "no_such_rag_project"}},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "RAG" in r.json()["detail"]


def test_patch_search_knowledge_project_not_rag(client):
    r = client.patch(
        f"/projects/{state['agent_id']}",
        json={"options": {"search_knowledge_project": guard_proj_name}},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "RAG" in r.json()["detail"]


# ---------------------------------------------------------------- non-RAG 400s


def test_knowledge_endpoints_reject_non_rag(client):
    pid = state["agent_id"]
    b64 = base64.b64encode(b"some_source").decode()

    r = client.post(f"/projects/{pid}/embeddings/reset", auth=ADMIN)
    assert r.status_code == 400

    r = client.post(f"/projects/{pid}/embeddings/search", json={"text": "hello"}, auth=ADMIN)
    assert r.status_code == 400

    r = client.get(f"/projects/{pid}/embeddings", auth=ADMIN)
    assert r.status_code == 400

    r = client.get(f"/projects/{pid}/embeddings/source/{b64}", auth=ADMIN)
    assert r.status_code == 400

    r = client.get(f"/projects/{pid}/embeddings/id/some-id", auth=ADMIN)
    assert r.status_code == 400

    r = client.delete(f"/projects/{pid}/embeddings/{b64}", auth=ADMIN)
    assert r.status_code == 400

    r = client.post(
        f"/projects/{pid}/embeddings/ingest/text",
        json={"text": "hello", "source": "src1"},
        auth=ADMIN,
    )
    assert r.status_code == 400


def test_ingest_url_requires_protocol(client):
    # Rejected at the Pydantic layer (422) — non-http(s) never reaches the route.
    r = client.post(
        f"/projects/{state['agent_id']}/embeddings/ingest/url",
        json={"url": "ftp://example.com/x", "source": "x"},
        auth=ADMIN,
    )
    assert r.status_code == 422


def test_ingest_url_blocks_private_ip(client):
    r = client.post(
        f"/projects/{state['agent_id']}/embeddings/ingest/url",
        json={"url": "http://127.0.0.1/secret", "source": "x"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"]


def test_sync_trigger_non_rag(client):
    r = client.post(f"/projects/{state['agent_id']}/sync/trigger", auth=ADMIN)
    assert r.status_code == 400
    assert "RAG" in r.json()["detail"]


def test_sync_status_shape(client):
    r = client.get(f"/projects/{state['agent_id']}/sync/status", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["sources"] == 0


# ---------------------------------------------------------------- tools endpoint


def test_project_tools_non_agent(client):
    r = client.get(f"/projects/{state['block_id']}/tools", auth=ADMIN)
    assert r.status_code == 400
    assert "agent" in r.json()["detail"]


def test_project_tools_no_mcp_servers(client):
    r = client.get(f"/projects/{state['agent_id']}/tools", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["tools"] == []
    assert "No MCP servers" in data["message"]


# ---------------------------------------------------------------- chat input validation


def test_chat_missing_question(client):
    r = client.post(
        f"/projects/{state['agent_id']}/chat",
        json={"question": "   "},
        auth=ADMIN,
    )
    assert r.status_code == 400


def test_question_missing_question(client):
    r = client.post(
        f"/projects/{state['agent_id']}/question",
        json={"question": ""},
        auth=ADMIN,
    )
    assert r.status_code == 400


def test_chat_stop_missing_id(client):
    r = client.post(f"/projects/{state['agent_id']}/chat/stop", json={}, auth=ADMIN)
    assert r.status_code == 400


def test_chat_stop_unknown_session(client):
    r = client.post(
        f"/projects/{state['agent_id']}/chat/stop",
        json={"id": f"no_such_chat_{suffix}"},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["stopped"] is False


# ---------------------------------------------------------------- invitations


def test_invitation_missing_username(client):
    r = client.post(
        f"/projects/{state['agent_id']}/invitations",
        json={},
        auth=ADMIN,
    )
    assert r.status_code == 400


def test_invitation_non_creator_forbidden(client):
    # member_user has project access but isn't the creator (admin is).
    r = client.post(
        f"/projects/{state['agent_id']}/invitations",
        json={"username": "admin"},
        auth=(member_user, member_pass),
    )
    assert r.status_code == 403


def test_invitation_unknown_project(client):
    r = client.post(
        "/projects/99999999/invitations",
        json={"username": member_user},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_invitation_unknown_user_generic_response(client):
    r = client.post(
        f"/projects/{state['agent_id']}/invitations",
        json={"username": "definitely_not_a_user_xyz"},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert "invitation" in r.json()["message"].lower()


def test_invitation_existing_member_generic_response(client):
    # member_user already has project access — same opaque message, no invite row.
    r = client.post(
        f"/projects/{state['agent_id']}/invitations",
        json={"username": member_user},
        auth=ADMIN,
    )
    assert r.status_code == 200
    count = client.get("/invitations/count", auth=(member_user, member_pass)).json()["count"]
    assert count == 0


# ---------------------------------------------------------------- cleanup


def test_cleanup(client):
    for key in ("agent_id", "guard_id", "block_id"):
        client.delete(f"/projects/{state[key]}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team2_id']}", auth=ADMIN)
    client.delete(f"/users/{member_user}", auth=ADMIN)
    for llm_id in state["llm_ids"]:
        client.delete(f"/llms/{llm_id}", auth=ADMIN)
    for emb_id in state["emb_ids"]:
        client.delete(f"/embeddings/{emb_id}", auth=ADMIN)
