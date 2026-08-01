from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
    Request,
)
from restai.auth import (
    get_current_username_project,
    check_not_restricted,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import (
    ProjectModelUpdate,
    User,
)

from restai.routers.projects._common import (
    router,
)

@router.get("/projects/{projectID}/prompts", tags=["Projects"])
async def list_prompt_versions(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all prompt versions for a project."""
    from restai.models.models import PromptVersionResponse
    versions = db_wrapper.get_prompt_versions(projectID)
    return [PromptVersionResponse.model_validate(v) for v in versions]


@router.get("/projects/{projectID}/prompts/{versionID}", tags=["Projects"])
async def get_prompt_version(
    projectID: int = PathParam(description="Project ID"),
    versionID: int = PathParam(description="Prompt version ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get a specific prompt version."""
    from restai.models.models import PromptVersionResponse
    version = db_wrapper.get_prompt_version(versionID)
    if version is None or version.project_id != projectID:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return PromptVersionResponse.model_validate(version)


@router.post("/projects/{projectID}/prompts/{versionID}/activate", tags=["Projects"])
async def activate_prompt_version(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    versionID: int = PathParam(description="Prompt version ID to activate"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Restore a previous prompt version as the active system prompt."""
    check_not_restricted(user)
    version = db_wrapper.get_prompt_version(versionID)
    if version is None or version.project_id != projectID:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    project = db_wrapper.get_project_by_id(projectID)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    update = ProjectModelUpdate(system=version.system_prompt)
    update._user_id = user.id
    db_wrapper.edit_project(projectID, update)

    return {"project": projectID, "activated_version": version.version}

