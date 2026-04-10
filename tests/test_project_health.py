import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
test_username = f"health_user_{_suffix}"
test_password = "health_test_pass"


def test_setup():
    """Create a restricted user for permission tests."""
    with TestClient(app) as client:
        resp = client.post(
            "/users",
            json={
                "username": test_username,
                "password": test_password,
                "admin": False,
                "private": False,
                "is_restricted": True,
            },
            auth=ADMIN,
        )
        assert resp.status_code in (200, 201)


def test_projects_health():
    """GET /projects/health as admin returns a list of project health scores."""
    with TestClient(app) as client:
        resp = client.get("/projects/health", auth=ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Each entry should have the expected fields if projects exist
        if len(data) > 0:
            item = data[0]
            assert "project_id" in item
            assert "health" in item


def test_projects_health_non_admin():
    """GET /projects/health as restricted user should still return 200 (read endpoint)."""
    with TestClient(app) as client:
        resp = client.get("/projects/health", auth=(test_username, test_password))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


def test_cleanup():
    with TestClient(app) as client:
        client.delete(f"/users/{test_username}", auth=ADMIN)
