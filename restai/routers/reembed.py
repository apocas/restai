"""Knowledge-base re-embedding for RAG projects.

Lets an admin move a project to a different embeddings model without losing
the knowledge base. The chunk text inside the vector store is the only
surviving copy — every ingest path deletes its source bytes — so the migration
re-embeds that rather than asking anyone to re-upload. See `restai/reembed.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Request

from restai import reembed
from restai.auth import check_not_restricted, get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.limits.budget import enforce_cost_budgets
from restai.models.databasemodels import ReembedJobDatabase
from restai.models.models import User
from restai.routers.projects._common import get_project


router = APIRouter()


def _job_to_dict(job: ReembedJobDatabase) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "from_embeddings": job.from_embeddings,
        "to_embeddings": job.to_embeddings,
        "status": job.status,
        "phase": job.phase,
        "error_message": job.error_message,
        "chunks_total": job.chunks_total,
        "chunks_done": job.chunks_done,
        "tokens_embedded": job.tokens_embedded,
        "cost": job.cost,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _require_rag(project_db):
    if project_db is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_db.type != "rag":
        raise HTTPException(
            status_code=400, detail="Re-embedding is only available for RAG projects."
        )


def _resolve_target(request: Request, project_db, embeddings_name: str, db_wrapper: DBWrapper):
    """Validate the target model exists and the project's team may use it.

    Mirrors the team-access check `route_edit_project` applies to the same
    field, so the two entry points cannot disagree about what is allowed."""
    target = request.app.state.brain.get_embedding(embeddings_name, db_wrapper)
    if target is None:
        raise HTTPException(
            status_code=404, detail=f"Embedding model '{embeddings_name}' not found"
        )

    team = db_wrapper.get_team_by_id(project_db.team_id)
    if team and target.model_name not in [e.name for e in team.embeddings]:
        raise HTTPException(
            status_code=403,
            detail=f"Team does not have access to embedding model '{embeddings_name}'",
        )
    return target


def enqueue_reembed(
    project_id: int, from_embeddings, to_embeddings: str, user_id, db_wrapper: DBWrapper,
) -> ReembedJobDatabase:
    """Create a queued job. Shared with the project-edit path, which enqueues
    automatically when the embeddings field changes.

    `from_embeddings` is passed in rather than read off the project row: the
    edit path has already written the new value by the time it enqueues, so
    reading the row there would record the migration as a no-op."""
    job = ReembedJobDatabase(
        project_id=project_id,
        user_id=user_id,
        from_embeddings=from_embeddings,
        to_embeddings=to_embeddings,
        status="queued",
        chunks_total=0,
        chunks_done=0,
        tokens_embedded=0,
        cost=0.0,
        created_at=datetime.now(timezone.utc),
    )
    db_wrapper.db.add(job)
    db_wrapper.db.commit()
    db_wrapper.db.refresh(job)
    return job


@router.post("/projects/{projectID}/reembed", status_code=202, tags=["Knowledge"])
async def enqueue(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    to_embeddings: str = Query(description="Name of the embedding model to migrate to"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Queue a knowledge-base migration to a different embeddings model."""
    check_not_restricted(user)

    project_db = db_wrapper.get_project_by_id(projectID)
    _require_rag(project_db)

    if reembed.is_migrating(projectID, db_wrapper):
        raise HTTPException(
            status_code=409, detail="A re-embed job is already in progress for this project."
        )

    target = _resolve_target(request, project_db, to_embeddings, db_wrapper)

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.vector is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vector store is unavailable, so its contents cannot be read back. "
                "Check that the vector database is running and retry."
            ),
        )

    estimate = reembed.estimate_reembed(project, target.props, db_wrapper)
    if not estimate["compatible"]:
        raise HTTPException(status_code=400, detail=estimate["reason"])
    if estimate["chunks"] == 0:
        raise HTTPException(
            status_code=400,
            detail="Knowledge base is empty — change the embeddings model directly instead.",
        )

    # Rejects a team that is already out of budget. It cannot answer "does
    # this specific amount fit", which is why the estimate is surfaced to the
    # caller separately.
    enforce_cost_budgets(
        db_wrapper, project=project, user=user, team=project.props.team,
    )

    job = enqueue_reembed(
        project_db.id, project_db.embeddings, to_embeddings, user.id, db_wrapper,
    )
    logging.info(
        "Queued re-embed job %s for project %s (%s -> %s, %s chunks)",
        job.id, projectID, project_db.embeddings, to_embeddings, estimate["chunks"],
    )
    return {"job": job.id, "estimate": estimate}


@router.get("/projects/{projectID}/reembed", tags=["Knowledge"])
async def list_jobs(
    projectID: int = PathParam(description="Project ID"),
    limit: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Re-embed history for a project, newest first. Polled by the UI."""
    jobs = (
        db_wrapper.db.query(ReembedJobDatabase)
        .filter(ReembedJobDatabase.project_id == projectID)
        .order_by(ReembedJobDatabase.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"jobs": [_job_to_dict(j) for j in jobs]}


@router.get("/projects/{projectID}/reembed/estimate", tags=["Knowledge"])
async def estimate(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    to: str = Query(description="Name of the embedding model to migrate to"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Chunk count, token estimate, cost and backend compatibility for a
    prospective migration — what the confirmation dialog shows."""
    project_db = db_wrapper.get_project_by_id(projectID)
    _require_rag(project_db)

    target = _resolve_target(request, project_db, to, db_wrapper)
    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.vector is None:
        raise HTTPException(status_code=503, detail="Vector store is unavailable.")

    return reembed.estimate_reembed(project, target.props, db_wrapper)


@router.delete("/projects/{projectID}/reembed/{jobID}", tags=["Knowledge"])
async def cancel(
    projectID: int = PathParam(description="Project ID"),
    jobID: int = PathParam(description="Re-embed job ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Cancel a queued job, or delete a finished row.

    A `processing` job cannot be cancelled: it may already have reset the
    store, and stopping mid-rebuild would leave the knowledge base partially
    populated — the exact failure this feature exists to prevent."""
    check_not_restricted(user)

    job = (
        db_wrapper.db.query(ReembedJobDatabase)
        .filter(
            ReembedJobDatabase.id == jobID,
            ReembedJobDatabase.project_id == projectID,
        )
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "processing":
        raise HTTPException(
            status_code=409,
            detail=(
                "Migration is already running and cannot be cancelled — stopping it "
                "would leave the knowledge base partially rebuilt."
            ),
        )

    db_wrapper.db.delete(job)
    db_wrapper.db.commit()
    return {"deleted": jobID}
