"""Bulk file ingest queue for RAG projects."""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, UploadFile

from restai import config
from restai import reembed
from restai.auth import check_not_restricted, get_current_username_project
from restai.constants import ERROR_MESSAGES
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import BulkIngestJobDatabase
from restai.models.models import User, sanitize_filename


router = APIRouter()


# Staging area for queued uploads. Deliberately NOT the system temp dir: the
# API and the cron consumer run in separate containers (docker-compose and the
# Helm chart alike) and only share the data volume, so a /tmp path is written
# by one and invisible to the other. See config.UPLOAD_STAGING_PATH.
_QUEUE_DIR = os.path.abspath(
    config.UPLOAD_STAGING_PATH or os.path.join(tempfile.gettempdir(), "restai_bulk_ingest")
)


def _ensure_queue_dir() -> str:
    os.makedirs(_QUEUE_DIR, exist_ok=True)
    return _QUEUE_DIR


# Keep this much of the staging filesystem free after a batch lands. Uploads
# are staged to local disk and only removed once the cron has ingested them,
# so a large batch on a small volume can otherwise fill the disk and take the
# rest of the app down with it.
_DISK_HEADROOM_BYTES = 512 * 1024 * 1024


def _require_free_space(path: str, needed_bytes: int) -> None:
    """Refuse a batch that wouldn't leave `_DISK_HEADROOM_BYTES` free.

    Best-effort: if the filesystem can't be queried we allow the write rather
    than block ingestion on a stat failure.
    """
    if needed_bytes <= 0:
        return
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        return
    if free - needed_bytes < _DISK_HEADROOM_BYTES:
        raise HTTPException(
            status_code=507,
            detail=(
                "Not enough free disk space to stage this upload "
                f"({needed_bytes // (1024 * 1024)} MB requested, "
                f"{free // (1024 * 1024)} MB free)."
            ),
        )


def _cleanup_staged(paths: list[str]) -> None:
    """Remove partially-staged files so a rejected batch leaves nothing behind."""
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


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
    chunks: int = Query(256, ge=32, le=8192),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Queue files for async ingestion. RAG projects only."""
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

    # A queued file would be ingested by the cron into a store the re-embed is
    # about to reset, so the work would be silently discarded.
    reembed.raise_if_migrating(projectID, db_wrapper)

    max_bytes = config.max_upload_bytes()
    queue_dir = _ensure_queue_dir()
    queued_ids: list[int] = []

    # Validate every part BEFORE staging anything. Starlette records the byte
    # count on `UploadFile.size` while parsing (spooling parts over 1 MB to
    # disk), so this is free — and it makes "refuse the whole request" true:
    # previously the size check ran per file mid-loop, after earlier files had
    # already been written to the queue dir AND committed as job rows.
    for upload in files:
        if upload.size is not None and upload.size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=ERROR_MESSAGES.FILE_TOO_LARGE(f"{max_bytes // (1024 * 1024)} MB"),
            )

    _require_free_space(queue_dir, sum((u.size or 0) for u in files))

    staged_paths: list[str] = []
    for upload in files:
        safe_name = sanitize_filename(upload.filename or "upload.bin")

        fd, path = tempfile.mkstemp(prefix=f"proj{projectID}_", suffix=f"_{safe_name}", dir=queue_dir)
        try:
            await upload.seek(0)
            with os.fdopen(fd, "wb") as fh:
                # Stream in 64 KB blocks — never materialize the file in RAM.
                shutil.copyfileobj(upload.file, fh)
            staged_paths.append(path)
            size_bytes = os.path.getsize(path)
        except Exception:
            _cleanup_staged(staged_paths + [path])
            db_wrapper.db.rollback()
            raise

        job = BulkIngestJobDatabase(
            project_id=projectID,
            filename=safe_name,
            mime_type=upload.content_type,
            size_bytes=size_bytes,
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
    """Cancel or reap a bulk-ingest job."""
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

    if job.file_path:
        try:
            os.unlink(job.file_path)
        except OSError:
            pass

    db_wrapper.db.delete(job)
    db_wrapper.db.commit()
    return {"deleted": jobID}
