from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from restai.audit import _log_to_db as _audit_log
from restai.auth import get_current_username_admin
from restai.config import detect_gpu_info
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import SettingsResponse, SettingsUpdate
from restai.settings import get_all_settings, mask_key, update_setting, reinit_oauth, _SECRET_KEYS
from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS

router = APIRouter()


@router.get("/settings/gpu-info")
async def get_gpu_info(
    user=Depends(get_current_username_admin),
) -> List[dict]:
    """Get detected GPU hardware information (admin only)."""
    return detect_gpu_info()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    user=Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get current platform settings (admin only)."""
    return get_all_settings(db_wrapper)


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(
    body: SettingsUpdate,
    request: Request,
    user=Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update platform settings (admin only)."""
    if body.max_audio_upload_size is not None and body.max_audio_upload_size < 1:
        raise HTTPException(status_code=400, detail="max_audio_upload_size must be >= 1")

    updates = body.model_dump(exclude_none=True)

    actor = getattr(user, "username", None) or "(admin)"

    def _audit_change(key: str, new_str: str) -> None:
        """Emit a per-key audit row. Resource carries the key + a status
        marker; values are NEVER included for SETTINGS_ENCRYPTED_KEYS so
        an attacker who reads the audit log can't recover secrets. For
        non-secret keys we include a short fingerprint (length + first
        chars) so an admin can confirm "yes that was the change I made"
        without leaking the full value either."""
        try:
            old = db_wrapper.get_setting_value(key, "")
        except Exception:
            old = ""
        if (old or "") == (new_str or ""):
            # No actual change — don't pollute the audit log.
            return
        if key in SETTINGS_ENCRYPTED_KEYS or key in _SECRET_KEYS:
            resource = f"settings/{key}:secret_changed"
        else:
            # Cap length for the column; small fingerprint for sanity.
            preview = (new_str or "")[:32].replace("\n", " ")
            resource = f"settings/{key}:{preview}"
        _audit_log(actor, "SETTING", resource[:500], 200)

    # Handle proxy_enabled=False: clear proxy fields
    if updates.get("proxy_enabled") is False:
        for key, value in (("proxy_enabled", "false"), ("proxy_url", ""), ("proxy_key", ""), ("proxy_team_id", "")):
            _audit_change(key, value)
            update_setting(db_wrapper, key, value)
        updates.pop("proxy_enabled", None)
        updates.pop("proxy_url", None)
        updates.pop("proxy_key", None)
        updates.pop("proxy_team_id", None)

    for key, value in updates.items():
        # Skip secret fields if masked or empty
        if key in _SECRET_KEYS:
            if not value or value.startswith("****"):
                continue

        if isinstance(value, bool):
            new_str = "true" if value else "false"
        elif isinstance(value, int):
            new_str = str(value)
        else:
            new_str = value
        _audit_change(key, new_str)
        update_setting(db_wrapper, key, new_str)

    redis_fields = {"redis_host", "redis_port", "redis_password", "redis_database"}
    if redis_fields & updates.keys():
        request.app.state.brain.reinit_chat_store()

    sso_fields = {k for k in updates.keys() if k.startswith("sso_") or k == "auth_disable_local"}
    if sso_fields:
        reinit_oauth(request.app)

    docker_fields = {"docker_enabled", "docker_url", "docker_image", "docker_timeout", "docker_network", "docker_read_only"}
    if docker_fields & updates.keys():
        request.app.state.brain.init_docker_manager()

    browser_fields = {"browser_enabled", "browser_image", "browser_network", "browser_timeout"}
    if browser_fields & updates.keys():
        request.app.state.brain.init_browser_manager()

    return get_all_settings(db_wrapper)


@router.post("/settings/docker/test", tags=["Settings"])
async def test_docker_connection(
    request: Request,
    _=Depends(get_current_username_admin),
):
    """Test the Docker connection using the current settings."""
    brain = request.app.state.brain
    if brain.docker_manager is None:
        docker_url = getattr(config, "DOCKER_URL", "") or ""
        if not docker_url.strip():
            raise HTTPException(status_code=400, detail="Docker URL is not configured")
        # Try to connect
        try:
            import docker as docker_sdk
            client = docker_sdk.DockerClient(base_url=docker_url)
            info = client.info()
            return {"status": "ok", "server_version": info.get("ServerVersion", "unknown")}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Connection failed: {e}")
    else:
        try:
            info = brain.docker_manager._client.info()
            return {"status": "ok", "server_version": info.get("ServerVersion", "unknown")}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Connection failed: {e}")


@router.get("/audit", tags=["Settings"])
async def get_audit_log(
    start: int = 0,
    end: int = 50,
    username: str = None,
    action: str = None,
    _=Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get paginated audit log entries (admin only)."""
    from restai.models.databasemodels import AuditLogDatabase

    query = db_wrapper.db.query(AuditLogDatabase)

    if username:
        query = query.filter(AuditLogDatabase.username == username)
    if action:
        query = query.filter(AuditLogDatabase.action == action)

    total = query.count()
    entries = query.order_by(AuditLogDatabase.date.desc()).offset(start).limit(end - start).all()

    return {
        "entries": [
            {
                "id": e.id,
                "username": e.username,
                "action": e.action,
                "resource": e.resource,
                "status_code": e.status_code,
                "date": e.date.isoformat() if e.date else None,
            }
            for e in entries
        ],
        "total": total,
    }


@router.delete("/cron-logs", tags=["Settings"])
async def purge_cron_logs(
    _=Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete all cron log entries (admin only)."""
    from restai.models.databasemodels import CronLogDatabase

    count = db_wrapper.db.query(CronLogDatabase).delete()
    db_wrapper.db.commit()
    return {"deleted": count}


@router.post("/cron-logs/run", tags=["Settings"])
async def run_crons(
    background_tasks: BackgroundTasks,
    _=Depends(get_current_username_admin),
):
    """Trigger all cron jobs now (admin only). Runs as a subprocess."""
    import subprocess, sys, os

    def _run():
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            subprocess.run(
                [sys.executable, "crons/runner.py"],
                cwd=project_root,
                timeout=300,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Manual cron run failed")

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/cron-logs", tags=["Settings"])
async def get_cron_logs(
    start: int = 0,
    end: int = 50,
    job: str = None,
    status: str = None,
    _=Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get paginated cron log entries (admin only)."""
    from restai.models.databasemodels import CronLogDatabase

    query = db_wrapper.db.query(CronLogDatabase)
    if job:
        query = query.filter(CronLogDatabase.job == job)
    if status:
        query = query.filter(CronLogDatabase.status == status)

    total = query.count()
    entries = query.order_by(CronLogDatabase.date.desc()).offset(start).limit(end - start).all()

    return {
        "entries": [
            {
                "id": e.id,
                "job": e.job,
                "status": e.status,
                "message": e.message,
                "details": e.details,
                "items_processed": e.items_processed,
                "duration_ms": e.duration_ms,
                "date": e.date.isoformat() if e.date else None,
            }
            for e in entries
        ],
        "total": total,
    }
