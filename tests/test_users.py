import random
import jwt
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.models.models import UserCreate, UserUpdate

test_username = "test_user_" + str(random.randint(0, 1000000))
test_admin_username = "admin"


def test_get_users():
    with TestClient(app) as client:
        response = client.get("/users", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert len(response.json()["users"]) >= 1

def test_create_user():
    with TestClient(app) as client:
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

def test_get_user():
    with TestClient(app) as client:
        # Test getting user details
        response = client.get(f"/users/{test_username}", auth=(test_username, "test_password"))
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_username
        assert data["is_admin"] == False
        assert data["is_private"] == False
        
        # Test getting admin user from non-admin user (should fail)
        response = client.get(f"/users/{test_admin_username}", auth=(test_username, "test_password"))
        assert response.status_code == 404

def test_update_user():
    with TestClient(app) as client:
        # Test user updating their own password
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

def test_user_apikeys():
    with TestClient(app) as client:
        # 1. Create key with description
        response = client.post(
            f"/users/{test_username}/apikeys",
            json={"description": "test key 1"},
            auth=(test_username, "new_password")
        )
        assert response.status_code == 201
        data = response.json()
        assert "api_key" in data
        assert "id" in data
        assert data["key_prefix"] == data["api_key"][:8]
        assert data["description"] == "test key 1"
        key1 = data["api_key"]
        key1_id = data["id"]

        # 2. Auth with Bearer token
        response = client.get(
            f"/users/{test_username}",
            headers={"Authorization": f"Bearer {key1}"}
        )
        assert response.status_code == 200

        # 3. Create second key
        response = client.post(
            f"/users/{test_username}/apikeys",
            json={"description": "test key 2"},
            auth=(test_username, "new_password")
        )
        assert response.status_code == 201
        key2 = response.json()["api_key"]
        key2_id = response.json()["id"]

        # 4. List keys - should have 2, no full key exposed
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

        # 5. Auth with second key
        response = client.get(
            f"/users/{test_username}",
            headers={"Authorization": f"Bearer {key2}"}
        )
        assert response.status_code == 200

        # 6. Delete first key
        response = client.delete(
            f"/users/{test_username}/apikeys/{key1_id}",
            auth=(test_username, "new_password")
        )
        assert response.status_code == 200

        # 7. Auth with deleted key -> 401
        response = client.get(
            f"/users/{test_username}",
            headers={"Authorization": f"Bearer {key1}"}
        )
        assert response.status_code == 401

        # 8. Auth with second key still works
        response = client.get(
            f"/users/{test_username}",
            headers={"Authorization": f"Bearer {key2}"}
        )
        assert response.status_code == 200

        # 9. List keys - should have 1 remaining
        response = client.get(
            f"/users/{test_username}/apikeys",
            auth=(test_username, "new_password")
        )
        assert response.status_code == 200
        keys = response.json()
        assert len(keys) == 1
        assert keys[0]["description"] == "test key 2"

def test_user_permissions_on_projects():
    with TestClient(app) as client:
        # Create a test LLM for this test
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

        # Create a team and add the test user
        team_name = f"perm_team_{random.randint(0, 1000000)}"
        team_resp = client.post(
            "/teams",
            json={"name": team_name, "users": [test_username], "llms": [test_llm]},
            auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        # Create a project as the test user
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

        # Create a project as admin
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

        # Test user can see own projects
        response = client.get("/projects", auth=(test_username, "new_password"))
        assert response.status_code == 200
        projects = response.json()["projects"]
        user_projects = [p for p in projects if p["name"] == user_project_name]
        assert len(user_projects) == 1
        
        # Test admin can see all projects
        response = client.get("/projects", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert len(projects) >= 2
        
        # Test user can't delete admin's project
        response = client.delete(f"/projects/{admin_project_id}", auth=(test_username, "new_password"))
        assert response.status_code in [401, 403, 404]  # Depending on how the API is designed
        
        # Cleanup: Delete the projects
        response = client.delete(f"/projects/{user_project_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        
        response = client.delete(f"/projects/{admin_project_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200

        # Cleanup: delete the team and test LLM
        client.delete(f"/teams/{team_id}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        client.delete(f"/llms/{test_llm}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))


def test_delete_user():
    with TestClient(app) as client:
        # Test deleting user
        response = client.delete(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        
        # Verify user is deleted
        response = client.get(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 404