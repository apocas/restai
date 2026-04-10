"""Tests for per-project budget checks (rate_limit is already covered by test_rate_limit.py)."""

import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 999999))
team_name = f"budget_team_{suffix}"
llm_name = f"budget_llm_{suffix}"
project_name = f"budget-proj-{suffix}"

team_id = None
project_id = None


def test_setup():
    """Create team, LLM, and block project."""
    global team_id, project_id

    with TestClient(app) as client:
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
            json={"name": team_name},
            auth=ADMIN,
        )
        assert r.status_code == 201
        team_id = r.json()["id"]

        r = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert r.status_code == 201
        project_id = r.json()["project"]


def test_project_options_rate_limit_persists():
    """Verify rate_limit option is saved and returned in project details."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{project_id}",
            json={"options": {"rate_limit": 50}},
            auth=ADMIN,
        )
        assert r.status_code == 200

        r = client.get(f"/projects/{project_id}", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["options"]["rate_limit"] == 50


def test_project_options_rate_limit_nullable():
    """Verify rate_limit can be set to null (unlimited)."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{project_id}",
            json={"options": {"rate_limit": None}},
            auth=ADMIN,
        )
        assert r.status_code == 200

        r = client.get(f"/projects/{project_id}", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["options"]["rate_limit"] is None


def test_cleanup():
    """Clean up resources."""
    with TestClient(app) as client:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
        client.delete(f"/teams/{team_id}", auth=ADMIN)
