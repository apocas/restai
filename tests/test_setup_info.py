"""Tests for /setup (public) and /info (authenticated) response shapes.

In particular: the admin-only `auth_secret_weak` security flag must
NOT leak via the public /setup endpoint — that would let an
unauthenticated attacker probe for weak-secret misconfigurations.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup_is_public_and_omits_security_flags(client):
    r = client.get("/setup")
    assert r.status_code == 200
    body = r.json()
    # Must NOT carry the admin-only weak-secret signal.
    assert "auth_secret_weak" not in body, (
        "auth_secret_weak leaked via unauthenticated /setup"
    )
    # Sanity: the pre-login UI knobs are still here.
    for k in ("app_name", "sso", "sso_provider_names", "mcp"):
        assert k in body, f"expected {k} in /setup response"


def test_info_requires_auth(client):
    r = client.get("/info")
    assert r.status_code == 401


def test_info_exposes_auth_secret_weak_to_admin(client):
    r = client.get("/info", auth=ADMIN)
    assert r.status_code == 200
    body = r.json()
    # Field is always present for authenticated callers; value is
    # environment-dependent.
    assert "auth_secret_weak" in body
    assert isinstance(body["auth_secret_weak"], bool)


def test_info_hides_auth_secret_weak_from_non_admin(client):
    """Non-admin users get False regardless of actual state — the
    signal is reconnaissance-relevant even for low-trust users."""
    import random
    username = f"info_viewer_{random.randint(0, 999999)}"
    client.post("/users", json={"username": username, "password": "x"}, auth=ADMIN)
    try:
        r = client.get("/info", auth=(username, "x"))
        assert r.status_code == 200
        body = r.json()
        assert body.get("auth_secret_weak") is False
    finally:
        client.delete(f"/users/{username}", auth=ADMIN)
