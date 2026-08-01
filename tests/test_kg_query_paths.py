"""Error/branch tests for restai/routers/projects/kg.py — kg/query + kg/rebuild.

test_knowledge_graph.py covers entity CRUD/merge/graph; this file covers
the natural-language kg/query pipeline branches (missing question,
non-RAG, KG disabled, empty graph, unmatched entities, matched-without-
sources, matched-without-content, and the full LLM-answer path with the
project/vector/LLM faked) plus kg/rebuild.
"""
import random
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"kgq_llm_{suffix}"
emb_name = f"kgq_emb_{suffix}"
team_name = f"kgq_team_{suffix}"
rag_proj_name = f"kgq_rag_{suffix}"
block_proj_name = f"kgq_block_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _no_ner(monkeypatch):
    """Disable the NER fallback so tests never try to download HF models."""
    import restai.integrations.knowledge_graph as kgmod

    monkeypatch.setattr(kgmod, "find_entities_in_text", lambda *a, **k: [])


def test_setup(client):
    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["llm_id"] = r.json()["id"]

    r = client.post(
        "/embeddings",
        json={
            "name": emb_name,
            "class_name": "Ollama",
            "options": '{"model_name": "test-emb"}',
            "privacy": "public",
            "dimension": 768,
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["emb_id"] = r.json()["id"]

    r = client.post(
        "/teams",
        json={"name": team_name, "llms": [llm_name], "embeddings": [emb_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={
            "name": rag_proj_name,
            "llm": llm_name,
            "embeddings": emb_name,
            "type": "rag",
            "team_id": state["team_id"],
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["rag_id"] = r.json()["project"]

    r = client.post(
        "/projects",
        json={"name": block_proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["block_id"] = r.json()["project"]


def test_kg_query_missing_question(client):
    r = client.post(f"/projects/{state['rag_id']}/kg/query", json={}, auth=ADMIN)
    assert r.status_code == 400
    assert "question" in r.json()["detail"]


def test_kg_query_non_rag(client):
    r = client.post(
        f"/projects/{state['block_id']}/kg/query",
        json={"question": "who is acme?"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "RAG" in r.json()["detail"]


def test_kg_entities_non_rag(client):
    r = client.get(f"/projects/{state['block_id']}/kg/entities", auth=ADMIN)
    assert r.status_code == 400


def test_kg_query_disabled(client):
    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "who is acme?"},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "not enabled" in r.json()["detail"]


def test_enable_kg(client):
    r = client.patch(
        f"/projects/{state['rag_id']}",
        json={"options": {"enable_knowledge_graph": True}},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text


def test_kg_query_empty_graph(client):
    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "who is acme?"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "empty" in data["answer"].lower()
    assert data["entities_matched"] == []
    assert data["source_count"] == 0


def _seed_entity(name, normalized, with_mention=False):
    from restai.database import DBWrapper
    from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase

    db = DBWrapper()
    try:
        now = datetime.now(timezone.utc)
        ent = KGEntityDatabase(
            project_id=state["rag_id"], name=name, normalized=normalized,
            entity_type="ORG", mention_count=1, created_at=now, updated_at=now,
        )
        db.db.add(ent)
        db.db.flush()
        if with_mention:
            db.db.add(KGEntityMentionDatabase(
                entity_id=ent.id, project_id=state["rag_id"],
                source="kgq_doc.txt", mention_count=1, created_at=now,
            ))
        db.db.commit()
        return ent.id
    finally:
        db.db.close()


def test_kg_query_no_entity_match(client, monkeypatch):
    _no_ner(monkeypatch)
    state["ent_nomention"] = _seed_entity("Globex", "globex")
    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "tell me about something unrelated"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "couldn't match" in data["answer"]
    assert "Globex" in data["answer"]  # sample of known entities is offered
    assert data["entities_matched"] == []


def test_kg_query_matched_but_no_sources(client, monkeypatch):
    _no_ner(monkeypatch)
    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "what does globex do?"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["entities_matched"] == ["Globex"]
    assert data["source_count"] == 0
    assert "no source documents" in data["answer"]


def test_kg_query_matched_but_no_content(client, monkeypatch):
    # Entity has a mention row, but the (empty/broken) vector store yields no
    # chunks for the source → "No content could be retrieved" branch.
    _no_ner(monkeypatch)
    _seed_entity("Initech", "initech", with_mention=True)
    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "what is initech?"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["entities_matched"] == ["Initech"]
    assert data["sources"] == ["kgq_doc.txt"]
    assert data["source_count"] == 1
    assert "No content" in data["answer"]


def test_kg_query_full_llm_path(client, monkeypatch):
    """Fake the project (vector included) + the LLM to walk the full path:
    entity match → source chunks → LLM answer → accounting."""
    import restai.routers.projects.kg as kg_router

    _no_ner(monkeypatch)

    class FakeVector:
        def find_source(self, src):
            return {"documents": ["Initech makes TPS reports."]}

    fake_project = SimpleNamespace(
        props=SimpleNamespace(
            id=state["rag_id"],
            type="rag",
            llm=llm_name,
            name=rag_proj_name,
            options=SimpleNamespace(enable_knowledge_graph=True),
        ),
        vector=FakeVector(),
    )
    monkeypatch.setattr(kg_router, "get_project", lambda *a, **k: fake_project)

    fake_resp = SimpleNamespace(
        message=SimpleNamespace(content="  Initech produces TPS reports.  ")
    )
    fake_llm = SimpleNamespace(llm=SimpleNamespace(chat=lambda msgs: fake_resp))
    monkeypatch.setattr(app.state.brain, "get_llm", lambda name, db: fake_llm)

    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "what does initech make?"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["answer"] == "Initech produces TPS reports."
    assert data["entities_matched"] == ["Initech"]
    assert data["sources"] == ["kgq_doc.txt"]


def test_kg_query_llm_failure_returns_500(client, monkeypatch):
    import restai.routers.projects.kg as kg_router

    _no_ner(monkeypatch)

    class FakeVector:
        def find_source(self, src):
            return {"documents": ["Initech makes TPS reports."]}

    fake_project = SimpleNamespace(
        props=SimpleNamespace(
            id=state["rag_id"], type="rag", llm=llm_name, name=rag_proj_name,
            options=SimpleNamespace(enable_knowledge_graph=True),
        ),
        vector=FakeVector(),
    )
    monkeypatch.setattr(kg_router, "get_project", lambda *a, **k: fake_project)

    def boom(name, db):
        raise RuntimeError("provider down")

    monkeypatch.setattr(app.state.brain, "get_llm", boom)

    r = client.post(
        f"/projects/{state['rag_id']}/kg/query",
        json={"question": "what does initech make?"},
        auth=ADMIN,
    )
    assert r.status_code == 500
    assert "LLM call failed" in r.json()["detail"]


def test_kg_rebuild_non_rag(client):
    r = client.post(f"/projects/{state['block_id']}/kg/rebuild", auth=ADMIN)
    assert r.status_code == 400


def test_kg_rebuild_clears_and_schedules(client):
    r = client.post(f"/projects/{state['rag_id']}/kg/rebuild", auth=ADMIN)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "Rebuild scheduled" in data["message"]
    assert "source_count" in data

    # All previously seeded entities are wiped synchronously.
    r = client.get(f"/projects/{state['rag_id']}/kg/entities", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_cleanup(client):
    client.delete(f"/projects/{state['rag_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['block_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
    client.delete(f"/embeddings/{state['emb_id']}", auth=ADMIN)
