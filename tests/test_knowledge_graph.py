"""Tests for the knowledge graph endpoints.

These tests use direct DB inserts to seed entities and verify the endpoints
work correctly without requiring HuggingFace model downloads.
"""
import random
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"kg_team_{suffix}"
project_name = f"kg_project_{suffix}"

team_id = None
project_id = None
entity_a_id = None
entity_b_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _seed_entities(project_id_int):
    """Insert two entities + a mention + a relationship directly via DB."""
    from restai.database import DBWrapper
    from restai.models.databasemodels import (
        KGEntityDatabase, KGEntityMentionDatabase, KGEntityRelationshipDatabase,
    )
    db = DBWrapper()
    try:
        now = datetime.now(timezone.utc)
        a = KGEntityDatabase(
            project_id=project_id_int, name="Acme Corp", normalized="acme corp",
            entity_type="ORG", mention_count=5, created_at=now, updated_at=now,
        )
        b = KGEntityDatabase(
            project_id=project_id_int, name="John Smith", normalized="john smith",
            entity_type="PERSON", mention_count=3, created_at=now, updated_at=now,
        )
        c = KGEntityDatabase(
            project_id=project_id_int, name="Acme", normalized="acme",
            entity_type="ORG", mention_count=2, created_at=now, updated_at=now,
        )
        db.db.add_all([a, b, c])
        db.db.flush()
        db.db.add(KGEntityMentionDatabase(
            entity_id=a.id, project_id=project_id_int, source="doc1.pdf",
            mention_count=5, created_at=now,
        ))
        db.db.add(KGEntityMentionDatabase(
            entity_id=b.id, project_id=project_id_int, source="doc1.pdf",
            mention_count=3, created_at=now,
        ))
        db.db.add(KGEntityRelationshipDatabase(
            project_id=project_id_int, from_entity_id=a.id, to_entity_id=b.id,
            weight=2, created_at=now,
        ))
        db.db.commit()
        return a.id, b.id, c.id
    finally:
        db.db.close()


def test_setup(client):
    global team_id, project_id, entity_a_id, entity_b_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]

    resp = client.post(
        "/projects",
        json={"name": project_name, "type": "rag", "team_id": team_id, "embeddings": "default"},
        auth=auth,
    )
    # Project creation may fail if no embeddings configured — try block project as fallback
    if resp.status_code != 201:
        resp = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=auth,
        )
        # Block projects can't use KG endpoints — skip test setup
        if resp.status_code != 201:
            import pytest
            pytest.skip("Cannot create project for KG tests")
    project_id = resp.json()["project"]
    entity_a_id, entity_b_id, _ = _seed_entities(project_id)


def test_list_entities(client):
    resp = client.get(
        f"/projects/{project_id}/kg/entities",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    # The endpoint returns 400 for non-RAG projects; if our project is non-RAG, skip
    if resp.status_code == 400:
        import pytest
        pytest.skip("Non-RAG project — KG endpoints unavailable")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert len(data["entities"]) >= 3
    names = [e["name"] for e in data["entities"]]
    assert "Acme Corp" in names
    assert "John Smith" in names


def test_filter_entities_by_type(client):
    resp = client.get(
        f"/projects/{project_id}/kg/entities?type=PERSON",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    if resp.status_code == 400:
        import pytest
        pytest.skip("Non-RAG")
    assert resp.status_code == 200
    for e in resp.json()["entities"]:
        assert e["entity_type"] == "PERSON"


def test_search_entities(client):
    resp = client.get(
        f"/projects/{project_id}/kg/entities?search=acme",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    if resp.status_code == 400:
        import pytest
        pytest.skip("Non-RAG")
    assert resp.status_code == 200
    for e in resp.json()["entities"]:
        assert "acme" in e["normalized"]


def test_get_entity_detail(client):
    resp = client.get(
        f"/projects/{project_id}/kg/entities/{entity_a_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    if resp.status_code == 400:
        import pytest
        pytest.skip("Non-RAG")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert len(data["mentions"]) >= 1
    assert data["mentions"][0]["source"] == "doc1.pdf"
    assert len(data["related"]) >= 1


def test_rename_entity(client):
    resp = client.patch(
        f"/projects/{project_id}/kg/entities/{entity_a_id}",
        json={"name": "Acme Corporation"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    if resp.status_code == 400 and "RAG" in str(resp.json()):
        import pytest
        pytest.skip("Non-RAG")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme Corporation"
    assert resp.json()["normalized"] == "acme corporation"


def test_get_graph(client):
    resp = client.get(
        f"/projects/{project_id}/kg/graph",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    # Graph endpoint doesn't check project type — always returns
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 3


def test_find_duplicates(client):
    resp = client.get(
        f"/projects/{project_id}/kg/duplicates?threshold=0.5",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert isinstance(data["candidates"], list)


def test_merge_entities(client):
    """Merge the smaller Acme into Acme Corporation."""
    from restai.database import DBWrapper
    from restai.models.databasemodels import KGEntityDatabase

    # Find the "Acme" entity (the third one we seeded)
    db = DBWrapper()
    try:
        acme = (
            db.db.query(KGEntityDatabase)
            .filter(
                KGEntityDatabase.project_id == project_id,
                KGEntityDatabase.normalized == "acme",
            )
            .first()
        )
        if not acme:
            import pytest
            pytest.skip("Seed entity not found")
        small_acme_id = acme.id
    finally:
        db.db.close()

    resp = client.post(
        f"/projects/{project_id}/kg/entities/{small_acme_id}/merge",
        json={"target_id": entity_a_id},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    assert resp.json()["merged_into"] == entity_a_id

    # Verify the small Acme is gone
    db = DBWrapper()
    try:
        assert db.db.query(KGEntityDatabase).filter(KGEntityDatabase.id == small_acme_id).first() is None
    finally:
        db.db.close()


def test_delete_entity(client):
    resp = client.delete(
        f"/projects/{project_id}/kg/entities/{entity_b_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 204

    # Verify it's gone
    resp = client.get(
        f"/projects/{project_id}/kg/entities/{entity_b_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 404


def test_cleanup(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/projects/{project_name}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
