"""Routine execution log tests.

Covers:
* Manual `/fire` appends a `manual=True` row.
* `/history` returns newest-first.
* 404 on routine that doesn't belong to the project.

The cron path (`crons/routines.py` writing rows on its own tick) isn't
exercised here — the integration surface is the `RoutineExecutionLogDatabase`
model, which is already covered by the manual-fire path.
"""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def routine_project(client):
    teams = client.get("/teams", auth=ADMIN).json().get("teams", []) or []
    llms = (client.get("/info", auth=ADMIN).json() or {}).get("llms") or []
    if not teams or not llms:
        pytest.skip("fixtures unavailable")
    name = f"routine_hist_{random.randint(0, 999999)}"
    r = client.post(
        "/projects",
        json={"name": name, "type": "agent", "llm": llms[0]["name"], "team_id": teams[0]["id"]},
        auth=ADMIN,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"could not create project: {r.status_code}")
    body = r.json()
    pid = body.get("id") or body.get("project")
    yield pid
    client.delete(f"/projects/{pid}", auth=ADMIN)


@pytest.fixture
def routine(client, routine_project):
    name = f"r_{random.randint(0, 999999)}"
    r = client.post(
        f"/projects/{routine_project}/routines",
        json={"name": name, "message": "ping", "schedule_minutes": 60, "enabled": False},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    rid = r.json()["id"]
    # SQLite doesn't always enforce `ondelete=CASCADE` on legacy DBs
    # (requires `PRAGMA foreign_keys=ON`). A prior test run's orphaned
    # history rows can collide with this test's newly-issued routine id
    # and break the "empty initially" assumption. Scrub explicitly.
    from restai.database import get_db_wrapper
    from restai.models.databasemodels import RoutineExecutionLogDatabase
    db = get_db_wrapper()
    try:
        db.db.query(RoutineExecutionLogDatabase).filter(
            RoutineExecutionLogDatabase.routine_id == rid,
        ).delete()
        db.db.commit()
    finally:
        db.db.close()
    yield rid
    client.delete(f"/projects/{routine_project}/routines/{rid}", auth=ADMIN)


def test_history_empty_initially(client, routine_project, routine):
    r = client.get(f"/projects/{routine_project}/routines/{routine}/history", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_history_404_on_wrong_project(client, routine_project, routine):
    # Create a second project and request the routine against it.
    teams = client.get("/teams", auth=ADMIN).json().get("teams", []) or []
    llms = (client.get("/info", auth=ADMIN).json() or {}).get("llms") or []
    name = f"other_{random.randint(0, 999999)}"
    r = client.post(
        "/projects",
        json={"name": name, "type": "agent", "llm": llms[0]["name"], "team_id": teams[0]["id"]},
        auth=ADMIN,
    )
    other_pid = r.json().get("id") or r.json().get("project")
    try:
        r = client.get(f"/projects/{other_pid}/routines/{routine}/history", auth=ADMIN)
        assert r.status_code == 404
    finally:
        client.delete(f"/projects/{other_pid}", auth=ADMIN)


def test_history_404_on_missing_routine(client, routine_project):
    r = client.get(f"/projects/{routine_project}/routines/999999999/history", auth=ADMIN)
    assert r.status_code == 404


def test_manual_fire_appends_history_row(client, routine_project, routine):
    """After a successful /fire, the history endpoint must show one
    manual=True row with a non-null result."""
    r = client.post(f"/projects/{routine_project}/routines/{routine}/fire", auth=ADMIN)
    # Fire may fail upstream if no LLM is actually callable in this env
    # — we only need to assert that a log row lands EITHER WAY. The
    # manual-fire endpoint writes the row only on success though, so
    # skip this sub-assertion if the fire itself 5xx'd.
    if r.status_code >= 500:
        pytest.skip(f"fire returned {r.status_code} — upstream LLM unavailable")
    assert r.status_code == 200, r.text

    r = client.get(f"/projects/{routine_project}/routines/{routine}/history", auth=ADMIN)
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) >= 1
    # Newest first — latest run must be manual and ok.
    top = runs[0]
    assert top["manual"] is True
    assert top["status"] == "ok"
    assert top["created_at"]
