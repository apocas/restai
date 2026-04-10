import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
llm_name = f"audit_llm_{suffix}"
team_name = f"audit_team_{suffix}"
project_name = f"audit_proj_{suffix}"
test_username = f"audit_user_{suffix}"
test_password = "audit_pass_123"

team_id = None
project_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


def test_audit_log_populated():
    """Perform mutations, then verify audit log has entries."""
    global team_id, project_id
    with TestClient(app) as client:
        # Create an LLM (mutation)
        client.post(
            "/llms",
            json={
                "name": llm_name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
            },
            auth=ADMIN,
        )

        # Create a team (mutation)
        resp = client.post(
            "/teams",
            json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        team_id = resp.json()["id"]

        # Create a project (mutation)
        resp = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        project_id = resp.json()["project"]

        # Check audit log has entries
        resp = client.get("/audit", auth=ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert data["total"] > 0
        assert len(data["entries"]) > 0

        # Each entry should have required fields
        entry = data["entries"][0]
        assert "id" in entry
        assert "username" in entry
        assert "action" in entry
        assert "date" in entry


def test_audit_log_admin_only():
    """Non-admin users cannot access the audit log."""
    with TestClient(app) as client:
        # Create a non-admin user
        client.post(
            "/users",
            json={
                "username": test_username,
                "password": test_password,
                "admin": False,
                "private": False,
            },
            auth=ADMIN,
        )

        # Non-admin tries to access audit log
        resp = client.get("/audit", auth=(test_username, test_password))
        assert resp.status_code == 403


def test_audit_pagination():
    """Audit log supports pagination via start/end parameters."""
    with TestClient(app) as client:
        resp = client.get("/audit?start=0&end=5", auth=ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        # Should return at most 5 entries
        assert len(data["entries"]) <= 5


def test_cleanup():
    """Remove all test resources."""
    with TestClient(app) as client:
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
        client.delete(f"/users/{test_username}", auth=ADMIN)
