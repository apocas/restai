import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request
import jwt
from restai import config
from restai.config import RESTAI_AUTH_SECRET
from restai.constants import ERROR_MESSAGES
from restai.database import get_db_wrapper, verify_password, DBWrapper
from restai.models.databasemodels import ProjectDatabase
from restai.models.models import User
import logging


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode: dict = data.copy()
    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire: datetime = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire.timestamp()})
    encoded_jwt: str = jwt.encode(to_encode, RESTAI_AUTH_SECRET, algorithm="HS512")
    return encoded_jwt


def _resolve_jwt_cookie(
    request: Request, auth_cookie: str, db_wrapper: DBWrapper
) -> User:
    """Decode the `restai_token` cookie → User. Raises 401 on any
    failure (bad signature, missing user, OR a `purpose` claim — see
    below).

    Rejects any token that carries a `purpose` claim. Purposed JWTs
    (currently `totp_verify` and `impersonation_restore`) are issued
    for narrow, single-purpose flows and are never valid as session
    cookies; if one of them ends up in the session slot — by browser
    quirk, hostile JS, or a future code regression — refusing it
    here is defense in depth.
    """
    try:
        data = jwt.decode(auth_cookie, RESTAI_AUTH_SECRET, algorithms=["HS512"])
    except Exception:
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_TOKEN)
    if data.get("purpose"):
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_TOKEN)
    user = db_wrapper.get_user_by_username(data["username"])
    if user is None:
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_TOKEN)
    request.state.audit_username = user.username
    return User.model_validate(user)


def _resolve_bearer_token(
    request: Request, token: str, db_wrapper: DBWrapper
) -> User:
    """Bearer API key → User, with API-key scope metadata attached."""
    user_db, api_key_row = db_wrapper.get_user_by_apikey(token)
    if user_db is None:
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)
    user = User.model_validate(user_db)
    if api_key_row is not None:
        if api_key_row.allowed_projects:
            try:
                user.api_key_allowed_projects = json.loads(api_key_row.allowed_projects)
            except (json.JSONDecodeError, TypeError):
                pass
        user.api_key_read_only = api_key_row.read_only or False
        user.api_key_id = api_key_row.id
    request.state.audit_username = f"{user_db.username} (api)"
    return user


def get_current_username(
    request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """The standard auth dependency.

    Accepts ONLY:
      - JWT cookie (`restai_token`) — humans, post-login
      - Bearer API key (`Authorization: Bearer <key>`) — programmatic

    HTTP **Basic** auth is intentionally NOT accepted here. That path
    used to bypass TOTP entirely (Basic→password→user, no second
    factor) and ignored the platform-wide `enforce_2fa` setting. The
    only place a password is verified now is `/auth/login`, which uses
    the dedicated `get_current_username_for_login` dep below; after
    login the user carries a JWT cookie that the TOTP step has already
    gated.
    """
    auth_cookie = request.cookies.get("restai_token")
    if auth_cookie:
        return _resolve_jwt_cookie(request, auth_cookie, db_wrapper)

    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        return _resolve_bearer_token(request, auth_header.split(" ", 1)[1], db_wrapper)

    raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)


def get_current_username_for_login(
    request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Login-only auth dep — used exclusively by `POST /auth/login`.

    Accepts JWT cookie / Bearer (so a re-login while already
    authenticated is a no-op rotate) AND HTTP Basic — the latter is
    the *only* remaining password-verification surface in the API,
    and the login flow itself enforces TOTP / `enforce_2fa` after a
    successful password check (see `routers/auth.py:login`).
    """
    auth_cookie = request.cookies.get("restai_token")
    if auth_cookie:
        return _resolve_jwt_cookie(request, auth_cookie, db_wrapper)

    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        return _resolve_bearer_token(request, auth_header.split(" ", 1)[1], db_wrapper)

    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)

        if config.RESTAI_AUTH_DISABLE_LOCAL or not username or not password:
            raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)

        user = db_wrapper.get_user_by_username(username)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)

        request.state.audit_username = user.username
        return User.model_validate(user)

    raise HTTPException(status_code=401, detail=ERROR_MESSAGES.INVALID_CRED)


def get_current_username_admin(user: User = Depends(get_current_username)):
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


def user_can_access_project(
    user: User, project_id: int, db_wrapper: DBWrapper
) -> bool:
    """Single source of truth for "is `user` allowed to use project
    `project_id`?". Combines the three layers the FastAPI dep below
    enforces:

      1. Direct membership / platform admin via `has_project_access`.
      2. Team-admin escalation — admins of a team can use any project
         in that team, even without explicit project membership.
      3. API-key project scope — Bearer-key sessions may have a
         narrower allow-list than the user's full project set.

    Pure function with no FastAPI dependency wiring, so callers
    outside the request/response cycle (e.g. the Block interpreter's
    `_eval_call_project`) can reuse it. Returns False on any miss;
    callers raise the appropriate HTTPException.
    """
    if not user.has_project_access(project_id):
        if not user.admin_teams:
            return False
        project_db = db_wrapper.get_project_by_id(project_id)
        if not (project_db and project_db.team_id and
                any(t.id == project_db.team_id for t in user.admin_teams)):
            return False
    return user.has_api_key_project_access(project_id)


def get_current_username_project(
    projectID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    if not user.has_project_access(projectID):
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
    if user.is_read_only:
        raise HTTPException(status_code=403, detail="This API key is read-only and cannot perform write operations")


# MCP supports two transport modes:
#
#   - Network transports (`http://`, `https://`, `sse://`) — the
#     MCP client connects to a running server. No process is spawned
#     locally. Safe for any authenticated user.
#
#   - Stdio transport — `host` is treated as a local executable path
#     and run as a subprocess (`anyio.open_process([host, *args])`).
#     `shell=False` means args don't go through a shell, but the
#     command itself is still arbitrary. With a host of `/bin/sh`
#     and args `["-c", "<payload>"]`, an attacker gets RCE as the
#     RESTai service account — read access to the Fernet key, the
#     auth secret, every project secret, and the Docker socket if
#     mounted.
#
# So: stdio is admin-only. Non-admins must use a network scheme.

_MCP_NETWORK_SCHEMES = ("http://", "https://", "sse://")


def _mcp_host_is_network(host: str) -> bool:
    if not host:
        return False
    lo = str(host).strip().lower()
    return any(lo.startswith(s) for s in _MCP_NETWORK_SCHEMES)


def check_user_can_use_mcp_host(user: User, host: str) -> None:
    """Refuse stdio MCP transport for non-admins. Network transports
    pass through (the MCP server runs elsewhere, no local subprocess
    is created).
    """
    if _mcp_host_is_network(host):
        return
    if user.is_admin:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Local-process (stdio) MCP transport is admin-only. "
            "Use an http://, https://, or sse:// MCP server instead."
        ),
    )


def check_not_restricted(user: User):
    if user.is_restricted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Restricted users cannot perform this operation")


def get_widget_from_request(request: Request, db_wrapper):
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

    creator = db_wrapper.get_user_by_id(widget.creator_id)
    if creator is not None and getattr(creator, "is_restricted", False) and not getattr(creator, "is_admin", False):
        raise HTTPException(status_code=403, detail="Widget owner is restricted")

    allowed = json.loads(widget.allowed_domains) if widget.allowed_domains else []
    if allowed and "*" not in allowed:
        origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if not origin:
            raise HTTPException(status_code=403, detail="Origin header required")
        try:
            host = urlparse(origin).hostname or ""
        except Exception:
            host = ""

        # Always allow the RESTai instance's own domain so the widget
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
    if p is not None and p.public and p.team_id:
        user_team_ids = {t.id for t in (user.teams or [])} | {t.id for t in (user.admin_teams or [])}
        if p.team_id in user_team_ids:
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
        )
    return user


def get_current_username_team_admin(
    team_id: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Check if user is an admin for the specified team or a platform admin"""
    if user.is_admin:
        return user

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
        )

    return user


# ─── Cross-team attach guards ────────────────────────────────────────────
# These prevent a team admin from attaching a resource owned by another
# team to their own team — credential / IP laundering. The auth dep
# `get_current_username_team_admin` only validates the *target* team;
# these helpers validate the *resource side* and are called from the
# attach endpoints + from `DBWrapper.update_team_members` (which is
# the parallel batch path the same data flows through).
#
# Pure functions that raise HTTPException(403) on failure — no FastAPI
# Depends wiring, so they're callable from inside DB layer code too.
# Platform admins (`user.is_admin`) bypass.


def _user_admins_team(user: User, team) -> bool:
    """True if `user` is an admin of `team`. Mirrors the membership-walk
    pattern used elsewhere (e.g. `routers/projects.py:902-907`)."""
    for admin in (team.admins or []):
        if admin.id == user.id:
            return True
    return False


def check_user_can_attach_project(user: User, project) -> None:
    """A team admin may attach a project to a team only if they're an
    admin of the project's owning team (the FK `project.team_id` —
    `team.projects` is a 1:M back-relationship, so this is a transfer-
    ownership operation in practice). Platform admins bypass.
    """
    if user.is_admin:
        return
    owning_team = getattr(project, "team", None)
    if owning_team is not None and _user_admins_team(user, owning_team):
        return
    raise HTTPException(
        status_code=403,
        detail="Not authorized to attach this project — you are not an admin of its owning team.",
    )


def check_user_can_attach_llm(user: User, llm) -> None:
    """A team admin may attach an LLM to a team only if they're an
    admin of at least one team the LLM is currently attached to.
    LLMs/embeddings have no single owning team (M2M), so the gate is
    "you must already legitimately have access via a team you
    administer." Public LLMs are NOT exempt — they still embed
    credentials in `LLMDatabase.options`. Platform admins bypass.
    """
    if user.is_admin:
        return
    for team in (getattr(llm, "teams", None) or []):
        if _user_admins_team(user, team):
            return
    raise HTTPException(
        status_code=403,
        detail="Not authorized to attach this LLM — you are not an admin of any team that has access to it.",
    )


def check_user_can_attach_embedding(user: User, embedding) -> None:
    """Same gate as `check_user_can_attach_llm`, applied to
    `EmbeddingDatabase`. Embeddings can carry credentials too."""
    if user.is_admin:
        return
    for team in (getattr(embedding, "teams", None) or []):
        if _user_admins_team(user, team):
            return
    raise HTTPException(
        status_code=403,
        detail="Not authorized to attach this embedding — you are not an admin of any team that has access to it.",
    )


def get_current_username_team_member(
    team_id: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Check if user is a member of the specified team (admin or normal member)"""
    if user.is_admin:
        return user

    team = db_wrapper.get_team_by_id(team_id)

    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

    is_team_member = False

    for team_user in team.users + team.admins:
        if team_user.id == user.id:
            is_team_member = True
            break

    if not is_team_member:
        raise HTTPException(
            status_code=403,
            detail=ERROR_MESSAGES.NOT_TEAM_MEMBER,
        )

    return user
