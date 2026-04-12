import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic
import jwt
from restai import config
from restai.config import RESTAI_AUTH_SECRET
from restai.constants import ERROR_MESSAGES
from restai.database import get_db_wrapper, verify_password, DBWrapper
from restai.models.databasemodels import ProjectDatabase
from restai.models.models import User
import logging

security: HTTPBasic = HTTPBasic()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode: dict = data.copy()
    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire: datetime = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire.timestamp()})
    encoded_jwt: str = jwt.encode(to_encode, RESTAI_AUTH_SECRET, algorithm="HS512")
    return encoded_jwt


def get_current_username(
    request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    auth_header = request.headers.get("Authorization")
    auth_cookie = request.cookies.get("restai_token")

    if auth_cookie:
        try:
            data = jwt.decode(auth_cookie, RESTAI_AUTH_SECRET, algorithms=["HS512"])

            user = db_wrapper.get_user_by_username(data["username"])
            
            if user is None:
                raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_TOKEN)

            return User.model_validate(user)
        except Exception:
            raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_TOKEN)
    elif auth_header:
        temp_bearer_token = auth_header.split(" ")[1]

        if "Bearer" in auth_header:
            user_db, api_key_row = db_wrapper.get_user_by_apikey(temp_bearer_token)

            if user_db is None:
                raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)

            user = User.model_validate(user_db)

            # Attach API key scope metadata
            if api_key_row is not None:
                if api_key_row.allowed_projects:
                    try:
                        user.api_key_allowed_projects = json.loads(api_key_row.allowed_projects)
                    except (json.JSONDecodeError, TypeError):
                        pass
                user.api_key_read_only = api_key_row.read_only or False

            return user
        elif "Basic" in auth_header:
            try:
                try:
                    credentials_b64 = base64.b64decode(temp_bearer_token).decode(
                        "utf-8"
                    )
                except Exception:
                    raise HTTPException(
                        status_code=401, detail=ERROR_MESSAGES.INVALID_CRED
                    )
                username, password = credentials_b64.split(":", 1)
                credentials = {"username": username, "password": password}

                if (
                    config.RESTAI_AUTH_DISABLE_LOCAL
                    or not credentials
                    or ("username" not in credentials or "password" not in credentials)
                ):
                    raise HTTPException(
                        status_code=401, detail=ERROR_MESSAGES.INVALID_CRED
                    )

                user = db_wrapper.get_user_by_username(credentials["username"])

                if user is None:
                    raise HTTPException(
                        status_code=401, detail=ERROR_MESSAGES.INVALID_CRED
                    )

                is_correct_username = credentials["username"] == user.username
                is_correct_password = verify_password(
                    credentials["password"], user.hashed_password
                )

                if not (is_correct_username and is_correct_password):
                    raise HTTPException(
                        status_code=401,
                        detail=ERROR_MESSAGES.INVALID_CRED,
                        headers={"WWW-Authenticate": "Basic"},
                    )

                return User.model_validate(user)

            except Exception as e:
                if isinstance(e, HTTPException):
                    raise e
                logging.exception(e)
                raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)
    else:
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)


def get_current_username_admin(user: User = Depends(get_current_username)):
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_username_project(
    projectID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    if not user.has_project_access(projectID):
        # Team admin: can access all projects in their administered teams
        if user.admin_teams:
            project_db = db_wrapper.get_project_by_id(projectID)
            if not (project_db and project_db.team_id and
                    any(t.id == project_db.team_id for t in user.admin_teams)):
                raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
        else:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
    if not user.has_api_key_project_access(projectID):
        raise HTTPException(status_code=403, detail="API key does not have access to this project")
    return user


def check_not_read_only(user: User):
    """Raise 403 if the user's API key is read-only."""
    if user.is_read_only:
        raise HTTPException(status_code=403, detail="This API key is read-only and cannot perform write operations")


def check_not_restricted(user: User):
    """Raise 403 if the user is restricted."""
    if user.is_restricted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Restricted users cannot perform this operation")


def get_widget_from_request(request: Request, db_wrapper):
    """Authenticate a widget request via X-Widget-Key header. Validates domain."""
    from urllib.parse import urlparse

    widget_key = request.headers.get("X-Widget-Key")
    if not widget_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer wk_"):
            widget_key = auth_header.split(" ", 1)[1]
    if not widget_key or not widget_key.startswith("wk_"):
        raise HTTPException(status_code=401, detail="Widget key required")

    widget = db_wrapper.get_widget_by_key(widget_key)
    if widget is None:
        raise HTTPException(status_code=401, detail="Invalid widget key")

    if not widget.enabled:
        raise HTTPException(status_code=403, detail="Widget is disabled")

    allowed = json.loads(widget.allowed_domains) if widget.allowed_domains else []
    if allowed and "*" not in allowed:
        origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if not origin:
            raise HTTPException(status_code=403, detail="Origin header required")
        try:
            host = urlparse(origin).hostname or ""
        except Exception:
            host = ""

        # Always allow the RestAI instance's own domain so the widget
        # preview on the admin UI works regardless of allowed_domains.
        own_host = None
        if config.RESTAI_URL:
            try:
                own_host = urlparse(config.RESTAI_URL).hostname
            except Exception:
                pass
        is_own_domain = own_host and host and host.lower() == own_host.lower()

        if not is_own_domain and not _domain_matches(host, allowed):
            raise HTTPException(status_code=403, detail="Domain not allowed")

    return widget


def _domain_matches(host: str, allowed: list) -> bool:
    """Check if host matches any allowed domain pattern (supports *.example.com)."""
    if not host:
        return False
    host = host.lower()
    for pattern in allowed:
        pattern = pattern.lower().strip()
        if pattern == host:
            return True
        if pattern.startswith("*.") and (host.endswith(pattern[1:]) or host == pattern[2:]):
            return True
    return False


def get_current_username_project_public(
    projectID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    has_access = user.has_project_access(projectID)
    # Team admin access
    if not has_access and user.admin_teams:
        p = db_wrapper.get_project_by_id(projectID)
        if p and p.team_id and any(t.id == p.team_id for t in user.admin_teams):
            has_access = True

    if has_access:
        if not user.has_api_key_project_access(projectID):
            raise HTTPException(status_code=403, detail="API key does not have access to this project")
        user.level = "own"
        return user

    p: Optional[ProjectDatabase] = db_wrapper.get_project_by_id(projectID)
    if p is not None and p.public:
        if not user.has_api_key_project_access(projectID):
            raise HTTPException(status_code=403, detail="API key does not have access to this project")
        user.level = "public"
        return user

    raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)


def get_current_username_user(
    username: str, user: User = Depends(get_current_username)
):
    found = False
    if not user.is_admin:
        if user.username == username:
            found = True
    else:
        found = True

    if not found:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
    return user


def get_current_username_platform_admin(user: User = Depends(get_current_username)):
    """Check if user is a platform admin (can manage teams)"""
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_username_team_admin(
    team_id: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Check if user is an admin for the specified team or a platform admin"""
    if user.is_admin:  # Platform admins can manage any team
        return user

    # Check if user is a team admin for this team
    is_team_admin = False
    team = db_wrapper.get_team_by_id(team_id)

    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

    for admin in team.admins:
        if admin.id == user.id:
            is_team_admin = True
            break

    if not is_team_admin:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.NOT_TEAM_ADMIN,
            headers={"WWW-Authenticate": "Basic"},
        )

    return user


def get_current_username_team_member(
    team_id: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Check if user is a member of the specified team (admin or normal member)"""
    if user.is_admin:  # Platform admins can access any team
        return user

    # Check if user is a team member
    team = db_wrapper.get_team_by_id(team_id)

    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

    is_team_member = False

    # Check if user is an admin or member
    for team_user in team.users + team.admins:
        if team_user.id == user.id:
            is_team_member = True
            break

    if not is_team_member:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.NOT_TEAM_MEMBER,
            headers={"WWW-Authenticate": "Basic"},
        )

    return user
