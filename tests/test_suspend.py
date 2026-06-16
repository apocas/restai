"""Tests for the user-suspension feature.

A suspended user cannot log in (password / SSO / LDAP) and all of their
credentials stop working — personal API keys and existing JWT session
cookies. Suspension applies to admins too (no is_admin escape hatch).

Auth-flow notes for these tests (see tests/conftest.py):
  - The `auth=(user, pass)` shim logs the tuple in for you, so we test the
    login gate by hitting `/auth/login` DIRECTLY with `auth=` (which the shim
    passes through as Basic).
  - A real `/auth/login` sets a `restai_token` cookie in the (module-scoped)
    client's jar, and `get_current_username` checks the cookie BEFORE the
    Bearer header. So the helpers below clear the jar after each login and
    before each Bearer check, otherwise a stray session cookie would
    authenticate the request instead of the API key under test.
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


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_sfx = str(random.randint(0, 1_000_000))
user = "suspend_user_" + _sfx
user_pw = "suspend_pass_123"
admin2 = "suspend_admin_" + _sfx
admin2_pw = "suspend_admin_pass_123"

user_key = None
admin2_key = None


def _mint_key(client, username, team_id):
    r = client.post(
        f"/users/{username}/apikeys",
        json={"description": "suspend-test", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


def _login(client, creds):
    """Status of a direct password login; clears the jar so the session
    cookie it sets can't leak into later requests."""
    r = client.post("/auth/login", auth=creds)
    client.cookies.clear()
    return r


def _apikey(client, key, path="/projects"):
    """GET `path` authenticated ONLY by the Bearer key (jar cleared first)."""
    client.cookies.clear()
    return client.get(path, headers={"Authorization": f"Bearer {key}"})


# --------------------------------------------------------------------------- setup


def test_setup(client):
    global user_key, admin2_key
    # A normal user and a SECOND admin (so the "applies to admins" test never
    # suspends the primary admin / itself).
    assert client.post("/users", json={"username": user, "password": user_pw}, auth=ADMIN).status_code == 201
    assert client.post("/users", json={"username": admin2, "password": admin2_pw, "is_admin": True}, auth=ADMIN).status_code == 201
    # API keys must belong to a team the owner is in — put both in one.
    tr = client.post(
        "/teams",
        json={"name": "suspend_team_" + _sfx, "users": [user, admin2], "admins": []},
        auth=ADMIN,
    )
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]
    user_key = _mint_key(client, user, team_id)
    admin2_key = _mint_key(client, admin2, team_id)


# --------------------------------------------------------------------------- field plumbing


def test_field_defaults_false_and_is_exposed(client):
    assert client.get(f"/users/{user}", auth=ADMIN).json()["is_suspended"] is False
    rows = client.get("/users", auth=ADMIN).json()["users"]
    assert next(u for u in rows if u["username"] == user)["is_suspended"] is False


# --------------------------------------------------------------------------- works before


def test_login_and_apikey_work_before_suspension(client):
    assert _login(client, (user, user_pw)).status_code == 200
    assert _apikey(client, user_key).status_code == 200


# --------------------------------------------------------------------------- the gate


def test_admin_can_suspend_user(client):
    assert client.patch(f"/users/{user}", json={"is_suspended": True}, auth=ADMIN).status_code == 200
    assert client.get(f"/users/{user}", auth=ADMIN).json()["is_suspended"] is True


def test_suspended_user_cannot_login(client):
    r = _login(client, (user, user_pw))
    assert r.status_code == 403
    assert "suspend" in r.text.lower()


def test_suspended_user_apikey_rejected(client):
    r = _apikey(client, user_key)
    assert r.status_code == 403
    assert "suspend" in r.text.lower()


def test_suspended_session_cookie_rejected(client):
    """An already-logged-in user's session JWT stops working once suspended."""
    cu = "suspend_cookie_" + _sfx
    cpw = "cookie_pass_123"
    client.post("/users", json={"username": cu, "password": cpw}, auth=ADMIN)
    try:
        # Fresh client so the session cookie lives in its own jar.
        with TestClient(app) as c2:
            assert c2.post("/auth/login", auth=(cu, cpw)).status_code == 200
            assert c2.get("/auth/whoami").status_code == 200  # cookie works
            client.patch(f"/users/{cu}", json={"is_suspended": True}, auth=ADMIN)
            r = c2.get("/auth/whoami")  # same cookie, now suspended
            assert r.status_code == 403 and "suspend" in r.text.lower(), r.text
    finally:
        client.delete(f"/users/{cu}", auth=ADMIN)


# --------------------------------------------------------------------------- applies to admins


def test_suspension_applies_to_admins(client):
    assert client.patch(f"/users/{admin2}", json={"is_suspended": True}, auth=ADMIN).status_code == 200
    # A suspended admin can neither log in nor use their API key.
    assert _login(client, (admin2, admin2_pw)).status_code == 403
    r = _apikey(client, admin2_key, path="/users")
    assert r.status_code == 403 and "suspend" in r.text.lower()


# --------------------------------------------------------------------------- guard rails


def test_admin_cannot_suspend_self(client):
    r = client.patch("/users/admin", json={"is_suspended": True}, auth=ADMIN)
    assert r.status_code == 400
    # admin must still be usable
    assert client.get("/users", auth=ADMIN).status_code == 200


def test_non_admin_cannot_set_suspension(client):
    """A non-admin (non-suspended) user cannot toggle suspension on anyone."""
    nu = "suspend_normal_" + str(random.randint(0, 1_000_000))
    client.post("/users", json={"username": nu, "password": "normalpass"}, auth=ADMIN)
    try:
        r = client.patch(f"/users/{nu}", json={"is_suspended": True}, auth=(nu, "normalpass"))
        assert r.status_code == 403
        assert "admin" in r.json()["detail"].lower()
    finally:
        client.delete(f"/users/{nu}", auth=ADMIN)


def test_create_user_already_suspended_cannot_login(client):
    """is_suspended honored at creation time."""
    su = "suspend_born_" + str(random.randint(0, 1_000_000))
    spw = "bornpass123"
    assert client.post("/users", json={"username": su, "password": spw, "is_suspended": True}, auth=ADMIN).status_code == 201
    try:
        assert client.get(f"/users/{su}", auth=ADMIN).json()["is_suspended"] is True
        assert _login(client, (su, spw)).status_code == 403
    finally:
        client.delete(f"/users/{su}", auth=ADMIN)


# --------------------------------------------------------------------------- restore


def test_unsuspend_restores_access(client):
    assert client.patch(f"/users/{user}", json={"is_suspended": False}, auth=ADMIN).status_code == 200
    assert _login(client, (user, user_pw)).status_code == 200
    assert _apikey(client, user_key).status_code == 200


# --------------------------------------------------------------------------- cleanup


def test_cleanup(client):
    client.delete(f"/users/{user}", auth=ADMIN)
    client.delete(f"/users/{admin2}", auth=ADMIN)
