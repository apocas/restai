from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


def test_top_projects():
    with TestClient(app) as client:
        response = client.get(
            "/statistics/top-projects",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)


def test_top_projects_with_limit():
    with TestClient(app) as client:
        response = client.get(
            "/statistics/top-projects?limit=5",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) <= 5


def test_summary():
    """GET /statistics/summary returns expected fields."""
    with TestClient(app) as client:
        resp = client.get("/statistics/summary", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_projects", "total_users", "total_teams", "total_tokens", "total_cost"):
            assert key in data


def test_daily_tokens():
    """GET /statistics/daily-tokens returns token data."""
    with TestClient(app) as client:
        resp = client.get("/statistics/daily-tokens?days=7", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens" in data
        assert isinstance(data["tokens"], list)


def test_top_llms():
    """GET /statistics/top-llms returns LLM usage data."""
    with TestClient(app) as client:
        resp = client.get("/statistics/top-llms?limit=5", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
        data = resp.json()
        assert "llms" in data
        assert isinstance(data["llms"], list)


def test_statistics_non_admin():
    """Non-admin user can access statistics (for their own projects)."""
    import random
    username = f"stats_user_{random.randint(0, 1000000)}"
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        client.post("/users", json={"username": username, "password": "pass123", "admin": False, "private": False}, auth=auth)

        resp = client.get("/statistics/summary", auth=(username, "pass123"))
        assert resp.status_code == 200

        resp = client.get("/statistics/top-projects", auth=(username, "pass123"))
        assert resp.status_code == 200

        client.delete(f"/users/{username}", auth=auth)
