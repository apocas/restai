"""Tests for project embeddings endpoints on non-RAG projects."""

import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 999999))
user_name = f"emb_user_{suffix}"
user_pass = "emb_pass_123"
team_name = f"emb_team_{suffix}"
llm_name = f"emb_llm_{suffix}"
project_name = f"emb-proj-{suffix}"

team_id = None
project_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create user, team, LLM, and block project for embeddings tests."""
    global team_id, project_id

    r = client.post(
        "/users",
        json={"username": user_name, "password": user_pass, "is_admin": False, "is_private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201

    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code in (200, 201)

    r = client.post(
        "/teams",
        json={"name": team_name, "users": [user_name], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201
    team_id = r.json()["id"]

    r = client.post(
        "/projects",
        json={
            "name": project_name,
            "llm": llm_name,
            "type": "block",
            "team_id": team_id,
        },
        auth=ADMIN,
    )
    assert r.status_code == 201
    project_id = r.json()["project"]

    # Assign user to project
    r = client.patch(
        f"/projects/{project_id}",
        json={"users": [user_name]},
        auth=ADMIN,
    )
    assert r.status_code == 200


def test_list_embeddings_non_rag(client):
    """GET /projects/{id}/embeddings on a block project should return 400."""
    r = client.get(
        f"/projects/{project_id}/embeddings",
        auth=(user_name, user_pass),
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    assert "RAG" in r.json().get("detail", "")


def test_search_non_rag(client):
    """POST /projects/{id}/embeddings/search on a block project should return 400."""
    r = client.post(
        f"/projects/{project_id}/embeddings/search",
        json={"text": "test query"},
        auth=(user_name, user_pass),
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    assert "RAG" in r.json().get("detail", "")


def test_reset_non_rag(client):
    """POST /projects/{id}/embeddings/reset on a block project should return 400."""
    r = client.post(
        f"/projects/{project_id}/embeddings/reset",
        auth=(user_name, user_pass),
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    assert "RAG" in r.json().get("detail", "")


def test_cleanup(client):
    """Clean up resources created for embeddings tests."""
    if project_id:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
    if team_id:
        client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/users/{user_name}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
