"""Bulk file ingest queue for RAG projects.

Three endpoints, all scoped to a project the user has access to:

* ``POST /projects/{id}/ingest-bulk`` — accepts one or more files,
  writes each to a tempfile, creates a ``queued`` row in
  ``bulk_ingest_jobs``, and returns the job ids. Returns 202 because
  the actual ingest happens in the cron.
* ``GET /projects/{id}/ingest-bulk`` — paginated list of recent jobs
  for the project, newest first, so the admin UI can poll / render a
  progress table.
* ``DELETE /projects/{id}/ingest-bulk/{jobID}`` — cancel/reap a job.
  If it's still queued, marks as ``error`` ("cancelled") and deletes
  the tempfile. Done/error rows are just deleted outright.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, UploadFile
from sqlalchemy.orm import Session

from restai import config
from restai.auth import check_not_restricted, get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import BulkIngestJobDatabase, ProjectDatabase
from restai.models.models import User, sanitize_filename


router = APIRouter()


# On-disk staging area for queued uploads. One subdir so clean-up /
# permissions are easy to reason about. Created lazily on first write.
_QUEUE_DIR = os.path.join(tempfile.gettempdir(), "restai_bulk_ingest")


def _ensure_queue_dir() -> str:
    os.makedirs(_QUEUE_DIR, exist_ok=True)
    return _QUEUE_DIR


def _job_to_dict(job: BulkIngestJobDatabase) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "filename": job.filename,
        "mime_type": job.mime_type,
        "size_bytes": job.size_bytes,
        "method": job.method,
        "status": job.status,
        "error_message": job.error_message,
        "documents_count": job.documents_count,
        "chunks_count": job.chunks_count,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/projects/{projectID}/ingest-bulk", status_code=202, tags=["Knowledge"])
async def enqueue_bulk_ingest(
    projectID: int = PathParam(description="Project ID"),
    files: list[UploadFile] = ...,
    method: str = "auto",
    splitter: str = "sentence",
    chunks: int = 256,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Accept one or more files and queue them for async ingestion.
    Returns ``{"queued": [job_id, ...]}`` — poll the list endpoint for
    status. Only RAG projects accept bulk ingest."""
    check_not_restricted(user)
    if splitter not in ("sentence", "token"):
        raise HTTPException(status_code=422, detail="splitter must be 'sentence' or 'token'")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    project = db_wrapper.get_project_by_id(projectID)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.type != "rag":
        raise HTTPException(status_code=400, detail="Bulk ingest only available for RAG projects")

    max_bytes = config.MAX_UPLOAD_SIZE
    queue_dir = _ensure_queue_dir()
    queued_ids: list[int] = []

    for upload in files:
        safe_name = sanitize_filename(upload.filename or "upload.bin")
        contents = await upload.read()
        if len(contents) > max_bytes:
            # Refuse the whole request so the admin doesn't end up with
            # a half-queued batch — easier to reason about than silent
            # partial success.
            raise HTTPException(
                status_code=413,
                detail=f"'{safe_name}' exceeds max upload size ({max_bytes // (1024*1024)} MB)",
            )

        # Tempfile name carries the project + job intent so an admin
        # inspecting /tmp/restai_bulk_ingest/ can correlate.
        fd, path = tempfile.mkstemp(prefix=f"proj{projectID}_", suffix=f"_{safe_name}", dir=queue_dir)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(contents)
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise

        job = BulkIngestJobDatabase(
            project_id=projectID,
            filename=safe_name,
            mime_type=upload.content_type,
            size_bytes=len(contents),
            file_path=path,
            method=method or "auto",
            splitter=splitter,
            chunks=chunks,
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        db_wrapper.db.add(job)
        db_wrapper.db.commit()
        db_wrapper.db.refresh(job)
        queued_ids.append(job.id)

    return {"queued": queued_ids, "count": len(queued_ids)}


@router.get("/projects/{projectID}/ingest-bulk", tags=["Knowledge"])
async def list_bulk_ingest_jobs(
    projectID: int = PathParam(description="Project ID"),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Recent bulk-ingest jobs for this project, newest first."""
    jobs = (
        db_wrapper.db.query(BulkIngestJobDatabase)
        .filter(BulkIngestJobDatabase.project_id == projectID)
        .order_by(BulkIngestJobDatabase.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"jobs": [_job_to_dict(j) for j in jobs]}


@router.delete("/projects/{projectID}/ingest-bulk/{jobID}", tags=["Knowledge"])
async def delete_bulk_ingest_job(
    projectID: int = PathParam(description="Project ID"),
    jobID: int = PathParam(description="Job ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Cancel or reap a bulk-ingest job. Queued jobs get marked
    cancelled + tempfile deleted. Done/error rows are deleted
    outright."""
    check_not_restricted(user)
    job = (
        db_wrapper.db.query(BulkIngestJobDatabase)
        .filter(
            BulkIngestJobDatabase.id == jobID,
            BulkIngestJobDatabase.project_id == projectID,
        )
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Always try to remove the tempfile if it's still there.
    if job.file_path:
        try:
            os.unlink(job.file_path)
        except OSError:
            pass

    db_wrapper.db.delete(job)
    db_wrapper.db.commit()
    return {"deleted": jobID}
