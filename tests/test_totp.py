import random
import pyotp
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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


test_username = "test_totp_user_" + str(random.randint(0, 1000000))
test_password = "totp_test_pass_123"
totp_secret = None
recovery_codes = []


def test_setup_totp_user(client):
    """Create a test user for TOTP tests."""
    response = client.post(
        "/users",
        json={"username": test_username, "password": test_password, "admin": False, "private": False},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 201


def test_totp_status_initially_disabled(client):
    response = client.get(
        f"/users/{test_username}/totp/status",
        auth=(test_username, test_password),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False


def test_totp_setup(client):
    global totp_secret, recovery_codes
    response = client.post(
        f"/users/{test_username}/totp/setup",
        json={},
        auth=(test_username, test_password),
    )
    assert response.status_code == 200
    data = response.json()
    assert "secret" in data
    assert "provisioning_uri" in data
    assert "recovery_codes" in data
    assert len(data["recovery_codes"]) == 8
    assert data["provisioning_uri"].startswith("otpauth://totp/")
    totp_secret = data["secret"]
    recovery_codes = data["recovery_codes"]


def test_totp_enable_with_invalid_code(client):
    response = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": "000000"},
        auth=(test_username, test_password),
    )
    assert response.status_code == 400
    assert "Invalid TOTP code" in response.json()["detail"]


def test_totp_enable_with_valid_code(client):
    code = pyotp.TOTP(totp_secret).now()
    response = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": code},
        auth=(test_username, test_password),
    )
    assert response.status_code == 200
    assert "enabled" in response.json()["message"].lower()


def test_totp_status_after_enable(client):
    response = client.get(
        f"/users/{test_username}/totp/status",
        auth=(test_username, test_password),
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_login_requires_totp_when_enabled():
    with TestClient(app) as c:
        response = c.post(
            "/auth/login",
            auth=(test_username, test_password),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requires_totp"] is True
        assert "totp_token" in data


def test_verify_totp_invalid_code():
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", auth=(test_username, test_password))
        totp_token = login_resp.json()["totp_token"]

        response = c.post(
            "/auth/verify-totp",
            json={"token": totp_token, "code": "000000"},
        )
        assert response.status_code == 401


def test_verify_totp_valid_code():
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", auth=(test_username, test_password))
        totp_token = login_resp.json()["totp_token"]

        code = pyotp.TOTP(totp_secret).now()
        response = c.post(
            "/auth/verify-totp",
            json={"token": totp_token, "code": code},
        )
        assert response.status_code == 200
        assert "Logged in" in response.json()["message"]


def test_verify_totp_expired_token():
    with TestClient(app) as c:
        response = c.post(
            "/auth/verify-totp",
            json={"token": "invalid.jwt.token", "code": "123456"},
        )
        assert response.status_code == 401


def test_verify_totp_recovery_code():
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", auth=(test_username, test_password))
        totp_token = login_resp.json()["totp_token"]

        response = c.post(
            "/auth/verify-totp",
            json={"token": totp_token, "code": recovery_codes[0]},
        )
        assert response.status_code == 200
        assert "Recovery code consumed" in response.json()["message"]


def test_recovery_code_single_use():
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", auth=(test_username, test_password))
        totp_token = login_resp.json()["totp_token"]

        # Same recovery code should fail now
        response = c.post(
            "/auth/verify-totp",
            json={"token": totp_token, "code": recovery_codes[0]},
        )
    assert response.status_code == 401


def test_totp_disable_wrong_password(client):
    response = client.post(
        f"/users/{test_username}/totp/disable",
        json={"password": "wrong_password"},
        auth=(test_username, test_password),
    )
    assert response.status_code == 403
    assert "Invalid password" in response.json()["detail"]


def test_totp_disable_with_password(client):
    response = client.post(
        f"/users/{test_username}/totp/disable",
        json={"password": test_password},
        auth=(test_username, test_password),
    )
    assert response.status_code == 200
    assert "disabled" in response.json()["message"].lower()


def test_login_normal_after_disable():
    """Uses separate client to avoid cookie pollution from login."""
    with TestClient(app) as c:
        response = c.post(
            "/auth/login",
            auth=(test_username, test_password),
        )
        assert response.status_code == 200
        data = response.json()
        assert "requires_totp" not in data or data.get("requires_totp") is not True
        assert "Logged in" in data.get("message", "")


def test_totp_setup_overwrites_previous(client):
    global totp_secret
    # Setup twice
    resp1 = client.post(f"/users/{test_username}/totp/setup", json={}, auth=(test_username, test_password))
    secret1 = resp1.json()["secret"]
    resp2 = client.post(f"/users/{test_username}/totp/setup", json={}, auth=(test_username, test_password))
    secret2 = resp2.json()["secret"]
    assert secret1 != secret2
    totp_secret = secret2


def test_non_admin_cannot_setup_other_user(client):
    response = client.post(
        "/users/admin/totp/setup",
        json={},
        auth=(test_username, test_password),
    )
    assert response.status_code == 403


def test_enforce_only_local_users(client):
    """API key auth should work regardless of 2FA enforcement."""
    # Create an API key for the test user
    response = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "totp_test_key"},
        auth=(test_username, test_password),
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]

    # Use API key auth — should work without 2FA
    response = client.get(
        "/auth/whoami",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == test_username


def test_enforce_2fa_setting(client):
    response = client.patch(
        "/settings",
        json={"enforce_2fa": True},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200


def test_cannot_disable_when_enforced(client):
    # First enable 2FA for the user
    client.post(f"/users/{test_username}/totp/setup", json={}, auth=(test_username, test_password))
    code = pyotp.TOTP(totp_secret).now()
    client.post(f"/users/{test_username}/totp/enable", json={"code": code}, auth=(test_username, test_password))

    # Try to disable — should fail
    response = client.post(
        f"/users/{test_username}/totp/disable",
        json={"password": test_password},
        auth=(test_username, test_password),
    )
    assert response.status_code == 403
    assert "enforced" in response.json()["detail"].lower()


def test_cleanup(client):
    """Reset enforce_2fa and delete test user."""
    client.patch("/settings", json={"enforce_2fa": False}, auth=("admin", RESTAI_DEFAULT_PASSWORD))
    client.delete(f"/users/{test_username}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
