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


def test_totp_setup_requires_password(client):
    """Step-up auth: setup without a password (or with the wrong one)
    must be refused, even though the session is valid. Closes the
    "session-only attacker rotates the second factor" pivot."""
    r1 = client.post(
        f"/users/{test_username}/totp/setup",
        json={},  # no password — schema rejects with 422
        auth=(test_username, test_password),
    )
    assert r1.status_code in (400, 422), r1.text

    r2 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": "definitely-not-the-right-password"},
        auth=(test_username, test_password),
    )
    assert r2.status_code == 403, r2.text


def test_totp_setup(client):
    global totp_secret, recovery_codes
    response = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password},
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
        json={"code": "000000", "password": test_password},
        auth=(test_username, test_password),
    )
    assert response.status_code == 400
    assert "Invalid TOTP code" in response.json()["detail"]


def test_totp_enable_with_wrong_password(client):
    code = pyotp.TOTP(totp_secret).now()
    response = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": code, "password": "wrong_password"},
        auth=(test_username, test_password),
    )
    assert response.status_code == 403
    assert "Invalid password" in response.json()["detail"]


def test_totp_enable_with_valid_code(client):
    code = pyotp.TOTP(totp_secret).now()
    response = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": code, "password": test_password},
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


def test_totp_setup_blocked_without_current_code_when_enabled(client):
    """The reported attack: an attacker with a valid session calls
    /totp/setup and silently overwrites the legitimate user's secret.
    Closed by requiring step-up — when 2FA is currently enabled,
    /totp/setup must also receive a valid current TOTP (or recovery)
    code BEFORE rotating the secret."""
    # Password alone, no `code` field — must 400.
    r1 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password},
        auth=(test_username, test_password),
    )
    assert r1.status_code == 400, r1.text
    assert "totp" in r1.json()["detail"].lower()

    # Wrong code — must 400.
    r2 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password, "code": "000000"},
        auth=(test_username, test_password),
    )
    assert r2.status_code == 400, r2.text
    assert "invalid totp" in r2.json()["detail"].lower()

    # Existing secret must NOT have been rotated by the failed attempts.
    # Compute the current valid code against `totp_secret` (set during
    # test_totp_setup) — if rotation had succeeded, this code wouldn't
    # match the stored secret on /enable any more.
    code = pyotp.TOTP(totp_secret).now()
    # Pass step-up successfully — this rotates and returns NEW codes,
    # which we keep so subsequent tests can use them.
    global recovery_codes
    r3 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password, "code": code},
        auth=(test_username, test_password),
    )
    assert r3.status_code == 200, r3.text
    new_secret = r3.json()["secret"]
    new_codes = r3.json()["recovery_codes"]
    assert new_secret != totp_secret, (
        "secret should rotate when step-up succeeds"
    )

    # Re-enable with the freshly minted secret so the rest of the
    # suite (which assumes 2FA is on with `totp_secret`) keeps
    # working. Re-stash `totp_secret` and `recovery_codes` for them.
    new_code = pyotp.TOTP(new_secret).now()
    r_enable = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": new_code, "password": test_password},
        auth=(test_username, test_password),
    )
    assert r_enable.status_code == 200, r_enable.text
    globals()["totp_secret"] = new_secret
    recovery_codes = new_codes


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


def test_totp_token_rejected_as_session_cookie():
    """The temp `totp_token` JWT issued by /auth/login (purpose=
    'totp_verify') must NOT authenticate a session if pasted into
    `restai_token`. Otherwise, an attacker who has the password but
    not the second factor could see the totp_token in the login
    response, drop it into the cookie jar, and get a 5-minute
    fully-authenticated session — bypassing 2FA.
    """
    with TestClient(app) as c:
        login_resp = c.post("/auth/login", auth=(test_username, test_password))
        assert login_resp.status_code == 200
        assert login_resp.json().get("requires_totp") is True
        totp_token = login_resp.json()["totp_token"]

        # Paste the purpose=totp_verify JWT into the session slot.
        # `/auth/whoami` is the simplest "am I logged in?" endpoint.
        r = c.get("/auth/whoami", cookies={"restai_token": totp_token})
        assert r.status_code == 401, (
            f"totp_token leaked into session: status={r.status_code} "
            f"body={r.text[:200]}"
        )


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
    """Two consecutive successful setups produce different secrets.
    Each setup requires step-up auth (password + current code while
    2FA is enabled), so this also exercises the recovery path of
    rotating using a freshly-minted code."""
    global totp_secret, recovery_codes

    code1 = pyotp.TOTP(totp_secret).now()
    resp1 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password, "code": code1},
        auth=(test_username, test_password),
    )
    assert resp1.status_code == 200, resp1.text
    secret1 = resp1.json()["secret"]

    code2 = pyotp.TOTP(secret1).now()
    resp2 = client.post(
        f"/users/{test_username}/totp/setup",
        json={"password": test_password, "code": code2},
        auth=(test_username, test_password),
    )
    assert resp2.status_code == 200, resp2.text
    secret2 = resp2.json()["secret"]

    assert secret1 != secret2

    # Re-enable with the latest secret so subsequent tests still see
    # 2FA as on and `totp_secret` matches the stored one.
    new_code = pyotp.TOTP(secret2).now()
    r_enable = client.post(
        f"/users/{test_username}/totp/enable",
        json={"code": new_code, "password": test_password},
        auth=(test_username, test_password),
    )
    assert r_enable.status_code == 200, r_enable.text
    totp_secret = secret2
    recovery_codes = resp2.json()["recovery_codes"]


def test_non_admin_cannot_setup_other_user(client):
    response = client.post(
        "/users/admin/totp/setup",
        json={"password": "any"},
        auth=(test_username, test_password),
    )
    assert response.status_code == 403


def test_enforce_only_local_users(client):
    """API key auth should work regardless of 2FA enforcement."""
    ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
    # API keys must belong to a team the owner is in — add them to admin's team.
    team_id = client.get("/users/admin", auth=ADMIN).json()["teams"][0]["id"]
    client.post(f"/teams/{team_id}/users/{test_username}", auth=ADMIN)
    response = client.post(
        f"/users/{test_username}/apikeys",
        json={"description": "totp_test_key", "team_id": team_id},
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


def test_enforce_2fa_blocks_login_for_unenrolled_user(client):
    """Regression for H3 — enforce_2fa was previously only consulted in
    UI status and the /totp/disable endpoint. Local /auth/login ignored
    the setting and minted full session cookies for users who hadn't
    enrolled in TOTP, defeating the platform-wide mandate.

    Setting must already be True when this runs (set by the preceding
    test_enforce_2fa_setting test in this module).
    """
    import base64
    unenrolled_user = "test_enforce2fa_unenrolled_" + str(random.randint(0, 1000000))
    unenrolled_pass = "no_totp_pass_456"
    create = client.post(
        "/users",
        json={"username": unenrolled_user, "password": unenrolled_pass, "admin": False, "private": False},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert create.status_code == 201

    # Hit /auth/login directly with Basic auth — bypassing the conftest's
    # auth-tuple shim so we can observe the exact response. The shim
    # swallows failures and re-sends requests unauthenticated, which
    # would mask the 403 we want to assert here.
    basic_header = "Basic " + base64.b64encode(
        f"{unenrolled_user}:{unenrolled_pass}".encode()
    ).decode()
    login = client.post("/auth/login", headers={"Authorization": basic_header})
    assert login.status_code == 403, f"expected 403, got {login.status_code}: {login.text}"
    assert "two-factor" in login.json().get("detail", "").lower()
    assert "restai_token" not in login.cookies

    # Cleanup the temp user. Uses admin shim (which logs in via the
    # configured admin path — admin retains TOTP-bypass via test setup).
    client.delete(f"/users/{unenrolled_user}", auth=("admin", RESTAI_DEFAULT_PASSWORD))


def test_cannot_disable_when_enforced(client):
    client.post(f"/users/{test_username}/totp/setup", json={}, auth=(test_username, test_password))
    code = pyotp.TOTP(totp_secret).now()
    client.post(f"/users/{test_username}/totp/enable", json={"code": code, "password": test_password}, auth=(test_username, test_password))

    # Try to disable — must 403 with the enforced-mode reason.
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
