"""Password-age warning tests.

Covers the soft "your password is N days old" notice in the login
response. The feature is opt-in (`password_max_age_days` setting,
default 0 = disabled) and never blocks authentication — verifying the
mechanism here is enough; we don't have to exercise actual aging since
we can write a backdated `password_updated_at` directly.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import get_db_wrapper
from restai.main import app
from restai.models.databasemodels import UserDatabase

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def stale_user(client):
    """Create a user whose password is older than any reasonable
    threshold. Returns (username, password)."""
    suffix = str(random.randint(0, 1_000_000))
    username = f"pwage_user_{suffix}"
    password = "first_pwd_123"

    r = client.post("/users", json={"username": username, "password": password}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text

    # Backdate password_updated_at to something definitely-stale.
    db = get_db_wrapper()
    try:
        u = db.db.query(UserDatabase).filter(UserDatabase.username == username).first()
        assert u is not None
        u.password_updated_at = datetime.now(timezone.utc) - timedelta(days=400)
        db.db.commit()
    finally:
        db.db.close()
    yield username, password
    client.delete(f"/users/{username}", auth=ADMIN)


def _set_max_age(client, days: int):
    # TestClient keeps cookies across requests; a previous /auth/login
    # from a non-admin test user would shadow the Basic-auth header.
    client.cookies.clear()
    r = client.patch("/settings", json={"password_max_age_days": days}, auth=ADMIN)
    assert r.status_code == 200, f"PATCH /settings failed: {r.status_code} {r.text}"


def _reset_login_rate_limit():
    """The test client uses one IP — without this, ~5 logins blow the
    `_LOGIN_MAX_ATTEMPTS=10` cap and subsequent tests in the module 429."""
    from restai.models.databasemodels import LoginAttemptDatabase
    db = get_db_wrapper()
    try:
        db.db.query(LoginAttemptDatabase).delete()
        db.db.commit()
    finally:
        db.db.close()


def test_login_no_warning_when_disabled(client, stale_user):
    """Default (0) means no warning even for ancient passwords."""
    username, password = stale_user
    _set_max_age(client, 0)
    _reset_login_rate_limit()
    client.cookies.clear()
    r = client.post("/auth/login", auth=(username, password))
    assert r.status_code == 200
    body = r.json()
    assert "password_warning" not in body, body


def test_login_warning_when_password_stale(client, stale_user):
    """With max_age=30 days and a 400-day-old password, the response
    must include a password_warning block."""
    username, password = stale_user
    _set_max_age(client, 30)
    try:
        _reset_login_rate_limit()
        r = client.post("/auth/login", auth=(username, password))
        assert r.status_code == 200
        body = r.json()
        assert "password_warning" in body, body
        warn = body["password_warning"]
        assert warn["password_max_age_days"] == 30
        assert warn["password_age_days"] >= 30
        assert "change it" in warn["message"].lower()
    finally:
        _set_max_age(client, 0)


def test_login_no_warning_when_password_fresh(client):
    """Admin's password is freshly created (or recently rotated). Setting
    a tight max_age must NOT warn unless we know the password is older."""
    _set_max_age(client, 1)
    try:
        # admin user has password_updated_at=NULL after the migration
        # (legacy row pre-tracking). NULL means "unknown — don't warn",
        # which is the right default.
        _reset_login_rate_limit()
        r = client.post("/auth/login", auth=ADMIN)
        assert r.status_code == 200
        body = r.json()
        assert "password_warning" not in body, body
    finally:
        _set_max_age(client, 0)


def test_password_change_resets_timestamp(client, stale_user):
    """After update_user with a new password, password_updated_at must
    be 'now' again, so the warning goes away on next login."""
    username, password = stale_user
    new_password = "second_pwd_456"
    r = client.patch(f"/users/{username}", json={"password": new_password}, auth=ADMIN)
    assert r.status_code in (200, 201)

    db = get_db_wrapper()
    try:
        u = db.db.query(UserDatabase).filter(UserDatabase.username == username).first()
        assert u.password_updated_at is not None
        # Should be within the last few seconds.
        last = u.password_updated_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        assert delta.total_seconds() < 30, f"timestamp not recent: {delta}"
    finally:
        db.db.close()

    # The new password works; the old one shouldn't (sanity check).
    _reset_login_rate_limit()
    client.cookies.clear()
    r = client.post("/auth/login", auth=(username, new_password))
    assert r.status_code == 200
    _reset_login_rate_limit()
    client.cookies.clear()
    r = client.post("/auth/login", auth=(username, password))
    assert r.status_code == 401
