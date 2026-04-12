import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
team_name = f"analytics_team_{suffix}"
llm_name = f"analytics_llm_{suffix}"
project_name = f"analytics_proj_{suffix}"

team_id = None
project_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, LLM, and block project for analytics tests."""
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

    # Create team
    resp = client.post(
        "/teams",
        json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert resp.status_code == 201
    team_id = resp.json()["id"]

    # Create block project
    resp = client.post(
        "/projects",
        json={"name": project_name, "type": "block", "team_id": team_id},
        auth=ADMIN,
    )
    assert resp.status_code == 201
    project_id = resp.json()["project"]


def test_daily_tokens(client):
    """GET /projects/{id}/tokens/daily returns 200 with a tokens list."""
    resp = client.get(f"/projects/{project_id}/tokens/daily", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens" in data
    assert isinstance(data["tokens"], list)


def test_chunking_analytics_non_rag(client):
    """Chunking analytics returns 400 for a non-RAG (block) project."""
    resp = client.get(
        f"/projects/{project_id}/analytics/chunking", auth=ADMIN
    )
    assert resp.status_code == 400
    assert "RAG" in resp.json()["detail"]


def test_conversations(client):
    """GET /projects/{id}/analytics/conversations returns 200."""
    resp = client.get(
        f"/projects/{project_id}/analytics/conversations", auth=ADMIN
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "total_messages" in data["summary"]
    assert "total_conversations" in data["summary"]


def test_sources_non_rag(client):
    """Source analytics returns 400 for a non-RAG (block) project."""
    resp = client.get(
        f"/projects/{project_id}/analytics/sources", auth=ADMIN
    )
    assert resp.status_code == 400
    assert "RAG" in resp.json()["detail"]


def test_cleanup(client):
    """Remove all test resources."""
    if project_id:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
    if team_id:
        client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
