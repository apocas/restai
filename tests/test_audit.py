import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
llm_name = f"audit_llm_{suffix}"
team_name = f"audit_team_{suffix}"
project_name = f"audit_proj_{suffix}"
test_username = f"audit_user_{suffix}"
test_password = "audit_pass_123"

team_id = None
project_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_audit_log_populated(client):
    """Perform mutations, then verify audit log has entries."""
    global team_id, project_id
    client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )

    resp = client.post(
        "/teams",
        json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
        auth=ADMIN,
    )
    assert resp.status_code == 201
    team_id = resp.json()["id"]

    resp = client.post(
        "/projects",
        json={"name": project_name, "type": "block", "team_id": team_id},
        auth=ADMIN,
    )
    assert resp.status_code == 201
    project_id = resp.json()["project"]

    resp = client.get("/audit", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data
    assert data["total"] > 0
    assert len(data["entries"]) > 0

    entry = data["entries"][0]
    assert "id" in entry
    assert "username" in entry
    assert "action" in entry
    assert "date" in entry


def test_audit_log_admin_only(client):
    """Non-admin users cannot access the audit log."""
    client.post(
        "/users",
        json={
            "username": test_username,
            "password": test_password,
            "admin": False,
            "private": False,
        },
        auth=ADMIN,
    )

    resp = client.get("/audit", auth=(test_username, test_password))
    assert resp.status_code == 403


def test_audit_pagination(client):
    """Audit log supports pagination via start/end parameters."""
    resp = client.get("/audit?start=0&end=5", auth=ADMIN)
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert "total" in data
    assert len(data["entries"]) <= 5


def test_settings_change_writes_per_key_audit_row(client):
    """PATCH /settings emits one SETTING audit row per changed key; secret keys log ':secret_changed' (no value)."""
    import time

    current = client.get("/settings", auth=ADMIN).json()
    original_currency = current.get("currency", "EUR")
    new_currency = "USD" if original_currency != "USD" else "EUR"

    try:
        r = client.patch("/settings", json={"currency": new_currency}, auth=ADMIN)
        assert r.status_code == 200

        # Audit logging happens in a daemon thread — give it a beat.
        time.sleep(0.5)

        log = client.get("/audit?start=0&end=200&action=SETTING", auth=ADMIN).json()
        entries = log.get("entries", [])
        currency_rows = [e for e in entries if "settings/currency" in (e.get("resource") or "")]
        assert currency_rows, f"expected SETTING audit row for currency change, got: {[e.get('resource') for e in entries[:10]]}"
        # Non-secret keys include a fingerprint of the new value.
        assert new_currency in currency_rows[0]["resource"]

        # Secret key path: ':secret_changed' marker, never the value itself.
        r = client.patch("/settings", json={"sso_google_client_secret": "test-not-real-secret-xyz"}, auth=ADMIN)
        assert r.status_code == 200
        time.sleep(0.5)
        log2 = client.get("/audit?start=0&end=200&action=SETTING", auth=ADMIN).json()
        secret_rows = [e for e in log2.get("entries", []) if "sso_google_client_secret" in (e.get("resource") or "")]
        assert secret_rows, "expected SETTING audit row for secret change"
        assert ":secret_changed" in secret_rows[0]["resource"]
        assert "test-not-real-secret-xyz" not in secret_rows[0]["resource"], (
            "secret value leaked into audit resource"
        )
    finally:
        client.patch("/settings", json={"currency": original_currency}, auth=ADMIN)
        client.patch("/settings", json={"sso_google_client_secret": ""}, auth=ADMIN)


def test_cleanup(client):
    """Remove all test resources."""
    if project_id:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
    if team_id:
        client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
    client.delete(f"/users/{test_username}", auth=ADMIN)
