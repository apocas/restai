"""Tests for read-only API key enforcement.

`read_only` was accepted on API-key creation, persisted, loaded onto the
authenticated user and returned by the API — but `check_not_read_only` had zero
callers repo-wide, so a "read-only" key could perform every write in the
application. Enforcement now lives in `auth._enforce_read_only`, called from
`get_current_username`, so it covers every authenticated endpoint at once and
fails closed for endpoints added later.

The unit tests below pin the gate's decision table; the integration tests prove
it reaches real endpoints and that a normal key is unaffected.
"""
import random
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from restai import auth
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 1000000))
team_name = f"ro_team_{suffix}"
project_name = f"ro_project_{suffix}"
username = f"ro_user_{suffix}"
password = "ro_password"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _request(method, route_path):
    """Minimal stand-in — the gate only reads `.method` and `.scope`."""
    scope = {}
    if route_path is not None:
        scope["route"] = SimpleNamespace(path=route_path)
    return SimpleNamespace(method=method, scope=scope)


# ─── unit: the decision table ───────────────────────────────────────────

def test_gate_ignores_keys_that_are_not_read_only():
    user = SimpleNamespace(is_read_only=False)
    auth._enforce_read_only(_request("DELETE", "/projects/{projectID}"), user)


def test_gate_allows_safe_methods():
    user = SimpleNamespace(is_read_only=True)
    for method in ("GET", "HEAD", "OPTIONS"):
        auth._enforce_read_only(_request(method, "/projects/{projectID}"), user)


def test_gate_allows_the_query_surface():
    user = SimpleNamespace(is_read_only=True)
    for route in ("/projects/{projectID}/chat", "/v1/chat/completions", "/search"):
        auth._enforce_read_only(_request("POST", route), user)


def test_gate_refuses_mutating_routes():
    user = SimpleNamespace(is_read_only=True)
    for method, route in (
        ("PATCH", "/projects/{projectID}"),
        ("DELETE", "/projects/{projectID}"),
        ("POST", "/projects/{projectID}/kg/entities/{entity_id}/merge"),
        ("POST", "/projects/{projectID}/embeddings/ingest/url"),
    ):
        with pytest.raises(HTTPException) as exc:
            auth._enforce_read_only(_request(method, route), user)
        assert exc.value.status_code == 403


def test_gate_fails_closed_on_unknown_route():
    """No resolved route → deny. A new endpoint must not be allowed by default."""
    user = SimpleNamespace(is_read_only=True)
    with pytest.raises(HTTPException) as exc:
        auth._enforce_read_only(_request("POST", None), user)
    assert exc.value.status_code == 403


def test_every_allowlisted_route_is_a_real_route(client):
    """Guard against typos and against the allow-list rotting as routes move.

    Takes `client` because `register_routers` runs inside the app lifespan
    (`main.py:140`) — `app.routes` is nearly empty until the app has started.
    """
    declared = {getattr(r, "path", None) for r in app.routes}
    missing = auth._READ_ONLY_ALLOWED_ROUTES - declared
    assert not missing, f"allow-list references non-existent routes: {sorted(missing)}"


# ─── integration ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def env(client):
    """Non-admin user (team admin, so it can reach the project) + two keys.

    Deliberately NOT a platform admin: `User.is_read_only` short-circuits to
    False for admins, so an admin's read-only key is not read-only.
    """
    r = client.post("/teams", json={"name": team_name}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    team_id = r.json()["id"]

    r = client.post("/users", json={
        "username": username, "password": password,
        "admin": False, "private": False,
    }, auth=ADMIN)
    assert r.status_code == 201, r.text

    assert client.post(f"/teams/{team_id}/users/{username}", auth=ADMIN).status_code in (200, 201)
    assert client.post(f"/teams/{team_id}/admins/{username}", auth=ADMIN).status_code in (200, 201)

    # Block project — needs no embeddings/LLM, so creation is deterministic.
    r = client.post("/projects", json={
        "name": project_name, "type": "block", "team_id": team_id,
    }, auth=ADMIN)
    assert r.status_code == 201, r.text
    project_id = r.json()["project"]

    def mint(read_only):
        r = client.post(f"/users/{username}/apikeys", json={
            "description": f"ro_{read_only}_{suffix}",
            "team_id": team_id,
            "read_only": read_only,
        }, auth=ADMIN)
        assert r.status_code == 201, r.text
        return r.json()["api_key"]

    yield SimpleNamespace(
        project_id=project_id, team_id=team_id,
        ro_key=mint(True), rw_key=mint(False),
    )

    client.delete(f"/projects/{project_id}", auth=ADMIN)
    client.delete(f"/users/{username}", auth=ADMIN)
    client.delete(f"/teams/{team_id}", auth=ADMIN)


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def test_read_only_key_can_read(client, env):
    r = client.get(f"/projects/{env.project_id}", headers=_bearer(env.ro_key))
    assert r.status_code == 200, r.text


def test_read_only_key_refused_on_project_patch(client, env):
    r = client.patch(
        f"/projects/{env.project_id}",
        json={"human_description": "should not apply"},
        headers=_bearer(env.ro_key),
    )
    assert r.status_code == 403
    assert "read-only" in r.json()["detail"].lower()


def test_read_only_key_refused_on_kg_merge(client, env):
    """The endpoint from GHSA-r3px-wf48-988x, now unreachable with such a key."""
    r = client.post(
        f"/projects/{env.project_id}/kg/entities/1/merge",
        json={"target_id": 2},
        headers=_bearer(env.ro_key),
    )
    assert r.status_code == 403


def test_read_only_key_refused_on_ingest(client, env):
    r = client.post(
        f"/projects/{env.project_id}/embeddings/ingest/url",
        json={"url": "https://example.com"},
        headers=_bearer(env.ro_key),
    )
    assert r.status_code == 403


def test_read_only_key_not_blocked_on_allowlisted_chat(client, env):
    """Chat may fail for unrelated reasons (no LLM configured) — it must not
    fail *because the key is read-only*, or the key is useless for its purpose."""
    r = client.post(
        f"/projects/{env.project_id}/chat",
        json={"question": "hello"},
        headers=_bearer(env.ro_key),
    )
    assert not (r.status_code == 403 and "read-only" in r.text.lower()), r.text


def test_normal_key_still_writes(client, env):
    """The gate must key off `read_only`, not merely off being an API key."""
    r = client.patch(
        f"/projects/{env.project_id}",
        json={"human_description": f"written_by_rw_key_{suffix}"},
        headers=_bearer(env.rw_key),
    )
    assert r.status_code == 200, r.text
