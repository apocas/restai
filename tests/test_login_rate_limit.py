"""Tests for login endpoint rate limiting."""
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _clear_login_attempts():
    from restai.database import DBWrapper
    from restai.models.databasemodels import LoginAttemptDatabase
    db = DBWrapper()
    db.db.query(LoginAttemptDatabase).delete()
    db.db.commit()
    db.db.close()


def test_login_success(client):
    """Valid login works."""
    _clear_login_attempts()
    resp = client.post("/auth/login", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert resp.status_code == 200


def test_login_wrong_password(client):
    """Wrong password returns 401."""
    _clear_login_attempts()
    resp = client.post("/auth/login", auth=("admin", "wrongpassword"))
    assert resp.status_code == 401


def test_login_rate_limit_triggers(client):
    """After 10 attempts, subsequent requests get 429."""
    _clear_login_attempts()
    for i in range(10):
        client.post("/auth/login", auth=("admin", "bad"))

    # 11th attempt should be rate limited
    resp = client.post("/auth/login", auth=("admin", "bad"))
    assert resp.status_code == 429
    assert "Too many" in resp.json()["detail"]

    _clear_login_attempts()


def test_login_rate_limit_doesnt_block_valid_after_reset(client):
    """After clearing state, valid login works again."""
    _clear_login_attempts()
    resp = client.post("/auth/login", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert resp.status_code == 200
