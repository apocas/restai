"""Project secrets CRUD — the credential vault the Agentic Browser uses.

Values are encrypted at rest and always masked (`"********"`) in API
responses. The `PATCH` handler preserves the existing value when it sees
that sentinel — same round-trip pattern LLMs and image generators use.

Every endpoint requires project membership + non-restricted + admin-ish
(team admin / platform admin) per `check_not_restricted` and the
existing project-access dependency.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path

from restai.auth import check_not_restricted, get_current_username_project
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import ProjectSecretDatabase
from restai.models.models import (
    ProjectSecretCreate,
    ProjectSecretModel,
    ProjectSecretUpdate,
    User,
)

router = APIRouter()


def _mask(row: ProjectSecretDatabase) -> dict:
    """Shape a DB row as the API response — value always masked."""
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "value": "********",
        "description": row.description,
    }


@router.get("/projects/{projectID}/secrets", response_model=list[ProjectSecretModel])
async def list_project_secrets(
    projectID: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    rows = db_wrapper.get_project_secrets(projectID)
    return [_mask(r) for r in rows]


@router.post("/projects/{projectID}/secrets", status_code=201, response_model=ProjectSecretModel)
async def create_project_secret(
    body: ProjectSecretCreate,
    projectID: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    check_not_restricted(user)
    existing = db_wrapper.get_project_secret_by_name(projectID, body.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Secret '{body.name}' already exists on this project")
    row = db_wrapper.create_project_secret(
        project_id=projectID,
        name=body.name,
        value=body.value,
        description=body.description,
    )
    return _mask(row)


@router.patch("/projects/{projectID}/secrets/{secretID}", response_model=ProjectSecretModel)
async def update_project_secret(
    body: ProjectSecretUpdate,
    projectID: int = Path(description="Project ID"),
    secretID: int = Path(description="Secret ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    check_not_restricted(user)
    row: Optional[ProjectSecretDatabase] = db_wrapper.get_project_secret_by_id(secretID)
    if row is None or row.project_id != projectID:
        raise HTTPException(status_code=404, detail="Secret not found")
    db_wrapper.edit_project_secret(row, body)
    return _mask(row)


@router.delete("/projects/{projectID}/secrets/{secretID}", status_code=204)
async def delete_project_secret(
    projectID: int = Path(description="Project ID"),
    secretID: int = Path(description="Secret ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    check_not_restricted(user)
    row: Optional[ProjectSecretDatabase] = db_wrapper.get_project_secret_by_id(secretID)
    if row is None or row.project_id != projectID:
        raise HTTPException(status_code=404, detail="Secret not found")
    db_wrapper.delete_project_secret(row)
