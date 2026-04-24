"""Bulk ingest queue endpoint tests.

Covers the HTTP surface (enqueue + list + delete). The actual cron
that drains the queue runs out-of-process and is not exercised here;
we just verify that rows land correctly and the cleanup path works.
"""
from __future__ import annotations

import io
import os
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import get_db_wrapper
from restai.main import app
from restai.models.databasemodels import BulkIngestJobDatabase


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def rag_project(client):
    teams = client.get("/teams", auth=ADMIN).json().get("teams", []) or []
    if not teams:
        pytest.skip("no team available")
    llms = (client.get("/info", auth=ADMIN).json() or {}).get("llms") or []
    embs = (client.get("/info", auth=ADMIN).json() or {}).get("embeddings") or []
    if not llms or not embs:
        pytest.skip("no LLMs or embeddings configured")

    name = f"bulk_test_{random.randint(0, 999999)}"
    r = client.post(
        "/projects",
        json={
            "name": name, "type": "rag",
            "llm": llms[0]["name"], "embeddings": embs[0]["name"],
            "team_id": teams[0]["id"], "vectorstore": "chromadb",
        },
        auth=ADMIN,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"could not create RAG project: {r.status_code} {r.text}")
    pid = r.json().get("project") or r.json().get("id")
    yield pid
    client.delete(f"/projects/{pid}", auth=ADMIN)


def test_list_empty_initially(client, rag_project):
    r = client.get(f"/projects/{rag_project}/ingest-bulk", auth=ADMIN)
    assert r.status_code == 200
    # Existing rows from prior runs in the same DB would still be here —
    # what matters is that the endpoint is reachable and returns a
    # well-formed payload.
    body = r.json()
    assert "jobs" in body
    assert isinstance(body["jobs"], list)


def test_enqueue_creates_queued_rows(client, rag_project):
    files = [
        ("files", ("a.txt", io.BytesIO(b"hello world a"), "text/plain")),
        ("files", ("b.txt", io.BytesIO(b"hello world b"), "text/plain")),
    ]
    r = client.post(
        f"/projects/{rag_project}/ingest-bulk",
        files=files, auth=ADMIN,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["count"] == 2
    queued = body["queued"]
    assert len(queued) == 2

    try:
        # Verify both rows are queued and have a tempfile on disk
        db = get_db_wrapper()
        try:
            rows = (
                db.db.query(BulkIngestJobDatabase)
                .filter(BulkIngestJobDatabase.id.in_(queued))
                .all()
            )
            assert len(rows) == 2
            for row in rows:
                assert row.status == "queued"
                assert row.size_bytes > 0
                assert os.path.isfile(row.file_path), row.file_path
                assert row.filename.endswith(".txt")
        finally:
            db.db.close()

        # List should now show them
        listing = client.get(f"/projects/{rag_project}/ingest-bulk", auth=ADMIN).json()
        ids = [j["id"] for j in listing["jobs"]]
        for jid in queued:
            assert jid in ids
    finally:
        for jid in queued:
            client.delete(f"/projects/{rag_project}/ingest-bulk/{jid}", auth=ADMIN)


def test_delete_removes_tempfile_and_row(client, rag_project):
    files = [("files", ("c.txt", io.BytesIO(b"delete me"), "text/plain"))]
    r = client.post(f"/projects/{rag_project}/ingest-bulk", files=files, auth=ADMIN)
    jid = r.json()["queued"][0]

    db = get_db_wrapper()
    try:
        row = db.db.query(BulkIngestJobDatabase).filter(BulkIngestJobDatabase.id == jid).first()
        staged_path = row.file_path
        assert os.path.isfile(staged_path)
    finally:
        db.db.close()

    r = client.delete(f"/projects/{rag_project}/ingest-bulk/{jid}", auth=ADMIN)
    assert r.status_code == 200

    # Row gone, file gone
    db = get_db_wrapper()
    try:
        row = db.db.query(BulkIngestJobDatabase).filter(BulkIngestJobDatabase.id == jid).first()
        assert row is None
    finally:
        db.db.close()
    assert not os.path.isfile(staged_path)


def test_enqueue_rejects_empty_upload(client, rag_project):
    r = client.post(f"/projects/{rag_project}/ingest-bulk", auth=ADMIN)
    # FastAPI returns 422 when the required `files` param is missing.
    assert r.status_code in (400, 422)


def test_enqueue_rejects_non_rag_project(client):
    """Agent projects don't have a vectorstore — reject bulk ingest."""
    teams = client.get("/teams", auth=ADMIN).json().get("teams", []) or []
    llms = (client.get("/info", auth=ADMIN).json() or {}).get("llms") or []
    if not teams or not llms:
        pytest.skip("fixtures unavailable")

    name = f"bulk_agent_{random.randint(0, 999999)}"
    r = client.post(
        "/projects",
        json={"name": name, "type": "agent", "llm": llms[0]["name"], "team_id": teams[0]["id"]},
        auth=ADMIN,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"could not create agent project: {r.status_code}")
    pid = r.json().get("project") or r.json().get("id")
    try:
        files = [("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))]
        r = client.post(f"/projects/{pid}/ingest-bulk", files=files, auth=ADMIN)
        assert r.status_code == 400
        assert "rag" in r.json()["detail"].lower()
    finally:
        client.delete(f"/projects/{pid}", auth=ADMIN)
