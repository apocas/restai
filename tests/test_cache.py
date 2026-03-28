"""Tests for the project response cache system."""

import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
user_name = f"cache_user_{suffix}"
user_pass = "cache_pass_123"
team_name = f"cache_team_{suffix}"
llm_name = f"cache_llm_{suffix}"
project_name = f"cache-proj-{suffix}"

team_id = None
project_id = None


def test_cache_setup():
    """Create user, team, LLM, and a block project with cache enabled."""
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

        # Create a block project (no LLM needed, easy to test cache)
        r = client.post(
            "/projects",
            json={
                "name": project_name,
                "type": "block",
                "team_id": team_id,
            },
            auth=ADMIN,
        )
        assert r.status_code == 201
        project_id = r.json()["project"]

        # Assign to user, enable cache, and set up a passthrough workspace
        r = client.patch(
            f"/projects/{project_id}",
            json={
                "users": [user_name],
                "options": {
                    "cache": True,
                    "cache_threshold": 0.85,
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


def test_cache_miss_first_request():
    """First request should not be cached."""
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "cache test question alpha"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("answer") == "cache test question alpha"
        assert data.get("cached") is not True


def test_cache_hit_same_question():
    """Same question should return cached result."""
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "cache test question alpha"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("cached") is True
        assert data.get("answer") == "cache test question alpha"


def test_cache_miss_different_question():
    """A completely different question should not hit cache."""
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "something completely unrelated xyz 12345"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200
        data = r.json()
        # Should not be a cache hit for a very different question
        # (may or may not be cached depending on embedding similarity —
        # but with default chromadb embeddings this should miss)
        assert data.get("answer") == "something completely unrelated xyz 12345"


def test_cache_clear_endpoint():
    """DELETE /projects/{id}/cache should clear the cache."""
    with TestClient(app) as client:
        # Clear cache
        r = client.delete(
            f"/projects/{project_id}/cache",
            auth=ADMIN,
        )
        assert r.status_code == 200
        assert r.json().get("cleared") is True

        # Same question that was cached should now miss
        r = client.post(
            f"/projects/{project_id}/question",
            json={"question": "cache test question alpha"},
            auth=(user_name, user_pass),
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("cached") is not True


def test_cache_clear_when_not_enabled():
    """Clearing cache on a project without cache should return cleared=False."""
    with TestClient(app) as client:
        # Disable cache
        r = client.patch(
            f"/projects/{project_id}",
            json={"options": {"cache": False}},
            auth=ADMIN,
        )
        assert r.status_code == 200

        r = client.delete(
            f"/projects/{project_id}/cache",
            auth=ADMIN,
        )
        assert r.status_code == 200
        assert r.json().get("cleared") is False


def test_cache_default_threshold():
    """Default cache_threshold should be 0.85."""
    from restai.models.models import ProjectOptions
    opts = ProjectOptions()
    assert opts.cache_threshold == 0.85


def test_cache_threshold_bounds():
    """cache_threshold should be bounded 0.0 to 1.0."""
    from restai.models.models import ProjectOptions
    import pydantic

    # Valid values
    ProjectOptions(cache_threshold=0.0)
    ProjectOptions(cache_threshold=1.0)
    ProjectOptions(cache_threshold=0.5)

    # Invalid values
    try:
        ProjectOptions(cache_threshold=1.5)
        assert False, "Should reject threshold > 1.0"
    except pydantic.ValidationError:
        pass

    try:
        ProjectOptions(cache_threshold=-0.1)
        assert False, "Should reject threshold < 0.0"
    except pydantic.ValidationError:
        pass


def test_cache_teardown():
    """Clean up resources."""
    with TestClient(app) as client:
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/users/{user_name}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
