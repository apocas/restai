import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
test_username = f"tools_user_{_suffix}"
test_password = "tools_test_pass"


def test_setup():
    """Create a non-admin user for permission tests."""
    with TestClient(app) as client:
        resp = client.post(
            "/users",
            json={"username": test_username, "password": test_password, "admin": False, "private": False},
            auth=ADMIN,
        )
        assert resp.status_code in (200, 201)


def test_list_classifiers():
    """GET /tools/classifiers returns available classifier models."""
    with TestClient(app) as client:
        resp = client.get("/tools/classifiers", auth=ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert "classifiers" in data
        assert isinstance(data["classifiers"], list)
        assert "default" in data


def test_classifier_endpoint():
    """POST /tools/classifier classifies text into provided labels."""
    with TestClient(app) as client:
        resp = client.post(
            "/tools/classifier",
            json={
                "sequence": "This is great",
                "labels": ["positive", "negative"],
            },
            auth=ADMIN,
        )
        # 200 if classifier is available, 500 if model not downloaded
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "labels" in data or "scores" in data or "sequence" in data


def test_openai_compat_models_admin_only():
    """GET /tools/openai-compat/models/{id} as non-admin should return 403."""
    with TestClient(app) as client:
        resp = client.get(
            "/tools/openai-compat/models/1",
            auth=(test_username, test_password),
        )
        assert resp.status_code == 403


def test_ollama_models_no_server():
    """POST /tools/ollama/models with unreachable server should return 500."""
    with TestClient(app) as client:
        resp = client.post(
            "/tools/ollama/models",
            json={"host": "localhost", "port": 99999},
            auth=ADMIN,
        )
        assert resp.status_code == 500


def test_ollama_pull_no_server():
    """POST /tools/ollama/pull with unreachable server should return 500."""
    with TestClient(app) as client:
        resp = client.post(
            "/tools/ollama/pull",
            json={"name": "test", "host": "localhost", "port": 99999},
            auth=ADMIN,
        )
        assert resp.status_code == 500


def test_cleanup():
    with TestClient(app) as client:
        client.delete(f"/users/{test_username}", auth=ADMIN)
