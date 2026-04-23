"""Tests for the project-secrets vault used by the Agentic Browser.

Covers the round-trip through the REST API: create → read (masked) → patch
(plaintext preserved when the sentinel comes back) → delete. Also spot-
checks that `DBWrapper.resolve_project_secret` actually decrypts what was
stored — the live-browser bit obviously isn't runnable here.
"""
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import get_db_wrapper
from restai.main import app


AUTH = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project_id(client):
    # Pick any project the admin has; create one if none.
    r = client.get("/projects", auth=AUTH)
    if r.status_code == 200:
        projects = r.json().get("projects", []) or []
        if projects:
            return projects[0]["id"]

    # Need a team + llm to create. Try to find one.
    teams = client.get("/teams", auth=AUTH).json().get("teams", []) or []
    team_id = teams[0]["id"] if teams else 1

    resp = client.post(
        "/projects",
        json={
            "name": "secret_test_project",
            "type": "agent",
            "llm": "fake",
            "team_id": team_id,
        },
        auth=AUTH,
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not bootstrap a project for secret tests ({resp.status_code})")
    return resp.json()["id"]


def test_secret_crud_roundtrip(client, project_id):
    # Create
    r = client.post(
        f"/projects/{project_id}/secrets",
        json={"name": "test_api_key", "value": "super-secret-plaintext", "description": "unit test"},
        auth=AUTH,
    )
    if r.status_code == 409:
        # Leftover from a previous run — delete + retry.
        existing = client.get(f"/projects/{project_id}/secrets", auth=AUTH).json()
        for s in existing:
            if s["name"] == "test_api_key":
                client.delete(f"/projects/{project_id}/secrets/{s['id']}", auth=AUTH)
        r = client.post(
            f"/projects/{project_id}/secrets",
            json={"name": "test_api_key", "value": "super-secret-plaintext", "description": "unit test"},
            auth=AUTH,
        )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "test_api_key"
    assert created["value"] == "********", "value must be masked on the response"

    secret_id = created["id"]
    try:
        # List — value still masked
        lst = client.get(f"/projects/{project_id}/secrets", auth=AUTH)
        assert lst.status_code == 200
        names = {s["name"]: s for s in lst.json()}
        assert "test_api_key" in names
        assert names["test_api_key"]["value"] == "********"

        # Resolve via DB helper — plaintext must match the original
        db = get_db_wrapper()
        try:
            plaintext = db.resolve_project_secret(project_id, "test_api_key")
        finally:
            db.db.close()
        assert plaintext == "super-secret-plaintext"

        # PATCH with masked value — plaintext must be preserved
        r = client.patch(
            f"/projects/{project_id}/secrets/{secret_id}",
            json={"value": "********", "description": "touched description"},
            auth=AUTH,
        )
        assert r.status_code == 200, r.text
        db = get_db_wrapper()
        try:
            assert db.resolve_project_secret(project_id, "test_api_key") == "super-secret-plaintext"
        finally:
            db.db.close()

        # PATCH with a real new value — plaintext changes
        r = client.patch(
            f"/projects/{project_id}/secrets/{secret_id}",
            json={"value": "rotated-value"},
            auth=AUTH,
        )
        assert r.status_code == 200
        db = get_db_wrapper()
        try:
            assert db.resolve_project_secret(project_id, "test_api_key") == "rotated-value"
        finally:
            db.db.close()

        # Duplicate name → 409
        dup = client.post(
            f"/projects/{project_id}/secrets",
            json={"name": "test_api_key", "value": "x"},
            auth=AUTH,
        )
        assert dup.status_code == 409
    finally:
        # Cleanup
        client.delete(f"/projects/{project_id}/secrets/{secret_id}", auth=AUTH)


def test_resolve_missing_secret_returns_none(client, project_id):
    db = get_db_wrapper()
    try:
        assert db.resolve_project_secret(project_id, "definitely_does_not_exist_xyz") is None
    finally:
        db.db.close()


def test_secret_name_validation(client, project_id):
    # Slashes / spaces etc. must reject (validate_safe_name).
    bad_names = ["has/slash", "has space", "../traversal"]
    for name in bad_names:
        r = client.post(
            f"/projects/{project_id}/secrets",
            json={"name": name, "value": "x"},
            auth=AUTH,
        )
        assert r.status_code == 422, f"expected 422 for name {name!r}, got {r.status_code}"
