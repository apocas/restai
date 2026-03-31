from datetime import timedelta
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import RedirectResponse
from restai import config
from restai.auth import create_access_token, get_current_username, get_current_username_admin
from restai.config import RESTAI_AUTH_SECRET
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User


logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Authenticate and receive a session cookie."""
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
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get the currently authenticated user's profile."""
    user_model = User.model_validate(db_wrapper.get_user_by_username(user.username))
    result = user_model.model_dump()
    result["impersonating"] = request.cookies.get("restai_token_admin") is not None
    return result


@router.post("/auth/impersonate/{username}")
async def impersonate_user(
    request: Request,
    response: Response,
    username: str = Path(description="Username to impersonate"),
    user: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Impersonate another user (admin only). Saves admin session for restoration."""
    target = db_wrapper.get_user_by_username(username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Save admin's current token
    admin_token = request.cookies.get("restai_token")
    if admin_token:
        response.set_cookie(
            key="restai_token_admin",
            value=admin_token,
            samesite="strict",
            expires=86400,
            httponly=True,
        )

    # Create token for target user
    jwt_token = create_access_token(
        data={"username": username},
        expires_delta=timedelta(minutes=1440),
    )
    response.set_cookie(
        key="restai_token",
        value=jwt_token,
        samesite="strict",
        expires=86400,
        httponly=True,
    )

    return {"message": f"Impersonating {username}", "impersonating": True}


@router.post("/auth/exit-impersonation")
async def exit_impersonation(
    request: Request,
    response: Response,
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Exit impersonation and restore the admin session."""
    admin_token = request.cookies.get("restai_token_admin")
    if not admin_token:
        raise HTTPException(status_code=400, detail="Not currently impersonating")

    # Validate the admin token is a valid JWT
    try:
        data = jwt.decode(admin_token, RESTAI_AUTH_SECRET, algorithms=["HS512"])
    except jwt.PyJWTError:
        response.delete_cookie(key="restai_token_admin")
        raise HTTPException(status_code=400, detail="Invalid admin token")

    # Verify the token belongs to an admin user
    admin_user = db_wrapper.get_user_by_username(data.get("username", ""))
    if admin_user is None or not admin_user.is_admin:
        response.delete_cookie(key="restai_token_admin")
        raise HTTPException(status_code=400, detail="Invalid admin token")

    # Restore admin token
    response.set_cookie(
        key="restai_token",
        value=admin_token,
        samesite="strict",
        expires=86400,
        httponly=True,
    )
    response.delete_cookie(key="restai_token_admin")

    return {"message": "Impersonation ended", "impersonating": False}


@router.post("/auth/logout")
async def logout(
    request: Request, response: Response, user: User = Depends(get_current_username)
):
    """Clear the session cookie and log out."""
    response.delete_cookie(key="restai_token")

    return {"message": "Logged out successfully."}
