"""HTTP endpoints for the App-Builder file IDE — file tree + file CRUD."""

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
from restai.app.storage import (
    MAX_FILE_BYTES,
    list_tree,
    project_lock,
    read_file,
    write_file,
)

from ._common import router, _require_app_project


class FilePayload(BaseModel):
    """Payload for PUT /app/files; UTF-8 only, no binary."""

    content: str = Field(description="Full file content (UTF-8 text)")


@router.get("/projects/{projectID}/app/tree", tags=["App Builder"])
async def route_app_tree(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the app project's file tree (recursive, dirs first then files)."""
    _require_app_project(request, projectID, db_wrapper)
    return {"tree": list_tree(projectID)}


@router.get("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_get_file(
    request: Request,
    response: Response,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return file contents + content-addressed ETag (use as If-Match on PUT)."""
    _require_app_project(request, projectID, db_wrapper)
    data, etag = read_file(projectID, path)
    response.headers["ETag"] = etag
    # Fail explicit on binary so the IDE doesn't silently corrupt binary files.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="binary file not editable")
    return {"path": path, "content": text, "etag": etag, "size": len(data)}


@router.put("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_put_file(
    request: Request,
    response: Response,
    payload: FilePayload,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Write file contents; If-Match required for existing files."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    if_match = request.headers.get("if-match") or request.headers.get("If-Match")
    data = payload.content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds size cap")
    async with project_lock(projectID):
        new_etag = write_file(projectID, path, data, if_match=if_match)
    response.headers["ETag"] = new_etag
    return {"path": path, "etag": new_etag, "size": len(data)}


@router.delete("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_delete_file(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a single file (directories not supported)."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    from restai.app.storage import resolve_path
    target = resolve_path(projectID, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="cannot delete directory")
    async with project_lock(projectID):
        target.unlink()
    return {"path": path, "deleted": True}
