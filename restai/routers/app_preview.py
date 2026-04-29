"""Reverse proxy for the App-Builder live preview.

Forwards every request under ``/projects/{projectID}/app/preview/{path:path}``
to the project's per-project Docker container. Same-origin so the IDE iframe
stays under the RESTai cookie / CSP, no CORS gymnastics.

Spins the container on first hit (via ``brain.app_manager.get_or_create``),
records every request as activity (so the cleanup cron doesn't kill an
actively-used preview).
"""

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


# RFC 7230 hop-by-hop headers — must NOT be forwarded across a proxy. Plus
# Host (we'll set our own) and Content-Length (httpx recomputes). Lower-case
# because we normalize on the way in.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "host", "content-length",
}

# Response headers to drop on the way back. X-Frame-Options would block the
# iframe embed; strip it so the IDE can render the preview. CSP is left
# intact — the generated app's own CSP, if any, applies inside the iframe.
_RESPONSE_HEADERS_TO_STRIP = {
    "x-frame-options",
    # The container speaks HTTP/1.1; we forward as ASGI. Drop transfer
    # encoding so Starlette can recompute (otherwise some clients see a
    # double "chunked" header).
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

    Generated PHP that calls ``session_start()`` will set ``Path=/`` — under
    the proxy that means the cookie scopes to the entire RESTai domain,
    which is wrong (it would be sent to /admin, /api/v1, etc.) AND clashes
    with RESTai's own cookies. Rewriting to the mount path scopes it to
    the iframe.
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
            # Redirects to / inside the container should land back on the
            # mount, not on the RESTai root.
            if value.startswith("/"):
                out.append((name, mount.rstrip("/") + value))
            else:
                out.append((name, value))
        else:
            out.append((name, value))
    return out


async def _ensure_app_running(request: Request, projectID: int, db_wrapper: DBWrapper):
    """Resolve the project, assert it's an `app`, and start its container if
    needed. Returns the host port the container listens on."""
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
    # Helpful for the generated app to know it's behind a proxy.
    forward_headers["X-Forwarded-Prefix"] = mount.rstrip("/")
    forward_headers["X-Forwarded-Proto"] = request.url.scheme
    if request.client:
        forward_headers["X-Forwarded-For"] = request.client.host

    try:
        # New client per request: simple, safe, the connection cost is
        # negligible against localhost. We can pool later if it ever shows
        # up in profiles.
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

    # Touch last_activity so the cleanup cron doesn't evict an actively-used
    # preview. Best-effort — never raise.
    mgr = getattr(request.app.state.brain, "app_manager", None)
    if mgr is not None:
        try:
            mgr._touch(projectID)  # noqa: SLF001 — internal but stable
        except Exception:
            pass

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
    """Cheap status check — no side effects. Tells the IDE whether the
    runtime is enabled, whether a container is running, and the host port
    if so. The iframe uses this before issuing the heavy first preview
    fetch (which would spin the container)."""
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
