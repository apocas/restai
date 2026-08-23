"""End-to-end re-embed against a REAL ChromaDB store, across a dimension change.

The unit tests in `test_cron_reembed.py` drive the phase machine over fakes,
which proves the control flow but not that the thing actually works: whether
Chroma accepts `limit`/`offset`, whether `reset()` really lets a new dimension
take effect (Chroma pins collection dimensionality at first insert), and
whether retrieval still functions afterwards.

This exercises the real `ChromaDBVector`, the real ingest helper and the real
`reembed.run_job` at two different embedding widths. Deterministic fake
embedding models stand in for a provider — no network, no API key.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import Document

from restai import reembed
from restai.embedding import Embedding
from restai.vectordb.chromadb import ChromaDBVector
from restai.vectordb.tools import index_documents_classic


# A project id well outside anything the API-level tests create, so the
# collection cannot collide with theirs.
PROJECT_ID = 990421


class _FakeEmbed(BaseEmbedding):
    """Deterministic embedding of a fixed width. Same text always maps to the
    same vector, so retrieval is reproducible without a provider."""

    dim: int = 8

    def _vec(self, text: str):
        return [float((sum(map(ord, text)) + i) % 97) / 97.0 for i in range(self.dim)]

    def _get_query_embedding(self, query): return self._vec(query)
    def _get_text_embedding(self, text): return self._vec(text)
    async def _aget_query_embedding(self, query): return self._vec(query)
    async def _aget_text_embedding(self, text): return self._vec(text)


def _embedding(name: str, dim: int) -> Embedding:
    return Embedding(
        name,
        SimpleNamespace(name=name, dimension=dim, input_cost=0.0),
        _FakeEmbed(dim=dim),
    )


class _Session:
    """Enough of a session for `run_job`'s commits. Deliberately has no
    `add()`: that makes `accounting.log_embedding_usage` fail, which asserts
    the property it promises — accounting must never break a migration that is
    mid-way through rebuilding a vector store."""

    def commit(self): pass


class _DB:
    def __init__(self):
        self.db = _Session()
        self.row = SimpleNamespace(embeddings=None, embeddings_indexed=None)

    def get_project_by_id(self, pid):
        return self.row


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(reembed, "snapshot_dir", lambda: str(tmp_path))
    return SimpleNamespace(
        vector=None,
        props=SimpleNamespace(
            id=PROJECT_ID, type="rag", team_id=None,
            embeddings="e2e-old-8d", vectorstore="chroma",
        ),
    )


def _brain(target):
    class _Brain:
        def find_project(self, pid, db): return _brain.project
        def get_embedding(self, name, db): return target
    return _Brain()


def _job(tmp_path, **kw):
    return SimpleNamespace(
        id=1, project_id=PROJECT_ID, user_id=None,
        from_embeddings="e2e-old-8d", to_embeddings="e2e-new-32d",
        status="processing", phase=None, error_message=None,
        snapshot_path=str(tmp_path / "e2e.jsonl"),
        chunks_total=0, chunks_done=0, tokens_embedded=0, cost=0.0,
        completed_at=None, **kw,
    )


def test_migration_across_a_dimension_change(project, tmp_path):
    old = _embedding("e2e-old-8d", 8)
    new = _embedding("e2e-new-32d", 32)

    brain = _brain(new)
    _brain.project = project

    # ---- seed a real Chroma store through the real ingest path ----------
    project.vector = ChromaDBVector(brain, project, old)
    project.vector.reset(brain)  # clean slate across reruns

    docs = [
        Document(
            text=f"Sentence number {i} about pumpkins and llamas. " * 4,
            metadata={"source": f"doc{i % 3}.pdf", "keywords": "pumpkin, llama"},
        )
        for i in range(12)
    ]
    index_documents_classic(project, docs, "sentence", 64)

    before_count = project.vector.info()
    before_texts = sorted(c["text"] for c in project.vector.list_all_nodes(limit=10_000))
    assert before_count > 0

    # ---- run the real migration -----------------------------------------
    job = _job(tmp_path)
    db = _DB()
    reembed.run_job(job, brain, db)

    # ---- verify against a freshly-opened handle on the new model --------
    after = ChromaDBVector(brain, project, new)

    assert after.info() == before_count, "chunk count changed"
    assert job.chunks_done == before_count

    nodes = after.list_all_nodes(limit=10_000)
    assert sorted(n["text"] for n in nodes) == before_texts, "chunk text not preserved"

    # `list_all_chunks` would have dropped `keywords` — this is why the engine
    # reads through `list_all_nodes` instead.
    assert {n["metadata"].get("keywords") for n in nodes} == {"pumpkin, llama"}
    assert {n["metadata"].get("source") for n in nodes} == {"doc0.pdf", "doc1.pdf", "doc2.pdf"}

    # The vectors really are the new width — i.e. `reset()` genuinely let the
    # new dimension take effect rather than the old collection surviving.
    raw = after.chroma_collection.get(include=["embeddings"], limit=1)
    assert len(raw["embeddings"][0]) == 32

    # And retrieval works against them.
    hits = after.chroma_collection.query(
        query_embeddings=[_FakeEmbed(dim=32)._vec("pumpkins and llamas")], n_results=3,
    )
    assert len(hits["ids"][0]) == 3

    # The project is repointed and stamped, so nothing is left querying the
    # old model against new-model vectors.
    assert db.row.embeddings == "e2e-new-32d"
    assert db.row.embeddings_indexed == "e2e-new-32d"

    reembed.finish_job(job, db, error=None)
    assert not os.path.exists(job.snapshot_path), "snapshot kept after success"


def test_count_mismatch_leaves_a_real_store_untouched(project, tmp_path, monkeypatch):
    """The safety check, against a real store rather than a fake one."""
    old = _embedding("e2e-old-8d", 8)
    brain = _brain(_embedding("e2e-new-32d", 32))
    _brain.project = project

    project.vector = ChromaDBVector(brain, project, old)
    project.vector.reset(brain)
    index_documents_classic(
        project,
        [Document(text="alpha beta gamma delta " * 10, metadata={"source": "a.pdf"})],
        "sentence", 64,
    )
    seeded = project.vector.info()
    assert seeded > 0

    # Simulate the backend under-reporting its contents — the Weaviate /
    # Pinecone partial-read signature.
    monkeypatch.setattr(type(project.vector), "info", lambda self: seeded + 500)

    with pytest.raises(reembed.ReembedError):
        reembed.run_job(_job(tmp_path), brain, _DB())

    monkeypatch.undo()
    survivor = ChromaDBVector(brain, project, old)
    assert survivor.info() == seeded, "knowledge base was destroyed on a bad read"
