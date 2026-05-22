"""Project template library."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from sqlalchemy.orm import Session

from restai.auth import (
    check_not_restricted,
    get_current_username,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import (
    ProjectDatabase,
    ProjectTemplateDatabase,
    TeamDatabase,
    UserDatabase,
)
from restai.models.models import (
    ProjectTemplateInstantiate,
    ProjectTemplatePublish,
    ProjectTemplateResponse,
    ProjectTemplateUpdate,
    User,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def _to_response(t: ProjectTemplateDatabase) -> ProjectTemplateResponse:
    """Adapt DB row to wire shape with creator_username + team_name."""
    return ProjectTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        project_type=t.project_type,
        suggested_llm=t.suggested_llm,
        suggested_embeddings=t.suggested_embeddings,
        visibility=t.visibility,
        creator_username=t.creator.username if t.creator else None,
        team_id=t.team_id,
        team_name=t.team.name if t.team else None,
        created_at=t.created_at,
        use_count=t.use_count or 0,
    )


def _user_team_ids(user: User) -> set[int]:
    return {t.id for t in (user.teams or [])} | {t.id for t in (user.admin_teams or [])}


def _can_see(t: ProjectTemplateDatabase, user: User) -> bool:
    if user.is_admin:
        return True
    if t.visibility == "public":
        return True
    if t.creator_id == user.id:
        return True
    if t.visibility == "team" and t.team_id and t.team_id in _user_team_ids(user):
        return True
    return False


def _can_edit(t: ProjectTemplateDatabase, user: User) -> bool:
    return user.is_admin or t.creator_id == user.id


@router.post(
    "/projects/{projectID}/publish-template",
    response_model=ProjectTemplateResponse,
    status_code=201,
    tags=["Templates"],
)
async def publish_template(
    body: ProjectTemplatePublish,
    projectID: int = PathParam(description="Source project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Snapshot the project's current state into a new template row."""
    check_not_restricted(user)

    src = db_wrapper.get_project_by_id(projectID)
    if src is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.visibility == "team" and not src.team_id:
        raise HTTPException(status_code=400, detail="Cannot publish team-visibility template — source project has no team")

    # Scrub credentials — templates are config blueprints; without this, publisher's
    # WhatsApp/SMTP/Twilio/webhook secrets transplant onto every instantiator's project.
    from restai.utils.crypto import strip_sensitive_project_options
    scrubbed_options = strip_sensitive_project_options(src.options)

    template = ProjectTemplateDatabase(
        name=body.name,
        description=body.description,
        project_type=src.type,
        suggested_llm=src.llm,
        suggested_embeddings=src.embeddings,
        system_prompt=src.system,
        options_json=scrubbed_options,
        blockly_workspace=None,
        visibility=body.visibility,
        creator_id=user.id,
        team_id=src.team_id if body.visibility == "team" else None,
        created_at=datetime.now(timezone.utc),
        use_count=0,
    )
    db_wrapper.db.add(template)
    db_wrapper.db.commit()
    db_wrapper.db.refresh(template)
    return _to_response(template)


@router.get("/templates", response_model=list[ProjectTemplateResponse], tags=["Templates"])
async def list_templates(
    project_type: str = Query(default=None, description="Filter by project_type (rag/agent/block)"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return templates visible to the user, newest first."""
    query = db_wrapper.db.query(ProjectTemplateDatabase)
    if project_type:
        query = query.filter(ProjectTemplateDatabase.project_type == project_type)
    rows = query.order_by(ProjectTemplateDatabase.created_at.desc()).all()
    visible = [t for t in rows if _can_see(t, user)]
    return [_to_response(t) for t in visible]


@router.get("/templates/{templateID}", response_model=ProjectTemplateResponse, tags=["Templates"])
async def get_template(
    templateID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    t = db_wrapper.db.query(ProjectTemplateDatabase).filter(ProjectTemplateDatabase.id == templateID).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_see(t, user):
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_response(t)


@router.patch("/templates/{templateID}", response_model=ProjectTemplateResponse, tags=["Templates"])
async def update_template(
    body: ProjectTemplateUpdate,
    templateID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    t = db_wrapper.db.query(ProjectTemplateDatabase).filter(ProjectTemplateDatabase.id == templateID).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_edit(t, user):
        raise HTTPException(status_code=403, detail="Only the template owner can edit it")

    if body.name is not None:
        t.name = body.name
    if body.description is not None:
        t.description = body.description
    if body.visibility is not None:
        if body.visibility == "team" and not t.team_id:
            raise HTTPException(status_code=400, detail="Template has no team_id — cannot switch to team visibility")
        t.visibility = body.visibility
    db_wrapper.db.commit()
    db_wrapper.db.refresh(t)
    return _to_response(t)


@router.delete("/templates/{templateID}", tags=["Templates"])
async def delete_template(
    templateID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    t = db_wrapper.db.query(ProjectTemplateDatabase).filter(ProjectTemplateDatabase.id == templateID).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_edit(t, user):
        raise HTTPException(status_code=403, detail="Only the template owner can delete it")
    db_wrapper.db.delete(t)
    db_wrapper.db.commit()
    return {"deleted": templateID}


@router.post(
    "/templates/{templateID}/instantiate",
    status_code=201,
    tags=["Templates"],
)
async def instantiate_template(
    body: ProjectTemplateInstantiate,
    templateID: int,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new project from the template; caller picks target team + LLM + embeddings."""
    check_not_restricted(user)
    t = db_wrapper.db.query(ProjectTemplateDatabase).filter(ProjectTemplateDatabase.id == templateID).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _can_see(t, user):
        raise HTTPException(status_code=404, detail="Template not found")

    if not user.is_admin and body.team_id not in _user_team_ids(user):
        raise HTTPException(status_code=403, detail="You are not a member of the target team")

    if db_wrapper.get_project_by_name(body.name):
        raise HTTPException(status_code=409, detail="A project with this name already exists")

    llm = body.llm or t.suggested_llm
    embeddings = body.embeddings or t.suggested_embeddings

    new_project = db_wrapper.create_project(
        name=body.name,
        embeddings=embeddings or "",
        llm=llm or "",
        vectorstore="chromadb",
        human_name=t.name,
        human_description=t.description,
        project_type=t.project_type,
        creator=user.id,
        team_id=body.team_id,
    )
    if new_project is None:
        raise HTTPException(
            status_code=400,
            detail="Failed to create project from template — check that the team has access to the chosen LLM/embeddings",
        )

    new_project.system = t.system_prompt
    if t.options_json:
        # Belt-and-suspenders: scrub on read so legacy template rows can't leak secrets.
        from restai.utils.crypto import strip_sensitive_project_options
        new_project.options = strip_sensitive_project_options(t.options_json)
    db_wrapper.db.commit()

    t.use_count = (t.use_count or 0) + 1
    db_wrapper.db.commit()

    return {"id": new_project.id, "name": new_project.name}
