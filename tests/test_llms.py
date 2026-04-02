import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

test_llm_name = "test_llm_" + str(random.randint(0, 1000000))
test_user = "test_llm_user_" + str(random.randint(0, 1000000))
test_llm_id = None


def test_get_llms():
    with TestClient(app) as client:
        response = client.get("/llms", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_create_llm():
    global test_llm_id
    with TestClient(app) as client:
        response = client.post(
            "/llms",
            json={
                "name": test_llm_name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake123"},
                "privacy": "public",
                "type": "chat",
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == test_llm_name
        test_llm_id = data["id"]


def test_create_llm_non_admin():
    with TestClient(app) as client:
        # Create a non-admin user
        client.post(
            "/users",
            json={
                "username": test_user,
                "password": "testpass",
                "admin": False,
                "private": False,
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )

        response = client.post(
            "/llms",
            json={
                "name": "should_fail_llm",
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
                "type": "chat",
            },
            auth=(test_user, "testpass"),
        )
        assert response.status_code == 403

        # Clean up user
        client.delete(
            f"/users/{test_user}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )


def test_get_llm():
    with TestClient(app) as client:
        response = client.get(
            f"/llms/{test_llm_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_llm_name
        assert data["class_name"] == "OpenAI"
        assert data["privacy"] == "public"
        # API key should be masked
        options = data["options"]
        if isinstance(options, str):
            import json
            options = json.loads(options)
        assert options.get("api_key") == "********"


def test_update_llm():
    with TestClient(app) as client:
        response = client.patch(
            f"/llms/{test_llm_id}",
            json={"description": "Updated test LLM"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200

        # Verify update
        response = client.get(
            f"/llms/{test_llm_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["description"] == "Updated test LLM"


def test_delete_llm():
    with TestClient(app) as client:
        response = client.delete(
            f"/llms/{test_llm_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200


def test_delete_llm_not_found():
    with TestClient(app) as client:
        response = client.delete(
            "/llms/999999",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 404
