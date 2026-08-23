"""Knowledge-base re-embedding: HTTP surface and the pure preflight helpers.

The phase machine itself is exercised in `tests/test_cron_reembed.py`, which
drives it against a fake vector store; here we check the endpoints, the
guards that stop anything else touching the store mid-migration, and the
per-backend compatibility rules.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from restai import reembed
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app
from restai.models.databasemodels import ReembedJobDatabase


ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = uuid.uuid4().hex[:8]
llm_name = f"reemb_llm_{suffix}"
emb_name = f"reemb_emb_{suffix}"
emb_name2 = f"reemb_emb2_{suffix}"
team_name = f"reemb-team-{suffix}"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def team(client):
    """Team that actually owns both embeddings — a migration needs the target
    to be team-accessible, and picking unrelated rows would 403 every test."""
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

    for name, dim in ((emb_name, 768), (emb_name2, 1536)):
        r = client.post(
            "/embeddings",
            json={
                "name": name, "class_name": "Ollama",
                "options": '{"model_name": "nomic-embed-text", "base_url": "http://127.0.0.1:11434"}',
                "privacy": "private", "dimension": dim, "input_cost": 0.02,
            },
            auth=ADMIN,
        )
        assert r.status_code in (200, 201), r.text

    r = client.post(
        "/teams",
        json={"name": team_name, "users": ["admin"], "llms": [llm_name],
              "embeddings": [emb_name, emb_name2]},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    yield r.json()["id"]


def _make_project(client, team_id, ptype="rag"):
    name = f"reemb_{ptype}_{random.randint(0, 999999)}"
    body = {"name": name, "type": ptype, "llm": llm_name, "team_id": team_id}
    if ptype == "rag":
        body.update({"embeddings": emb_name, "vectorstore": "chromadb"})
    r = client.post("/projects", json=body, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    return r.json().get("project") or r.json().get("id")


@pytest.fixture(scope="module")
def rag_project(client, team):
    return _make_project(client, team, "rag")


def _open_job(project_id: int, to=emb_name2, status="queued"):
    """Insert an open job row directly — the migration itself needs a live
    embedding provider, which the test environment has no business calling."""
    db = open_db_wrapper()
    job = ReembedJobDatabase(
        project_id=project_id, user_id=None,
        from_embeddings=emb_name, to_embeddings=to,
        status=status, chunks_total=0, chunks_done=0,
        tokens_embedded=0, cost=0.0,
        created_at=datetime.now(timezone.utc),
    )
    db.db.add(job)
    db.db.commit()
    db.db.refresh(job)
    job_id = job.id
    db.db.close()
    return job_id


def _clear_jobs(project_id: int):
    db = open_db_wrapper()
    db.db.query(ReembedJobDatabase).filter(
        ReembedJobDatabase.project_id == project_id
    ).delete()
    db.db.commit()
    db.db.close()


# ---------------------------------------------------------------- endpoints

def test_list_is_empty_for_new_project(client, rag_project):
    r = client.get(f"/projects/{rag_project}/reembed", auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["jobs"] == []


def test_enqueue_rejects_non_rag_project(client, team):
    agent_id = _make_project(client, team, "agent")
    r = client.post(
        f"/projects/{agent_id}/reembed?to_embeddings={emb_name2}", auth=ADMIN,
    )
    assert r.status_code == 400, r.text
    assert "RAG" in r.json()["detail"]


def test_enqueue_rejects_unknown_embedding(client, rag_project):
    r = client.post(
        f"/projects/{rag_project}/reembed?to_embeddings=does_not_exist", auth=ADMIN,
    )
    assert r.status_code == 404, r.text


def test_enqueue_conflicts_while_a_job_is_open(client, rag_project):
    _open_job(rag_project)
    try:
        r = client.post(
            f"/projects/{rag_project}/reembed?to_embeddings={emb_name2}", auth=ADMIN,
        )
        assert r.status_code == 409, r.text
    finally:
        _clear_jobs(rag_project)


def test_enqueue_rejects_empty_knowledge_base(client, rag_project):
    """A project with nothing stored has nothing to migrate — the model should
    just be changed directly rather than queueing a no-op job."""
    r = client.post(
        f"/projects/{rag_project}/reembed?to_embeddings={emb_name2}", auth=ADMIN,
    )
    assert r.status_code in (400, 503), r.text


def test_list_returns_inserted_job(client, rag_project):
    job_id = _open_job(rag_project)
    try:
        r = client.get(f"/projects/{rag_project}/reembed", auth=ADMIN)
        assert r.status_code == 200, r.text
        jobs = r.json()["jobs"]
        assert [j["id"] for j in jobs] == [job_id]
        assert jobs[0]["to_embeddings"] == emb_name2
        assert jobs[0]["status"] == "queued"
    finally:
        _clear_jobs(rag_project)


def test_cancel_queued_job(client, rag_project):
    job_id = _open_job(rag_project)
    try:
        r = client.delete(f"/projects/{rag_project}/reembed/{job_id}", auth=ADMIN)
        assert r.status_code == 200, r.text
        r = client.get(f"/projects/{rag_project}/reembed", auth=ADMIN)
        assert r.json()["jobs"] == []
    finally:
        _clear_jobs(rag_project)


def test_cannot_cancel_a_running_job(client, rag_project):
    """Stopping a migration mid-rebuild would leave the knowledge base half
    populated — the exact outcome the feature exists to prevent."""
    job_id = _open_job(rag_project, status="processing")
    try:
        r = client.delete(f"/projects/{rag_project}/reembed/{job_id}", auth=ADMIN)
        assert r.status_code == 409, r.text
    finally:
        _clear_jobs(rag_project)


# ------------------------------------------------------- serving guards

@pytest.mark.parametrize("method,path", [
    ("get", "/embeddings"),
    ("post", "/embeddings/reset"),
    ("post", "/embeddings/ingest/text"),
])
def test_knowledge_endpoints_503_while_migrating(client, rag_project, method, path):
    """Reads would show a half-rebuilt store; writes landing between the
    snapshot and the reset would be captured by neither and silently lost."""
    _open_job(rag_project)
    try:
        url = f"/projects/{rag_project}{path}"
        if method == "get":
            r = client.get(url, auth=ADMIN)
        else:
            r = client.post(url, json={"text": "hello", "source": "t.txt"}, auth=ADMIN)
        assert r.status_code == 503, r.text
        assert "re-embedded" in r.json()["detail"]
    finally:
        _clear_jobs(rag_project)


def test_sync_trigger_blocked_while_migrating(client, rag_project):
    """`run_sync_now` spawns a thread that writes straight into the store, and
    its RAG check is phrased differently from the other knowledge routes —
    which is exactly why it was missed the first time."""
    _open_job(rag_project)
    try:
        r = client.post(f"/projects/{rag_project}/sync/trigger", auth=ADMIN)
        assert r.status_code == 503, r.text
    finally:
        _clear_jobs(rag_project)


def test_patch_embeddings_conflicts_while_migrating(client, rag_project):
    _open_job(rag_project)
    try:
        r = client.patch(
            f"/projects/{rag_project}", json={"embeddings": emb_name2}, auth=ADMIN,
        )
        assert r.status_code == 409, r.text
    finally:
        _clear_jobs(rag_project)


# ------------------------------------------------------------- preflight

def test_compatibility_allows_same_dimension_everywhere():
    for store in ("chroma", "chromadb", "pgvector", "weaviate", "pinecone"):
        out = reembed.check_compatibility(store, 1536, 1536)
        assert out["compatible"] is True
        assert out["dimension_change"] is False


def test_compatibility_allows_dimension_change_on_self_owned_stores():
    for store in (None, "chroma", "pgvector", "weaviate"):
        out = reembed.check_compatibility(store, 768, 1536)
        assert out["compatible"] is True, store
        assert out["dimension_change"] is True


def test_compatibility_refuses_pinecone_dimension_change():
    """Every project shares one Pinecone index whose dimension is fixed at
    creation, so no amount of resetting the namespace can change it."""
    out = reembed.check_compatibility("pinecone", 768, 1536)
    assert out["compatible"] is False
    assert "index" in out["reason"].lower()


def test_compatibility_tolerates_unknown_dimensions():
    out = reembed.check_compatibility("pinecone", None, 1536)
    assert out["compatible"] is True
    assert out["dimension_change"] is False


# -------------------------------------------------------------- embeddings

def test_embedding_input_cost_round_trips(client, team):
    name = f"reemb_cost_{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/embeddings",
        json={"name": name, "class_name": "Ollama",
              "options": '{"model_name": "nomic-embed-text"}',
              "privacy": "private", "dimension": 768, "input_cost": 0.13},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["input_cost"] == pytest.approx(0.13)

    emb_id = r.json()["id"]
    r = client.patch(f"/embeddings/{emb_id}", json={"input_cost": 0.5}, auth=ADMIN)
    assert r.status_code == 200, r.text

    r = client.get("/embeddings", auth=ADMIN)
    row = next(e for e in r.json() if e["name"] == name)
    assert row["input_cost"] == pytest.approx(0.5)


def test_embedding_input_cost_defaults_to_zero(client):
    """Existing installs must migrate for free until an admin sets a rate,
    so an embedding created without the field bills nothing."""
    name = f"reemb_nocost_{uuid.uuid4().hex[:6]}"
    r = client.post(
        "/embeddings",
        json={"name": name, "class_name": "Ollama",
              "options": '{"model_name": "nomic-embed-text"}',
              "privacy": "private", "dimension": 768},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text
    assert (r.json().get("input_cost") or 0.0) == pytest.approx(0.0)
