import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
test_username = f"admin_ep_user_{suffix}"
test_password = "admin_ep_pass_123"
nonadmin_username = f"admin_ep_nonadmin_{suffix}"
nonadmin_password = "nonadmin_pass_123"

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


def test_setup():
    """Create test users for admin endpoint tests."""
    with TestClient(app) as client:
        # Create a non-admin user
        resp = client.post(
            "/users",
            json={
                "username": test_username,
                "password": test_password,
                "admin": False,
                "private": False,
            },
            auth=ADMIN,
        )
        assert resp.status_code == 201

        resp = client.post(
            "/users",
            json={
                "username": nonadmin_username,
                "password": nonadmin_password,
                "admin": False,
                "private": False,
            },
            auth=ADMIN,
        )
        assert resp.status_code == 201


def test_impersonate():
    """Admin can impersonate another user."""
    with TestClient(app) as client:
        resp = client.post(
            f"/auth/impersonate/{test_username}",
            auth=ADMIN,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["impersonating"] is True
        assert test_username in data["message"]


def test_impersonate_nonexistent_user():
    """Impersonating a user that doesn't exist returns 404."""
    with TestClient(app) as client:
        resp = client.post(
            f"/auth/impersonate/nonexistent_user_{suffix}",
            auth=ADMIN,
        )
        assert resp.status_code == 404


def test_impersonate_non_admin_rejected():
    """Non-admin users cannot impersonate others."""
    with TestClient(app) as client:
        resp = client.post(
            f"/auth/impersonate/{test_username}",
            auth=(nonadmin_username, nonadmin_password),
        )
        assert resp.status_code == 403


def test_gpu_info():
    """GET /settings/gpu-info returns 200 (may be empty list if no GPU)."""
    with TestClient(app) as client:
        resp = client.get("/settings/gpu-info", auth=ADMIN)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_cleanup():
    """Remove test users."""
    with TestClient(app) as client:
        client.delete(f"/users/{test_username}", auth=ADMIN)
        client.delete(f"/users/{nonadmin_username}", auth=ADMIN)
