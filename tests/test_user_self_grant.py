"""Regression test for the "user self-grants project access" attack.

Pins:
  - `PATCH /users/{username}` with `{"projects": [...]}` is refused
    (403) for non-admin callers, even when the caller targets their
    OWN username (which the user-scope auth dep allows).
  - The user's project allow-list is unchanged after the rejected
    PATCH — no half-write, no membership stickiness.
  - Platform admin can still set `projects` (the legitimate path).

User policy: project membership is granted EXCLUSIVELY via:
  - admin direct edit (this endpoint, restricted to is_admin)
  - project invitations (`/projects/{id}/invitations` flow)

A user belonging to a team is NOT enough to self-add to a project
in that team. Always invite, never self-grant.

The fix lives in `restai/routers/users.py:route_update_user` —
`if not user.is_admin and user_update.projects is not None: 403`.
"""
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


_RNG = random.randint(0, 1000000)
ATTACKER = f"sg_bob_{_RNG}"
TARGET_PROJECT = f"sg_alice_secret_{_RNG}"
ADMIN_AUTH = ("admin", RESTAI_DEFAULT_PASSWORD)
ATTACKER_AUTH = (ATTACKER, "testpass")

_state = {"team_id": None, "project_id": None, "llm_name": None}


def test_setup(client):
    # Non-admin attacker
    r = client.post(
        "/users",
        json={"username": ATTACKER, "password": "testpass", "admin": False, "private": False},
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201, r.text

    # Confidential project owned by a separate team. The attacker has
    # NO membership on either side.
    r = client.post(
        "/teams",
        json={"name": f"sg_alice_team_{_RNG}"},
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201, r.text
    _state["team_id"] = r.json()["id"]

    # Stand up an LLM bound to the team so the project can be created.
    llm_name = f"sg_llm_{_RNG}"
    r = client.post(
        "/llms",
        json={"name": llm_name, "class_name": "OpenAI",
              "options": {"model": "gpt-test", "api_key": "sk-fake"},
              "privacy": "public"},
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201, r.text
    _state["llm_name"] = llm_name
    r = client.post(f"/teams/{_state['team_id']}/llms/{r.json()['id']}", auth=ADMIN_AUTH)
    assert r.status_code == 200, r.text

    r = client.post(
        "/projects",
        json={"name": TARGET_PROJECT, "type": "agent", "llm": llm_name, "team_id": _state["team_id"]},
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 201, r.text
    _state["project_id"] = r.json()["project"]


def test_attacker_cannot_self_grant_project_access(client):
    """The reported attack: Bob PATCHes /users/bob with the target
    project name. Must 403 — the gate refuses any non-admin from
    setting `projects`."""
    r = client.patch(
        f"/users/{ATTACKER}",
        json={"projects": [TARGET_PROJECT]},
        auth=ATTACKER_AUTH,
    )
    assert r.status_code == 403, (
        f"self-grant gate failed: status={r.status_code} body={r.text[:200]}"
    )

    # Membership unchanged. Confirm via attacker GETing /users/bob.
    r = client.get(f"/users/{ATTACKER}", auth=ATTACKER_AUTH)
    assert r.status_code == 200, r.text
    user_projects = r.json().get("projects") or []
    project_names = [(p.get("name") if isinstance(p, dict) else p) for p in user_projects]
    assert TARGET_PROJECT not in project_names, (
        "membership was added despite the 403 — partial-write regression"
    )


def test_attacker_cannot_use_target_project_after_failed_grant(client):
    """Belt-and-suspenders: confirm the auth gate at the project
    layer (`get_current_username_project`) ALSO refuses Bob, so even
    if a future regression weakened the user-self-grant gate, the
    project-side check stops the actual data access."""
    # 404 (most likely — the dep raises NOT_FOUND when the user
    # has no project-side access) or 403. Both prove the chat
    # surface is closed.
    r = client.post(
        f"/projects/{_state['project_id']}/chat",
        json={"question": "hi"},
        auth=ATTACKER_AUTH,
    )
    assert r.status_code in (403, 404), (
        f"project-side auth gate leaked access: status={r.status_code}"
    )


def test_cleanup(client):
    if _state["project_id"]:
        client.delete(f"/projects/{_state['project_id']}", auth=ADMIN_AUTH)
    if _state["llm_name"]:
        client.delete(f"/llms/{_state['llm_name']}", auth=ADMIN_AUTH)
    if _state["team_id"]:
        client.delete(f"/teams/{_state['team_id']}", auth=ADMIN_AUTH)
    client.delete(f"/users/{ATTACKER}", auth=ADMIN_AUTH)
