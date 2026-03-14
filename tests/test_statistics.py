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
