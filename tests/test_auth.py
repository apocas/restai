import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    """Clear DB-backed login rate limiter before each test."""
    from restai.database import DBWrapper
    from restai.models.databasemodels import LoginAttemptDatabase
    db = DBWrapper()
    try:
        db.db.query(LoginAttemptDatabase).delete()
        db.db.commit()
    except Exception:
        db.db.rollback()
    finally:
        db.db.close()


test_username = "test_auth_user_" + str(random.randint(0, 1000000))
test_password = "auth_test_pass"


def test_setup_user():
    with TestClient(app) as client:
        response = client.post(
            "/users",
            json={
                "username": test_username,
                "password": test_password,
                "admin": False,
                "private": False,
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 201
        assert response.json()["username"] == test_username


def test_login():
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            auth=(test_username, test_password),
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logged in successfully."
        assert "restai_token" in response.cookies


def test_whoami_with_cookie():
    with TestClient(app) as client:
        login_resp = client.post(
            "/auth/login",
            auth=(test_username, test_password),
        )
        cookie = login_resp.cookies.get("restai_token")
        assert cookie is not None

        response = client.get(
            "/auth/whoami",
            cookies={"restai_token": cookie},
        )
        assert response.status_code == 200
        assert response.json()["username"] == test_username


def test_whoami_with_basic_auth():
    with TestClient(app) as client:
        response = client.get(
            "/auth/whoami",
            auth=(test_username, test_password),
        )
        assert response.status_code == 200
        assert response.json()["username"] == test_username


def test_whoami_admin():
    with TestClient(app) as client:
        response = client.get(
            "/auth/whoami",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["is_admin"] is True


def test_login_wrong_password():
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            auth=(test_username, "wrong_password"),
        )
        assert response.status_code == 401


def test_whoami_no_auth():
    with TestClient(app) as client:
        response = client.get("/auth/whoami")
        assert response.status_code == 401


def test_logout_and_cleanup():
    with TestClient(app) as client:
        login_resp = client.post(
            "/auth/login",
            auth=(test_username, test_password),
        )
        cookie = login_resp.cookies.get("restai_token")

        response = client.post(
            "/auth/logout",
            cookies={"restai_token": cookie},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully."

        # Clean up test user
        response = client.delete(
            f"/users/{test_username}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
