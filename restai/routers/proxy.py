import logging
from fastapi import (
    APIRouter,
    Depends,
)
import requests
from restai import config
from restai.auth import (
    get_current_username_admin,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import (
    KeyCreate,
    User,
)

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()


@router.post("/proxy/keys")
async def route_create_key(
    key_create: KeyCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + "/key/generate"
    headers = {
        "Authorization": "Bearer " + config.PROXY_KEY,
        "Content-Type": "application/json",
    }
    data = {"models": key_create.models, "key_alias": key_create.name, "max_budget": key_create.max_budget, "budget_duration": key_create.duration_budget, "tpm_limit": key_create.tpm, "rpm_limit": key_create.rpm}
    
    if config.PROXY_TEAM_ID:
        data["team_id"] = config.PROXY_TEAM_ID

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        data = response.json()
        return {"key": data["key"], "models": data["models"]}
    else:
        return {"error": "Failed to generate new key"}


@router.get("/proxy/keys")
async def route_get_keys(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + "/user/info"
    headers = {
        "Authorization": "Bearer " + config.PROXY_KEY,
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["keys"]:
            if config.PROXY_TEAM_ID and key["team_id"] != config.PROXY_TEAM_ID:
                continue
            output.append(
                {"key": key["key_name"], "models": key["models"], "id": key["token"], "spend": key["spend"], "max_budget": key["max_budget"], "duration_budget": key["budget_duration"], "tpm": key["tpm_limit"], "rpm": key["rpm_limit"], "name": key["key_alias"]}
            )
        return {"keys": output}
    else:
        return {"error": "Failed to list keys"}


@router.delete("/proxy/keys/{key_id}")
async def route_delete_key(
    key_id: str,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + "/key/delete"
    headers = {
        "Authorization": "Bearer " + config.PROXY_KEY,
        "Content-Type": "application/json",
    }
    data = {"keys": [key_id]}

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        return {"message": "Key deleted"}
    else:
        return {"error": "Failed to delete key"}


@router.get("/proxy/info")
async def route_proxy_info(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + "/models"
    headers = {
        "Authorization": "Bearer " + config.PROXY_KEY,
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["data"]:
            output.append(key["id"])
        return {"models": output, "url": config.PROXY_URL}
    else:
        return {"error": "Failed to list keys"}
