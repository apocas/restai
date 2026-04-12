import logging

import requests
from fastapi import APIRouter, Depends, HTTPException, Path

from restai.auth import get_current_username_admin
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import KeyCreate, User

logging.basicConfig(level=logging.INFO)

router = APIRouter()


def _proxy_settings(db_wrapper: DBWrapper):
    """Read proxy settings fresh from DB for multi-worker safety."""
    url = db_wrapper.get_setting_value("proxy_url", "")
    key = db_wrapper.get_setting_value("proxy_key", "")
    team_id = db_wrapper.get_setting_value("proxy_team_id", "")
    if not url:
        raise HTTPException(status_code=400, detail="Proxy URL is not configured")
    return url.rstrip("/"), key, team_id


@router.post("/proxy/keys")
async def route_create_key(
    key_create: KeyCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new LiteLLM proxy API key (admin only)."""
    proxy_url, proxy_key, proxy_team_id = _proxy_settings(db_wrapper)
    url = proxy_url + "/key/generate"
    headers = {
        "Authorization": "Bearer " + proxy_key,
        "Content-Type": "application/json",
    }
    data = {"models": key_create.models, "key_alias": key_create.name, "max_budget": key_create.max_budget, "budget_duration": key_create.duration_budget, "tpm_limit": key_create.tpm, "rpm_limit": key_create.rpm}

    if proxy_team_id:
        data["team_id"] = proxy_team_id

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        data = response.json()
        return {"key": data["key"], "models": data["models"]}
    else:
        raise HTTPException(status_code=502, detail="Failed to generate proxy key")


@router.get("/proxy/keys")
async def route_get_keys(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all LiteLLM proxy API keys (admin only)."""
    proxy_url, proxy_key, proxy_team_id = _proxy_settings(db_wrapper)
    url = proxy_url + "/user/info"
    headers = {
        "Authorization": "Bearer " + proxy_key,
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["keys"]:
            if proxy_team_id and key["team_id"] != proxy_team_id:
                continue
            output.append(
                {"key": key["key_name"], "models": key["models"], "id": key["token"], "spend": key["spend"], "max_budget": key["max_budget"], "duration_budget": key["budget_duration"], "tpm": key["tpm_limit"], "rpm": key["rpm_limit"], "name": key["key_alias"]}
            )
        return {"keys": output}
    else:
        raise HTTPException(status_code=502, detail="Failed to list proxy keys")


@router.delete("/proxy/keys/{key_id}")
async def route_delete_key(
    key_id: str = Path(description="Proxy key ID"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a LiteLLM proxy API key (admin only)."""
    proxy_url, proxy_key, proxy_team_id = _proxy_settings(db_wrapper)
    url = proxy_url + "/key/delete"
    headers = {
        "Authorization": "Bearer " + proxy_key,
        "Content-Type": "application/json",
    }
    data = {"keys": [key_id]}

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return {"message": "Key deleted"}
    else:
        raise HTTPException(status_code=502, detail="Failed to delete proxy key")


@router.get("/proxy/info")
async def route_proxy_info(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get LiteLLM proxy info and available models (admin only)."""
    proxy_url, proxy_key, proxy_team_id = _proxy_settings(db_wrapper)
    url = proxy_url + "/models"
    headers = {
        "Authorization": "Bearer " + proxy_key,
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["data"]:
            output.append(key["id"])
        return {"models": output, "url": proxy_url}
    else:
        raise HTTPException(status_code=502, detail="Failed to list proxy models")
