import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
team_name = f"prompts_team_{suffix}"
llm_name = f"prompts_llm_{suffix}"
project_name = f"prompts_proj_{suffix}"

team_id = None
project_id = None
version_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, LLM, and block project for prompt version tests."""
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


def test_list_prompts_initial(client):
    """A new project with a system prompt has an initial version."""
    resp = client.get(f"/projects/{project_id}/prompts", auth=ADMIN)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_auto_version_on_edit(client):
    """Editing the system prompt creates a prompt version automatically."""
    global version_id
    # Set a system prompt
    resp = client.patch(
        f"/projects/{project_id}",
        json={"system": "First version of the prompt."},
        auth=ADMIN,
    )
    assert resp.status_code == 200

    # List prompt versions
    resp = client.get(f"/projects/{project_id}/prompts", auth=ADMIN)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    version_id = versions[0]["id"]
    assert versions[0]["system_prompt"] == "First version of the prompt."


def test_get_version(client):
    """Retrieve a specific prompt version by ID."""
    resp = client.get(
        f"/projects/{project_id}/prompts/{version_id}", auth=ADMIN
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == version_id
    assert data["project_id"] == project_id
    assert data["system_prompt"] == "First version of the prompt."
    assert "version" in data
    assert "created_at" in data


def test_activate_version(client):
    """Update prompt, then activate the old version to restore it."""
    # Change the prompt to something new
    resp = client.patch(
        f"/projects/{project_id}",
        json={"system": "Second version of the prompt."},
        auth=ADMIN,
    )
    assert resp.status_code == 200

    # Verify the project now has the new prompt
    resp = client.get(f"/projects/{project_id}", auth=ADMIN)
    assert resp.json()["system"] == "Second version of the prompt."

    # Activate the first version
    resp = client.post(
        f"/projects/{project_id}/prompts/{version_id}/activate",
        auth=ADMIN,
    )
    assert resp.status_code == 200

    # Verify the prompt was restored
    resp = client.get(f"/projects/{project_id}", auth=ADMIN)
    assert resp.json()["system"] == "First version of the prompt."


def test_cleanup(client):
    """Remove all test resources."""
    if project_id:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
    if team_id:
        client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
