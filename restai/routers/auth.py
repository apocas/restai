from datetime import timedelta
import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from restai import config
from restai.auth import create_access_token, get_current_username
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User
from restai.routers.users import sanitize_user


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()


@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    jwt_token = create_access_token(
        data={"username": user.username}, expires_delta=timedelta(minutes=1440)
    )

    response.set_cookie(
        key="restai_token",
        value=jwt_token,
        samesite="strict",
        expires=86400,
        httponly=True,
    )

    return {"message": "Logged in successfully."}



@router.get("/auth/whoami")
async def get_whoami(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    user_model = User.model_validate(db_wrapper.get_user_by_username(user.username))
    return sanitize_user(user_model)


@router.post("/auth/logout")
async def logout(
    request: Request, response: Response, user: User = Depends(get_current_username)
):
    response.delete_cookie(key="restai_token")

    return {"message": "Logged out successfully."}
