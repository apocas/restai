"""Edge-path tests for restai/routers/users.py (LDAP-free paths).

Covers branches untouched by test_users.py / test_api_key_quota.py:
API-key CRUD edge cases (unknown key/user, cross-user isolation,
allowed_projects scoping), profile-update permission errors,
self-suspension guard, the permissions matrix, and TOTP guard rails
not exercised by test_totp.py.
"""
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
user_a = f"uedge_a_{suffix}"
user_b = f"uedge_b_{suffix}"
user_pass = "uedge_pass_123"
team_name = f"uedge_team_{suffix}"
proj_name = f"uedge_proj_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    for username in (user_a, user_b):
        r = client.post(
            "/users",
            json={"username": username, "password": user_pass, "admin": False, "private": False},
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text

    r = client.post(
        "/teams",
        json={"name": team_name, "users": [user_a, user_b]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    # A project user_a has NO access to (admin-owned, no assignment).
    r = client.post(
        "/projects",
        json={"name": proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["project_id"] = r.json()["project"]


# ---------------------------------------------------------------- api keys


def test_apikey_scoped_to_inaccessible_project_forbidden(client):
    r = client.post(
        f"/users/{user_a}/apikeys",
        json={
            "description": "scoped key",
            "team_id": state["team_id"],
            "allowed_projects": [state["project_id"]],
        },
        auth=(user_a, user_pass),
    )
    assert r.status_code == 403
    assert "access denied" in r.json()["detail"].lower()


def test_apikey_scoped_key_as_admin_ok(client):
    r = client.post(
        f"/users/{user_a}/apikeys",
        json={
            "description": "admin scoped key",
            "team_id": state["team_id"],
            "allowed_projects": [state["project_id"]],
            "read_only": True,
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["allowed_projects"] == [state["project_id"]]
    assert data["read_only"] is True
    state["key_a_id"] = data["id"]

    listing = client.get(f"/users/{user_a}/apikeys", auth=(user_a, user_pass)).json()
    row = next(k for k in listing if k["id"] == state["key_a_id"])
    assert row["allowed_projects"] == [state["project_id"]]
    assert row["read_only"] is True


def test_apikey_patch_description_and_reset(client):
    r = client.patch(
        f"/users/{user_a}/apikeys/{state['key_a_id']}",
        json={"description": "renamed key", "reset_usage": True},
        auth=(user_a, user_pass),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["description"] == "renamed key"
    assert data["tokens_used_this_month"] == 0
    assert data["quota_reset_at"] is not None


def test_apikey_patch_unknown_key(client):
    r = client.patch(
        f"/users/{user_a}/apikeys/99999999",
        json={"description": "x"},
        auth=(user_a, user_pass),
    )
    assert r.status_code == 404


def test_apikey_cross_user_isolation(client):
    # user_a's key id under user_b's path → not found (admin auth so the
    # username guard passes and the ownership filter is what rejects).
    r = client.patch(
        f"/users/{user_b}/apikeys/{state['key_a_id']}",
        json={"description": "steal"},
        auth=ADMIN,
    )
    assert r.status_code == 404

    r = client.delete(f"/users/{user_b}/apikeys/{state['key_a_id']}", auth=ADMIN)
    assert r.status_code == 404


def test_apikey_delete_unknown_key(client):
    r = client.delete(f"/users/{user_a}/apikeys/99999999", auth=(user_a, user_pass))
    assert r.status_code == 404


def test_apikey_endpoints_other_user_hidden(client):
    # user_a cannot even see user_b's key list (opaque 404 from the dep).
    r = client.get(f"/users/{user_b}/apikeys", auth=(user_a, user_pass))
    assert r.status_code == 404


# ---------------------------------------------------------------- user listing / details


def test_get_unknown_user_as_admin(client):
    r = client.get("/users/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


def test_users_listing_limited_for_non_admin(client):
    r = client.get("/users", auth=(user_a, user_pass))
    assert r.status_code == 200
    users = r.json()["users"]
    usernames = {u["username"] for u in users}
    # Sees teammates only, and only limited fields (no API keys leak).
    assert user_b in usernames
    for u in users:
        assert not u.get("api_keys")


def test_team_budgets_unknown_user(client):
    r = client.get("/users/no_such_user_xyz/team-budgets", auth=ADMIN)
    assert r.status_code == 404


def test_team_budgets_self(client):
    r = client.get(f"/users/{user_a}/team-budgets", auth=(user_a, user_pass))
    assert r.status_code == 200
    teams = r.json()["teams"]
    row = next(t for t in teams if t["team_id"] == state["team_id"])
    assert row["is_admin"] is False
    assert row["budget"] is None


# ---------------------------------------------------------------- update permissions


def test_user_cannot_self_promote_admin(client):
    r = client.patch(f"/users/{user_a}", json={"is_admin": True}, auth=(user_a, user_pass))
    assert r.status_code == 403


def test_user_cannot_change_own_privacy(client):
    r = client.patch(f"/users/{user_a}", json={"is_private": True}, auth=(user_a, user_pass))
    assert r.status_code == 403


def test_user_cannot_change_restriction(client):
    r = client.patch(f"/users/{user_a}", json={"is_restricted": True}, auth=(user_a, user_pass))
    assert r.status_code == 403


def test_user_cannot_change_suspension(client):
    r = client.patch(f"/users/{user_a}", json={"is_suspended": True}, auth=(user_a, user_pass))
    assert r.status_code == 403


def test_user_cannot_assign_projects(client):
    r = client.patch(f"/users/{user_a}", json={"projects": [proj_name]}, auth=(user_a, user_pass))
    assert r.status_code == 403


def test_admin_cannot_suspend_self(client):
    r = client.patch("/users/admin", json={"is_suspended": True}, auth=ADMIN)
    assert r.status_code == 400


def test_patch_unknown_user(client):
    r = client.patch("/users/no_such_user_xyz", json={"is_private": True}, auth=ADMIN)
    assert r.status_code == 404


def test_delete_unknown_user(client):
    r = client.delete("/users/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------- totp guard rails


def test_totp_status_other_user_forbidden(client):
    r = client.get(f"/users/{user_b}/totp/status", auth=(user_a, user_pass))
    assert r.status_code == 403


def test_totp_status_unknown_user(client):
    r = client.get("/users/no_such_user_xyz/totp/status", auth=ADMIN)
    assert r.status_code == 404


def test_totp_setup_wrong_password(client):
    r = client.post(
        f"/users/{user_a}/totp/setup",
        json={"password": "wrong_password"},
        auth=(user_a, user_pass),
    )
    assert r.status_code == 403


def test_totp_enable_without_setup(client):
    r = client.post(
        f"/users/{user_a}/totp/enable",
        json={"password": user_pass, "code": "123456"},
        auth=(user_a, user_pass),
    )
    assert r.status_code == 400
    assert "setup" in r.json()["detail"].lower()


def test_totp_disable_wrong_password(client):
    r = client.post(
        f"/users/{user_a}/totp/disable",
        json={"password": "wrong_password"},
        auth=(user_a, user_pass),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------- permissions matrix


def test_permission_matrix_admin(client):
    r = client.get("/permissions/matrix", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert {"users", "projects", "assignments"} <= set(data.keys())
    usernames = {u["username"] for u in data["users"]}
    assert user_a in usernames
    project_names = {p["name"] for p in data["projects"]}
    assert proj_name in project_names


def test_permission_matrix_plain_user_forbidden(client):
    r = client.get("/permissions/matrix", auth=(user_a, user_pass))
    assert r.status_code == 403


def test_permission_matrix_team_admin_scoped(client):
    # Promote user_b to team admin → matrix restricted to that team.
    r = client.post(f"/teams/{state['team_id']}/admins/{user_b}", auth=ADMIN)
    assert r.status_code == 200

    r = client.get("/permissions/matrix", auth=(user_b, user_pass))
    assert r.status_code == 200
    data = r.json()
    project_team_ids = {p["team_id"] for p in data["projects"]}
    assert project_team_ids <= {state["team_id"]}
    usernames = {u["username"] for u in data["users"]}
    assert user_a in usernames


# ---------------------------------------------------------------- cleanup


def test_cleanup(client):
    client.delete(f"/projects/{state['project_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    for username in (user_a, user_b):
        client.delete(f"/users/{username}", auth=ADMIN)
