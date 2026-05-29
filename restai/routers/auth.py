from datetime import timedelta, datetime, timezone
from typing import Optional
import logging

import jwt
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import RedirectResponse
from restai import config
from restai.auth import (
    create_access_token,
    get_current_username,
    get_current_username_admin,
    get_current_username_for_login,
)
from restai.config import RESTAI_AUTH_SECRET
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User, TOTPVerifyRequest
from restai.utils.crypto import decrypt_totp_secret, hash_recovery_code, verify_recovery_code
import json


logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300


def _check_login_rate_limit(request: Request, db_wrapper: DBWrapper):
    from restai.models.databasemodels import LoginAttemptDatabase

    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_LOGIN_WINDOW_SECONDS)

    count = (
        db_wrapper.db.query(LoginAttemptDatabase)
        .filter(
            LoginAttemptDatabase.ip == ip,
            LoginAttemptDatabase.attempted_at > cutoff,
        )
        .count()
    )
    if count >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    db_wrapper.db.add(LoginAttemptDatabase(ip=ip, attempted_at=now))
    db_wrapper.db.commit()

    # Probabilistic cleanup (~1% of requests) to avoid query overhead per call.
    import random
    if random.random() < 0.01:
        db_wrapper.db.query(LoginAttemptDatabase).filter(
            LoginAttemptDatabase.attempted_at < cutoff
        ).delete()
        db_wrapper.db.commit()


def _rate_limit_dependency(request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """FastAPI dependency that checks the login rate limit BEFORE authentication."""
    _check_login_rate_limit(request, db_wrapper)


def _password_age_warning(user_db, db_wrapper) -> Optional[dict]:
    """Soft warning when password older than `password_max_age_days`; never blocks login."""
    try:
        max_days = int(db_wrapper.get_setting_value("password_max_age_days", "0") or "0")
    except (TypeError, ValueError):
        return None
    if max_days <= 0 or user_db is None or user_db.password_updated_at is None:
        return None
    from datetime import datetime, timezone
    last = user_db.password_updated_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last).days
    if age_days < max_days:
        return None
    return {
        "password_age_days": age_days,
        "password_max_age_days": max_days,
        "message": (
            f"Your password is {age_days} days old (limit: {max_days}). "
            "Please change it from the Account page."
        ),
    }


@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    _rl=Depends(_rate_limit_dependency),
    user: User = Depends(get_current_username_for_login),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Authenticate and receive a session cookie. If 2FA is enabled, returns a temporary token instead."""
    user_db = db_wrapper.get_user_by_username(user.username)
    if user_db and user_db.totp_enabled:
        totp_token = create_access_token(
            data={"username": user.username, "purpose": "totp_verify"},
            expires_delta=timedelta(minutes=5),
        )
        return {"requires_totp": True, "totp_token": totp_token}

    # Enforce platform-wide `enforce_2fa` at the auth gate (not just on disable).
    # Bootstrap escape: admin can disable enforce_2fa via settings, have users enroll, re-enable.
    if user_db and not user_db.totp_enabled and db_wrapper.get_setting_value(
        "enforce_2fa", "false"
    ).lower() in ("true", "1"):
        raise HTTPException(
            status_code=403,
            detail=(
                "Two-factor authentication is required by the administrator. "
                "Enroll a TOTP authenticator before signing in. "
                "If you cannot enroll, contact your administrator."
            ),
        )

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

    out = {"message": "Logged in successfully."}
    warning = _password_age_warning(user_db, db_wrapper)
    if warning:
        out["password_warning"] = warning
    return out


@router.post("/auth/verify-totp")
async def verify_totp(
    request: Request,
    body: TOTPVerifyRequest,
    response: Response,
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Complete 2FA login by verifying a TOTP code or recovery code."""
    _check_login_rate_limit(request, db_wrapper)
    try:
        data = jwt.decode(body.token, RESTAI_AUTH_SECRET, algorithms=["HS512"])
        if data.get("purpose") != "totp_verify":
            raise ValueError("Invalid token purpose")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired TOTP token")

    username = data.get("username")
    user_db = db_wrapper.get_user_by_username(username)
    if user_db is None or not user_db.totp_enabled or not user_db.totp_secret:
        raise HTTPException(status_code=401, detail="Invalid TOTP configuration")

    try:
        secret = decrypt_totp_secret(user_db.totp_secret)
        totp = pyotp.TOTP(secret)
        if totp.verify(body.code, valid_window=1):
            jwt_token = create_access_token(
                data={"username": username}, expires_delta=timedelta(minutes=1440)
            )
            response.set_cookie(
                key="restai_token", value=jwt_token,
                samesite="strict", expires=86400, httponly=True,
            )
            out = {"message": "Logged in successfully."}
            warning = _password_age_warning(user_db, db_wrapper)
            if warning:
                out["password_warning"] = warning
            return out
    except Exception:
        pass

    if user_db.totp_recovery_codes:
        try:
            codes = json.loads(user_db.totp_recovery_codes)
            matched_code = None
            for stored_hash in codes:
                if verify_recovery_code(body.code, stored_hash):
                    matched_code = stored_hash
                    break
            if matched_code is not None:
                codes.remove(matched_code)
                user_db.totp_recovery_codes = json.dumps(codes)
                db_wrapper.db.commit()

                jwt_token = create_access_token(
                    data={"username": username}, expires_delta=timedelta(minutes=1440)
                )
                response.set_cookie(
                    key="restai_token", value=jwt_token,
                    samesite="strict", expires=86400, httponly=True,
                )
                out = {"message": "Logged in successfully. Recovery code consumed."}
                warning = _password_age_warning(user_db, db_wrapper)
                if warning:
                    out["password_warning"] = warning
                return out
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid TOTP code")



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

    # Purposed restore token (claim `impersonation_restore`); `get_current_username`
    # rejects any cookie with a `purpose` claim so swap-into-restai_token can't auth as admin.
    admin_session_token = request.cookies.get("restai_token")
    if admin_session_token:
        restore_token = create_access_token(
            data={"username": user.username, "purpose": "impersonation_restore"},
            expires_delta=timedelta(minutes=30),
        )
        response.set_cookie(
            key="restai_token_admin",
            value=restore_token,
            samesite="strict",
            max_age=1800,
            httponly=True,
        )

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

    from restai.observability.audit import _log_to_db
    _log_to_db(user.username, "IMPERSONATE_START", username, 200)

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

    # Reject any token without the `impersonation_restore` purpose claim.
    try:
        data = jwt.decode(admin_token, RESTAI_AUTH_SECRET, algorithms=["HS512"])
    except jwt.PyJWTError:
        response.delete_cookie(key="restai_token_admin")
        raise HTTPException(status_code=400, detail="Invalid admin token")

    if data.get("purpose") != "impersonation_restore":
        response.delete_cookie(key="restai_token_admin")
        raise HTTPException(status_code=400, detail="Invalid admin token")

    admin_user = db_wrapper.get_user_by_username(data.get("username", ""))
    if admin_user is None or not admin_user.is_admin:
        response.delete_cookie(key="restai_token_admin")
        raise HTTPException(status_code=400, detail="Invalid admin token")

    # Fresh non-purposed session token; purpose-bearing tokens are rejected by `get_current_username`.
    admin_session_token = create_access_token(
        data={"username": admin_user.username},
        expires_delta=timedelta(minutes=1440),
    )
    response.set_cookie(
        key="restai_token",
        value=admin_session_token,
        samesite="strict",
        expires=86400,
        httponly=True,
    )
    response.delete_cookie(key="restai_token_admin")

    from restai.observability.audit import _log_to_db
    _log_to_db(admin_user.username, "IMPERSONATE_END", "", 200)

    return {"message": "Impersonation ended", "impersonating": False}


@router.post("/auth/logout")
async def logout(
    request: Request, response: Response, user: User = Depends(get_current_username)
):
    """Clear session cookies and log out.

    Both `restai_token` AND `restai_token_admin` deleted; otherwise an admin
    who impersonates then logs out leaves a dangling admin-scoped JWT that
    `POST /auth/exit-impersonation` could swap back into the session slot.
    """
    response.delete_cookie(key="restai_token")
    response.delete_cookie(key="restai_token_admin")

    return {"message": "Logged out successfully."}
