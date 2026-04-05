from datetime import timedelta, datetime, timezone
from collections import defaultdict
import logging
import threading

import jwt
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import RedirectResponse
from restai import config
from restai.auth import create_access_token, get_current_username, get_current_username_admin
from restai.config import RESTAI_AUTH_SECRET
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User, TOTPVerifyRequest
from restai.utils.crypto import decrypt_totp_secret, hash_recovery_code
import json


logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

# --- IP-based rate limiter for auth endpoints ---
_login_attempts = defaultdict(list)  # ip -> [timestamps]
_login_lock = threading.Lock()
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300  # 5 minutes


_login_last_cleanup = datetime.now(timezone.utc)


def _check_login_rate_limit(request: Request):
    global _login_last_cleanup
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_LOGIN_WINDOW_SECONDS)
    with _login_lock:
        # Periodic cleanup of stale IPs
        if (now - _login_last_cleanup).total_seconds() > _LOGIN_WINDOW_SECONDS:
            stale = [k for k, v in _login_attempts.items() if not v or v[-1] < cutoff]
            for k in stale:
                del _login_attempts[k]
            _login_last_cleanup = now
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
        if len(_login_attempts[ip]) >= _LOGIN_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        _login_attempts[ip].append(now)


def _rate_limit_dependency(request: Request):
    _check_login_rate_limit(request)


@router.post("/auth/login")
async def login(
    request: Request,
    response: Response,
    _rl=Depends(_rate_limit_dependency),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Authenticate and receive a session cookie. If 2FA is enabled, returns a temporary token instead."""
    # Check if user has TOTP enabled
    user_db = db_wrapper.get_user_by_username(user.username)
    if user_db and user_db.totp_enabled:
        # Return temp token for TOTP verification (5 min expiry)
        totp_token = create_access_token(
            data={"username": user.username, "purpose": "totp_verify"},
            expires_delta=timedelta(minutes=5),
        )
        return {"requires_totp": True, "totp_token": totp_token}

    # Normal login — no 2FA
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


@router.post("/auth/verify-totp")
async def verify_totp(
    request: Request,
    body: TOTPVerifyRequest,
    response: Response,
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Complete 2FA login by verifying a TOTP code or recovery code."""
    _check_login_rate_limit(request)
    # Decode temp token
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

    # Try TOTP code first
    try:
        secret = decrypt_totp_secret(user_db.totp_secret)
        totp = pyotp.TOTP(secret)
        if totp.verify(body.code, valid_window=1):
            # Valid TOTP code — create session
            jwt_token = create_access_token(
                data={"username": username}, expires_delta=timedelta(minutes=1440)
            )
            response.set_cookie(
                key="restai_token", value=jwt_token,
                samesite="strict", expires=86400, httponly=True,
            )
            return {"message": "Logged in successfully."}
    except Exception:
        pass

    # Try recovery code
    if user_db.totp_recovery_codes:
        try:
            codes = json.loads(user_db.totp_recovery_codes)
            code_hash = hash_recovery_code(body.code)
            if code_hash in codes:
                # Consume the recovery code
                codes.remove(code_hash)
                user_db.totp_recovery_codes = json.dumps(codes)
                db_wrapper.db.commit()

                jwt_token = create_access_token(
                    data={"username": username}, expires_delta=timedelta(minutes=1440)
                )
                response.set_cookie(
                    key="restai_token", value=jwt_token,
                    samesite="strict", expires=86400, httponly=True,
                )
                return {"message": "Logged in successfully. Recovery code consumed."}
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
