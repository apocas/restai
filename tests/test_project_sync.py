import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
team_name = f"sync_team_{_suffix}"
llm_name = f"sync_llm_{_suffix}"
proj_name = f"sync_proj_{_suffix}"
team_id = None
project_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, LLM, and a block project for sync endpoint tests."""
    global team_id, project_id
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

    # Create a block project
    resp = client.post(
        "/projects",
        json={"name": proj_name, "type": "block", "team_id": team_id},
        auth=ADMIN,
    )
    assert resp.status_code == 201
    project_id = resp.json()["project"]


def test_sync_status(client):
    """GET /projects/{id}/sync/status returns sync status info."""
    resp = client.get(
        f"/projects/{project_id}/sync/status",
        auth=ADMIN,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "sources" in data
    assert data["sources"] == 0


def test_sync_trigger_no_sources(client):
    """POST /projects/{id}/sync/trigger with no sync sources should return 400."""
    resp = client.post(
        f"/projects/{project_id}/sync/trigger",
        auth=ADMIN,
    )
    # Block projects return 400 ("Sync only available for RAG projects")
    # or if it were RAG with no sources, also 400
    assert resp.status_code == 400


def test_sync_status_persists(client):
    """Verify sync status reflects project options."""
    # Initially no sync sources
    resp = client.get(
        f"/projects/{project_id}/sync/status",
        auth=ADMIN,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["sources"] == 0


def test_cleanup(client):
    client.delete(f"/projects/{project_id}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
    client.delete(f"/teams/{team_id}", auth=ADMIN)
