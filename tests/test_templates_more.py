"""Template library tests for restai/routers/templates.py.

Self-contained (creates its own LLM/teams/users/projects, unlike
tests/test_templates.py which skips when the shared DB has no LLMs):
publish across all three visibilities, visibility filtering across
users/teams, GET single, owner-only PATCH/DELETE, and instantiate
(team membership check, LLM pick, duplicate name, use_count bump,
system-prompt + options replay).
"""
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"tplm_llm_{suffix}"
team1_name = f"tplm_team1_{suffix}"
team2_name = f"tplm_team2_{suffix}"
user_a = f"tplm_a_{suffix}"       # team1 member, project member (publisher)
user_b = f"tplm_b_{suffix}"       # team1 member, NOT project member
user_c = f"tplm_c_{suffix}"       # team2 member only
password = "tplm_pass_123"
src_proj_name = f"tplm_src_{suffix}"

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

    for u in (user_a, user_b, user_c):
        r = client.post(
            "/users",
            json={"username": u, "password": password, "admin": False, "private": False},
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text

    r = client.post(
        "/teams",
        json={"name": team1_name, "users": [user_a, user_b], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team1_id"] = r.json()["id"]

    r = client.post(
        "/teams",
        json={"name": team2_name, "users": [user_c], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team2_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": src_proj_name, "llm": llm_name, "type": "agent", "team_id": state["team1_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["src_id"] = r.json()["project"]

    # user_a becomes a project member; give the source a system prompt and
    # a distinctive option so instantiate can prove the replay.
    r = client.patch(
        f"/projects/{state['src_id']}",
        json={
            "users": [user_a, "admin"],
            "system": "You are the template source bot.",
            "options": {"rate_limit": 42},
        },
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ publish


def test_publish_private_as_member(client):
    r = client.post(
        f"/projects/{state['src_id']}/publish-template",
        json={"name": f"tpl_private_{suffix}", "description": "private tpl", "visibility": "private"},
        auth=(user_a, password),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["visibility"] == "private"
    assert data["creator_username"] == user_a
    assert data["project_type"] == "agent"
    assert data["suggested_llm"] == llm_name
    assert data["team_id"] is None  # only team-visibility keeps the team
    assert data["use_count"] == 0
    state["tpl_private"] = data["id"]


def test_publish_team_as_admin(client):
    r = client.post(
        f"/projects/{state['src_id']}/publish-template",
        json={"name": f"tpl_team_{suffix}", "visibility": "team"},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["visibility"] == "team"
    assert data["team_id"] == state["team1_id"]
    assert data["team_name"] == team1_name
    state["tpl_team"] = data["id"]


def test_publish_public_as_admin(client):
    r = client.post(
        f"/projects/{state['src_id']}/publish-template",
        json={"name": f"tpl_public_{suffix}", "visibility": "public"},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["tpl_public"] = r.json()["id"]


def test_publish_requires_project_access(client):
    # user_c has no access to the source project -> opaque 404 from auth.
    r = client.post(
        f"/projects/{state['src_id']}/publish-template",
        json={"name": "nope", "visibility": "private"},
        auth=(user_c, password),
    )
    assert r.status_code == 404


def test_publish_team_visibility_without_team(client):
    # Null the source project's team directly (the API always requires one on
    # create) to reach the "no team" guard.
    from restai.database import open_db_wrapper

    r = client.post(
        "/projects",
        json={"name": f"tplm_noteam_{suffix}", "type": "block", "team_id": state["team1_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["project"]
    db = open_db_wrapper()
    try:
        row = db.get_project_by_id(pid)
        row.team_id = None
        db.db.commit()
    finally:
        db.db.close()

    r = client.post(
        f"/projects/{pid}/publish-template",
        json={"name": "x", "visibility": "team"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "no team" in r.json()["detail"]
    client.delete(f"/projects/{pid}", auth=ADMIN)


def test_publish_unknown_project(client):
    r = client.post(
        "/projects/99999999/publish-template",
        json={"name": "x", "visibility": "private"},
        auth=ADMIN,
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ listing / visibility


def test_list_admin_sees_all_three(client):
    r = client.get("/templates", auth=ADMIN)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert {state["tpl_private"], state["tpl_team"], state["tpl_public"]} <= ids


def test_list_creator_sees_own_private(client):
    r = client.get("/templates", auth=(user_a, password))
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert state["tpl_private"] in ids
    assert state["tpl_team"] in ids     # same team
    assert state["tpl_public"] in ids


def test_list_teammate_sees_team_not_private(client):
    r = client.get("/templates", auth=(user_b, password))
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert state["tpl_private"] not in ids
    assert state["tpl_team"] in ids
    assert state["tpl_public"] in ids


def test_list_outsider_sees_only_public(client):
    r = client.get("/templates", auth=(user_c, password))
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert state["tpl_private"] not in ids
    assert state["tpl_team"] not in ids
    assert state["tpl_public"] in ids


def test_list_project_type_filter(client):
    r = client.get("/templates", params={"project_type": "rag"}, auth=ADMIN)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert state["tpl_public"] not in ids  # agent template filtered out


# ------------------------------------------------------------------ get single


def test_get_single_visible(client):
    r = client.get(f"/templates/{state['tpl_public']}", auth=(user_c, password))
    assert r.status_code == 200
    assert r.json()["id"] == state["tpl_public"]


def test_get_single_invisible_is_404(client):
    r = client.get(f"/templates/{state['tpl_private']}", auth=(user_c, password))
    assert r.status_code == 404


def test_get_single_unknown(client):
    r = client.get("/templates/99999999", auth=ADMIN)
    assert r.status_code == 404


# ------------------------------------------------------------------ patch


def test_patch_non_owner_forbidden(client):
    # tpl_team was created by admin; user_b can see it but not edit it.
    r = client.patch(
        f"/templates/{state['tpl_team']}",
        json={"name": "hax"},
        auth=(user_b, password),
    )
    assert r.status_code == 403


def test_patch_owner_updates_fields(client):
    r = client.patch(
        f"/templates/{state['tpl_private']}",
        json={"name": f"tpl_private2_{suffix}", "description": "updated desc"},
        auth=(user_a, password),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == f"tpl_private2_{suffix}"
    assert data["description"] == "updated desc"


def test_patch_visibility_team_without_team_id(client):
    # tpl_public has team_id NULL (publish only keeps team for team-visibility).
    r = client.patch(
        f"/templates/{state['tpl_public']}",
        json={"visibility": "team"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "team_id" in r.json()["detail"]


def test_patch_visibility_change_valid(client):
    r = client.patch(
        f"/templates/{state['tpl_team']}",
        json={"visibility": "private"},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["visibility"] == "private"
    # Now user_b can no longer see it.
    r = client.get(f"/templates/{state['tpl_team']}", auth=(user_b, password))
    assert r.status_code == 404
    # Restore.
    r = client.patch(f"/templates/{state['tpl_team']}", json={"visibility": "team"}, auth=ADMIN)
    assert r.status_code == 200


def test_patch_unknown_template(client):
    r = client.patch("/templates/99999999", json={"name": "x"}, auth=ADMIN)
    assert r.status_code == 404


# ------------------------------------------------------------------ instantiate


def test_instantiate_non_member_team(client):
    r = client.post(
        f"/templates/{state['tpl_public']}/instantiate",
        json={"name": f"tplm_inst_bad_{suffix}", "team_id": state["team2_id"]},
        auth=(user_a, password),
    )
    assert r.status_code == 403
    assert "not a member" in r.json()["detail"]


def test_instantiate_duplicate_name(client):
    r = client.post(
        f"/templates/{state['tpl_public']}/instantiate",
        json={"name": src_proj_name, "team_id": state["team1_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 409


def test_instantiate_invisible_template_404(client):
    r = client.post(
        f"/templates/{state['tpl_private']}/instantiate",
        json={"name": f"tplm_inst_x_{suffix}", "team_id": state["team2_id"]},
        auth=(user_c, password),
    )
    assert r.status_code == 404


def test_instantiate_unknown_template(client):
    r = client.post(
        "/templates/99999999/instantiate",
        json={"name": f"tplm_inst_y_{suffix}", "team_id": state["team1_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_instantiate_happy_path_replays_state(client):
    name = f"tplm_inst_{suffix}"
    r = client.post(
        f"/templates/{state['tpl_public']}/instantiate",
        json={"name": name, "team_id": state["team2_id"], "llm": llm_name},
        auth=(user_c, password),
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    assert r.json()["name"] == name
    state["inst_id"] = new_id

    r = client.get(f"/projects/{new_id}", auth=(user_c, password))
    assert r.status_code == 200
    proj = r.json()
    assert proj["type"] == "agent"
    assert proj["llm"] == llm_name
    assert proj["system"] == "You are the template source bot."
    assert proj["options"]["rate_limit"] == 42
    assert proj["team"]["id"] == state["team2_id"]

    # use_count bumped.
    r = client.get(f"/templates/{state['tpl_public']}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["use_count"] == 1


def test_instantiate_llm_not_accessible_to_team(client):
    # A team without any LLMs cannot host the new project -> create fails.
    r = client.post("/teams", json={"name": f"tplm_team3_{suffix}"}, auth=ADMIN)
    assert r.status_code == 201
    team3_id = r.json()["id"]
    r = client.post(
        f"/templates/{state['tpl_public']}/instantiate",
        json={"name": f"tplm_inst_nollm_{suffix}", "team_id": team3_id},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "Failed to create project" in r.json()["detail"]
    client.delete(f"/teams/{team3_id}", auth=ADMIN)


# ------------------------------------------------------------------ delete


def test_delete_non_owner_forbidden(client):
    r = client.delete(f"/templates/{state['tpl_team']}", auth=(user_b, password))
    assert r.status_code == 403


def test_delete_owner(client):
    r = client.delete(f"/templates/{state['tpl_private']}", auth=(user_a, password))
    assert r.status_code == 200
    assert r.json()["deleted"] == state["tpl_private"]
    r = client.get(f"/templates/{state['tpl_private']}", auth=(user_a, password))
    assert r.status_code == 404


def test_delete_unknown(client):
    r = client.delete("/templates/99999999", auth=ADMIN)
    assert r.status_code == 404


# ------------------------------------------------------------------ cleanup


def test_cleanup(client):
    for key in ("tpl_team", "tpl_public"):
        client.delete(f"/templates/{state[key]}", auth=ADMIN)
    if "inst_id" in state:
        client.delete(f"/projects/{state['inst_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['src_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team1_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team2_id']}", auth=ADMIN)
    for u in (user_a, user_b, user_c):
        client.delete(f"/users/{u}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
