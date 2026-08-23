"""pgvector backend: table-name contract, plus optional live-database checks.

The contract test needs no database and is the one that matters for CI. Every
raw-SQL method in `PGVectorDB` targets a table whose name llama-index chooses,
and llama-index adds a `data_` prefix of its own on top of the name we hand it.
Getting that wrong is silent in the worst way: ingest and retrieval keep
working (they go through llama-index), while `info`, `list`, `find_*`,
`delete_source`, `delete_id`, `list_all_chunks` and `list_all_nodes` all raise
UndefinedTable and `delete()` — a `DROP TABLE IF EXISTS` — drops nothing at
all, leaking a project's entire vector table on deletion.

The live tests run only when a pgvector Postgres is configured and reachable.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from restai.vectordb.pgvector import PGVectorDB


def _project(pid=4242):
    return SimpleNamespace(
        vector=None,
        props=SimpleNamespace(id=pid, type="rag", team_id=None,
                              embeddings="e", vectorstore="pgvector"),
    )


def _names(pid=4242):
    """Derive both names the way `PGVectorDB.__init__` does, without touching
    a database (the constructor would connect)."""
    store_key = f"p{pid}"
    table_name = f"data_{store_key}"
    return store_key, table_name, f"data_{table_name}"


def test_physical_table_matches_what_llama_index_actually_creates():
    """The regression test for the bug. Asserts our raw-SQL target against
    llama-index's own naming rather than a hardcoded string, so a change to
    their convention fails here instead of silently breaking every management
    operation on pgvector projects."""
    from llama_index.vector_stores.postgres import PGVectorStore

    _, table_name, physical = _names()

    store = PGVectorStore.from_params(
        host="localhost", port="5432", user="u", password="p", database="d",
        table_name=table_name, embed_dim=8, perform_setup=False,
    )
    assert store._table_class.__tablename__ == physical, (
        "llama-index no longer names the table `data_<table_name>`; the raw SQL "
        "in PGVectorDB targets the wrong relation"
    )


def test_table_name_and_physical_table_are_distinct():
    """`table_name` is what we hand llama-index; `physical_table` is what it
    creates. Collapsing the two is exactly the mistake that broke this."""
    store_key, table_name, physical = _names()
    assert table_name == f"data_{store_key}"
    assert physical == f"data_{table_name}"
    assert physical != table_name


def test_raw_sql_never_targets_the_llama_index_facing_name():
    """Static guard: no query string may interpolate `table_name`.

    Cheap, but it is the check that fails the moment someone adds a new method
    by copy-pasting an old one — which is how all nine of them ended up wrong.
    """
    import inspect

    src = inspect.getsource(PGVectorDB)
    assert 'public."{self.table_name}"' not in src
    # `table_name` may appear only where llama-index consumes it.
    for line in src.splitlines():
        if "self.table_name" in line and "physical" not in line:
            assert (
                "table_name=self.table_name" in line
                or "self.table_name = " in line
                or "f\"data_{self.table_name}\"" in line
            ), f"suspicious use of table_name outside the llama-index handoff: {line.strip()}"


# ---------------------------------------------------------------- live tests

def _live_store(pid):
    """Build a real PGVectorDB, or skip when pgvector isn't reachable."""
    import restai.config as _cfg

    if not _cfg.PGVECTOR_HOST:
        pytest.skip("pgvector not configured (vectordb_pgvector_host unset)")

    from llama_index.core.base.embeddings.base import BaseEmbedding
    from restai.embedding import Embedding

    class _Embed(BaseEmbedding):
        dim: int = 8

        def _vec(self, t):
            return [float((sum(map(ord, t)) + i) % 97) / 97.0 for i in range(self.dim)]

        def _get_query_embedding(self, q): return self._vec(q)
        def _get_text_embedding(self, t): return self._vec(t)
        async def _aget_query_embedding(self, q): return self._vec(q)
        async def _aget_text_embedding(self, t): return self._vec(t)

    project = _project(pid)
    emb = Embedding("t-8d", SimpleNamespace(name="t-8d", dimension=8, input_cost=0.0), _Embed(dim=8))
    try:
        store = PGVectorDB(SimpleNamespace(), project, emb)
    except Exception as e:  # unreachable / extension missing
        pytest.skip(f"pgvector unreachable: {type(e).__name__}")
    project.vector = store
    return project, store


def test_live_every_method_hits_a_real_table():
    from llama_index.core.schema import Document
    from restai.vectordb.tools import index_documents_classic

    project, store = _live_store(990901)
    store.delete()
    project.vector = store = PGVectorDB(SimpleNamespace(), project, store.embedding)

    index_documents_classic(
        project,
        [Document(text="pumpkins and llamas " * 20, metadata={"source": "a.pdf", "keywords": "k"})],
        "sentence", 64,
    )

    n = store.info()
    assert n > 0
    assert store.list() == ["a.pdf"]
    assert len(store.list_source("a.pdf")) == n
    assert len(store.find_source("a.pdf")["ids"]) == n

    nodes = store.list_all_nodes(limit=1000)
    assert len(nodes) == n
    # Full metadata — `list_all_chunks` would have projected `keywords` away,
    # and a re-embed reading through it would silently degrade the project.
    assert nodes[0]["metadata"]["keywords"] == "k"
    assert nodes[0]["metadata"]["source"] == "a.pdf"
    assert nodes[0]["text"]

    # Pagination really pages (this is what a snapshot walks).
    if n > 1:
        first = store.list_all_nodes(limit=1, offset=0)
        second = store.list_all_nodes(limit=1, offset=1)
        assert first[0]["id"] != second[0]["id"]

    assert len(store.delete_source("a.pdf")) == n
    assert store.info() == 0


def test_live_delete_actually_drops_the_table():
    """`DROP TABLE IF EXISTS` on the wrong name is a silent no-op, so deleting
    a project used to leak its vectors forever."""
    from sqlalchemy import create_engine, text
    from llama_index.core.schema import Document
    from restai.vectordb.pgvector import _get_sync_connection_string
    from restai.vectordb.tools import index_documents_classic

    project, store = _live_store(990902)
    physical = store.physical_table

    def exists():
        eng = create_engine(_get_sync_connection_string())
        try:
            with eng.connect() as c:
                return c.execute(text(
                    "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public' AND tablename=:t"
                ), {"t": physical}).scalar() > 0
        finally:
            eng.dispose()

    # PGVectorStore creates the table lazily on first write, not on construction.
    index_documents_classic(
        project,
        [Document(text="pumpkins " * 30, metadata={"source": "b.pdf"})],
        "sentence", 64,
    )
    assert exists(), "ingest should have created the physical table"

    store.delete()
    assert not exists(), "delete() left the table behind"
