import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
restricted_username = "test_restricted_" + str(random.randint(0, 1000000))
restricted_password = "restricted_pass_123"
llm_name = "restricted_test_llm_" + str(random.randint(0, 1000000))
llm_id = None
team_id = None
project_id = None


def test_setup():
    """Create restricted user, LLM, team, and project."""
    global llm_id, team_id, project_id
    with TestClient(app) as client:
        # Create restricted user
        r = client.post("/users", json={
            "username": restricted_username,
            "password": restricted_password,
            "admin": False,
            "private": False,
            "is_restricted": True,
        }, auth=ADMIN)
        assert r.status_code == 201

        # Verify user is restricted
        r = client.get(f"/users/{restricted_username}", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["is_restricted"] is True

        # Create LLM
        r = client.post("/llms", json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        }, auth=ADMIN)
        assert r.status_code == 201
        llm_id = r.json()["id"]

        # Create team with restricted user + LLM
        team_name = "restricted_team_" + str(random.randint(0, 1000000))
        r = client.post("/teams", json={
            "name": team_name,
            "users": [restricted_username],
            "admins": [],
            "llms": [llm_name],
        }, auth=ADMIN)
        assert r.status_code == 201
        team_id = r.json()["id"]

        # Create project and assign restricted user
        proj_name = "restricted_proj_" + str(random.randint(0, 1000000))
        r = client.post("/projects", json={
            "name": proj_name,
            "type": "agent",
            "llm": llm_name,
            "team_id": team_id,
        }, auth=ADMIN)
        assert r.status_code == 201
        project_id = r.json()["project"]

        client.patch(f"/projects/{project_id}", json={
            "users": ["admin", restricted_username],
        }, auth=ADMIN)


# --- Read operations (ALLOWED) ---

def test_restricted_can_list_projects():
    with TestClient(app) as client:
        r = client.get("/projects", auth=(restricted_username, restricted_password))
        assert r.status_code == 200


def test_restricted_can_get_project():
    with TestClient(app) as client:
        r = client.get(f"/projects/{project_id}", auth=(restricted_username, restricted_password))
        assert r.status_code == 200


def test_restricted_can_list_llms():
    with TestClient(app) as client:
        r = client.get("/llms", auth=(restricted_username, restricted_password))
        assert r.status_code == 200


def test_restricted_can_get_llm():
    with TestClient(app) as client:
        r = client.get(f"/llms/{llm_id}", auth=(restricted_username, restricted_password))
        assert r.status_code == 200


def test_restricted_can_list_comments():
    with TestClient(app) as client:
        r = client.get(f"/projects/{project_id}/comments", auth=(restricted_username, restricted_password))
        assert r.status_code == 200


# --- Write operations (BLOCKED) ---

def test_restricted_cannot_create_project():
    with TestClient(app) as client:
        r = client.post("/projects", json={
            "name": "should_fail",
            "type": "agent",
            "llm": llm_name,
            "team_id": team_id,
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403
        assert "Restricted" in r.json()["detail"]


def test_restricted_cannot_edit_project():
    with TestClient(app) as client:
        r = client.patch(f"/projects/{project_id}", json={
            "human_description": "hacked",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_delete_project():
    with TestClient(app) as client:
        r = client.delete(f"/projects/{project_id}", auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_clone_project():
    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/clone", json={
            "name": "should_fail_clone",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_ingest_text():
    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/embeddings/ingest/text", json={
            "text": "test data",
            "source": "test",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_ingest_url():
    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/embeddings/ingest/url", json={
            "url": "https://example.com",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_trigger_sync():
    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/sync/trigger", auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_create_comment():
    with TestClient(app) as client:
        r = client.post(f"/projects/{project_id}/comments", json={
            "content": "should fail",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_edit_own_profile():
    with TestClient(app) as client:
        r = client.patch(f"/users/{restricted_username}", json={
            "password": "new_password",
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403
        assert "Restricted" in r.json()["detail"]


def test_restricted_cannot_unrestrict_self():
    with TestClient(app) as client:
        r = client.patch(f"/users/{restricted_username}", json={
            "is_restricted": False,
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


# --- Admin can manage restricted flag ---

def test_admin_can_toggle_restricted():
    with TestClient(app) as client:
        # Unrestrict
        r = client.patch(f"/users/{restricted_username}", json={
            "is_restricted": False,
        }, auth=ADMIN)
        assert r.status_code == 200

        r = client.get(f"/users/{restricted_username}", auth=ADMIN)
        assert r.json()["is_restricted"] is False

        # Re-restrict
        r = client.patch(f"/users/{restricted_username}", json={
            "is_restricted": True,
        }, auth=ADMIN)
        assert r.status_code == 200

        r = client.get(f"/users/{restricted_username}", auth=ADMIN)
        assert r.json()["is_restricted"] is True


def test_non_admin_cannot_set_restricted():
    """A non-admin non-restricted user cannot modify is_restricted on anyone."""
    with TestClient(app) as client:
        # Create a normal user
        normal_user = "normal_user_" + str(random.randint(0, 1000000))
        client.post("/users", json={
            "username": normal_user,
            "password": "normalpass",
            "admin": False,
            "private": False,
        }, auth=ADMIN)

        # Normal user tries to set is_restricted on themselves
        r = client.patch(f"/users/{normal_user}", json={
            "is_restricted": True,
        }, auth=(normal_user, "normalpass"))
        assert r.status_code == 403
        assert "Only admins" in r.json()["detail"]

        # Cleanup
        client.delete(f"/users/{normal_user}", auth=ADMIN)


# --- Direct access (BLOCKED) ---

def test_restricted_cannot_use_direct_chat():
    with TestClient(app) as client:
        r = client.post("/v1/chat/completions", json={
            "model": llm_name,
            "messages": [{"role": "user", "content": "hello"}],
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


def test_restricted_cannot_use_direct_embeddings():
    with TestClient(app) as client:
        r = client.post("/v1/embeddings", json={
            "model": llm_name,
            "input": ["hello"],
        }, auth=(restricted_username, restricted_password))
        assert r.status_code == 403


# --- Cleanup ---

def test_cleanup():
    with TestClient(app) as client:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
        client.delete(f"/users/{restricted_username}", auth=ADMIN)
        client.delete(f"/llms/{llm_id}", auth=ADMIN)
