"""HTTP endpoints for the App-Builder planning chat history."""

from __future__ import annotations

from fastapi import (
    Depends,
    Path as PathParam,
    Request,
)

from restai.auth import (
    check_not_restricted,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User

from ._common import (
    router,
    _require_app_project,
    _app_chat_id,
    _serialize_app_messages,
)


@router.get("/projects/{projectID}/app/chat", tags=["App Builder"])
async def route_app_chat_history(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the project's persisted planning chat in chronological order."""
    _require_app_project(request, projectID, db_wrapper)
    from restai.agent2.memory import get_session
    session = await get_session(request.app.state.brain, _app_chat_id(projectID))
    return {"messages": _serialize_app_messages(session)}


@router.delete("/projects/{projectID}/app/chat", tags=["App Builder"])
async def route_app_chat_clear(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Wipe the planning chat; doesn't touch project files."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    from restai.agent2.memory import clear_session
    await clear_session(request.app.state.brain, _app_chat_id(projectID))
    try:
        from restai.audit import _log_to_db as _audit
        _audit(user.username, "APP_CHAT_CLEAR", f"projects/{projectID}", 200)
    except Exception:
        pass
    return {"cleared": True}
