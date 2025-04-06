import random
import jwt
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from restai.config import RESTAI_DEFAULT_PASSWORD, RESTAI_SSO_SECRET, RESTAI_SSO_ALG
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
        assert response.status_code == 200
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
        # Test updating user details
        response = client.patch(
            f"/users/{test_username}",
            json={
                "is_private": True,
                "password": "new_password"
            },
            auth=(test_username, "test_password")
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_username
        assert data["is_private"] == True
        
        # Verify changes by logging in with new password
        response = client.get(f"/users/{test_username}", auth=(test_username, "new_password"))
        assert response.status_code == 200

def test_user_apikey():
    with TestClient(app) as client:
        # Test generating API key
        response = client.post(
            f"/users/{test_username}/apikey",
            auth=(test_username, "new_password")
        )
        assert response.status_code == 200
        assert "api_key" in response.json()
        api_key = response.json()["api_key"]
        
        # Test using API key for authentication
        response = client.get(
            f"/users/{test_username}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        assert response.status_code == 200

def test_user_permissions_on_projects():
    with TestClient(app) as client:
        # Create a project as the test user
        user_project_name = f"user_project_{random.randint(0, 1000000)}"
        response = client.post(
            "/projects", 
            json={
                "name": user_project_name, 
                "llm": "llama31_8b", 
                "type": "inference"
            }, 
            auth=(test_username, "new_password")
        )
        assert response.status_code == 200
        user_project_id = response.json()["project"]
        
        # Create a project as admin
        admin_project_name = f"admin_project_{random.randint(0, 1000000)}"
        response = client.post(
            "/projects", 
            json={
                "name": admin_project_name, 
                "llm": "llama31_8b", 
                "type": "inference"
            }, 
            auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
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


def test_delete_user():
    with TestClient(app) as client:
        # Test deleting user
        response = client.delete(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        
        # Verify user is deleted
        response = client.get(f"/users/{test_username}", auth=(test_admin_username, RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 404