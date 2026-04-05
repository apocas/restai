"""Tests for login endpoint rate limiting."""
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


def test_login_success():
    """Valid login works."""
    with TestClient(app) as client:
        resp = client.post("/auth/login", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200


def test_login_wrong_password():
    """Wrong password returns 401."""
    with TestClient(app) as client:
        resp = client.post("/auth/login", auth=("admin", "wrongpassword"))
        assert resp.status_code == 401


def test_login_rate_limit_triggers():
    """After 10 failed attempts, subsequent requests get 429."""
    # Reset the rate limiter state
    from restai.routers.auth import _login_attempts, _login_lock
    with _login_lock:
        _login_attempts.clear()

    with TestClient(app) as client:
        for i in range(10):
            client.post("/auth/login", auth=("admin", "bad"))

        # 11th attempt should be rate limited
        resp = client.post("/auth/login", auth=("admin", "bad"))
        assert resp.status_code == 429
        assert "Too many" in resp.json()["detail"]

    # Cleanup
    with _login_lock:
        _login_attempts.clear()


def test_login_rate_limit_doesnt_block_valid_after_reset():
    """After clearing state, valid login works again."""
    from restai.routers.auth import _login_attempts, _login_lock
    with _login_lock:
        _login_attempts.clear()

    with TestClient(app) as client:
        resp = client.post("/auth/login", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
