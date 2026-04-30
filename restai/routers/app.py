"""HTTP endpoints for the App-Builder file IDE.

All endpoints live under ``/projects/{projectID}/app/...`` and require the
caller to be a member of the project's team. Path arguments are validated
through :mod:`restai.app.storage`'s traversal guard.
"""

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
    """Resolve the project and assert it is an `app` type project."""
    project = request.app.state.brain.find_project(projectID, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.props.type != "app":
        raise HTTPException(
            status_code=400,
            detail="Endpoint only available for app-builder projects",
        )
    return project


class FilePayload(BaseModel):
    """Payload for PUT /app/files. Body carries the file contents as a UTF-8
    string. Binary writes via this endpoint are intentionally not supported —
    deploy assets via the FTP/SFTP path instead."""

    content: str = Field(description="Full file content (UTF-8 text)")


@router.get("/projects/{projectID}/app/tree", tags=["App Builder"])
async def route_app_tree(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the app project's file tree (recursive, dirs first then files)."""
    _require_app_project(request, projectID, db_wrapper)
    return {"tree": list_tree(projectID)}


@router.get("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_get_file(
    request: Request,
    response: Response,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return file contents + ETag.

    The ETag is content-addressed (sha256/12). Pass it back as `If-Match` on
    PUT so a stale tab can't silently overwrite a fresher edit.
    """
    _require_app_project(request, projectID, db_wrapper)
    data, etag = read_file(projectID, path)
    response.headers["ETag"] = etag
    # UTF-8 decode; fail explicit on binary so the IDE never silently corrupts
    # a binary file by treating it as text.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="binary file not editable")
    return {"path": path, "content": text, "etag": etag, "size": len(data)}


@router.put("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_put_file(
    request: Request,
    response: Response,
    payload: FilePayload,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Write file contents. Requires `If-Match` header when the file already
    exists; first-write of a new file is unconditional."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    if_match = request.headers.get("if-match") or request.headers.get("If-Match")
    data = payload.content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds size cap")
    async with project_lock(projectID):
        new_etag = write_file(projectID, path, data, if_match=if_match)
    response.headers["ETag"] = new_etag
    return {"path": path, "etag": new_etag, "size": len(data)}


@router.delete("/projects/{projectID}/app/files", tags=["App Builder"])
async def route_app_delete_file(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    path: str = Query(description="Project-relative file path"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a single file inside the project tree. Directories are not
    removed by this endpoint — the IDE doesn't support it yet, and shelling
    out to recursive removal from the API is the kind of thing we'd rather
    not invite a future bug into."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    from restai.app.storage import resolve_path
    target = resolve_path(projectID, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="cannot delete directory")
    async with project_lock(projectID):
        target.unlink()
    return {"path": path, "deleted": True}


# ──────────────────────────────────────────────────────────────────────
# SQLite DB editor.
#
# All endpoints operate on `<install_root>/apps/<id>/database.sqlite` via
# stdlib `sqlite3`. We never `docker exec sqlite3` — Docker isn't required
# for the DB editor to work (the file is on host disk), and shelling out
# is more attack surface for no benefit.
#
# Safety:
# - Table names are NOT user-validated text; they MUST appear in
#   `sqlite_master`. The list endpoint reads sqlite_master and the row
#   endpoints re-check on every call.
# - Column names are read from `PRAGMA table_info(<table>)` and re-checked
#   against the request payload. Anything outside the allowlist is rejected.
# - Values are always bound; the only string interpolation that touches SQL
#   is the table/column name, which has been validated against the actual
#   schema two lines up.
# - Reserved tables (`sqlite_*`, internal) are filtered.
# ──────────────────────────────────────────────────────────────────────


# SQLite's own table-name rule is permissive (almost anything in quotes),
# but exposing weird names through a JSON API invites bugs. Stick to a
# conservative identifier shape — generated apps stick to it anyway.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RowUpsertPayload(BaseModel):
    """Body for POST/PUT /app/db/rows.

    `rowid` is required on PUT (which row to update) and forbidden on POST
    (insert). `values` is a column->value dict; columns missing from the
    payload are left unchanged on PUT, and SQLite supplies the default on
    POST. Values are JSON-native — we don't try to type-coerce, the caller
    sends what they want bound."""

    table: str = Field(description="Table name")
    values: dict = Field(default_factory=dict, description="Column → value")
    rowid: int | None = Field(default=None, description="rowid of the row to update; required on PUT")


class RowDeletePayload(BaseModel):
    table: str
    rowid: int


def _db_path(project_id: int) -> str:
    """Resolve the project's SQLite file path. The file may not exist on
    every project (the seed creates it but a user could delete it from the
    file editor). Endpoints surface that as 404."""
    root = get_project_root(int(project_id))
    return str((root / "database.sqlite").resolve())


def _check_identifier(name: str, kind: str) -> None:
    if not name or not _IDENTIFIER_RE.match(name):
        raise HTTPException(status_code=400, detail=f"invalid {kind}")


def _open_db(project_id: int) -> sqlite3.Connection:
    import os
    path = _db_path(project_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="database.sqlite not found")
    # `isolation_level=None` so we control transactions; not strictly needed
    # but keeps row updates from getting wrapped in a long-lived implicit
    # transaction that conflicts with the PHP container.
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    """PRAGMA table_info(<table>) — returns [{name, type, notnull, pk, dflt_value}]."""
    # PRAGMA can't be parameterised by table name, but we already validated
    # the identifier shape and we'll cross-check against the master list.
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    cols = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    return cols


def _resolve_table(conn: sqlite3.Connection, table: str) -> str:
    """Validate the table name shape AND existence. Returns the canonical
    name (same as input — but ensures it really exists)."""
    _check_identifier(table, "table")
    if table not in _list_tables(conn):
        raise HTTPException(status_code=404, detail="table not found")
    return table


def _resolve_columns(conn: sqlite3.Connection, table: str, requested: list[str]) -> list[str]:
    cols_info = _table_columns(conn, table)
    if not cols_info:
        raise HTTPException(status_code=404, detail="table has no columns")
    valid = {c["name"] for c in cols_info}
    out: list[str] = []
    for name in requested:
        _check_identifier(name, "column")
        if name not in valid:
            raise HTTPException(status_code=400, detail=f"unknown column: {name}")
        out.append(name)
    return out


@router.get("/projects/{projectID}/app/db/tables", tags=["App Builder"])
async def route_app_db_tables(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List user tables in the app's SQLite database, with row counts and
    column metadata."""
    _require_app_project(request, projectID, db_wrapper)
    try:
        conn = _open_db(projectID)
    except HTTPException:
        raise
    try:
        tables: list[dict] = []
        for name in _list_tables(conn):
            cols = _table_columns(conn, name)
            try:
                count_row = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
                count = int(count_row[0])
            except sqlite3.Error:
                count = -1  # signals "could not count"
            tables.append({
                "name": name,
                "row_count": count,
                "columns": [
                    {"name": c["name"], "type": c["type"], "pk": bool(c["pk"]), "notnull": bool(c["notnull"])}
                    for c in cols
                ],
            })
        return {"tables": tables}
    finally:
        conn.close()


@router.get("/projects/{projectID}/app/db/rows", tags=["App Builder"])
async def route_app_db_rows(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    table: str = Query(description="Table name"),
    offset: int = Query(0, ge=0, le=10_000_000),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Paginated SELECT * from <table>. Returns rows keyed by their internal
    `rowid` so the caller can update / delete them without needing to know
    the table's primary key."""
    _require_app_project(request, projectID, db_wrapper)
    conn = _open_db(projectID)
    try:
        canonical = _resolve_table(conn, table)
        cols_info = _table_columns(conn, canonical)
        col_names = [c["name"] for c in cols_info]
        total_row = conn.execute(f'SELECT COUNT(*) FROM "{canonical}"').fetchone()
        total = int(total_row[0]) if total_row else 0
        # Explicit alias: in tables with `INTEGER PRIMARY KEY`, sqlite folds
        # `rowid` into the PK column, leaving `r["rowid"]` undefined. The
        # alias guarantees the key is always there.
        cur = conn.execute(
            f'SELECT rowid AS __restai_rowid__, * FROM "{canonical}" LIMIT ? OFFSET ?',
            (int(limit), int(offset)),
        )
        rows = []
        for r in cur.fetchall():
            d = {"rowid": r["__restai_rowid__"]}
            for name in col_names:
                d[name] = r[name]
            rows.append(d)
        return {
            "table": canonical,
            "columns": [{"name": c["name"], "type": c["type"], "pk": bool(c["pk"]), "notnull": bool(c["notnull"])} for c in cols_info],
            "rows": rows,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    finally:
        conn.close()


@router.put("/projects/{projectID}/app/db/rows", tags=["App Builder"])
async def route_app_db_update_row(
    request: Request,
    payload: RowUpsertPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update a row identified by ``rowid``. Columns missing from
    ``values`` are left unchanged."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    if payload.rowid is None:
        raise HTTPException(status_code=400, detail="rowid is required for update")
    if not payload.values:
        raise HTTPException(status_code=400, detail="values cannot be empty")

    conn = _open_db(projectID)
    try:
        canonical = _resolve_table(conn, payload.table)
        cols = _resolve_columns(conn, canonical, list(payload.values.keys()))
        assignments = ", ".join(f'"{c}" = ?' for c in cols)
        params = [payload.values[c] for c in cols] + [int(payload.rowid)]
        try:
            conn.execute(
                f'UPDATE "{canonical}" SET {assignments} WHERE rowid = ?',
                params,
            )
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=f"sqlite error: {e}")
        return {"updated": payload.rowid}
    finally:
        conn.close()


@router.post("/projects/{projectID}/app/db/rows", tags=["App Builder"])
async def route_app_db_insert_row(
    request: Request,
    payload: RowUpsertPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Insert a new row. ``rowid`` must be omitted — SQLite assigns it."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    if payload.rowid is not None:
        raise HTTPException(status_code=400, detail="rowid must be omitted on insert")

    conn = _open_db(projectID)
    try:
        canonical = _resolve_table(conn, payload.table)
        if payload.values:
            cols = _resolve_columns(conn, canonical, list(payload.values.keys()))
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(f'"{c}"' for c in cols)
            params = [payload.values[c] for c in cols]
            sql = f'INSERT INTO "{canonical}" ({col_list}) VALUES ({placeholders})'
        else:
            # All-defaults insert.
            sql = f'INSERT INTO "{canonical}" DEFAULT VALUES'
            params = []
        try:
            cur = conn.execute(sql, params)
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=f"sqlite error: {e}")
        return {"rowid": cur.lastrowid}
    finally:
        conn.close()


@router.delete("/projects/{projectID}/app/db/rows", tags=["App Builder"])
async def route_app_db_delete_row(
    request: Request,
    payload: RowDeletePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a row by rowid."""
    check_not_restricted(user)
    _require_app_project(request, projectID, db_wrapper)
    conn = _open_db(projectID)
    try:
        canonical = _resolve_table(conn, payload.table)
        try:
            conn.execute(f'DELETE FROM "{canonical}" WHERE rowid = ?', (int(payload.rowid),))
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=f"sqlite error: {e}")
        return {"deleted": payload.rowid}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# AI generation: full app scaffold + per-file targeted edit.
#
# Both run on the project's own LLM (selected at project create time),
# NOT the platform System LLM. Token cost flows through the regular
# log_inference pipeline so per-project budgets and per-key quotas
# apply naturally.
#
# `check_budget` and `check_rate_limit` are called up-front so a project
# that's hit its monthly cap can't burn LLM cycles via this path either.
# ──────────────────────────────────────────────────────────────────────


class FixFilePayload(BaseModel):
    path: str = Field(description="Project-relative file path")
    instruction: str = Field(min_length=2, max_length=4000, description="What you want changed in this file")


class PlanPayload(BaseModel):
    """Body for POST /app/generate/plan.

    Server-stateful chat: the project's planning thread lives in the
    `app_chat_messages` table and the wizard hydrates it on open. Each
    plan call sends ONE new user message; the server appends it, builds
    the full prompt from the persisted history, runs the LLM, then
    appends the assistant reply (with parsed plan if any).
    """
    message: str = Field(min_length=1, max_length=20000, description="The new user message to add to the chat thread")


class ExecutePayload(BaseModel):
    """Body for POST /app/generate/execute — the approved plan + an
    overwrite flag. Files are checked-and-written one at a time; if a
    file exists and overwrite=false, that file is skipped (the rest of
    the plan still runs)."""
    plan: dict = Field(description="The full approved plan dict from /generate/plan")
    overwrite: bool = Field(default=False, description="If false, skip files that already exist on disk")


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
    """Log the generation as an inference row so per-project budgets +
    per-key monthly quotas tick. We deliberately do NOT call check_budget
    here — the caller does that up-front (so an exhausted project gets a
    clean 402 instead of burning the LLM cycles before the failure)."""
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
        # Don't fail the user's generate just because logging hiccupped.
        logger.exception("log_inference failed for app AI on project %s", project.props.id)


def _sse_frame(event: str, data: dict) -> str:
    """Format a Server-Sent Events frame. Mirrors the framing in
    `route_app_deploy` exactly so the frontend has one parser to maintain."""
    import json as _json
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _app_chat_id(project_id: int) -> str:
    """The agent2.memory chat_id for this project's planning thread.

    Project-scoped (not user-scoped): every team member working on the
    same app project sees the same conversation, exactly like other
    project-level features. Backend is Redis when configured, with an
    in-process LRU fallback — same store the agent project type uses
    for chat sessions, no new infrastructure.
    """
    return f"app-plan-{int(project_id)}"


def _serialize_app_messages(session) -> list[dict]:
    """Flatten an AgentSession into the wire format the wizard expects.

    Each assistant message's text is the FULL reply including the
    fenced JSON tail; we re-extract the structured plan on read with
    `extract_plan_from_reply` so we never need a separate column for
    it (the source of truth is always the message text).
    """
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


@router.get("/projects/{projectID}/app/chat", tags=["App Builder"])
async def route_app_chat_history(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the project's persisted planning chat in chronological order.

    Backed by agent2.memory (Redis when configured, in-process fallback)
    — the same session store agent and block projects use. The wizard
    hydrates from this on open so the user lands back in the conversation."""
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
    """Wipe the project's planning chat. Used by the wizard's Reset
    button. Doesn't touch the project files — only the conversation."""
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


@router.post("/projects/{projectID}/app/generate/plan", tags=["App Builder"])
async def route_app_generate_plan(
    request: Request,
    payload: PlanPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Chat-style planning. Streams the LLM's reply as `plan_chunk` SSE
    events, terminates with `plan_complete` (which carries the parsed plan
    dict, or null if the AI replied with a clarifying question)."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    from fastapi.responses import StreamingResponse
    from restai.app.ai import stream_plan
    from restai.agent2.memory import get_session, save_session
    from restai.agent2.types import Message, TextBlock, user_text_message

    # Load the persisted thread from agent2.memory (Redis when configured,
    # in-process LRU fallback). Same store agent/block projects use — no
    # new infrastructure for the App Builder.
    chat_id = _app_chat_id(projectID)
    session = await get_session(request.app.state.brain, chat_id)

    # Append the new user message and PERSIST IMMEDIATELY. If the LLM call
    # fails or the client disconnects mid-stream, we still want the
    # question on record so the user can refine without retyping.
    session.messages.append(user_text_message(payload.message))
    await save_session(request.app.state.brain, chat_id, session)

    # Soft cap: only the last 40 messages flow into the prompt to keep the
    # context window in check. The full thread stays in memory for replay.
    sliced = session.messages[-40:]
    messages = [
        {"role": m.role, "content": m.text_content() if hasattr(m, "text_content") else ""}
        for m in sliced
    ]
    last_user_msg = payload.message

    async def stream():
        # We run the LLM stream in a worker thread because LlamaIndex
        # `stream_complete` is sync. Pulling deltas off a queue keeps the
        # SSE generator async-friendly.
        import asyncio as _asyncio
        import threading as _threading
        import queue as _queue

        events: _queue.Queue = _queue.Queue()

        def producer():
            try:
                for evt_name, evt_data in stream_plan(
                    request.app.state.brain, db_wrapper, project.props.llm, messages,
                    project_id=projectID,
                ):
                    events.put((evt_name, evt_data))
            except ValueError as e:
                events.put(("error", {"message": str(e)}))
            except Exception as e:
                logger.exception("plan stream crashed")
                events.put(("error", {"message": str(e)}))
            finally:
                events.put(("__end__", None))

        thread = _threading.Thread(target=producer, daemon=True)
        thread.start()

        final_tokens = {"input": 0, "output": 0}
        final_reply = ""
        final_plan = None
        had_plan = False
        try:
            while True:
                # Yield control while waiting on the queue, and bail if
                # the client disconnected.
                try:
                    evt = await _asyncio.get_event_loop().run_in_executor(
                        None, events.get, True, 0.5,
                    )
                except _queue.Empty:
                    if await request.is_disconnected():
                        return
                    continue
                if evt is None:
                    continue
                name, data = evt
                if name == "__end__":
                    break
                if name == "plan_complete":
                    final_tokens = data.get("tokens", final_tokens)
                    final_reply = data.get("reply", "") or ""
                    final_plan = data.get("plan")
                    had_plan = final_plan is not None
                yield _sse_frame(name, data or {})
        finally:
            # Persist the assistant reply (the FULL text including the
            # fenced JSON tail). The plan dict is re-extracted on read by
            # `extract_plan_from_reply` — single source of truth.
            try:
                if final_reply:
                    session.messages.append(
                        Message(role="assistant", content=[TextBlock(text=final_reply)])
                    )
                    await save_session(request.app.state.brain, chat_id, session)
            except Exception:
                logger.exception("failed to persist assistant chat turn")
            try:
                _record_ai_cost(
                    request, project, user, db_wrapper,
                    question=f"plan: {last_user_msg[:200]}",
                    answer=f"plan_replied={'yes' if had_plan else 'clarify'}",
                    tokens=final_tokens, status="success",
                )
            except Exception:
                pass
            try:
                from restai.audit import _log_to_db as _audit
                _audit(
                    user.username, "APP_PLAN",
                    f"projects/{projectID}:turns={len(messages)}", 200,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/projects/{projectID}/app/generate/dry-run", tags=["App Builder"])
async def route_app_generate_dry_run(
    request: Request,
    payload: ExecutePayload,  # same shape as execute — accepts {plan, overwrite}
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Diff preview: show what files will change WITHOUT calling the LLM
    or writing anything. Used by the wizard's "Preview changes" expander
    so the user can confirm the plan targets the right files before
    burning tokens on Approve & Build."""
    _require_app_project(request, projectID, db_wrapper)

    # Validate the plan shape (same defense in depth as execute does).
    from restai.app.ai import validate_plan
    try:
        clean_plan = validate_plan(payload.plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {e}")

    import asyncio as _asyncio
    from collections import Counter
    from restai.app.storage import get_project_root
    root = get_project_root(projectID)

    out_files = await _asyncio.get_event_loop().run_in_executor(
        None, _build_dry_run_diff, root, clean_plan,
    )
    counts = Counter(f["change_kind"] for f in out_files)
    return {"files": out_files, "counts": dict(counts)}


def _build_dry_run_diff(root, clean_plan: dict) -> list[dict]:
    """Sync helper for the dry-run endpoint — dispatched via executor
    because each `read_bytes()` is blocking I/O."""
    out: list[dict] = []
    root_resolved = root.resolve()
    for ph_idx, phase in enumerate(clean_plan.get("phases", []), 1):
        for file_spec in phase.get("files", []):
            path = file_spec["path"]
            target = root / path
            # Defense-in-depth against symlink escapes: validate_plan
            # already rejected `..` paths upstream, but a symlink inside
            # the project root could still point outside.
            try:
                if not target.resolve().is_relative_to(root_resolved):
                    continue
            except OSError:
                continue
            current_content = None
            size_bytes = 0
            change_kind = "new"
            if target.is_file():
                try:
                    raw = target.read_bytes()
                    size_bytes = len(raw)
                    if size_bytes > _DRY_RUN_PREVIEW_BYTES:
                        current_content = (
                            raw[:_DRY_RUN_PREVIEW_BYTES].decode("utf-8", errors="replace")
                            + "\n/* [truncated for preview] */"
                        )
                    else:
                        current_content = raw.decode("utf-8", errors="replace")
                except OSError:
                    current_content = None
                change_kind = "overwrite"
            out.append({
                "path": path,
                "purpose": file_spec.get("purpose", ""),
                "current_content": current_content,
                "change_kind": change_kind,
                "size_bytes": size_bytes,
                "phase": phase.get("name") or f"Phase {ph_idx}",
                "phase_index": ph_idx,
            })
    return out


@router.post("/projects/{projectID}/app/generate/execute", tags=["App Builder"])
async def route_app_generate_execute(
    request: Request,
    payload: ExecutePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Build the approved plan, file by file. Streams per-file progress.
    Per-file overwrite check: if `payload.overwrite` is false, files that
    already exist on disk are skipped (emit `file_error`) and the rest of
    the plan continues. Cancellable between files via client disconnect."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    from fastapi.responses import StreamingResponse
    from restai.app.ai import (
        validate_plan, stream_file_content,
    )
    from restai.app.storage import (
        ensure_project_root, project_lock, write_file, get_project_root,
    )

    # Defense in depth — the client could have edited the plan.
    try:
        clean_plan = validate_plan(payload.plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {e}")

    ensure_project_root(projectID)
    root = get_project_root(projectID)
    phases = clean_plan["phases"]
    overwrite = bool(payload.overwrite)

    async def stream():
        import asyncio as _asyncio
        import threading as _threading
        import queue as _queue
        from restai.app.ai import generate_contracts

        written: list[str] = []
        failed: list[dict] = []
        # Total file count across all phases for global progress display.
        total_files = sum(len(ph.get("files", [])) for ph in phases)
        total_tokens = {"input": 0, "output": 0}
        global_idx = 0  # 1-indexed across all phases
        contracts_text = ""  # populated by the sketch-then-fill pass below

        try:
            # ── Sketch-then-fill: generate shared contracts BEFORE any
            # code. The contracts (TS interfaces, function signatures,
            # SQL schemas) get injected into every per-file LLM prompt
            # so cross-file references stay consistent.
            yield _sse_frame("contracts_start", {
                "message": "Sketching shared contracts (TS interfaces, PHP signatures, SQL schemas)…",
            })
            try:
                contracts_text, contracts_tokens = await _asyncio.get_event_loop().run_in_executor(
                    None,
                    generate_contracts,
                    request.app.state.brain, db_wrapper,
                    project.props.llm, clean_plan,
                )
                total_tokens["input"] += int(contracts_tokens.get("input", 0) or 0)
                total_tokens["output"] += int(contracts_tokens.get("output", 0) or 0)
            except Exception as e:
                logger.warning("contracts pass failed (degrading gracefully): %s", e)
                contracts_text = ""
            yield _sse_frame("contracts_done", {
                "length": len(contracts_text or ""),
                "preview": (contracts_text or "")[:500],
            })

            # ── Test pack generation (after contracts, before files).
            # Produces tests/api.php that hits each /api/ endpoint and
            # asserts JSON shape per the contracts. The test runner
            # (called from /app/validate) feeds failures into the
            # auto-fix loop with line-attributed evidence. Skips for
            # backendless apps (no /api/ files in plan).
            try:
                from restai.app.ai import generate_tests
                tests_text, tests_tokens = await _asyncio.get_event_loop().run_in_executor(
                    None,
                    generate_tests,
                    request.app.state.brain, db_wrapper,
                    project.props.llm, clean_plan, contracts_text,
                )
                total_tokens["input"] += int(tests_tokens.get("input", 0) or 0)
                total_tokens["output"] += int(tests_tokens.get("output", 0) or 0)
            except Exception as e:
                logger.warning("test gen failed (degrading gracefully): %s", e)
                tests_text = ""
            if tests_text:
                # Write tests/api.php to disk. Don't run static_arch
                # checks here — tests are CLI PHP, not API/UI files;
                # the regular content-pattern checks would fire false
                # positives on test asserter helpers.
                try:
                    async with project_lock(projectID):
                        write_file(
                            projectID, "tests/api.php",
                            tests_text.encode("utf-8"),
                            if_match=None,
                        )
                    yield _sse_frame("tests_generated", {
                        "path": "tests/api.php",
                        "size": len(tests_text),
                    })
                except Exception as e:
                    logger.warning("test file write failed: %s", e)

            for ph_idx, phase in enumerate(phases, 1):
                if await request.is_disconnected():
                    yield _sse_frame("error", {"message": "client disconnected"})
                    return

                ph_files = phase.get("files", [])
                yield _sse_frame("phase_start", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "description": phase.get("description") or "",
                    "index": ph_idx,
                    "total": len(phases),
                    "file_count": len(ph_files),
                })

                phase_written: list[str] = []
                phase_failed: list[dict] = []

                for f_idx, file_spec in enumerate(ph_files, 1):
                    if await request.is_disconnected():
                        yield _sse_frame("error", {"message": "client disconnected"})
                        return
                    global_idx += 1

                    path = file_spec["path"]
                    purpose = file_spec.get("purpose", "")
                    target = root / path

                    yield _sse_frame("file_start", {
                        "path": path, "purpose": purpose,
                        "index": global_idx, "total": total_files,
                        "phase": phase.get("name"),
                        "phase_index": ph_idx,
                        "phase_file_index": f_idx,
                        "phase_file_total": len(ph_files),
                    })

                    # Per-file overwrite check.
                    if target.exists() and not overwrite:
                        failed.append({"path": path, "error": "exists (overwrite not set)"})
                        phase_failed.append({"path": path, "error": "exists (overwrite not set)"})
                        yield _sse_frame("file_error", {
                            "path": path, "error": "exists (overwrite not set)",
                        })
                        continue

                    # Snapshot of files written so far so the LLM can
                    # reference them by exact path.
                    already_written_snapshot = list(written)

                    events: _queue.Queue = _queue.Queue()
                    final_content_holder: dict = {}
                    def producer(_spec=file_spec, _phase=phase, _already=already_written_snapshot,
                                 _pid=projectID, _contracts=contracts_text):
                        try:
                            for evt_name, evt_data in stream_file_content(
                                request.app.state.brain, db_wrapper,
                                project.props.llm, clean_plan, _spec,
                                phase=_phase, already_written=_already,
                                project_id=_pid, contracts=_contracts,
                            ):
                                events.put((evt_name, evt_data))
                        except ValueError as e:
                            events.put(("file_error", {"path": _spec["path"], "error": str(e)}))
                        except Exception as e:
                            logger.exception("file stream crashed for %s", _spec["path"])
                            events.put(("file_error", {"path": _spec["path"], "error": str(e)}))
                        finally:
                            events.put(("__end__", None))

                    thread = _threading.Thread(target=producer, daemon=True)
                    thread.start()

                    file_failed = False
                    while True:
                        try:
                            evt = await _asyncio.get_event_loop().run_in_executor(
                                None, events.get, True, 0.5,
                            )
                        except _queue.Empty:
                            if await request.is_disconnected():
                                return
                            continue
                        name, data = evt
                        if name == "__end__":
                            break
                        if name == "file_done":
                            final_content_holder.update(data)
                        elif name == "file_error":
                            failed.append({"path": path, "error": data.get("error", "")})
                            phase_failed.append({"path": path, "error": data.get("error", "")})
                            yield _sse_frame("file_error", data)
                            file_failed = True
                            continue
                        if name in ("file_delta",):
                            yield _sse_frame(name, data)

                    if file_failed or not final_content_holder:
                        continue

                    # Static architecture check — reject obviously broken
                    # output BEFORE it hits disk (PHP that emits HTML, TS
                    # that imports npm, HTML with PHP tags, etc.). Each
                    # violation becomes a file_error that the auto-fix
                    # loop picks up.
                    from restai.app.ai import static_architecture_checks
                    arch_issues = static_architecture_checks(
                        path, final_content_holder["content"],
                    )
                    if arch_issues:
                        err_msg = "Architecture violation(s):\n- " + "\n- ".join(arch_issues)
                        failed.append({"path": path, "error": err_msg})
                        phase_failed.append({"path": path, "error": err_msg})
                        yield _sse_frame("file_error", {"path": path, "error": err_msg})
                        continue

                    # Tally cost.
                    t = final_content_holder.get("tokens", {})
                    total_tokens["input"] += int(t.get("input", 0) or 0)
                    total_tokens["output"] += int(t.get("output", 0) or 0)

                    # Write under the per-project lock so we don't race the IDE.
                    try:
                        async with project_lock(projectID):
                            new_etag = write_file(
                                projectID, path,
                                final_content_holder["content"].encode("utf-8"),
                                if_match=None,
                            )
                        written.append(path)
                        phase_written.append(path)
                        yield _sse_frame("file_done", {
                            "path": path,
                            "etag": new_etag,
                            "size": len(final_content_holder["content"]),
                        })
                    except HTTPException as e:
                        failed.append({"path": path, "error": str(e.detail)})
                        phase_failed.append({"path": path, "error": str(e.detail)})
                        yield _sse_frame("file_error", {"path": path, "error": str(e.detail)})
                    except Exception as e:
                        failed.append({"path": path, "error": str(e)})
                        phase_failed.append({"path": path, "error": str(e)})
                        yield _sse_frame("file_error", {"path": path, "error": str(e)})

                yield _sse_frame("phase_done", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "index": ph_idx,
                    "total": len(phases),
                    "written": phase_written,
                    "failed": phase_failed,
                })

                # Per-phase runtime probes — run after each phase so the
                # user (and the next phase's LLM, indirectly via the
                # auto-fix loop on completion) sees real failures
                # immediately. Files are bind-mounted so the container
                # has the latest source already; PHP picks up changes
                # without restart, esbuild watches src/ and recompiles.
                # Probes are best-effort: never block the build, never
                # raise.
                try:
                    phase_runtime_issues = _runtime_probes(request, projectID)
                except Exception:
                    logger.exception("phase runtime probes crashed (non-fatal)")
                    phase_runtime_issues = []
                yield _sse_frame("phase_check", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "index": ph_idx,
                    "issues": phase_runtime_issues,
                })

                # ── Per-phase inline auto-fix ───────────────────────
                # If the phase_check surfaced issues that point at files
                # we've already written, take ONE focused fix turn before
                # the next phase starts. This prevents broken phase-N
                # files from poisoning phase N+1's LLM context.
                #
                # Cap: 1 inline fix per phase (no recursion). Skip when:
                #   - no issues, OR
                #   - all issues point at files outside `written`
                #     (those will be fixed by a future phase or the
                #     end-of-build auto-fix loop).
                fix_targets: list[str] = []
                fix_relevant_issues: list[dict] = []
                written_set = set(written)
                for issue in phase_runtime_issues:
                    p = issue.get("path") or ""
                    if p in written_set and p not in fix_targets:
                        fix_targets.append(p)
                        fix_relevant_issues.append(issue)

                if fix_targets and not await request.is_disconnected():
                    yield _sse_frame("phase_fix_start", {
                        "phase": phase.get("name") or f"Phase {ph_idx}",
                        "index": ph_idx,
                        "targets": fix_targets,
                        "issue_count": len(fix_relevant_issues),
                    })
                    try:
                        from restai.app.ai import inline_fix_files
                        # Sync helper — push to a worker so the SSE
                        # generator stays async.
                        fixed_map, fix_tokens = await _asyncio.get_event_loop().run_in_executor(
                            None,
                            inline_fix_files,
                            request.app.state.brain, db_wrapper,
                            project.props.llm, clean_plan, contracts_text,
                            fix_relevant_issues, fix_targets, projectID,
                        )
                        total_tokens["input"] += int(fix_tokens.get("input", 0) or 0)
                        total_tokens["output"] += int(fix_tokens.get("output", 0) or 0)
                    except Exception:
                        logger.exception("inline fix failed for phase %s", ph_idx)
                        fixed_map = {}

                    fixed_paths: list[str] = []
                    fix_errors: list[dict] = []
                    for fp, fc in (fixed_map or {}).items():
                        # Architecture check on the fixed content too.
                        from restai.app.ai import static_architecture_checks
                        arch_issues = static_architecture_checks(fp, fc)
                        if arch_issues:
                            fix_errors.append({"path": fp, "error": "Architecture violation: " + "; ".join(arch_issues)})
                            continue
                        try:
                            async with project_lock(projectID):
                                write_file(projectID, fp, fc.encode("utf-8"), if_match=None)
                            fixed_paths.append(fp)
                        except HTTPException as e:
                            fix_errors.append({"path": fp, "error": str(e.detail)})
                        except Exception as e:
                            fix_errors.append({"path": fp, "error": str(e)})

                    yield _sse_frame("phase_fix_done", {
                        "phase": phase.get("name") or f"Phase {ph_idx}",
                        "index": ph_idx,
                        "fixed": fixed_paths,
                        "errors": fix_errors,
                    })

            # Restart preview so esbuild picks up the new src tree.
            mgr = getattr(request.app.state.brain, "app_manager", None)
            if mgr is not None and mgr.get_port(projectID) is not None:
                try:
                    await mgr.restart(projectID)
                except Exception:
                    logger.exception("Preview restart failed after execute (project=%s)", projectID)

            yield _sse_frame("complete", {
                "written": written,
                "failed": failed,
                "tokens": total_tokens,
            })
        finally:
            try:
                _record_ai_cost(
                    request, project, user, db_wrapper,
                    question=f"execute: {clean_plan.get('summary','')[:160]}",
                    answer=f"wrote {len(written)} files, {len(failed)} failed",
                    tokens=total_tokens,
                    status="success" if not failed else "partial",
                )
            except Exception:
                pass
            try:
                from restai.audit import _log_to_db as _audit
                _audit(
                    user.username, "APP_EXECUTE",
                    f"projects/{projectID}:wrote={len(written)}:failed={len(failed)}",
                    200,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/projects/{projectID}/app/files/fix-ai", tags=["App Builder"])
async def route_app_fix_file(
    request: Request,
    payload: FixFilePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Per-file targeted edit. Cheaper than full regeneration."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    # Read current content (re-uses the file router's safety guarantees:
    # traversal guard, size cap, 404 on missing).
    current_bytes, current_etag = read_file(projectID, payload.path)
    try:
        current_text = current_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="binary file is not editable")

    from restai.app.ai import fix_file_with_ai
    try:
        new_content, tokens = fix_file_with_ai(
            request.app.state.brain, db_wrapper, project.props.llm,
            payload.path, current_text, payload.instruction,
        )
    except ValueError as e:
        _record_ai_cost(
            request, project, user, db_wrapper,
            question=f"fix {payload.path}: {payload.instruction}",
            answer="", tokens={"input": 0, "output": 0}, status="error",
        )
        raise HTTPException(status_code=400, detail=str(e))

    async with project_lock(projectID):
        new_etag = write_file(
            projectID, payload.path,
            new_content.encode("utf-8"),
            if_match=current_etag,
        )

    _record_ai_cost(
        request, project, user, db_wrapper,
        question=f"fix {payload.path}: {payload.instruction}",
        answer=new_content[:200],
        tokens=tokens, status="success",
    )

    try:
        from restai.audit import _log_to_db as _audit
        _audit(user.username, "APP_FIX_FILE", f"projects/{projectID}:{payload.path}", 200)
    except Exception:
        pass

    return {"path": payload.path, "etag": new_etag, "size": len(new_content)}


# ──────────────────────────────────────────────────────────────────────
# Deploy: download zip + push via FTP/SFTP.
#
# Generated apps are deliberately standalone (no RESTai dependency at
# runtime), so "deploy" really is just "copy these files to a host".
# Most cheap PHP hosts only offer FTP/SFTP — that's exactly what we
# wire up here.
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{projectID}/app/download",
    tags=["App Builder"],
    response_class=Response,  # bypass FastAPI's JSON encoder
)
async def route_app_download(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    include_source: bool = Query(False, description="Ship src/*.ts source files alongside the compiled dist/"),
    include_db: bool = Query(False, description="Include database.sqlite (the dev database) in the zip"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Stream a ZIP of the project's source tree.

    Defaults are tuned for "deploy this to my shared host":
    - `node_modules`, `.git`, `__pycache__`, dotfiles → never shipped
    - `src/*.ts` → excluded (the deployed app only needs `public/dist/app.js`)
    - `database.sqlite` → excluded (dev DB, would clobber prod data on overwrite)
    Toggle either via the query flags.
    """
    project = _require_app_project(request, projectID, db_wrapper)
    from fastapi.responses import StreamingResponse
    from restai.app.deploy import ZipFilters, stream_zip
    from restai.app.storage import get_project_root

    root = get_project_root(projectID)
    if not root.exists():
        raise HTTPException(status_code=404, detail="project has no source tree")

    filters = ZipFilters(include_source=include_source, include_db=include_db)
    safe_name = (project.props.name or f"app-{projectID}").replace("/", "_")
    return StreamingResponse(
        stream_zip(root, filters),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.zip"',
            # Hint: the response is fully bytes, no caching.
            "Cache-Control": "no-store",
        },
    )


class DeployTestPayload(BaseModel):
    """Payload for the connection-test endpoint. Lets the user verify
    credentials without committing to a real upload."""
    protocol: str = Field(default="sftp", description="'sftp' or 'ftp'")
    host: str = Field(description="Hostname (no scheme, no port)")
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str = Field(description="Login username")
    password: str = Field(description="Login password (or '' to use saved credentials)")
    path: str = Field(default="/", description="Remote directory")
    use_passive: bool = Field(default=True, description="FTP passive mode (ignored for SFTP)")


def _resolve_deploy_credentials(project, payload_password: str) -> str:
    """Allow the UI to send `''` for the password to mean 'use what's
    stored on the project'. Avoids forcing the user to retype the
    password every time they hit Test Connection."""
    if payload_password:
        return payload_password
    opts = project.props.options
    saved = getattr(opts, "ftp_password", None)
    if not saved:
        raise HTTPException(status_code=400, detail="No saved password — fill in the password field.")
    return saved


@router.post("/projects/{projectID}/app/deploy/test", tags=["App Builder"])
async def route_app_deploy_test(
    request: Request,
    payload: DeployTestPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Connect to the deploy target, list the remote directory, return
    success/failure. No file transfer — safe to call repeatedly."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.app.deploy import test_connection
    pw = _resolve_deploy_credentials(project, payload.password)
    result = test_connection(
        protocol=payload.protocol,
        host=payload.host,
        port=payload.port or (22 if payload.protocol == "sftp" else 21),
        user=payload.user,
        password=pw,
        remote_dir=payload.path,
        use_passive=payload.use_passive,
    )
    return result


class DeployRunPayload(BaseModel):
    include_source: bool = Field(default=False)
    include_db: bool = Field(default=False)
    # Optional credential overrides — in the common case the user has
    # already saved them on the project and we read from there.
    protocol: str | None = Field(default=None)
    host: str | None = Field(default=None)
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None)
    password: str | None = Field(default=None)
    path: str | None = Field(default=None)
    use_passive: bool | None = Field(default=None)


@router.post("/projects/{projectID}/app/deploy", tags=["App Builder"])
async def route_app_deploy(
    request: Request,
    payload: DeployRunPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Push the project's files to the configured host. Streams progress
    as Server-Sent Events: ``event: <type>\\ndata: <json>\\n\\n``.

    Reads stored credentials from `project.options.ftp_*` by default;
    the request body can override individual fields if the user wants to
    deploy to a one-off host without saving the credentials.
    """
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    opts = project.props.options
    proto = (payload.protocol or getattr(opts, "ftp_protocol", None) or "sftp").lower()
    host = payload.host or getattr(opts, "ftp_host", None)
    port = payload.port or getattr(opts, "ftp_port", None) or (22 if proto == "sftp" else 21)
    login = payload.user or getattr(opts, "ftp_user", None)
    password = payload.password or getattr(opts, "ftp_password", None)
    path = payload.path or getattr(opts, "ftp_path", None) or "/"
    use_passive = payload.use_passive if payload.use_passive is not None else bool(
        getattr(opts, "ftp_use_passive", True)
    )

    if not host:
        raise HTTPException(status_code=400, detail="ftp_host is not configured")
    if not login or not password:
        raise HTTPException(status_code=400, detail="ftp_user / ftp_password are not configured")
    if proto not in ("sftp", "ftp"):
        raise HTTPException(status_code=400, detail=f"unknown protocol {proto!r}")

    from fastapi.responses import StreamingResponse
    from restai.app.deploy import ZipFilters, deploy_sftp, deploy_ftp
    from restai.app.storage import get_project_root, project_lock
    import json as _json

    root = get_project_root(projectID)
    if not root.exists():
        raise HTTPException(status_code=404, detail="project has no source tree")

    filters = ZipFilters(
        include_source=bool(payload.include_source),
        include_db=bool(payload.include_db),
    )

    async def stream():
        # SSE framing: each event is `event:<name>\ndata:<json>\n\n`.
        # Per-project lock so two parallel deploys can't race.
        async with project_lock(projectID):
            if proto == "sftp":
                gen = deploy_sftp(
                    root, filters,
                    host=host, port=port, user=login, password=password,
                    remote_dir=path,
                )
            else:
                gen = deploy_ftp(
                    root, filters,
                    host=host, port=port, user=login, password=password,
                    remote_dir=path, use_passive=use_passive,
                )
            uploaded = 0
            had_error = False
            try:
                for evt in gen:
                    et = evt.get("event") or "message"
                    if et == "upload":
                        uploaded += 1
                    if et == "error":
                        had_error = True
                    yield f"event: {et}\ndata: {_json.dumps(evt)}\n\n"
            except Exception as e:
                logger.exception("deploy stream crashed for project=%s", projectID)
                yield f"event: error\ndata: {_json.dumps({'message': str(e)})}\n\n"
                had_error = True

            # Audit row + log_inference (so it shows up in project activity).
            try:
                from restai.audit import _log_to_db as _audit
                _audit(
                    user.username,
                    "APP_DEPLOY" if not had_error else "APP_DEPLOY_FAIL",
                    f"projects/{projectID}:proto={proto}:files={uploaded}",
                    200 if not had_error else 500,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────────────────────
# Reset + post-build validation
# ──────────────────────────────────────────────────────────────────────


@router.post("/projects/{projectID}/app/reset", tags=["App Builder"])
async def route_app_reset(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Wipe everything for this app project and start fresh.

    - Stops the preview container (so the bind-mount releases the tree).
    - Deletes every file under <install_root>/apps/<id>/.
    - Clears the planning chat memory.
    - Re-seeds the hello-world SPA scaffold.
    - Restarts the preview container so esbuild rebuilds the new src.

    Used by the Reset Project button when the user wants a clean slate."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)
    from restai.app.storage import (
        delete_project_root, seed_hello_world,
    )
    from restai.agent2.memory import clear_session

    # 1) Stop the container before wiping — Docker bind mount otherwise
    # holds public/ open and rmtree leaves orphan dirs.
    mgr = getattr(request.app.state.brain, "app_manager", None)
    if mgr is not None:
        try:
            mgr._remove(projectID)  # noqa: SLF001 — internal but stable
        except Exception:
            logger.exception("reset: failed to stop container before wipe")

    # 2) Wipe disk.
    delete_project_root(projectID)

    # 3) Clear chat memory.
    try:
        await clear_session(request.app.state.brain, _app_chat_id(projectID))
    except Exception:
        logger.exception("reset: failed to clear chat memory")

    # 4) Re-seed.
    seed_hello_world(projectID, project.props.human_name or project.props.name)

    # 5) Optionally restart container if the runtime was already enabled.
    # The frontend will trigger a preview reload after this returns.
    if mgr is not None:
        try:
            await mgr.get_or_create(projectID)
        except Exception:
            logger.exception("reset: failed to start container after reseed")

    try:
        from restai.audit import _log_to_db as _audit
        _audit(user.username, "APP_RESET", f"projects/{projectID}", 200)
    except Exception:
        pass

    return {"reset": True}


# Soft cap on what we feed into the validator. A 200KB code review is
# already pushing it; we'd rather skip the bottom of the file than burn
# tokens on it.
_VALIDATE_MAX_BYTES = 120 * 1024
_VALIDATE_MAX_FILES = 30


def _collect_review_files(project_id: int) -> list[dict]:
    """Read up to _VALIDATE_MAX_FILES editable files from the project,
    truncating per-file content so the total payload stays under
    _VALIDATE_MAX_BYTES. Returns [{path, content}] in tree order."""
    from restai.app.storage import (
        get_project_root, EDITABLE_EXTENSIONS,
    )
    root = get_project_root(project_id)
    if not root.exists():
        return []
    out: list[dict] = []
    used = 0
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root).as_posix()
        # Skip hidden / build-output / vendored.
        if (
            rel.startswith("public/dist/")
            or rel.startswith("node_modules/")
            or rel.startswith(".")
            or "/." in "/" + rel
            or rel == "database.sqlite"
        ):
            continue
        if fp.suffix.lower() not in EDITABLE_EXTENSIONS:
            continue
        try:
            data = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Per-file budget: never let any single file blow the whole budget.
        per_file_cap = max(2048, (_VALIDATE_MAX_BYTES - used) // max(1, _VALIDATE_MAX_FILES - len(out)))
        if len(data) > per_file_cap:
            data = data[:per_file_cap] + "\n/* [truncated for review] */"
        used += len(data)
        out.append({"path": rel, "content": data})
        if len(out) >= _VALIDATE_MAX_FILES or used >= _VALIDATE_MAX_BYTES:
            break
    return out


# Runtime-probe limits. Per-request timeout and per-response body cap so
# a hung backend can't stall the validate endpoint and a 50MB error page
# can't blow the LLM context.
_RUNTIME_PROBE_TIMEOUT = 6  # seconds, per request
_RUNTIME_PROBE_BODY_CAP = 1500  # chars of error body to surface
_DRY_RUN_PREVIEW_BYTES = 64 * 1024
# Test runner output: `FAIL <endpoint> [<method>]: <message>` per the _TESTS_SYSTEM contract.
_TEST_FAIL_RE = re.compile(r"^FAIL\s+(\S+)(?:\s+(\S+))?\s*:\s*(.*)$", re.MULTILINE)


def _run_tests(request: Request, project_id: int) -> list[dict]:
    """Execute `tests/api.php` inside the dev container and convert FAIL
    lines into auto-fix-eligible issues attributed to each endpoint.

    Returns ``[]`` when there's no test file, no container, or all
    assertions passed.

    Each FAIL line in the test pack's stdout has the shape
    ``FAIL <endpoint> [<method>]: <message>``. The endpoint is parsed
    out as the issue's `path` so the auto-fix loop targets the actual
    broken file, not the test file.
    """
    from restai.app.storage import get_project_root
    root = get_project_root(project_id)
    test_file = root / "tests" / "api.php"
    if not test_file.is_file():
        return []
    brain = request.app.state.brain
    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        return []
    info = mgr._containers.get(int(project_id))  # noqa: SLF001
    if not info:
        return []
    try:
        container = mgr._client.containers.get(info.container_id)
    except Exception:
        return []

    # Run with a wall-clock guard. exec_run wrapper has no native
    # timeout, so we use the lower-level exec_create + exec_start
    # streamed inside a thread that we abandon after 60 s.
    import threading as _threading
    import queue as _queue
    out_q: _queue.Queue = _queue.Queue(maxsize=1)

    def _exec():
        try:
            exec_id = mgr._client.api.exec_create(  # noqa: SLF001
                container.id,
                cmd=["php", "/var/www/tests/api.php"],
                stdout=True,
                stderr=True,
                workdir="/var/www",
            )["Id"]
            output = mgr._client.api.exec_start(exec_id, stream=False)  # noqa: SLF001
            inspect = mgr._client.api.exec_inspect(exec_id)  # noqa: SLF001
            out_q.put((inspect.get("ExitCode"), output or b""))
        except Exception as e:
            out_q.put(("error", str(e).encode("utf-8")))

    th = _threading.Thread(target=_exec, daemon=True)
    th.start()
    try:
        exit_code, raw = out_q.get(timeout=60)
    except _queue.Empty:
        return [{
            "path": "tests/api.php",
            "severity": "high",
            "message": "Test runner timed out after 60 seconds. The test file may have a hung curl call.",
        }]

    if exit_code == "error":
        return [{
            "path": "tests/api.php",
            "severity": "low",
            "message": f"Test runner could not start: {raw.decode('utf-8', errors='replace')[:500]}",
        }]

    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    issues: list[dict] = []
    for m in _TEST_FAIL_RE.finditer(text):
        endpoint = m.group(1).strip()
        method = (m.group(2) or "").strip()
        msg = m.group(3).strip()
        # Drop FAIL lines whose endpoint isn't a recognisable project
        # path — attributing them to tests/ would only get them filtered
        # by the auto-fix immutability guard.
        if not endpoint.startswith("public/") and not endpoint.startswith("/"):
            continue
        endpoint_attr = endpoint.lstrip("/")
        prefix = f"[{method}] " if method else ""
        issues.append({
            "path": endpoint_attr,
            "severity": "high",
            "message": f"{prefix}Test failure: {msg}",
        })

    # If exit code was non-zero but no FAIL lines parsed, surface stderr
    # so the user/auto-fix loop sees something actionable.
    if exit_code not in (0, None) and not issues:
        snippet = text[-600:] if text else "(no output)"
        issues.append({
            "path": "tests/api.php",
            "severity": "medium",
            "message": f"Test runner exit code {exit_code}. Output tail:\n{snippet}",
        })
    return issues


def _runtime_probes(request: Request, project_id: int) -> list[dict]:
    """Hit the live preview container and surface real runtime errors as
    issues. Three checks:

    1. ``GET /`` — the SPA shell. Non-200 or missing mount point → issue.
    2. ``GET /api/<file>.php`` for every public/api/*.php that isn't a
       _underscore-prefixed include. 5xx, non-JSON content-type, or a
       JSON ``{"error": ...}`` body all become issues. PHP fatal errors
       and parse errors typically come through as 500 + HTML, which this
       catches cleanly.
    3. esbuild log via ``docker exec`` into the dev container. Any line
       containing "ERROR" / "error:" gets surfaced — a TypeScript file
       that won't compile is the #1 reason a build "looks fine on disk"
       but the iframe is blank.

    Returns a list of issue dicts in the same shape as the LLM review
    issues (path/severity/message). Empty list when the runtime is
    disabled or all probes pass.
    """
    import os as _os
    import requests as _requests
    from restai.app.storage import get_project_root

    issues: list[dict] = []
    brain = request.app.state.brain
    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        return issues
    port = mgr.get_port(project_id)
    if not port:
        # Container hasn't been spun yet (e.g. user opened the wizard
        # before viewing the preview). Skip silently — static analysis
        # still runs.
        return issues
    base = f"http://127.0.0.1:{port}"

    # ── Probe 1: SPA shell ──────────────────────────────────────────
    try:
        r = _requests.get(base + "/", timeout=_RUNTIME_PROBE_TIMEOUT)
        if r.status_code >= 500:
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": f"GET / returned HTTP {r.status_code}. Body: {r.text[:_RUNTIME_PROBE_BODY_CAP]}",
            })
        elif r.status_code >= 400:
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": f"GET / returned HTTP {r.status_code} — the SPA shell isn't being served. Check that public/index.html exists.",
            })
        # The new React contract uses `<div id="root">`; legacy vanilla
        # projects used `<div id="app">`. Accept either (and any quoting /
        # unquoted form) so the probe doesn't report a phantom "missing
        # mount" issue when the page is actually fine — that issue used
        # to drive the auto-fix loop to wreck working React apps by
        # renaming `#root` → `#app`.
        elif not re.search(r'\bid\s*=\s*["\']?(?:root|app)["\']?[\s/>]',
                           r.text, re.IGNORECASE):
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": "GET / served a page with no `id=\"root\"` (or `id=\"app\"`) mount element — the SPA can't render.",
            })
        if "<script type=\"module\" src=\"dist/app.js\"" not in r.text and "src=\"dist/app.js\"" not in r.text and "dist/app.js" not in r.text and r.status_code < 400:
            issues.append({
                "path": "public/index.html",
                "severity": "medium",
                "message": "Index page has no <script src=\"dist/app.js\"> — the TypeScript bundle won't load.",
            })
    except _requests.exceptions.RequestException as e:
        issues.append({
            "path": "/",
            "severity": "high",
            "message": f"GET / failed: {e}. The preview container is unreachable.",
        })

    # ── Probe 2: hit each public/api/*.php (skip underscore includes) ─
    root = get_project_root(project_id)
    api_dir = root / "public" / "api"
    if api_dir.is_dir():
        for php in sorted(api_dir.glob("*.php")):
            if php.name.startswith("_"):
                continue
            url = f"{base}/api/{php.name}"
            try:
                r = _requests.get(url, timeout=_RUNTIME_PROBE_TIMEOUT)
            except _requests.exceptions.RequestException as e:
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} failed: {e}",
                })
                continue
            ct = (r.headers.get("content-type") or "").lower()
            body_snip = r.text[:_RUNTIME_PROBE_BODY_CAP] if r.text else ""
            if r.status_code >= 500:
                # PHP fatal errors / parse errors land here. Body is
                # usually HTML with the actual error message — surface it
                # so the LLM can fix the right line.
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} returned HTTP {r.status_code} (likely a PHP error). Body:\n{body_snip}",
                })
                continue
            if "application/json" not in ct:
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} returned content-type {ct or 'none'!r} (not application/json). PHP must `header('Content-Type: application/json');`. Body:\n{body_snip}",
                })
                continue
            # Endpoint is JSON — but if it returned an `error` field with
            # a 4xx, that's still useful runtime evidence (e.g. missing
            # required field on a route that the SPA will hit).
            if 400 <= r.status_code < 500:
                # 405 (method not allowed for GET on a POST-only route) is
                # expected and not interesting; only flag 4xx with errors.
                if r.status_code != 405:
                    try:
                        body = r.json()
                        err_msg = body.get("error") if isinstance(body, dict) else None
                        if err_msg:
                            issues.append({
                                "path": f"public/api/{php.name}",
                                "severity": "medium",
                                "message": f"GET /api/{php.name} returned HTTP {r.status_code}: {err_msg}",
                            })
                    except Exception:
                        pass

    # ── Probe 3: esbuild log via docker exec ───────────────────────
    try:
        info = mgr._containers.get(int(project_id))  # noqa: SLF001
        if info:
            container = mgr._client.containers.get(info.container_id)
            res = container.exec_run(
                ["sh", "-c", "test -f /tmp/esbuild.log && tail -c 6000 /tmp/esbuild.log || true"],
                demux=False,
            )
            if res.exit_code == 0 and res.output:
                log = res.output.decode("utf-8", errors="replace").strip()
                # esbuild prints lines like:
                #   ✘ [ERROR] Could not resolve "./views/Home"
                #     src/app.ts:3:21:
                # Anything matching ERROR / "error:" is fatal for the bundle.
                lower = log.lower()
                if log and ("✘ [error]" in lower or "[error]" in lower or "error:" in lower):
                    # Trim to most recent ~3000 chars (esbuild appends, we
                    # want the tail = current state).
                    snippet = log[-3000:]
                    issues.append({
                        "path": "src/",
                        "severity": "high",
                        "message": "esbuild build failed — the TypeScript bundle is broken so the page won't run. Build log tail:\n" + snippet,
                    })
    except Exception as e:
        logger.debug("validate: esbuild log read failed: %s", e)

    return issues


_VALIDATE_SYSTEM = """You are a code reviewer for a tiny React + MUI +
PHP + SQLite web app. The runtime is bundled by esbuild into one JS
file; the deploy needs only PHP + the bundle. You may be shown:

1. RUNTIME EVIDENCE — concrete failures observed by actually hitting the
   live preview (HTTP status codes, PHP error messages, esbuild build
   log). These are FACTS, not guesses. If present, every runtime
   failure must map to an entry in your `issues` array.

2. The full project source. Look ONLY for things that would actually
   break the deployed app:
   - Dangling refs to files/functions/exports that genuinely don't exist
     in the file list.
   - An HTML form / fetch call pointing at an `api/<x>.php` that has no
     matching file.
   - PHP that emits HTML or uses string-concat SQL.
   - SPA shell missing `<div id="root">` or `<script src="dist/app.js">`.

NPM IMPORT ALLOWLIST — these are LEGITIMATE, do NOT flag them:
  react, react-dom, react-dom/client, @mui/material/*,
  @mui/icons-material/*, @mui/system, @emotion/react, @emotion/styled.
Flag ONLY `import x from "<other-package>"` (e.g. axios, react-router,
lodash). Relative imports (./ or ../) are always fine.

INNOCENT UNTIL PROVEN GUILTY — bias hard against false positives:
- If you can't point at a SPECIFIC line that breaks the deployed app,
  say `ok: true`. Stylistic preferences, "could be more idiomatic",
  "should add error handling", "could split into smaller components",
  unused imports, missing TypeScript types — NONE of these are issues.
- The user's last build was working. A false-positive issue triggers an
  auto-fix loop that often WRECKS the working app to address phantom
  problems. When in doubt, return `ok: true`.

OUTPUT FORMAT — exactly this JSON, no prose, no fences:

{
  "ok": true,
  "summary": "Looks good — wired up correctly.",
  "issues": []
}

OR

{
  "ok": false,
  "summary": "1-sentence overview of the problems",
  "issues": [
    {"path": "src/app.ts", "severity": "high", "message": "Imports './views/Cart' but the plan/files list doesn't include src/views/Cart.ts."},
    {"path": "public/api/items.php", "severity": "medium", "message": "$id is interpolated into the SQL on line 14 — should be parameter-bound."}
  ]
}

`severity` is one of `low`, `medium`, `high`. Output ONLY the JSON object."""


@router.post("/projects/{projectID}/app/validate", tags=["App Builder"])
async def route_app_validate(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Have the project's LLM review the generated app for bugs and
    architecture violations. Returns a structured report.

    Called automatically by the wizard after Approve & Build completes;
    can also be triggered manually."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    files = _collect_review_files(projectID)
    if not files:
        return {"ok": False, "summary": "No source files to review.", "issues": []}

    # Live runtime probes run BEFORE the LLM so we can:
    #   1. Surface concrete failures (HTTP 500, esbuild errors, non-JSON
    #      API responses) as issues that don't depend on the LLM noticing.
    #   2. Feed them to the LLM as evidence so the static review can
    #      target the actual broken thing instead of guessing.
    # Probes degrade gracefully — if the runtime is disabled or the
    # container is down, we just get an empty list and fall back to the
    # LLM-only review.
    runtime_issues: list[dict] = []
    try:
        runtime_issues = _runtime_probes(request, projectID)
    except Exception:
        logger.exception("validate: runtime probes crashed")

    # Run the LLM-generated test pack (if it exists) and merge its
    # failures into the runtime evidence. Tests carry endpoint-attributed
    # failures so the auto-fix loop targets real files, not the test
    # file itself. Best-effort: never block the build.
    try:
        # esbuild may still be compiling after the last execute; give it
        # a beat to settle so the test pack hits a stable backend.
        import asyncio as _asyncio_v
        await _asyncio_v.sleep(1.5)
        test_issues = await _asyncio_v.get_event_loop().run_in_executor(
            None, _run_tests, request, projectID,
        )
        if test_issues:
            runtime_issues.extend(test_issues)
    except Exception:
        logger.exception("validate: test runner crashed")

    # FAST PATH: when runtime probes + test runner found NOTHING, the app
    # is observably working. Skip the LLM "static review" entirely — it's
    # a known source of false positives that wreck working apps via the
    # auto-fix loop. Real bugs surface as runtime evidence on the next
    # validate run anyway.
    if not runtime_issues:
        return {
            "ok": True,
            "summary": "Runtime probes + test runner clean — app is observably working.",
            "issues": [],
        }

    # Build the user prompt: runtime evidence first (highest signal),
    # then file tree + each file's content.
    parts: list[str] = []
    if runtime_issues:
        parts.append(
            "RUNTIME EVIDENCE (concrete failures observed by hitting the live preview):\n"
        )
        for i, issue in enumerate(runtime_issues, 1):
            parts.append(
                f"\n[{i}] {issue.get('severity','?').upper()} @ {issue.get('path','?')}\n"
                f"    {issue.get('message','')}\n"
            )
        parts.append(
            "\nThe failures above are facts, not guesses. Your fix plan must address them.\n\n"
        )
    parts.append("Project files:\n")
    for f in files:
        parts.append(f"\n=== {f['path']} ===\n{f['content']}\n")
    user_prompt = "".join(parts)
    full_prompt = _VALIDATE_SYSTEM + "\n\n" + user_prompt

    # Use the project's LLM, non-streaming (we want the JSON in one shot).
    from restai.app.ai import _resolve_llm, _FENCE_RE  # internal but stable
    import json as _json_pkg
    try:
        llm = _resolve_llm(request.app.state.brain, db_wrapper, project.props.llm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = llm.llm.complete(full_prompt)
    except Exception as e:
        # Degrade gracefully: LLM hiccups (timeouts, 5xx from the provider,
        # quota errors) shouldn't black-hole the runtime evidence we already
        # collected. Return what we have so the wizard can still show it
        # and the auto-fix loop can act on the runtime/test failures.
        logger.exception("validate: LLM call failed; returning runtime evidence only")
        clean_issues = []
        seen: set[tuple[str, str]] = set()
        for it in runtime_issues:
            path = str(it.get("path", "") or "")[:200]
            message = str(it.get("message", "") or "")[:1000]
            if (path, message) in seen:
                continue
            seen.add((path, message))
            clean_issues.append({
                "path": path,
                "severity": str(it.get("severity", "high") or "high").lower(),
                "message": message,
            })
        return {
            "ok": False,
            "summary": (
                f"AI reviewer unreachable ({type(e).__name__}). "
                f"{len(clean_issues)} runtime issue(s) reported below — "
                "auto-fix will still target these."
            ),
            "issues": clean_issues,
            "ai_error": str(e)[:500],
        }

    raw = (result.text if hasattr(result, "text") else str(result)) or ""
    raw = raw.strip()
    fence = _FENCE_RE.search(raw)
    if fence and fence.group(1):
        raw = fence.group(1).strip()

    parsed: dict = {"ok": False, "summary": "Validator returned unparseable output.", "issues": []}
    try:
        # Tolerate prose around the JSON: take outermost braces.
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            cand = _json_pkg.loads(raw[start : end + 1])
            if isinstance(cand, dict):
                parsed = cand
    except Exception:
        pass

    # Normalise the response.
    parsed.setdefault("ok", False)
    parsed.setdefault("summary", "")
    issues = parsed.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    clean_issues = []
    for it in issues[:50]:
        if not isinstance(it, dict):
            continue
        clean_issues.append({
            "path": str(it.get("path", "") or "")[:200],
            "severity": str(it.get("severity", "medium") or "medium").lower(),
            "message": str(it.get("message", "") or "")[:1000],
        })

    # Merge runtime evidence into the final issue list. Dedupe on
    # (path, message) to avoid double-reporting when the LLM already
    # mentioned the same thing. Runtime issues take priority — they're
    # observed facts, not interpretations.
    seen = {(it["path"], it["message"]) for it in clean_issues}
    runtime_count = 0
    for it in runtime_issues:
        key = (str(it.get("path", "") or "")[:200], str(it.get("message", "") or "")[:1000])
        if key in seen:
            continue
        seen.add(key)
        clean_issues.insert(0, {
            "path": key[0],
            "severity": str(it.get("severity", "high") or "high").lower(),
            "message": key[1],
        })
        runtime_count += 1

    # If runtime probes found anything, the build can't be "ok" regardless
    # of what the LLM said.
    if runtime_count > 0:
        parsed["ok"] = False
        if not parsed.get("summary"):
            parsed["summary"] = (
                f"{runtime_count} runtime failure(s) observed when hitting the live preview."
            )

    parsed["issues"] = clean_issues

    # Cost log.
    try:
        in_tokens = len(request.app.state.brain.tokenizer(full_prompt)) if hasattr(request.app.state.brain, "tokenizer") else 0
        out_tokens = len(request.app.state.brain.tokenizer(raw)) if hasattr(request.app.state.brain, "tokenizer") else 0
        _record_ai_cost(
            request, project, user, db_wrapper,
            question=f"validate: {len(files)} files",
            answer=parsed.get("summary", "")[:200],
            tokens={"input": in_tokens, "output": out_tokens},
            status="success",
        )
    except Exception:
        pass

    try:
        from restai.audit import _log_to_db as _audit
        _audit(
            user.username, "APP_VALIDATE",
            f"projects/{projectID}:ok={parsed.get('ok')}:issues={len(clean_issues)}", 200,
        )
    except Exception:
        pass

    return parsed


__all__ = ["router"]
