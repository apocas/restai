"""Happy-path coverage for restai/routers/projects/core.py left untouched by
test_projects_core_edges.py / test_project_clone.py.

The vectorstore is replaced module-wide with an in-memory fake (patched at
`restai.vectordb.tools.find_vector_db`, which both `Brain.find_project` and
the create route resolve through), so RAG create / ingest-text / upload /
list / source / id / delete / reset run without ChromaDB or a live
embedding server. Also: the public listing filter + pagination, sensitive
option masking on list and detail, deep clone (prompt versions + eval
datasets), and the /logs + conversation-replay endpoints with seeded rows.
"""
import base64
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"corem_llm_{suffix}"
emb_name = f"corem_emb_{suffix}"
team_name = f"corem_team_{suffix}"
member_user = f"corem_member_{suffix}"
outsider_user = f"corem_out_{suffix}"
password = "corem_pass_123"
rag_proj_name = f"corem_rag_{suffix}"
public_proj_name = f"corem_pub_{suffix}"

state = {}

# ---------------------------------------------------------------- fake vector

_STORES: dict[str, dict] = {}


class _FakeIndex:
    def __init__(self, store):
        self.store = store

    def _add(self, text, metadata):
        self.store["counter"] += 1
        doc_id = f"fake-{self.store['counter']}"
        self.store["docs"][doc_id] = {"text": text, "metadata": dict(metadata or {})}
        return doc_id

    def insert(self, doc):
        self._add(doc.text, doc.metadata)

    def insert_nodes(self, nodes):
        for n in nodes:
            self._add(getattr(n, "text", ""), getattr(n, "metadata", {}))


class FakeVector:
    def __init__(self, brain, project, embedding):
        self.project = project
        self.store = _STORES.setdefault(project.props.name, {"docs": {}, "counter": 0})
        self.index = _FakeIndex(self.store)

    def save(self):
        pass

    def info(self):
        return len(self.store["docs"])

    def list(self):
        out = []
        for d in self.store["docs"].values():
            src = d["metadata"].get("source")
            if src not in out:
                out.append(src)
        return out

    def list_source(self, source):
        return [
            d["metadata"].get("source")
            for d in self.store["docs"].values()
            if d["metadata"].get("source") == source
        ]

    def find_source(self, source):
        ids = [k for k, d in self.store["docs"].items() if d["metadata"].get("source") == source]
        return {
            "ids": ids,
            "metadatas": [self.store["docs"][i]["metadata"] for i in ids],
            "documents": [self.store["docs"][i]["text"] for i in ids],
        }

    def find_id(self, doc_id):
        d = self.store["docs"].get(doc_id)
        if d is None:
            return {"id": doc_id}
        return {"id": doc_id, "metadata": d["metadata"], "document": d["text"]}

    def delete_source(self, source):
        ids = [k for k, d in self.store["docs"].items() if d["metadata"].get("source") == source]
        for i in ids:
            del self.store["docs"][i]
        return ids

    def reset(self, brain):
        self.store["docs"].clear()

    def delete(self):
        # Called by Project.delete() when the project row is removed.
        self.store["docs"].clear()
        _STORES.pop(self.project.props.name, None)


@pytest.fixture(scope="module", autouse=True)
def fake_vectordb():
    mp = pytest.MonkeyPatch()
    mp.setattr("restai.vectordb.tools.find_vector_db", lambda project: FakeVector)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- setup


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

    for u in (member_user, outsider_user):
        r = client.post(
            "/users",
            json={"username": u, "password": password, "admin": False, "private": False},
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text

    r = client.post(
        "/teams",
        json={"name": team_name, "users": [member_user], "llms": [llm_name], "embeddings": [emb_name]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]


def test_create_rag_project(client):
    r = client.post(
        "/projects",
        json={
            "name": rag_proj_name,
            "llm": llm_name,
            "embeddings": emb_name,
            "type": "rag",
            "team_id": state["team_id"],
            "vectorstore": "chromadb",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["rag_id"] = r.json()["project"]


def test_get_rag_project_detail(client):
    r = client.get(f"/projects/{state['rag_id']}", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "rag"
    assert data["chunks"] == 0
    assert data["embeddings"] == emb_name
    assert data["vectorstore"] == "chromadb"
    assert data["system"] == ""
    assert data["llm_privacy"] == "public"
    assert data["team"]["id"] == state["team_id"]


# ---------------------------------------------------------------- knowledge


def test_ingest_text_with_keywords(client):
    r = client.post(
        f"/projects/{state['rag_id']}/embeddings/ingest/text",
        json={
            "text": "The moon orbits the earth. " * 10,
            "source": "moon_facts",
            "keywords": ["moon", "orbit"],
        },
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "moon_facts"
    assert data["documents"] == 1
    assert data["chunks"] >= 1


def test_ingest_text_auto_keywords(client):
    r = client.post(
        f"/projects/{state['rag_id']}/embeddings/ingest/text",
        json={"text": "The sun is a star at the center of the solar system.", "source": "sun_facts"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["chunks"] >= 1


def test_ingest_text_unknown_project(client):
    r = client.post(
        "/projects/99999999/embeddings/ingest/text",
        json={"text": "x", "source": "y"},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_upload_file_classic(client):
    content = b"# Notes\n\nSome markdown knowledge about testing.\n"
    r = client.post(
        f"/projects/{state['rag_id']}/embeddings/ingest/upload",
        files={"file": ("notes.md", content, "text/markdown")},
        data={"method": "classic", "splitter": "sentence", "chunks": "256"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "notes.md"
    assert data["chunks"] >= 1
    # NOTE: the route also returns a "method" key, but response_model=
    # IngestResponse (no `method` field) silently strips it — clients never
    # see which ingest method ran. Pre-existing modelling gap, not asserted.
    assert "method" not in data


def test_upload_invalid_splitter(client):
    r = client.post(
        f"/projects/{state['rag_id']}/embeddings/ingest/upload",
        files={"file": ("notes2.md", b"# X\n", "text/markdown")},
        data={"method": "classic", "splitter": "banana"},
        auth=ADMIN,
    )
    assert r.status_code == 422


def test_list_embeddings_sources(client):
    r = client.get(f"/projects/{state['rag_id']}/embeddings", auth=ADMIN)
    assert r.status_code == 200
    sources = r.json()["embeddings"]
    assert {"moon_facts", "sun_facts", "notes.md"} <= set(sources)


def test_project_detail_counts_chunks(client):
    r = client.get(f"/projects/{state['rag_id']}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["chunks"] >= 3


def test_search_by_source(client):
    r = client.post(
        f"/projects/{state['rag_id']}/embeddings/search",
        json={"source": "moon_facts"},
        auth=ADMIN,
    )
    assert r.status_code == 200
    found = r.json()["embeddings"]
    assert len(found) >= 1
    assert all(s == "moon_facts" for s in found)


def test_get_embeddings_by_source(client):
    b64 = base64.b64encode(b"moon_facts").decode()
    r = client.get(f"/projects/{state['rag_id']}/embeddings/source/{b64}", auth=ADMIN)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs["ids"]) >= 1
    state["chunk_id"] = docs["ids"][0]


def test_get_embeddings_by_source_unknown(client):
    b64 = base64.b64encode(b"no_such_source").decode()
    r = client.get(f"/projects/{state['rag_id']}/embeddings/source/{b64}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"ids": []}


def test_get_embedding_by_id(client):
    r = client.get(f"/projects/{state['rag_id']}/embeddings/id/{state['chunk_id']}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["id"] == state["chunk_id"]
    assert r.json()["metadata"]["source"] == "moon_facts"


def test_delete_embedding_source(client):
    b64 = base64.b64encode(b"sun_facts").decode()
    r = client.delete(f"/projects/{state['rag_id']}/embeddings/{b64}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1

    r = client.get(f"/projects/{state['rag_id']}/embeddings", auth=ADMIN)
    assert "sun_facts" not in r.json()["embeddings"]


def test_reset_embeddings(client):
    r = client.post(f"/projects/{state['rag_id']}/embeddings/reset", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["project"] == rag_proj_name

    r = client.get(f"/projects/{state['rag_id']}", auth=ADMIN)
    assert r.json()["chunks"] == 0


# ---------------------------------------------------------------- clone (deep copy)


def test_clone_copies_datasets_and_prompt_versions(client):
    # Prompt version via a system-prompt edit + an eval dataset with a case.
    r = client.patch(
        f"/projects/{state['rag_id']}",
        json={"system": f"rag system prompt {suffix}", "options": {"rate_limit": 7}},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/projects/{state['rag_id']}/evals/datasets",
        json={"name": f"corem_ds_{suffix}", "test_cases": [{"question": "Q1?", "expected_answer": "A1"}]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text

    clone_name = f"corem_clone_{suffix}"
    r = client.post(
        f"/projects/{state['rag_id']}/clone",
        json={"name": clone_name},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    clone_id = r.json()["project"]
    state["clone_id"] = clone_id

    r = client.get(f"/projects/{clone_id}", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == clone_name
    assert data["human_name"].endswith("(copy)")
    assert data["system"] == f"rag system prompt {suffix}"
    assert data["options"]["rate_limit"] == 7
    assert data["type"] == "rag"

    # Eval datasets deep-copied with their cases. Filter by our unique name
    # and question: the shared test DB holds orphaned eval rows from other
    # modules (delete_project's raw-SQL cascade removes eval_datasets but not
    # their eval_test_cases), and reused autoincrement ids re-attach them.
    r = client.get(f"/projects/{clone_id}/evals/datasets", auth=ADMIN)
    assert r.status_code == 200
    ours = [d for d in r.json() if d["name"] == f"corem_ds_{suffix}"]
    assert len(ours) == 1

    r = client.get(f"/projects/{clone_id}/evals/datasets/{ours[0]['id']}", auth=ADMIN)
    assert r.status_code == 200
    questions = [tc["question"] for tc in r.json()["test_cases"]]
    assert "Q1?" in questions

    # Prompt versions replayed onto the clone.
    r = client.get(f"/projects/{clone_id}/prompts", auth=ADMIN)
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) >= 1
    assert any(v["system_prompt"] == f"rag system prompt {suffix}" for v in versions)


def test_clone_requires_name(client):
    r = client.post(f"/projects/{state['rag_id']}/clone", json={"name": "  "}, auth=ADMIN)
    assert r.status_code == 400
    assert "Name is required" in r.json()["detail"]


# ---------------------------------------------------------------- listing


def test_list_public_filter(client):
    r = client.post(
        "/projects",
        json={"name": public_proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["pub_id"] = r.json()["project"]
    r = client.patch(f"/projects/{state['pub_id']}", json={"public": True}, auth=ADMIN)
    assert r.status_code == 200, r.text

    # Admin: all public projects.
    r = client.get("/projects", params={"filter": "public"}, auth=ADMIN)
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["projects"]}
    assert state["pub_id"] in ids
    assert state["rag_id"] not in ids  # not public

    # Team member sees the team's public project without being a member of it.
    r = client.get("/projects", params={"filter": "public"}, auth=(member_user, password))
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["projects"]}
    assert state["pub_id"] in ids

    # Outsider (no teams) sees none of ours.
    r = client.get("/projects", params={"filter": "public"}, auth=(outsider_user, password))
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["projects"]}
    assert state["pub_id"] not in ids


def test_list_pagination(client):
    r = client.get("/projects", params={"start": 0, "end": 1}, auth=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert len(body["projects"]) == 1
    assert body["start"] == 0 and body["end"] == 1
    assert body["total"] >= 2


def test_list_non_admin_scoped(client):
    # outsider has no project access at all.
    r = client.get("/projects", auth=(outsider_user, password))
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["projects"]}
    assert state["rag_id"] not in ids and state["pub_id"] not in ids


def test_sensitive_options_masked_on_list_and_detail(client):
    secret = f"whsec_corem_{suffix}"
    r = client.patch(
        f"/projects/{state['rag_id']}",
        json={"options": {"webhook_secret": secret}},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/projects/{state['rag_id']}", auth=ADMIN)
    assert r.status_code == 200
    masked = r.json()["options"]["webhook_secret"]
    assert masked.startswith("****") and masked != secret
    assert secret not in r.text

    r = client.get("/projects", auth=ADMIN)
    assert r.status_code == 200
    row = next(p for p in r.json()["projects"] if p["id"] == state["rag_id"])
    assert row["options"]["webhook_secret"].startswith("****")
    assert secret not in r.text


# ---------------------------------------------------------------- logs


def test_logs_pagination_and_replay(client):
    from datetime import datetime, timedelta, timezone
    from restai.models.databasemodels import OutputDatabase

    chat_id = f"corem_chat_{suffix}"
    now = datetime.now(timezone.utc)
    db = open_db_wrapper()
    try:
        for i in range(3):
            db.db.add(OutputDatabase(
                question=f"q{i}", answer=f"a{i}",
                project_id=state["rag_id"], llm=llm_name,
                input_tokens=5, output_tokens=5,
                input_cost=0.0, output_cost=0.0,
                date=now + timedelta(seconds=i),
                chat_id=chat_id if i < 2 else f"other_{suffix}",
            ))
        db.db.commit()
    finally:
        db.db.close()

    r = client.get(f"/projects/{state['rag_id']}/logs", auth=ADMIN)
    assert r.status_code == 200
    assert len(r.json()["logs"]) == 3

    r = client.get(f"/projects/{state['rag_id']}/logs", params={"start": 0, "end": 2}, auth=ADMIN)
    assert len(r.json()["logs"]) == 2

    r = client.get(f"/projects/{state['rag_id']}/logs/conversation/{chat_id}", auth=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["chat_id"] == chat_id
    assert body["truncated"] is False
    assert [t["question"] for t in body["turns"]] == ["q0", "q1"]

    # chat_id fails safe-name validation -> 400.
    r = client.get(f"/projects/{state['rag_id']}/logs/conversation/bad%20chat!", auth=ADMIN)
    assert r.status_code == 400

    r = client.get("/projects/99999999/logs", auth=ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------- cleanup


def test_cleanup(client):
    for key in ("clone_id", "rag_id", "pub_id"):
        if key in state:
            client.delete(f"/projects/{state[key]}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    for u in (member_user, outsider_user):
        client.delete(f"/users/{u}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
    client.delete(f"/embeddings/{state['emb_id']}", auth=ADMIN)
    _STORES.clear()
