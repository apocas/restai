import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
team_name = f"guards_team_{_suffix}"
llm_name = f"guards_llm_{_suffix}"
proj_name = f"guards_proj_{_suffix}"
team_id = None
project_id = None


def test_setup():
    """Create team, LLM, and a block project for guard endpoint tests."""
    global team_id, project_id
    with TestClient(app) as client:
        # Create LLM
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

        # Create team with LLM
        resp = client.post(
            "/teams",
            json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
            auth=ADMIN,
        )
        assert resp.status_code in (200, 201)
        team_id = resp.json()["id"]

        # Create a block project (no LLM required)
        resp = client.post(
            "/projects",
            json={"name": proj_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        project_id = resp.json()["project"]


def test_guards_summary():
    """GET /projects/{id}/guards/summary returns guard statistics."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/guards/summary",
            auth=ADMIN,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_checks" in data
        assert "total_blocks" in data
        assert "block_rate" in data


def test_guards_events():
    """GET /projects/{id}/guards/events returns paginated event list."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/guards/events",
            auth=ADMIN,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)
        assert "total" in data


def test_guards_daily():
    """GET /projects/{id}/guards/daily returns daily guard counts."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/guards/daily",
            auth=ADMIN,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)


def test_cleanup():
    with TestClient(app) as client:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
        client.delete(f"/teams/{team_id}", auth=ADMIN)
