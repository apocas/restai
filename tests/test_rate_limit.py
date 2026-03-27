"""Tests for per-project rate limiting."""

import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
user_name = f"rl_user_{suffix}"
user_pass = "rl_pass_123"
team_name = f"rl_team_{suffix}"
llm_name = f"rl_llm_{suffix}"
project_name = f"rl-proj-{suffix}"

team_id = None
project_id = None


def test_rate_limit_setup():
    """Create user, team, LLM, and project for rate limit tests."""
    global team_id, project_id

    with TestClient(app) as client:
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
                "type": "chat",
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

        # Assign to user and configure a simple passthrough block workspace
        r = client.patch(
            f"/projects/{project_id}",
            json={
                "users": [user_name],
                "options": {
                    "rate_limit": 2,
                    "blockly_workspace": {
                        "blocks": {
                            "blocks": [
                                {
                                    "type": "restai_set_output",
                                    "inputs": {
                                        "VALUE": {
                                            "block": {"type": "restai_get_input"}
                                        }
                                    },
                                }
                            ]
                        },
                        "variables": [],
                    },
                },
            },
            auth=ADMIN,
        )
        assert r.status_code == 200


def test_rate_limit_allows_under_limit():
    """Requests under the rate limit should succeed."""
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "hello"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200, f"First request failed: {r.status_code} {r.text}"


def test_rate_limit_blocks_over_limit():
    """Requests over the rate limit should return 429."""
    with TestClient(app) as client:
        # Send requests up to and past the limit (rate_limit=2, one already sent above)
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "hello2"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200, f"Second request failed: {r.status_code}"

        # Third request should be rate limited
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "hello3"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 429, f"Expected 429, got {r.status_code}"
        assert "Rate limit" in r.json().get("detail", "")


def test_rate_limit_disabled_allows_all():
    """With rate_limit removed, requests that were previously blocked should succeed."""
    with TestClient(app) as client:
        # Remove rate limit but keep the workspace
        r = client.get(f"/projects/{project_id}", auth=ADMIN)
        current_options = r.json().get("options", {})
        current_options["rate_limit"] = None
        r = client.patch(
            f"/projects/{project_id}",
            json={"options": current_options},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Should succeed without limit even though there are already 2+ requests in the window
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "unlimited"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200, f"Request failed with rate limit disabled: {r.status_code}"


def test_rate_limit_teardown():
    """Clean up resources."""
    with TestClient(app) as client:
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/users/{user_name}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
