"""HTTP endpoints for App-Builder download + deploy (SFTP/FTP)."""

from __future__ import annotations

from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel, Field

from restai.auth import (
    check_not_restricted,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User

from ._common import router, logger, _require_app_project


@router.get(
    "/projects/{projectID}/app/download",
    tags=["App Builder"],
    response_class=Response,
)
async def route_app_download(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    include_source: bool = Query(False, description="Ship src/*.ts source files alongside the compiled dist/"),
    include_db: bool = Query(False, description="Include database.sqlite (the dev database) in the zip"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Stream a ZIP of the project's source tree."""
    project = _require_app_project(request, projectID, db_wrapper)
    from fastapi.responses import StreamingResponse
    from restai.app.deploy import ZipFilters, stream_zip
    from restai.app.storage import get_project_root

    root = get_project_root(projectID)
    if not root.exists():
        raise HTTPException(status_code=404, detail="project has no source tree")

    filters = ZipFilters(include_source=include_source, include_db=include_db)
    safe_name = (project.props.name or f"app-{projectID}").replace("/", "_")
    return StreamingResponse(
        stream_zip(root, filters),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.zip"',
            "Cache-Control": "no-store",
        },
    )


class DeployTestPayload(BaseModel):
    """Payload for the connection-test endpoint."""
    protocol: str = Field(default="sftp", description="'sftp' or 'ftp'")
    host: str = Field(description="Hostname (no scheme, no port)")
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str = Field(description="Login username")
    password: str = Field(description="Login password (or '' to use saved credentials)")
    path: str = Field(default="/", description="Remote directory")
    use_passive: bool = Field(default=True, description="FTP passive mode (ignored for SFTP)")


def _resolve_deploy_credentials(project, payload_password: str) -> str:
    """Empty password means 'use what's stored on the project'."""
    if payload_password:
        return payload_password
    opts = project.props.options
    saved = getattr(opts, "ftp_password", None)
    if not saved:
        raise HTTPException(status_code=400, detail="No saved password — fill in the password field.")
    return saved


@router.post("/projects/{projectID}/app/deploy/test", tags=["App Builder"])
async def route_app_deploy_test(
    request: Request,
    payload: DeployTestPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Test deploy connection (no file transfer)."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.app.deploy import test_connection
    pw = _resolve_deploy_credentials(project, payload.password)
    result = test_connection(
        protocol=payload.protocol,
        host=payload.host,
        port=payload.port or (22 if payload.protocol == "sftp" else 21),
        user=payload.user,
        password=pw,
        remote_dir=payload.path,
        use_passive=payload.use_passive,
    )
    return result


class DeployRunPayload(BaseModel):
    include_source: bool = Field(default=False)
    include_db: bool = Field(default=False)
    protocol: str | None = Field(default=None)
    host: str | None = Field(default=None)
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None)
    password: str | None = Field(default=None)
    path: str | None = Field(default=None)
    use_passive: bool | None = Field(default=None)


@router.post("/projects/{projectID}/app/deploy", tags=["App Builder"])
async def route_app_deploy(
    request: Request,
    payload: DeployRunPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Push project files to the configured host; SSE-streamed progress."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    opts = project.props.options
    proto = (payload.protocol or getattr(opts, "ftp_protocol", None) or "sftp").lower()
    host = payload.host or getattr(opts, "ftp_host", None)
    port = payload.port or getattr(opts, "ftp_port", None) or (22 if proto == "sftp" else 21)
    login = payload.user or getattr(opts, "ftp_user", None)
    password = payload.password or getattr(opts, "ftp_password", None)
    path = payload.path or getattr(opts, "ftp_path", None) or "/"
    use_passive = payload.use_passive if payload.use_passive is not None else bool(
        getattr(opts, "ftp_use_passive", True)
    )

    if not host:
        raise HTTPException(status_code=400, detail="ftp_host is not configured")
    if not login or not password:
        raise HTTPException(status_code=400, detail="ftp_user / ftp_password are not configured")
    if proto not in ("sftp", "ftp"):
        raise HTTPException(status_code=400, detail=f"unknown protocol {proto!r}")

    from fastapi.responses import StreamingResponse
    from restai.app.deploy import ZipFilters, deploy_sftp, deploy_ftp
    from restai.app.storage import get_project_root, project_lock
    import json as _json

    root = get_project_root(projectID)
    if not root.exists():
        raise HTTPException(status_code=404, detail="project has no source tree")

    filters = ZipFilters(
        include_source=bool(payload.include_source),
        include_db=bool(payload.include_db),
    )

    async def stream():
        # Per-project lock so two parallel deploys can't race.
        async with project_lock(projectID):
            if proto == "sftp":
                gen = deploy_sftp(
                    root, filters,
                    host=host, port=port, user=login, password=password,
                    remote_dir=path,
                )
            else:
                gen = deploy_ftp(
                    root, filters,
                    host=host, port=port, user=login, password=password,
                    remote_dir=path, use_passive=use_passive,
                )
            uploaded = 0
            had_error = False
            try:
                for evt in gen:
                    et = evt.get("event") or "message"
                    if et == "upload":
                        uploaded += 1
                    if et == "error":
                        had_error = True
                    yield f"event: {et}\ndata: {_json.dumps(evt)}\n\n"
            except Exception as e:
                logger.exception("deploy stream crashed for project=%s", projectID)
                yield f"event: error\ndata: {_json.dumps({'message': str(e)})}\n\n"
                had_error = True

            try:
                from restai.observability.audit import _log_to_db as _audit
                _audit(
                    user.username,
                    "APP_DEPLOY" if not had_error else "APP_DEPLOY_FAIL",
                    f"projects/{projectID}:proto={proto}:files={uploaded}",
                    200 if not had_error else 500,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")
