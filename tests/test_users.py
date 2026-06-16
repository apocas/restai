import random
import pytest
import jwt
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.models.models import UserCreate, UserUpdate

test_username = "test_user_" + str(random.randint(0, 1000000))
test_admin_username = "admin"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_get_users(client):
    response = client.get("/users", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    assert len(response.json()["users"]) >= 1

def test_create_user(client):
    response = client.post(
        "/users",
        json={
            "username": test_username,
            "password": "test_password",
            "admin": False,
            "private": False
        },
        auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == test_username

def test_get_user(client):
    response = client.get(f"/users/{test_username}", auth=(test_username, "test_password"))
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_username
    assert data["is_admin"] == False
    assert data["is_private"] == False

    # Test getting admin user from non-admin user (should fail)
    response = client.get(f"/users/{test_admin_username}", auth=(test_username, "test_password"))
    assert response.status_code == 404

def test_update_user(client):
    response = client.patch(
        f"/users/{test_username}",
        json={
            "password": "new_password"
        },
        auth=(test_username, "test_password")
    )
    assert response.status_code == 200

    # Verify changes by logging in with new password
    response = client.get(f"/users/{test_username}", auth=(test_username, "new_password"))
    assert response.status_code == 200

    # Test admin updating is_private (only admins/team admins can change this)
    response = client.patch(
        f"/users/{test_username}",
        json={
            "is_private": True,
        },
        auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_username
    assert data["is_private"] == True

def test_user_apikeys(client):
    ADMIN = (test_admin_username, RESTAI_DEFAULT_PASSWORD)
    # API keys must belong to a team the owner is in (it's billed for the
    # key's direct-access usage). Put the test user in a fresh team.
    team_name = "apikey_team_" + str(random.randint(0, 1000000))
    tr = client.post(
        "/teams",
        json={"name": team_name, "users": [test_username], "admins": []},
        auth=ADMIN,
    )
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # team_id is obligatory — omitting it is a validation error.
    missing = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "no team"},
        auth=(test_username, "new_password"),
    )
    assert missing.status_code == 422

    # A team the owner doesn't belong to is rejected.
    bad = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "wrong team", "team_id": 999999},
        auth=(test_username, "new_password"),
    )
    assert bad.status_code == 400

    response = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "test key 1", "team_id": team_id},
        auth=(test_username, "new_password")
    )
    assert response.status_code == 201
    data = response.json()
    assert "api_key" in data
    assert "id" in data
    assert data["key_prefix"] == data["api_key"][:8]
    assert data["description"] == "test key 1"
    assert data["team_id"] == team_id
    key1 = data["api_key"]
    key1_id = data["id"]

    response = client.get(
        f"/users/{test_username}",
        headers={"Authorization": f"Bearer {key1}"}
    )
    assert response.status_code == 200

    response = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "test key 2", "team_id": team_id},
        auth=(test_username, "new_password")
    )
    assert response.status_code == 201
    key2 = response.json()["api_key"]
    key2_id = response.json()["id"]

    response = client.get(
        f"/users/{test_username}/apikeys",
        auth=(test_username, "new_password")
    )
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 2
    descriptions = {k["description"] for k in keys}
    assert descriptions == {"test key 1", "test key 2"}
    for k in keys:
        assert "api_key" not in k

    response = client.get(
        f"/users/{test_username}",
        headers={"Authorization": f"Bearer {key2}"}
    )
    assert response.status_code == 200

    response = client.delete(
        f"/users/{test_username}/apikeys/{key1_id}",
        auth=(test_username, "new_password")
    )
    assert response.status_code == 200

    response = client.get(
        f"/users/{test_username}",
        headers={"Authorization": f"Bearer {key1}"}
    )
    assert response.status_code == 401

    response = client.get(
        f"/users/{test_username}",
        headers={"Authorization": f"Bearer {key2}"}
    )
    assert response.status_code == 200

    response = client.get(
        f"/users/{test_username}/apikeys",
        auth=(test_username, "new_password")
    )
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 1
    assert keys[0]["description"] == "test key 2"

def test_user_permissions_on_projects(client):
    test_llm = f"test_perm_llm_{random.randint(0, 1000000)}"
    resp = client.post(
        "/llms",
        json={
            "name": test_llm,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "private",
        },
        auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 201

    team_name = f"perm_team_{random.randint(0, 1000000)}"
    team_resp = client.post(
        "/teams",
        json={"name": team_name, "users": [test_username], "llms": [test_llm]},
        auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
    )
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    user_project_name = f"user_project_{random.randint(0, 1000000)}"
    response = client.post(
        "/projects",
        json={
            "name": user_project_name,
            "llm": test_llm,
            "type": "agent",
            "team_id": team_id
        },
        auth=(test_username, "new_password")
    )
    assert response.status_code == 201
    user_project_id = response.json()["project"]

    admin_project_name = f"admin_project_{random.randint(0, 1000000)}"
    response = client.post(
        "/projects",
        json={
            "name": admin_project_name,
            "llm": test_llm,
            "type": "agent",
            "team_id": team_id
        },
        auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
    )
    assert response.status_code == 201
    admin_project_id = response.json()["project"]

    response = client.get("/projects", auth=(test_username, "new_password"))
    assert response.status_code == 200
    projects = response.json()["projects"]
    user_projects = [p for p in projects if p["name"] == user_project_name]
    assert len(user_projects) == 1

    response = client.get("/projects", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    projects = response.json()["projects"]
    assert len(projects) >= 2

    response = client.delete(f"/projects/{admin_project_id}", auth=(test_username, "new_password"))
    assert response.status_code in [401, 403, 404]

    response = client.delete(f"/projects/{user_project_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200

    response = client.delete(f"/projects/{admin_project_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200

    client.delete(f"/teams/{team_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    client.delete(f"/llms/{test_llm}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))


def test_delete_user(client):
    response = client.delete(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200

    response = client.get(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 404
