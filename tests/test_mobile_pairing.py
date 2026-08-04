"""Mobile pairing tests for restai/routers/projects/mobile.py.

Enable mints a read-only project-scoped API key and exposes the QR
payload; status re-reads keep surfacing the plaintext; regenerate
invalidates old paired keys; disable deletes the key entirely.
"""
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"mob_llm_{suffix}"
team_name = f"mob_team_{suffix}"
proj_name = f"mob_proj_{suffix}"
other_proj_name = f"mob_other_{suffix}"
mob_user = f"mob_user_{suffix}"
mob_pass = "mob_pass_123"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


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

    for name, key in ((proj_name, "proj_id"), (other_proj_name, "other_id")):
        r = client.post(
            "/projects",
            json={"name": name, "llm": llm_name, "type": "agent", "team_id": state["team_id"]},
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text
        state[key] = r.json()["project"]

    # Non-admin member who pairs the phone. Admin-minted keys bypass the
    # API-key project scope entirely (`has_api_key_project_access` short-
    # circuits on is_admin), so scoping is only observable for normal users.
    r = client.post(
        "/users",
        json={"username": mob_user, "password": mob_pass, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    r = client.patch(f"/teams/{state['team_id']}", json={"users": [mob_user]}, auth=ADMIN)
    assert r.status_code == 200, r.text
    r = client.patch(
        f"/projects/{state['proj_id']}", json={"users": [mob_user, "admin"]}, auth=ADMIN
    )
    assert r.status_code == 200, r.text


def test_status_disabled_initially(client):
    r = client.get(f"/projects/{state['proj_id']}/mobile", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["key_prefix"] is None
    assert "host" in data
    assert "qr" not in data


def test_enable_mints_key_and_qr(client):
    r = client.post(f"/projects/{state['proj_id']}/mobile/enable", auth=(mob_user, mob_pass))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    qr = data["qr"]
    assert set(qr) == {"host", "project_id", "project_name", "api_key"}
    assert qr["project_id"] == state["proj_id"]
    assert qr["project_name"] == proj_name
    assert qr["host"] == data["host"]
    assert data["key_prefix"] == qr["api_key"][:8]
    state["key1"] = qr["api_key"]


def test_minted_key_authenticates_bearer(client):
    r = client.get(f"/projects/{state['proj_id']}", headers=_bearer(state["key1"]))
    assert r.status_code == 200
    assert r.json()["name"] == proj_name


def test_minted_key_is_project_scoped(client):
    # allowed_projects only contains the paired project; the minting user
    # has no access to the other project either way.
    r = client.get(f"/projects/{state['other_id']}", headers=_bearer(state["key1"]))
    assert r.status_code in (403, 404)


def test_enable_idempotent(client):
    r = client.post(f"/projects/{state['proj_id']}/mobile/enable", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    # Same key, not a new mint.
    assert data["qr"]["api_key"] == state["key1"]


def test_status_reread_does_not_surface_plaintext(client):
    """The status GET is ungated (no check_not_restricted, any project member),
    so it must not hand back a live credential. It used to decrypt the stored
    key on every read. The QR is re-issued by POST /enable instead, which is
    gated — and which the UI already re-POSTs when the payload is absent."""
    r = client.get(f"/projects/{state['proj_id']}/mobile", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert "qr" not in data
    assert data["key_prefix"] == state["key1"][:8]


def test_enable_reissues_qr_for_existing_key(client):
    """Pairing UX is preserved: the gated POST still returns the same key."""
    r = client.post(f"/projects/{state['proj_id']}/mobile/enable", auth=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    assert data["qr"]["api_key"] == state["key1"]


def test_regenerate_invalidates_old_key(client):
    r = client.post(f"/projects/{state['proj_id']}/mobile/regenerate", auth=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is True
    key2 = data["qr"]["api_key"]
    assert key2 != state["key1"]
    state["key2"] = key2

    # Old key is dead, new key works.
    r = client.get(f"/projects/{state['proj_id']}", headers=_bearer(state["key1"]))
    assert r.status_code == 401
    r = client.get(f"/projects/{state['proj_id']}", headers=_bearer(key2))
    assert r.status_code == 200


def test_disable_deletes_key(client):
    r = client.post(f"/projects/{state['proj_id']}/mobile/disable", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert "qr" not in data

    r = client.get(f"/projects/{state['proj_id']}", headers=_bearer(state["key2"]))
    assert r.status_code == 401

    r = client.get(f"/projects/{state['proj_id']}/mobile", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_disable_idempotent(client):
    r = client.post(f"/projects/{state['proj_id']}/mobile/disable", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_mobile_unknown_project(client):
    for path in ("mobile", "mobile/enable", "mobile/disable", "mobile/regenerate"):
        method = client.get if path == "mobile" else client.post
        r = method(f"/projects/99999999/{path}", auth=ADMIN)
        assert r.status_code == 404


def test_cleanup(client):
    client.delete(f"/projects/{state['proj_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['other_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    client.delete(f"/users/{mob_user}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
