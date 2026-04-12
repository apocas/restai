import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

_suffix = str(random.randint(0, 999999))
test_username = f"statuser_{_suffix}"
test_password = "stat_test_pass"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create a non-admin user for permission tests."""
    resp = client.post(
        "/users",
        json={"username": test_username, "password": test_password, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert resp.status_code in (200, 201)


def test_statistics_users_list(client):
    """GET /statistics/users as admin returns a users list."""
    resp = client.get("/statistics/users", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert isinstance(data["users"], list)


def test_statistics_users_detail(client):
    """GET /statistics/users/1 as admin returns user activity details."""
    resp = client.get("/statistics/users/1", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "daily" in data
    assert "top_projects" in data
    assert "hourly" in data


def test_statistics_users_non_admin(client):
    """GET /statistics/users as non-admin should return 403."""
    resp = client.get("/statistics/users", auth=(test_username, test_password))
    assert resp.status_code == 403


def test_cleanup(client):
    client.delete(f"/users/{test_username}", auth=ADMIN)
