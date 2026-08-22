"""Live re-embed against real Ollama embedding models, across a real
dimension change (all-minilm 384-d -> nomic-embed-text 768-d).

Everything else in the suite fakes the embedding provider. This drives the
actual HTTP API end to end — ingest, retrieve, swap the model, run the real
cron, retrieve again — and asserts that retrieval is still *semantically
correct* afterwards, which is the only check that proves the migration
produced usable vectors rather than merely well-shaped ones.

Skipped unless an Ollama server is reachable with both models pulled:

    docker run -d --gpus all --name ollama -p 11434:11434 ollama/ollama
    docker exec ollama ollama pull all-minilm
    docker exec ollama ollama pull nomic-embed-text
    docker exec ollama ollama pull qwen2.5:0.5b

Point the tests at it with RESTAI_LIVE_OLLAMA (default http://ollama:11434).
Set RESTAI_LIVE_VECTORSTORE=pgvector to run the same proof against pgvector
(needs a reachable pgvector Postgres configured in Settings).
"""
from __future__ import annotations

import base64
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
OLLAMA = os.environ.get("RESTAI_LIVE_OLLAMA", "http://ollama:11434")
VECTORSTORE = os.environ.get("RESTAI_LIVE_VECTORSTORE", "chromadb")

CHAT_MODEL = "qwen2.5:0.5b"
SMALL_MODEL, SMALL_DIM = "all-minilm", 384
BIG_MODEL, BIG_DIM = "nomic-embed-text", 768

S = uuid.uuid4().hex[:6]
LLM = f"live_llm_{S}"
EMB_SMALL = f"live_small_{S}"
EMB_BIG = f"live_big_{S}"
TEAM = f"live-team-{S}"
PROJ = f"live_proj_{S}"

# Deliberately unrelated topics, so "did retrieval come back correct?" is a
# real question with a checkable answer.
DOCS = {
    "espresso.txt": (
        "Espresso is brewed by forcing pressurised hot water through finely ground "
        "coffee beans. A good shot pulls in twenty five to thirty seconds and carries "
        "a thick golden crema on top."
    ),
    "penguins.txt": (
        "Emperor penguins breed on Antarctic sea ice during the polar winter. The male "
        "incubates the single egg on his feet beneath a feathered brood pouch for about "
        "two months while the female feeds at sea."
    ),
    "bridges.txt": (
        "A suspension bridge carries its deck from cables draped between tall towers. "
        "The Golden Gate Bridge spans the strait at the mouth of San Francisco Bay."
    ),
}

PROBES = {
    "how long should a coffee shot take": "espresso.txt",
    "which bird carries its egg on its feet": "penguins.txt",
    "cables hanging between tall towers": "bridges.txt",
}


def _ollama_ready() -> bool:
    try:
        import requests
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=3).json()
        names = {m["name"].split(":")[0] for m in tags.get("models", [])}
        return {SMALL_MODEL, BIG_MODEL}.issubset(names)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_ready(),
    reason=f"live Ollama with {SMALL_MODEL} + {BIG_MODEL} not reachable at {OLLAMA}",
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def project(client):
    r = client.post("/llms", json={
        "name": LLM, "class_name": "Ollama", "type": "chat",
        "options": json.dumps({"model": CHAT_MODEL, "base_url": OLLAMA}),
        "privacy": "private"}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text

    for name, model, dim in ((EMB_SMALL, SMALL_MODEL, SMALL_DIM),
                             (EMB_BIG, BIG_MODEL, BIG_DIM)):
        r = client.post("/embeddings", json={
            "name": name, "class_name": "Ollama",
            "options": json.dumps({"model_name": model, "base_url": OLLAMA}),
            "privacy": "private", "dimension": dim, "input_cost": 0.02}, auth=ADMIN)
        assert r.status_code in (200, 201), r.text

    r = client.post("/teams", json={
        "name": TEAM, "users": ["admin"], "llms": [LLM],
        "embeddings": [EMB_SMALL, EMB_BIG]}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    team_id = r.json()["id"]

    r = client.post("/projects", json={
        "name": PROJ, "type": "rag", "llm": LLM, "team_id": team_id,
        "embeddings": EMB_SMALL, "vectorstore": VECTORSTORE}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["project"]

    for source, text in DOCS.items():
        r = client.post(f"/projects/{pid}/embeddings/ingest/text",
                        json={"text": text, "source": source}, auth=ADMIN)
        assert r.status_code == 200, r.text

    return pid


def _top_source(client, pid, query):
    r = client.post(f"/projects/{pid}/embeddings/search",
                    json={"text": query, "k": 1}, auth=ADMIN)
    assert r.status_code == 200, r.text
    hits = r.json()["embeddings"]
    return hits[0]["source"] if hits else None


def test_live_migration_across_a_real_dimension_change(client, project):
    pid = project

    # ---- baseline on the 384-d model ------------------------------------
    r = client.get(f"/projects/{pid}/embeddings", auth=ADMIN)
    sources_before = sorted(r.json()["embeddings"])
    assert sources_before == sorted(DOCS)

    before = {q: _top_source(client, pid, q) for q in PROBES}
    assert before == PROBES, f"baseline retrieval already wrong: {before}"

    r = client.get(f"/projects/{pid}", auth=ADMIN)
    assert r.json()["embeddings_indexed"] == EMB_SMALL, "ingest did not stamp provenance"

    # ---- preflight -------------------------------------------------------
    r = client.get(f"/projects/{pid}/reembed/estimate?to={EMB_BIG}", auth=ADMIN)
    assert r.status_code == 200, r.text
    est = r.json()
    assert est["compatible"] is True
    assert est["dimension_change"] is True, "384 -> 768 must register as a dimension change"
    assert est["chunks"] == len(DOCS)
    assert est["tokens"] > 0

    # ---- the swap queues a migration ------------------------------------
    r = client.patch(f"/projects/{pid}", json={"embeddings": EMB_BIG}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert "reembed_job" in r.json(), "changing the model did not queue a migration"

    # ---- everything that touches the store is blocked --------------------
    r = client.post(f"/projects/{pid}/embeddings/search",
                    json={"text": "coffee", "k": 1}, auth=ADMIN)
    assert r.status_code == 503 and "re-embedded" in r.json()["detail"]

    r = client.post(f"/projects/{pid}/embeddings/ingest/text",
                    json={"text": "refused", "source": "x.txt"}, auth=ADMIN)
    assert r.status_code == 503, "ingest must be blocked or the write is lost"

    r = client.post(f"/projects/{pid}/chat", json={"question": "coffee?"}, auth=ADMIN)
    assert r.status_code == 503, "chat must 503 rather than answer from a store mid-reset"

    # ---- run the real cron ----------------------------------------------
    from crons import reembed as reembed_cron
    reembed_cron.main()

    # ---- verify ----------------------------------------------------------
    r = client.get(f"/projects/{pid}/reembed", auth=ADMIN)
    job = r.json()["jobs"][0]
    assert job["status"] == "done", f"migration failed: {job.get('error_message')}"
    assert job["chunks_done"] == len(DOCS)
    assert job["tokens_embedded"] > 0, "embedding usage was not metered"

    r = client.get(f"/projects/{pid}", auth=ADMIN)
    proj = r.json()
    assert proj["embeddings"] == EMB_BIG
    assert proj["embeddings_indexed"] == EMB_BIG, "provenance not updated on completion"

    r = client.get(f"/projects/{pid}/embeddings", auth=ADMIN)
    assert sorted(r.json()["embeddings"]) == sources_before, "a source was lost"

    # The point of the whole exercise: retrieval must still be RIGHT, not
    # merely non-empty. Vectors of the correct width that encode nothing
    # useful would pass every other assertion in this file.
    after = {q: _top_source(client, pid, q) for q in PROBES}
    assert after == PROBES, f"retrieval wrong after migration: {after}"

    # Chunk metadata survived the round trip.
    src = base64.b64encode(b"espresso.txt").decode()
    r = client.get(f"/projects/{pid}/embeddings/source/{src}", auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json(), "espresso.txt has no chunks after migration"


def test_live_chat_works_against_the_migrated_store(client, project):
    """A real RAG turn through the real LLM, after the migration."""
    pid = project
    r = client.post(f"/projects/{pid}/chat",
                    json={"question": "How long should an espresso shot take?"},
                    auth=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("sources"), "chat retrieved nothing from the migrated store"
    assert "espresso.txt" in [s.get("source") for s in body["sources"]]
    assert body["answer"].strip(), "empty answer"
