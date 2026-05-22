"""Reverse proxy for the App-Builder live preview."""

from __future__ import annotations

import logging
import time
from typing import Iterable

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path as PathParam,
    Request,
)
from fastapi.responses import Response, StreamingResponse

from restai.auth import get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User

router = APIRouter()
logger = logging.getLogger(__name__)


# RFC 7230 hop-by-hop headers — must NOT be forwarded across a proxy.
# Plus Host (we set our own) and Content-Length (httpx recomputes).
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "host", "content-length",
}

# Drop X-Frame-Options so the iframe embed works. CSP left intact.
# Drop transfer-encoding so Starlette doesn't double-chunk.
_RESPONSE_HEADERS_TO_STRIP = {
    "x-frame-options",
    "transfer-encoding",
    "connection",
    "keep-alive",
}


def _filter_request_headers(headers) -> dict:
    out = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in _HOP_BY_HOP:
            continue
        out[name] = value
    return out


def _rewrite_set_cookie(value: str, mount: str) -> str:
    """Rewrite ``Set-Cookie`` ``Path=`` to live under the proxy mount.

    PHP session_start() sets Path=/ — under the proxy that scopes the
    cookie to the entire RESTai domain (sent to /admin, /api/v1, etc.)
    and clashes with RESTai's own cookies.
    """
    parts = [p.strip() for p in value.split(";")]
    new_parts: list[str] = []
    saw_path = False
    for p in parts:
        if not p:
            continue
        if p.lower().startswith("path="):
            new_parts.append(f"Path={mount}")
            saw_path = True
        else:
            new_parts.append(p)
    if not saw_path:
        new_parts.append(f"Path={mount}")
    return "; ".join(new_parts)


def _filter_response_headers(items: Iterable[tuple[str, str]], mount: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name, value in items:
        lower = name.lower()
        if lower in _RESPONSE_HEADERS_TO_STRIP:
            continue
        if lower == "set-cookie":
            out.append((name, _rewrite_set_cookie(value, mount)))
        elif lower == "location":
            # Redirects to / inside the container should land back on the mount.
            if value.startswith("/"):
                out.append((name, mount.rstrip("/") + value))
            else:
                out.append((name, value))
        else:
            out.append((name, value))
    return out


async def _ensure_app_running(request: Request, projectID: int, db_wrapper: DBWrapper):
    """Resolve the project, assert app type, start container if needed; returns host port."""
    brain = request.app.state.brain
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.props.type != "app":
        raise HTTPException(
            status_code=400,
            detail="Preview is only available for app-builder projects",
        )

    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail="App Builder runtime is not enabled. Set app_docker_enabled in admin settings.",
        )

    try:
        _, port = await mgr.get_or_create(projectID)
    except Exception as e:
        logger.exception("AppManager get_or_create failed for project %s", projectID)
        raise HTTPException(status_code=502, detail=f"Container failed to start: {e}")
    return port


@router.api_route(
    "/projects/{projectID}/app/preview",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    tags=["App Builder"],
    include_in_schema=False,
)
async def route_preview_root(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Mount root: forwards to ``/`` inside the container."""
    return await _proxy(request, projectID, "", db_wrapper)


@router.api_route(
    "/projects/{projectID}/app/preview/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    tags=["App Builder"],
    include_in_schema=False,
)
async def route_preview_path(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    path: str = PathParam(description="Path inside the container"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    return await _proxy(request, projectID, path, db_wrapper)


async def _proxy(request: Request, projectID: int, path: str, db_wrapper: DBWrapper):
    port = await _ensure_app_running(request, projectID, db_wrapper)

    mount = f"/projects/{int(projectID)}/app/preview/"
    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    body = await request.body()
    forward_headers = _filter_request_headers(request.headers)
    forward_headers["Host"] = f"127.0.0.1:{port}"
    forward_headers["X-Forwarded-Prefix"] = mount.rstrip("/")
    forward_headers["X-Forwarded-Proto"] = request.url.scheme
    if request.client:
        forward_headers["X-Forwarded-For"] = request.client.host

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                target_url,
                headers=forward_headers,
                content=body if body else None,
            )
    except httpx.ConnectError as e:
        logger.warning("Preview proxy connect failed for project %s: %s", projectID, e)
        raise HTTPException(status_code=502, detail="Preview container unreachable")
    except httpx.RequestError as e:
        logger.warning("Preview proxy request failed for project %s: %s", projectID, e)
        raise HTTPException(status_code=502, detail=f"Preview proxy error: {e}")

    response_headers = _filter_response_headers(upstream.headers.multi_items(), mount)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(response_headers),
    )


@router.post(
    "/projects/{projectID}/app/restart",
    tags=["App Builder"],
)
async def route_app_restart(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Stop + recreate the project's preview container. Returns the new port."""
    from restai.auth import check_not_restricted
    check_not_restricted(user)

    brain = request.app.state.brain
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.props.type != "app":
        raise HTTPException(status_code=400, detail="Only available for app-builder projects")

    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail="App Builder runtime is not enabled.",
        )
    try:
        _, port = await mgr.restart(projectID)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Restart failed: {e}")
    return {"port": port, "restarted_at": int(time.time())}


@router.get(
    "/projects/{projectID}/app/runtime/status",
    tags=["App Builder"],
)
async def route_app_runtime_status(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Cheap status check — no side effects."""
    brain = request.app.state.brain
    project = brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.props.type != "app":
        raise HTTPException(status_code=400, detail="Only available for app-builder projects")

    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        return {"enabled": False, "running": False, "port": None}
    return {
        "enabled": True,
        "running": mgr.get_port(projectID) is not None,
        "port": mgr.get_port(projectID),
    }


__all__ = ["router"]
