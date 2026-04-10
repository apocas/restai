import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
team_name = f"clone_team_{suffix}"
llm_name = f"clone_llm_{suffix}"
project_name = f"clone_proj_{suffix}"
cloned_name = f"cloned_proj_{suffix}"

team_id = None
project_id = None
cloned_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


def test_setup():
    """Create a team, LLM, and block project with system prompt and censorship."""
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

        # Create team with the LLM
        resp = client.post(
            "/teams",
            json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        team_id = resp.json()["id"]

        # Create block project (no LLM required)
        resp = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        project_id = resp.json()["project"]

        # Set system prompt and censorship via PATCH
        resp = client.patch(
            f"/projects/{project_id}",
            json={
                "system": "You are a helpful test assistant.",
                "censorship": "This content is not allowed.",
            },
            auth=ADMIN,
        )
        assert resp.status_code == 200


def test_clone_project():
    """Clone a project and verify settings are copied."""
    global cloned_id
    with TestClient(app) as client:
        resp = client.post(
            f"/projects/{project_id}/clone",
            json={"name": cloned_name},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        cloned_id = resp.json()["project"]
        assert cloned_id != project_id

        # Verify cloned project exists and settings match
        resp = client.get(f"/projects/{cloned_id}", auth=ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"] == "You are a helpful test assistant."
        assert data["censorship"] == "This content is not allowed."
        assert data["type"] == "block"


def test_clone_duplicate_name():
    """Cloning with a name that already exists returns 409."""
    with TestClient(app) as client:
        resp = client.post(
            f"/projects/{project_id}/clone",
            json={"name": cloned_name},
            auth=ADMIN,
        )
        assert resp.status_code == 409


def test_clone_nonexistent():
    """Cloning a project that doesn't exist returns 404."""
    with TestClient(app) as client:
        resp = client.post(
            "/projects/999999/clone",
            json={"name": f"ghost_{suffix}"},
            auth=ADMIN,
        )
        assert resp.status_code in (404, 403)


def test_cleanup():
    """Remove all test resources."""
    with TestClient(app) as client:
        if cloned_id:
            client.delete(f"/projects/{cloned_id}", auth=ADMIN)
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
