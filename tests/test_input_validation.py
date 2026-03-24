from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

INVALID_NAMES = [
    "has/slash",
    "has space",
    "has@at",
    "has&amp",
    "has?query",
    "has#hash",
    "has%percent",
    "has+plus",
    "has=equals",
    "../traversal",
]

VALID_NAMES = [
    "simple",
    "with-hyphen",
    "with_underscore",
    "with.dot",
    "MixedCase123",
]


def test_project_name_validation():
    with TestClient(app) as client:
        for name in INVALID_NAMES:
            response = client.post(
                "/projects",
                json={"name": name, "type": "inference", "llm": "fake", "team_id": 1},
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            assert response.status_code == 422, f"Expected 422 for project name {name!r}, got {response.status_code}"


def test_user_name_validation():
    with TestClient(app) as client:
        for name in INVALID_NAMES:
            response = client.post(
                "/users",
                json={"username": name, "password": "testpass"},
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            assert response.status_code == 422, f"Expected 422 for username {name!r}, got {response.status_code}"


def test_team_name_validation():
    with TestClient(app) as client:
        for name in INVALID_NAMES:
            response = client.post(
                "/teams",
                json={"name": name},
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            assert response.status_code == 422, f"Expected 422 for team name {name!r}, got {response.status_code}"


def test_llm_name_validation():
    with TestClient(app) as client:
        for name in INVALID_NAMES:
            response = client.post(
                "/llms",
                json={
                    "name": name,
                    "class_name": "OpenAI",
                    "options": {"model": "test"},
                    "privacy": "public",
                    "type": "chat",
                },
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            assert response.status_code == 422, f"Expected 422 for LLM name {name!r}, got {response.status_code}"


def test_embedding_name_validation():
    with TestClient(app) as client:
        for name in INVALID_NAMES:
            response = client.post(
                "/embeddings",
                json={
                    "name": name,
                    "class_name": "OpenAI",
                    "options": "{}",
                    "privacy": "public",
                },
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            assert response.status_code == 422, f"Expected 422 for embedding name {name!r}, got {response.status_code}"


def test_valid_names_accepted():
    """Ensure valid names don't trigger validation errors (they may fail for other reasons like missing LLM)."""
    with TestClient(app) as client:
        for name in VALID_NAMES:
            response = client.post(
                "/users",
                json={"username": name, "password": "testpass"},
                auth=("admin", RESTAI_DEFAULT_PASSWORD),
            )
            # Should not be 422 (validation error) — may be 201 or other status
            assert response.status_code != 422, f"Valid username {name!r} was incorrectly rejected"

        # Clean up created users
        for name in VALID_NAMES:
            client.delete(f"/users/{name}", auth=("admin", RESTAI_DEFAULT_PASSWORD))


def test_llm_invalid_privacy():
    with TestClient(app) as client:
        response = client.post(
            "/llms",
            json={
                "name": "test-llm",
                "class_name": "OpenAI",
                "options": {"model": "test"},
                "privacy": "secret",
                "type": "chat",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 422, f"Expected 422 for invalid privacy, got {response.status_code}"


def test_llm_invalid_type():
    with TestClient(app) as client:
        response = client.post(
            "/llms",
            json={
                "name": "test-llm",
                "class_name": "OpenAI",
                "options": {"model": "test"},
                "privacy": "public",
                "type": "magic",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 422, f"Expected 422 for invalid type, got {response.status_code}"


def test_llm_invalid_class_name():
    with TestClient(app) as client:
        response = client.post(
            "/llms",
            json={
                "name": "test-llm",
                "class_name": "FakeProvider",
                "options": {"model": "test"},
                "privacy": "public",
                "type": "chat",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 422, f"Expected 422 for invalid class_name, got {response.status_code}"


def test_embedding_invalid_class_name():
    with TestClient(app) as client:
        response = client.post(
            "/embeddings",
            json={
                "name": "test-emb",
                "class_name": "FakeEmbedding",
                "options": "{}",
                "privacy": "public",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 422, f"Expected 422 for invalid embedding class_name, got {response.status_code}"


def test_project_invalid_type():
    with TestClient(app) as client:
        response = client.post(
            "/projects",
            json={"name": "test-proj", "type": "magic", "llm": "fake", "team_id": 1},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 422, f"Expected 422 for invalid project type, got {response.status_code}"


def test_llm_valid_enums_accepted():
    """Ensure valid enum values don't trigger validation errors."""
    with TestClient(app) as client:
        response = client.post(
            "/llms",
            json={
                "name": "test-valid-llm",
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
                "type": "chat",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        # Should not be 422 — may succeed (201) or fail for other reasons
        assert response.status_code != 422, f"Valid LLM enums were incorrectly rejected"
        # Clean up if created
        if response.status_code == 201:
            client.delete("/llms/test-valid-llm", auth=("admin", RESTAI_DEFAULT_PASSWORD))
