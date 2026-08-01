from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
)
from restai.auth import (
    get_current_username_project,
    check_not_restricted,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import (
    ProjectCommentCreate,
    ProjectCommentUpdate,
    User,
)

from restai.routers.projects._common import (
    router,
)

@router.get("/projects/{projectID}/comments", tags=["Comments"])
async def list_project_comments(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all comments for a project (newest first)."""
    from restai.models.databasemodels import ProjectCommentDatabase
    from restai.models.models import ProjectCommentResponse

    comments = (
        db_wrapper.db.query(ProjectCommentDatabase)
        .filter(ProjectCommentDatabase.project_id == projectID)
        .order_by(ProjectCommentDatabase.created_at.desc())
        .all()
    )
    return [
        ProjectCommentResponse(
            id=c.id,
            project_id=c.project_id,
            username=c.user.username if c.user else "unknown",
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in comments
    ]


@router.post("/projects/{projectID}/comments", status_code=201, tags=["Comments"])
async def create_project_comment(
    projectID: int = PathParam(description="Project ID"),
    body: ProjectCommentCreate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Add a comment to a project."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    comment = ProjectCommentDatabase(
        project_id=projectID,
        user_id=user.id,
        content=body.content,
        created_at=now,
        updated_at=now,
    )
    db_wrapper.db.add(comment)
    db_wrapper.db.commit()
    db_wrapper.db.refresh(comment)
    return {"id": comment.id, "message": "Comment added."}


@router.patch("/projects/{projectID}/comments/{commentID}", tags=["Comments"])
async def update_project_comment(
    projectID: int = PathParam(description="Project ID"),
    commentID: int = PathParam(description="Comment ID"),
    body: ProjectCommentUpdate = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Edit a comment (owner or admin only)."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase
    from datetime import datetime, timezone

    comment = db_wrapper.db.query(ProjectCommentDatabase).filter(
        ProjectCommentDatabase.id == commentID,
        ProjectCommentDatabase.project_id == projectID,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")

    comment.content = body.content
    comment.updated_at = datetime.now(timezone.utc)
    db_wrapper.db.commit()
    return {"message": "Comment updated."}


@router.delete("/projects/{projectID}/comments/{commentID}", tags=["Comments"])
async def delete_project_comment(
    projectID: int = PathParam(description="Project ID"),
    commentID: int = PathParam(description="Comment ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a comment (owner or admin only)."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectCommentDatabase

    comment = db_wrapper.db.query(ProjectCommentDatabase).filter(
        ProjectCommentDatabase.id == commentID,
        ProjectCommentDatabase.project_id == projectID,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Can only delete your own comments")

    db_wrapper.db.delete(comment)
    db_wrapper.db.commit()
    return {"message": "Comment deleted."}

