"""Shared router, helpers, and imports for the App-Builder router package."""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import (
    APIRouter,
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
    get_project_root,
    list_tree,
    project_lock,
    read_file,
    write_file,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_app_project(
    request: Request, projectID: int, db_wrapper: DBWrapper
):
    """Resolve the project and assert it's `app` type."""
    project = request.app.state.brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.props.type != "app":
        raise HTTPException(
            status_code=400,
            detail="Endpoint only available for app-builder projects",
        )
    return project


def _record_ai_cost(
    request: Request,
    project,
    user,
    db_wrapper,
    *,
    question: str,
    answer: str,
    tokens: dict,
    status: str,
):
    """Log generation as inference row for budgets/quotas; check_budget is caller's job."""
    from restai.tools import log_inference
    output = {
        "question": question,
        "answer": answer,
        "tokens": tokens,
        "type": "app",
        "sources": [],
        "guard": False,
        "project": project.props.name,
        "status": status,
    }
    try:
        log_inference(project, user, output, db_wrapper, latency_ms=None)
    except Exception:
        logger.exception("log_inference failed for app AI on project %s", project.props.id)


def _sse_frame(event: str, data: dict) -> str:
    """Format a Server-Sent Events frame."""
    import json as _json
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _app_chat_id(project_id: int) -> str:
    """Project-scoped (not user-scoped) chat_id for the planning thread."""
    return f"app-plan-{int(project_id)}"


def _serialize_app_messages(session) -> list[dict]:
    """Flatten AgentSession to wire format; plan re-extracted from message text."""
    from restai.app.ai import extract_plan_from_reply
    out: list[dict] = []
    for m in session.messages:
        content = m.text_content() if hasattr(m, "text_content") else ""
        plan = None
        if (m.role or "") == "assistant" and content:
            try:
                plan = extract_plan_from_reply(content)
            except Exception:
                plan = None
        out.append({"role": m.role, "content": content, "plan": plan})
    return out
