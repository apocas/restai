import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
team_name = f"direct_team_{_suffix}"
llm_name = f"direct_llm_{_suffix}"
test_username = f"direct_user_{_suffix}"
test_password = "direct_test_pass"
team_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, LLM, user, and wire them together."""
    global team_id
    # Create LLM
    resp = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)

    # Create user
    resp = client.post(
        "/users",
        json={"username": test_username, "password": test_password, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)

    # Create team with user and LLM
    resp = client.post(
        "/teams",
        json={"name": team_name, "users": [test_username], "admins": [], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]


def test_list_models_admin(client):
    """Admin should see all models including the test LLM."""
    resp = client.get("/direct/models", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "llms" in data
    assert isinstance(data["llms"], list)
    # Our LLM should be present
    names = [l["name"] for l in data["llms"]]
    assert llm_name in names


def test_list_models_user(client):
    """Non-admin user should see LLMs filtered by team membership."""
    resp = client.get("/direct/models", auth=(test_username, test_password))
    assert resp.status_code == 200
    data = resp.json()
    assert "llms" in data
    assert isinstance(data["llms"], list)
    # User's team has our test LLM
    names = [l["name"] for l in data["llms"]]
    assert llm_name in names


def test_chat_completions_no_model(client):
    """POST /v1/chat/completions with a nonexistent model should fail."""
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent_model_xyz",
            "messages": [{"role": "user", "content": "hi"}],
        },
        auth=ADMIN,
    )
    # Should return a 4xx or 5xx error (403 team resolution or 404 not found)
    assert resp.status_code >= 400


def test_cleanup(client):
    client.delete(f"/users/{test_username}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
    client.delete(f"/teams/{team_id}", auth=ADMIN)
