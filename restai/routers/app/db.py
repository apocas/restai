"""HTTP endpoints for the App-Builder SQLite DB editor."""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
)
from pydantic import BaseModel, Field

from restai.auth import (
    check_not_restricted,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User
from restai.app.storage import get_project_root

from ._common import router, _require_app_project

logger = logging.getLogger(__name__)


# SQLite DB editor safety:
# - Table names must appear in `sqlite_master` (re-checked per call).
# - Column names come from PRAGMA table_info, re-checked against payload.
# - Values always bound; only table/column names string-interpolated (validated).
# - Reserved tables (`sqlite_*`) filtered.

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RowUpsertPayload(BaseModel):
    """Body for POST/PUT /app/db/rows."""

    table: str = Field(description="Table name")
    values: dict = Field(default_factory=dict, description="Column → value")
    rowid: int | None = Field(default=None, description="rowid of the row to update; required on PUT")


class RowDeletePayload(BaseModel):
    table: str
    rowid: int


def _db_path(project_id: int) -> str:
    """Resolve the project's SQLite file path (may not exist; surfaced as 404)."""
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
    # `isolation_level=None` so we control transactions and avoid implicit
    # long-lived txns conflicting with the PHP container.
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    """PRAGMA table_info(<table>) — [{name, type, notnull, pk, dflt_value}]."""
    # PRAGMA can't be parameterised; identifier shape validated + master-list cross-check.
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    cols = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    return cols


def _resolve_table(conn: sqlite3.Connection, table: str) -> str:
    """Validate the table name shape AND existence."""
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
    """List user tables with row counts + column metadata."""
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
                count = -1
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
    """Paginated SELECT keyed by internal `rowid` so caller can update/delete without PK."""
    _require_app_project(request, projectID, db_wrapper)
    conn = _open_db(projectID)
    try:
        canonical = _resolve_table(conn, table)
        cols_info = _table_columns(conn, canonical)
        col_names = [c["name"] for c in cols_info]
        total_row = conn.execute(f'SELECT COUNT(*) FROM "{canonical}"').fetchone()
        total = int(total_row[0]) if total_row else 0
        # `INTEGER PRIMARY KEY` folds rowid into the PK column; alias guarantees presence.
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
            logger.warning("app db write failed: %s", e)
            raise HTTPException(status_code=400, detail="database write failed")
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
            logger.warning("app db write failed: %s", e)
            raise HTTPException(status_code=400, detail="database write failed")
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
            logger.warning("app db write failed: %s", e)
            raise HTTPException(status_code=400, detail="database write failed")
        return {"deleted": payload.rowid}
    finally:
        conn.close()
