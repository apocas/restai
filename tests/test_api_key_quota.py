"""Per-API-key monthly token quota tests.

Covers:
* PATCH /users/{u}/apikeys/{id} updates token_quota_monthly + reset_usage
* check_api_key_quota raises 429 when tokens_used_this_month >= quota
* check_api_key_quota rolls the counter over when quota_reset_at lapses
* record_api_key_tokens increments the counter

The actual inference path (helper.py) is exercised in other tests; here
we unit-test the two budget.py helpers directly and the PATCH endpoint
end-to-end.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from restai.budget import (
    _first_of_next_month,
    check_api_key_quota,
    record_api_key_tokens,
)
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import get_db_wrapper
from restai.main import app
from restai.models.databasemodels import ApiKeyDatabase


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api_key(client):
    """Create a fresh API key for the admin user, yield the DB row id,
    clean up after."""
    suffix = str(random.randint(0, 1_000_000))
    r = client.post(
        "/users/admin/apikeys",
        json={"description": f"quota_test_{suffix}"},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    key_id = r.json()["id"]
    yield key_id
    client.delete(f"/users/admin/apikeys/{key_id}", auth=ADMIN)


# ─── unit tests ─────────────────────────────────────────────────────────

def test_check_api_key_quota_noop_without_api_key_id():
    """Basic / cookie auth has no api_key_id — must be a no-op."""
    user = SimpleNamespace(api_key_id=None)
    db = SimpleNamespace(db=SimpleNamespace())  # not touched
    # Would AttributeError if the function dereferenced db.
    check_api_key_quota(user, db)


def test_check_api_key_quota_noop_when_unlimited(api_key):
    """token_quota_monthly=NULL is unlimited — skip the cap check."""
    db = get_db_wrapper()
    try:
        key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key).first()
        assert key.token_quota_monthly is None
        key.tokens_used_this_month = 999_999_999
        db.db.commit()
        user = SimpleNamespace(api_key_id=api_key)
        check_api_key_quota(user, db)  # must NOT raise
    finally:
        db.db.close()


def test_check_api_key_quota_raises_when_exceeded(api_key):
    db = get_db_wrapper()
    try:
        key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key).first()
        key.token_quota_monthly = 1000
        key.tokens_used_this_month = 1000
        # Future reset date so the rollover branch doesn't fire.
        key.quota_reset_at = datetime.now(timezone.utc) + timedelta(days=7)
        db.db.commit()
        user = SimpleNamespace(api_key_id=api_key)
        with pytest.raises(HTTPException) as ei:
            check_api_key_quota(user, db)
        assert ei.value.status_code == 429
        assert "quota reached" in str(ei.value.detail).lower()
    finally:
        db.db.close()


def test_check_api_key_quota_rolls_over_on_lapsed_reset(api_key):
    """quota_reset_at in the past → counter zeros, new reset date set,
    NO 429."""
    db = get_db_wrapper()
    try:
        key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key).first()
        key.token_quota_monthly = 10
        key.tokens_used_this_month = 999
        key.quota_reset_at = datetime(2024, 1, 1, tzinfo=timezone.utc)  # past
        db.db.commit()

        user = SimpleNamespace(api_key_id=api_key)
        check_api_key_quota(user, db)  # must NOT raise

        db.db.refresh(key)
        assert key.tokens_used_this_month == 0
        # SQLite strips tzinfo on storage; normalize before comparing.
        reset = key.quota_reset_at
        if reset.tzinfo is None:
            reset = reset.replace(tzinfo=timezone.utc)
        assert reset > datetime.now(timezone.utc)
    finally:
        db.db.close()


def test_record_api_key_tokens_bumps_counter(api_key):
    db = get_db_wrapper()
    try:
        key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key).first()
        key.tokens_used_this_month = 100
        db.db.commit()
        record_api_key_tokens(api_key, 50, db)
        db.db.refresh(key)
        assert key.tokens_used_this_month == 150
    finally:
        db.db.close()


def test_record_api_key_tokens_silent_on_unknown_id():
    db = get_db_wrapper()
    try:
        # Shouldn't raise — key may have been deleted between auth and log.
        record_api_key_tokens(999_999_999, 10, db)
    finally:
        db.db.close()


def test_first_of_next_month_rolls_december():
    dec = datetime(2025, 12, 15, tzinfo=timezone.utc)
    out = _first_of_next_month(dec)
    assert out == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_first_of_next_month_rolls_mid_year():
    mar = datetime(2026, 3, 9, 14, 30, tzinfo=timezone.utc)
    out = _first_of_next_month(mar)
    assert out == datetime(2026, 4, 1, tzinfo=timezone.utc)


# ─── PATCH endpoint ─────────────────────────────────────────────────────

def test_patch_sets_quota(client, api_key):
    r = client.patch(
        f"/users/admin/apikeys/{api_key}",
        json={"token_quota_monthly": 5000, "description": "monthly-capped"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_quota_monthly"] == 5000
    assert body["description"] == "monthly-capped"


def test_patch_clears_quota_with_zero(client, api_key):
    # First set a cap.
    client.patch(f"/users/admin/apikeys/{api_key}", json={"token_quota_monthly": 100}, auth=ADMIN)
    # Then clear with 0.
    r = client.patch(
        f"/users/admin/apikeys/{api_key}",
        json={"token_quota_monthly": 0},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["token_quota_monthly"] is None


def test_patch_reset_usage(client, api_key):
    # Stamp some usage directly.
    db = get_db_wrapper()
    try:
        key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key).first()
        key.tokens_used_this_month = 12345
        db.db.commit()
    finally:
        db.db.close()

    r = client.patch(
        f"/users/admin/apikeys/{api_key}",
        json={"reset_usage": True},
        auth=ADMIN,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tokens_used_this_month"] == 0
    assert body["quota_reset_at"] is not None
