from fastapi import APIRouter, Depends, HTTPException, Request

from restai.auth import get_current_username_admin
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import SettingsResponse, SettingsUpdate
from restai.settings import get_all_settings, mask_key, update_setting

router = APIRouter()


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
    if body.agent_max_iterations is not None and body.agent_max_iterations < 1:
        raise HTTPException(status_code=400, detail="agent_max_iterations must be >= 1")
    if body.max_audio_upload_size is not None and body.max_audio_upload_size < 1:
        raise HTTPException(status_code=400, detail="max_audio_upload_size must be >= 1")

    updates = body.model_dump(exclude_none=True)

    # Handle proxy_enabled=False: clear proxy fields
    if updates.get("proxy_enabled") is False:
        update_setting(db_wrapper, "proxy_enabled", "false")
        update_setting(db_wrapper, "proxy_url", "")
        update_setting(db_wrapper, "proxy_key", "")
        update_setting(db_wrapper, "proxy_team_id", "")
        updates.pop("proxy_enabled", None)
        updates.pop("proxy_url", None)
        updates.pop("proxy_key", None)
        updates.pop("proxy_team_id", None)

    for key, value in updates.items():
        # Skip proxy_key if it's masked or empty
        if key == "proxy_key":
            if not value or value.startswith("****"):
                continue

        # Skip redis_password if it's masked or empty
        if key == "redis_password":
            if not value or value.startswith("****"):
                continue

        if isinstance(value, bool):
            update_setting(db_wrapper, key, "true" if value else "false")
        elif isinstance(value, int):
            update_setting(db_wrapper, key, str(value))
        else:
            update_setting(db_wrapper, key, value)

    redis_fields = {"redis_host", "redis_port", "redis_password", "redis_database"}
    if redis_fields & updates.keys():
        request.app.state.brain.reinit_chat_store()

    return get_all_settings(db_wrapper)
