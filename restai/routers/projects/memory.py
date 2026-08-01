import json
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
    User,
)

from restai.routers.projects._common import (
    router,
)

@router.get("/projects/{projectID}/memory-bank", tags=["Memory Bank"])
async def list_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Visualizer payload: entries grouped by granularity + aggregate stats."""
    from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    options = json.loads(project.options) if project.options else {}
    enabled = bool(options.get("memory_bank_enabled"))
    max_tokens = int(options.get("memory_bank_max_tokens") or 2000)

    rows = (
        db_wrapper.db.query(ProjectMemoryBankEntryDatabase)
        .filter(ProjectMemoryBankEntryDatabase.project_id == projectID)
        .all()
    )

    def _row(r):
        return {
            "id": r.id,
            "chat_id": r.chat_id,
            "granularity": r.granularity,
            "period_key": r.period_key,
            "summary": r.summary or "",
            "token_count": r.token_count or 0,
            "source_message_count": r.source_message_count or 0,
            "last_source_at": r.last_source_at.isoformat() if r.last_source_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    entries = [_row(r) for r in rows]
    entries.sort(
        key=lambda e: e["last_source_at"] or e["updated_at"] or e["created_at"] or "",
        reverse=True,
    )
    counts = {"conversation": 0, "day": 0, "week": 0, "month": 0}
    for r in rows:
        counts[r.granularity] = counts.get(r.granularity, 0) + 1
    total_tokens = sum((r.token_count or 0) for r in rows)

    return {
        "enabled": enabled,
        "max_tokens": max_tokens,
        "total_tokens": total_tokens,
        "entry_count": len(rows),
        "counts_by_granularity": counts,
        "entries": entries,
    }


@router.get("/projects/{projectID}/memory-bank/preview", tags=["Memory Bank"])
async def preview_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the exact text block prepended to the system prompt this turn."""
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    options = json.loads(project.options) if project.options else {}
    max_tokens = int(options.get("memory_bank_max_tokens") or 2000)
    from restai.memory import bank as memory_bank
    block = memory_bank.render_for_prompt(db_wrapper, projectID, max_tokens)
    from restai.tools import tokens_from_string
    return {
        "block": block,
        "tokens": tokens_from_string(block) if block else 0,
        "max_tokens": max_tokens,
    }


@router.post("/projects/{projectID}/memory-search", tags=["Memory Search"])
async def memory_search_query(
    request: Request,
    body: dict,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Run the agent's `search_memories` tool and return its raw text result."""
    project = db_wrapper.get_project_by_id(projectID)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    try:
        k = int(body.get("k") or 5)
    except Exception:
        k = 5

    from restai.llms.tools.search_memories import search_memories
    brain = request.app.state.brain
    result = search_memories(
        query=query,
        k=k,
        _brain=brain,
        _project_id=projectID,
    )
    return {"result": result}


@router.post("/projects/{projectID}/memory-bank/clear", tags=["Memory Bank"])
async def clear_memory_bank(
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Wipe every entry for this project. Cron will re-summarize new
    conversations from `OutputDatabase` on the next tick."""
    check_not_restricted(user)
    from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
    deleted = (
        db_wrapper.db.query(ProjectMemoryBankEntryDatabase)
        .filter(ProjectMemoryBankEntryDatabase.project_id == projectID)
        .delete(synchronize_session=False)
    )
    db_wrapper.db.commit()
    return {"deleted": int(deleted or 0)}

