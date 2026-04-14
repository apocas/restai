import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_get():
    with TestClient(app, follow_redirects=False) as c:
        response = c.get("/")
        assert response.status_code in (301, 302, 307, 308)
        assert "/admin" in response.headers.get("location", "")

def test_version(client):
    response = client.get("/version", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert isinstance(data["version"], str)

def test_version_unauthenticated(client):
    response = client.get("/version")
    assert response.status_code == 401

def test_setup(client):
    response = client.get("/setup")
    assert response.status_code == 200
    data = response.json()
    for key in ("sso", "proxy", "gpu", "app_name", "hide_branding", "proxy_url"):
        assert key in data

def test_info_authenticated(client):
    response = client.get("/info", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    data = response.json()
    for key in ("version", "loaders", "llms", "embeddings", "vectorstores"):
        assert key in data

def test_info_no_auth(client):
    response = client.get("/info")
    assert response.status_code == 401
