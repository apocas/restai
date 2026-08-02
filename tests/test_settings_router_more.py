"""Settings router edge tests for restai/routers/settings.py.

Complements tests/test_settings.py with: secret masking + preserve-on-mask
round-trip, per-key audit rows (fingerprint vs secret_changed), the docker
test endpoint with the client mocked, gpu-info, cron-log listing/purge with
seeded rows, the manual cron trigger with subprocess mocked, and the admin
routine inventory/toggle endpoints.
"""
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
plain_user = f"setx_user_{suffix}"
plain_pass = "setx_pass_123"
secret_value = f"setx_secret_{suffix}9"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    r = client.post(
        "/users",
        json={"username": plain_user, "password": plain_pass, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    # Remember RAW stored values (get_setting_value decrypts secrets on
    # read) so cleanup can restore them verbatim.
    from restai.models.databasemodels import SettingDatabase

    db = open_db_wrapper()
    try:
        for key, target in (("smtp_password", "smtp_original"), ("app_name", "app_name_original")):
            row = db.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
            state[target] = row.value if row and row.value else ""
    finally:
        db.db.close()


# ------------------------------------------------------------------ gpu info


def test_gpu_info_admin(client):
    r = client.get("/settings/gpu-info", auth=ADMIN)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_gpu_info_non_admin(client):
    r = client.get("/settings/gpu-info", auth=(plain_user, plain_pass))
    assert r.status_code in (401, 403)


# ------------------------------------------------------------------ secrets


def test_secret_masked_on_read(client):
    r = client.patch("/settings", json={"smtp_password": secret_value}, auth=ADMIN)
    assert r.status_code == 200, r.text
    masked = r.json()["smtp_password"]
    assert masked.startswith("****")
    assert masked == "****" + secret_value[-4:]
    assert secret_value not in r.text
    state["masked"] = masked


def test_secret_masked_value_not_written_back(client):
    # Re-submitting the masked value (what the settings form sends when the
    # admin didn't touch the field) must NOT overwrite the stored secret.
    r = client.patch("/settings", json={"smtp_password": state["masked"]}, auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["smtp_password"] == state["masked"]

    # get_setting_value decrypts on read — the stored secret is unchanged.
    db = open_db_wrapper()
    try:
        stored = db.get_setting_value("smtp_password", "")
    finally:
        db.db.close()
    assert stored == secret_value


def test_secret_encrypted_at_rest(client):
    # Raw row (bypassing the decrypt-on-read getter) must be ciphertext.
    from restai.models.databasemodels import SettingDatabase

    db = open_db_wrapper()
    try:
        row = db.db.query(SettingDatabase).filter(SettingDatabase.key == "smtp_password").first()
        raw = row.value if row else ""
    finally:
        db.db.close()
    assert raw.startswith("$ENC$")
    assert secret_value not in raw


# ------------------------------------------------------------------ audit rows


def test_audit_row_for_secret_key(client):
    r = client.get("/audit", params={"action": "SETTING"}, auth=ADMIN)
    assert r.status_code == 200
    resources = [e["resource"] for e in r.json()["entries"]]
    assert any(res == "settings/smtp_password:secret_changed" for res in resources)
    # The secret value itself must never land in the audit log.
    assert all(secret_value not in (res or "") for res in resources)


def test_audit_row_for_plain_key_has_fingerprint(client):
    new_name = f"RESTai-{suffix}"
    r = client.patch("/settings", json={"app_name": new_name}, auth=ADMIN)
    assert r.status_code == 200

    r = client.get("/audit", params={"action": "SETTING"}, auth=ADMIN)
    resources = [e["resource"] for e in r.json()["entries"]]
    assert any(res == f"settings/app_name:{new_name[:32]}" for res in resources)

    # Unchanged value -> no new audit row.
    before = sum(1 for res in resources if res.startswith("settings/app_name:"))
    r = client.patch("/settings", json={"app_name": new_name}, auth=ADMIN)
    assert r.status_code == 200
    r = client.get("/audit", params={"action": "SETTING"}, auth=ADMIN)
    after = sum(
        1 for e in r.json()["entries"]
        if (e["resource"] or "").startswith("settings/app_name:")
    )
    assert after == before


def test_audit_filters(client):
    r = client.get("/audit", params={"username": "no_such_user_xyz"}, auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["entries"] == []
    assert r.json()["total"] == 0


# ------------------------------------------------------------------ docker test endpoint


def test_docker_test_not_configured(client, monkeypatch):
    import restai.docker as docker_mod

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: False)
    r = client.post("/settings/docker/test", auth=ADMIN)
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


def test_docker_test_ok_mocked(client, monkeypatch):
    import restai.docker as docker_mod

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(docker_mod, "client_info", lambda: {"ServerVersion": "99.9-test"})
    r = client.post("/settings/docker/test", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "server_version": "99.9-test"}


def test_docker_test_connection_failure_mocked(client, monkeypatch):
    import restai.docker as docker_mod

    def boom():
        raise RuntimeError("daemon unreachable")

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(docker_mod, "client_info", boom)
    r = client.post("/settings/docker/test", auth=ADMIN)
    assert r.status_code == 502
    assert "daemon unreachable" in r.json()["detail"]


def test_docker_settings_patch_flushes_client(client):
    import restai.docker as docker_mod

    docker_mod._client_url = "tcp://stale:1234"
    r = client.patch("/settings", json={"docker_network": "none"}, auth=ADMIN)
    assert r.status_code == 200
    assert docker_mod._client is None
    assert docker_mod._client_url == ""


# ------------------------------------------------------------------ cron logs


def test_cron_logs_seeded_and_filtered(client):
    from datetime import datetime, timezone
    from restai.models.databasemodels import CronLogDatabase

    job_name = f"setx_job_{suffix}"
    db = open_db_wrapper()
    try:
        db.db.add(CronLogDatabase(
            job=job_name, status="success", message="all good",
            items_processed=3, duration_ms=12, date=datetime.now(timezone.utc),
        ))
        db.db.add(CronLogDatabase(
            job=job_name, status="error", message="boom",
            details="Traceback...", items_processed=0, duration_ms=5,
            date=datetime.now(timezone.utc),
        ))
        db.db.commit()
    finally:
        db.db.close()

    r = client.get("/cron-logs", params={"job": job_name}, auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["total"] == 2

    r = client.get("/cron-logs", params={"job": job_name, "status": "error"}, auth=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["entries"][0]["message"] == "boom"
    assert body["entries"][0]["details"] == "Traceback..."


def test_cron_logs_purge(client):
    r = client.delete("/cron-logs", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 2  # at least the two rows seeded above

    r = client.get("/cron-logs", auth=ADMIN)
    assert r.json()["total"] == 0


def test_cron_run_now_mocked_subprocess(client, monkeypatch):
    import subprocess

    calls = []

    def fake_run(cmd, cwd=None, timeout=None, **kwargs):
        calls.append((cmd, cwd, timeout))

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = client.post("/cron-logs/run", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"status": "started"}
    # TestClient runs background tasks before returning the response.
    assert len(calls) == 1
    assert calls[0][0][-1] == "crons/runner.py"


def test_cron_logs_non_admin(client):
    assert client.get("/cron-logs", auth=(plain_user, plain_pass)).status_code in (401, 403)
    assert client.delete("/cron-logs", auth=(plain_user, plain_pass)).status_code in (401, 403)


# ------------------------------------------------------------------ admin routines


def test_admin_routines_inventory_and_toggle(client):
    r = client.post(
        "/llms",
        json={
            "name": f"setx_llm_{suffix}",
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201
    llm_id = r.json()["id"]
    r = client.post("/teams", json={"name": f"setx_team_{suffix}", "llms": [f"setx_llm_{suffix}"]}, auth=ADMIN)
    assert r.status_code == 201
    team_id = r.json()["id"]
    r = client.post(
        "/projects",
        json={"name": f"setx_proj_{suffix}", "llm": f"setx_llm_{suffix}", "type": "agent", "team_id": team_id},
        auth=ADMIN,
    )
    assert r.status_code == 201
    proj_id = r.json()["project"]

    r = client.post(
        f"/projects/{proj_id}/routines",
        json={"name": f"setx_rtn_{suffix}", "message": "ping", "schedule_minutes": 60, "enabled": True},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    routine_id = r.json()["id"]

    r = client.get("/admin/routines", auth=ADMIN)
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()["routines"]}
    assert routine_id in rows
    row = rows[routine_id]
    assert row["project_id"] == proj_id
    assert row["project_name"] == f"setx_proj_{suffix}"
    assert row["enabled"] is True

    r = client.patch(f"/admin/routines/{routine_id}", json={"enabled": False}, auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"id": routine_id, "enabled": False}

    # Toggle lands in the audit log.
    r = client.get("/audit", params={"action": "ROUTINE"}, auth=ADMIN)
    resources = [e["resource"] for e in r.json()["entries"]]
    assert any(res == f"admin/routines/{routine_id}:enabled=False" for res in resources)

    r = client.patch("/admin/routines/99999999", json={"enabled": True}, auth=ADMIN)
    assert r.status_code == 404

    client.delete(f"/projects/{proj_id}", auth=ADMIN)
    client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/llms/{llm_id}", auth=ADMIN)


def test_admin_routines_non_admin(client):
    r = client.get("/admin/routines", auth=(plain_user, plain_pass))
    assert r.status_code in (401, 403)


# ------------------------------------------------------------------ cleanup


def test_cleanup(client):
    # Restore the raw stored values directly (upsert_setting would
    # re-encrypt the already-encrypted smtp_password ciphertext).
    from restai.models.databasemodels import SettingDatabase

    db = open_db_wrapper()
    try:
        for key, value in (
            ("smtp_password", state.get("smtp_original", "")),
            ("app_name", state.get("app_name_original", "RESTai")),
        ):
            row = db.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
            if row is not None:
                row.value = value
        db.db.commit()
    finally:
        db.db.close()
    client.delete(f"/users/{plain_user}", auth=ADMIN)
