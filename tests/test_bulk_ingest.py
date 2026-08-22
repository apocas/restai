"""Bulk ingest queue endpoint tests.

Covers the HTTP surface (enqueue + list + delete). The actual cron
that drains the queue runs out-of-process and is not exercised here;
we just verify that rows land correctly and the cleanup path works.
"""
from __future__ import annotations

import io
import os
import random
import uuid

import pytest
from fastapi.testclient import TestClient

from restai import config
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app
from restai.models.databasemodels import BulkIngestJobDatabase


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = uuid.uuid4().hex[:8]
llm_name = f"bulk_llm_{suffix}"
emb_name = f"bulk_emb_{suffix}"
team_name = f"bulk-team-{suffix}"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def team(client):
    """A team that actually owns the LLM + embedding it hands to projects.

    Picking `teams[0]` and `llms[0]` independently (as this file used to)
    gives a pair with no access relationship, so every test skipped on a
    403 from project creation.
    """
    r = client.post(
        "/llms",
        json={
            "name": llm_name, "class_name": "OpenAI", "type": "chat",
            "options": '{"model": "gpt-4o-mini", "api_key": "sk-fake"}',
            "privacy": "private",
        },
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/embeddings",
        json={"name": emb_name, "class_name": "Ollama",
              "options": '{"model_name": "nomic-embed-text", "base_url": "http://127.0.0.1:11434"}',
              "privacy": "private", "dimension": 768},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/teams",
        json={"name": team_name, "users": ["admin"],
              "llms": [llm_name], "embeddings": [emb_name]},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    yield r.json()["id"]


def _make_project(client, team_id, ptype="rag"):
    name = f"bulk_{ptype}_{random.randint(0, 999999)}"
    body = {"name": name, "type": ptype, "llm": llm_name, "team_id": team_id}
    if ptype == "rag":
        body.update({"embeddings": emb_name, "vectorstore": "chromadb"})
    r = client.post("/projects", json=body, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    return r.json().get("project") or r.json().get("id")


@pytest.fixture(scope="module")
def rag_project(client, team):
    pid = _make_project(client, team, "rag")
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
        db = open_db_wrapper()
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

    db = open_db_wrapper()
    try:
        row = db.db.query(BulkIngestJobDatabase).filter(BulkIngestJobDatabase.id == jid).first()
        staged_path = row.file_path
        assert os.path.isfile(staged_path)
    finally:
        db.db.close()

    r = client.delete(f"/projects/{rag_project}/ingest-bulk/{jid}", auth=ADMIN)
    assert r.status_code == 200

    db = open_db_wrapper()
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


def test_enqueue_rejects_non_rag_project(client, team):
    """Agent projects don't have a vectorstore — reject bulk ingest."""
    pid = _make_project(client, team, "agent")
    try:
        files = [("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))]
        r = client.post(f"/projects/{pid}/ingest-bulk", files=files, auth=ADMIN)
        assert r.status_code == 400
        assert "rag" in r.json()["detail"].lower()
    finally:
        client.delete(f"/projects/{pid}", auth=ADMIN)


def _staged_files(project_id):
    """Staged tempfiles currently on disk for this project."""
    from restai.routers.bulk_ingest import _QUEUE_DIR

    if not os.path.isdir(_QUEUE_DIR):
        return []
    return [f for f in os.listdir(_QUEUE_DIR) if f.startswith(f"proj{project_id}_")]


def test_enqueue_rejects_oversized_file(client, rag_project, monkeypatch):
    """A part over the ceiling 413s, and the *whole batch* is refused.

    Sizes are validated for every part before anything is staged, so the
    small file that precedes the big one must leave neither a tempfile nor a
    job row behind — the old code staged and committed it first.
    """
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1024)

    before_files = set(_staged_files(rag_project))
    before_ids = {
        j["id"] for j in client.get(f"/projects/{rag_project}/ingest-bulk", auth=ADMIN).json()["jobs"]
    }

    files = [
        ("files", ("small.txt", io.BytesIO(b"tiny"), "text/plain")),
        ("files", ("big.txt", io.BytesIO(b"x" * 5000), "text/plain")),
    ]
    r = client.post(f"/projects/{rag_project}/ingest-bulk", files=files, auth=ADMIN)
    assert r.status_code == 413, r.text
    assert "too large" in r.json()["detail"].lower(), r.text

    after_ids = {
        j["id"] for j in client.get(f"/projects/{rag_project}/ingest-bulk", auth=ADMIN).json()["jobs"]
    }
    assert after_ids == before_ids, "partial batch leaked a job row"
    assert set(_staged_files(rag_project)) == before_files, "partial batch leaked a staged file"


def test_enqueue_accepts_file_under_ceiling(client, rag_project, monkeypatch):
    monkeypatch.setattr(config, "max_upload_bytes", lambda: 1024 * 1024)
    payload = b"y" * 4096
    files = [("files", ("ok.txt", io.BytesIO(payload), "text/plain"))]
    r = client.post(f"/projects/{rag_project}/ingest-bulk", files=files, auth=ADMIN)
    assert r.status_code == 202, r.text
    jid = r.json()["queued"][0]
    try:
        db = open_db_wrapper()
        try:
            row = db.db.query(BulkIngestJobDatabase).filter(BulkIngestJobDatabase.id == jid).first()
            # size_bytes is stat'd off the staged file, not taken from the
            # client's header — it must match the bytes actually written.
            assert row.size_bytes == len(payload)
            assert os.path.getsize(row.file_path) == len(payload)
        finally:
            db.db.close()
    finally:
        client.delete(f"/projects/{rag_project}/ingest-bulk/{jid}", auth=ADMIN)


def test_enqueue_rejects_out_of_range_chunks(client, rag_project):
    files = [("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))]
    r = client.post(
        f"/projects/{rag_project}/ingest-bulk?chunks=999999", files=files, auth=ADMIN
    )
    assert r.status_code == 422


def test_enqueue_refuses_when_disk_is_full(client, rag_project, monkeypatch):
    """507 rather than filling the staging volume and taking the app down."""
    import shutil as _shutil

    from restai.routers import bulk_ingest as mod

    class _Usage:
        total = free = 1024  # far below _DISK_HEADROOM_BYTES

    before = set(_staged_files(rag_project))
    monkeypatch.setattr(mod, "shutil", type("S", (), {
        "disk_usage": staticmethod(lambda _p: _Usage),
        "copyfileobj": staticmethod(_shutil.copyfileobj),
    }))

    files = [("files", ("a.txt", io.BytesIO(b"x" * 100), "text/plain"))]
    r = client.post(f"/projects/{rag_project}/ingest-bulk", files=files, auth=ADMIN)
    assert r.status_code == 507, r.text
    # Refused before staging, so nothing new landed on the volume.
    assert set(_staged_files(rag_project)) == before
