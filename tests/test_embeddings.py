import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

test_embedding_name = "test_embedding_" + str(random.randint(0, 1000000))
test_user = "test_emb_user_" + str(random.randint(0, 1000000))
test_embedding_id = None


def test_get_embeddings():
    with TestClient(app) as client:
        response = client.get("/embeddings", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_create_embedding():
    global test_embedding_id
    with TestClient(app) as client:
        response = client.post(
            "/embeddings",
            json={
                "name": test_embedding_name,
                "class_name": "Ollama",
                "options": "{}",
                "privacy": "public",
                "dimension": 768,
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == test_embedding_name
        test_embedding_id = data["id"]


def test_create_embedding_non_admin():
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
            "/embeddings",
            json={
                "name": "should_fail_embedding",
                "class_name": "Ollama",
                "options": "{}",
                "privacy": "public",
                "dimension": 768,
            },
            auth=(test_user, "testpass"),
        )
        assert response.status_code == 403

        # Clean up user
        client.delete(
            f"/users/{test_user}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )


def test_get_embedding():
    with TestClient(app) as client:
        response = client.get(
            f"/embeddings/{test_embedding_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_embedding_name
        assert data["class_name"] == "Ollama"
        assert data["privacy"] == "public"


def test_update_embedding():
    with TestClient(app) as client:
        response = client.patch(
            f"/embeddings/{test_embedding_id}",
            json={"description": "Updated test embedding", "dimension": 512},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200

        # Verify update
        response = client.get(
            f"/embeddings/{test_embedding_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated test embedding"
        assert data["dimension"] == 512


def test_delete_embedding():
    with TestClient(app) as client:
        response = client.delete(
            f"/embeddings/{test_embedding_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200


def test_delete_embedding_not_found():
    with TestClient(app) as client:
        response = client.delete(
            "/embeddings/999999",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 404
