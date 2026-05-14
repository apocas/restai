"""Per-project conversation-history vector index, used by the
`search_memories` builtin tool.

The embedding model is resolved via the project's ``embeddings`` field
(same as RAG), so quality matches whatever the admin already configured.
Indexing is gated on that embedding being set; the tool returns a clear
ERROR if it isn't.

Backend selection mirrors ``restai/vectordb/chromadb.py:_get_client``:

- ``CHROMADB_HOST`` set → ``chromadb.HttpClient`` against a remote Chroma
  server. All projects share that one connection; isolation is via
  collection name.
- Otherwise → ``chromadb.PersistentClient`` rooted at
  ``<EMBEDDINGS_PATH>/_memory/``. Local SQLite-backed Chroma.

Indexed documents are individual `OutputDatabase` rows (every Q/A turn).
Document id = ``str(output_id)`` so re-running the indexer is idempotent
via Chroma's upsert. Per-document metadata: ``chat_id``, ``date_iso``,
``output_id``. Collection-level metadata tracks
``last_indexed_output_id`` and ``embedding_model`` so the cron can
resume incrementally across ticks AND detect a model swap (drop +
rebuild the collection in that case).
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

import chromadb

from restai.config import EMBEDDINGS_PATH
import restai.config as _cfg

logger = logging.getLogger(__name__)

# One client per (mode, path) within a worker process. Without this,
# multiple connections to the same Chroma SQLite race for the lock.
# Remote mode reuses a single key.
_client_cache: dict[str, object] = {}

_REMOTE_CACHE_KEY = "__remote__"


def _store_path() -> str:
    """Local-mode root dir. Ignored when ``CHROMADB_HOST`` is set."""
    return os.path.join(EMBEDDINGS_PATH, "_memory")


def _legacy_project_dir(project_id: int) -> str:
    """Path used by an earlier per-project-subdir layout. Kept around
    purely so `delete_project` can sweep stale dirs left over from that
    layout — new code never writes there."""
    return os.path.join(_store_path(), str(int(project_id)))


def _get_client():
    """Return the Chroma client appropriate for the current deployment.

    Mirrors ``restai/vectordb/chromadb.py:_get_client`` so admins flipping
    the ``CHROMADB_HOST`` setting get the same behavior across RAG and
    memory search. `_cfg.X` reads the live DB value on every call."""
    host = _cfg.CHROMADB_HOST
    if host:
        cached = _client_cache.get(_REMOTE_CACHE_KEY)
        if cached is None:
            cached = chromadb.HttpClient(host=host, port=_cfg.CHROMADB_PORT)
            _client_cache[_REMOTE_CACHE_KEY] = cached
        return cached
    path = _store_path()
    cached = _client_cache.get(path)
    if cached is None:
        os.makedirs(path, exist_ok=True)
        cached = chromadb.PersistentClient(path=path)
        _client_cache[path] = cached
    return cached


def _collection_name(project_id: int) -> str:
    """Per-project collection name. Same in local and remote modes so
    we have a single code path for indexing / search / delete."""
    return f"memory_{int(project_id)}"


def _get_or_create_collection(project_id: int):
    # Cosine distance over Chroma's default L2 — works for both
    # normalized and unnormalized embeddings, and the score conversion
    # below stays sane (`score = 1 - distance`).
    return _get_client().get_or_create_collection(
        name=_collection_name(project_id),
        metadata={"hnsw:space": "cosine"},
    )


def get_collection(project_id: int):
    return _get_or_create_collection(project_id)


# Chroma collection metadata must be a flat dict of primitives. We stash
# the indexer's two pieces of state here so we don't need a sidecar DB
# table (and so the state is co-located with the data it describes —
# wiping the dir resets both).


def _read_meta(coll) -> dict:
    return dict(coll.metadata or {})


def _write_meta(coll, **patch) -> None:
    """Update writable metadata keys. Chroma forbids modifying hnsw:*
    keys after collection creation (e.g. distance space), so we strip
    those from the merged dict before calling `modify`."""
    meta = {k: v for k, v in _read_meta(coll).items() if not str(k).startswith("hnsw:")}
    meta.update(patch)
    coll.modify(metadata=meta)


def get_last_indexed_id(project_id: int) -> Optional[int]:
    coll = _get_or_create_collection(project_id)
    val = _read_meta(coll).get("last_indexed_output_id")
    return int(val) if val is not None else None


def set_last_indexed_id(project_id: int, output_id: int) -> None:
    coll = _get_or_create_collection(project_id)
    _write_meta(coll, last_indexed_output_id=int(output_id))


def get_indexed_embedding_model(project_id: int) -> Optional[str]:
    coll = _get_or_create_collection(project_id)
    return _read_meta(coll).get("embedding_model")


def set_indexed_embedding_model(project_id: int, name: str) -> None:
    coll = _get_or_create_collection(project_id)
    _write_meta(coll, embedding_model=name)


# ─── Index / search / delete ────────────────────────────────────────────


def index_turn(
    project_id: int,
    output_id: int,
    chat_id: Optional[str],
    question: str,
    answer: str,
    date_iso: str,
    embedding: list[float],
) -> None:
    """Idempotent — Chroma `upsert` keys on doc id so re-running the
    indexer over the same row is safe. Document text is the raw Q+A
    so the agent can quote the original turn in its reply. Caller is
    responsible for producing the embedding via the project's embedding
    model."""
    text = f"{(question or '').strip()}\n\n{(answer or '').strip()}".strip()
    if not text:
        return
    coll = _get_or_create_collection(project_id)
    coll.upsert(
        ids=[str(output_id)],
        embeddings=[embedding],
        documents=[text],
        metadatas=[{
            "output_id": int(output_id),
            "chat_id": chat_id or "",
            "date_iso": date_iso or "",
        }],
    )


def search(
    project_id: int,
    query_embedding: list[float],
    k: int,
) -> list[dict]:
    """Returns up to `k` hits sorted best-first as dicts:
    ``{output_id, chat_id, date_iso, document, score}``.
    Score is similarity in [0..1] (1 = identical) — Chroma returns
    cosine distances; we convert."""
    coll = _get_or_create_collection(project_id)
    if coll.count() == 0:
        return []
    n = max(1, min(int(k), coll.count()))
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out: list[dict] = []
    for i, doc_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        # Cosine distance ∈ [0, 2]: 0 = identical, 1 = orthogonal,
        # 2 = opposite. Most semantic hits land in [0, 1]. Convert to
        # an intuitive 0..1 similarity and clamp against numerical
        # jitter that can push slightly out of bounds.
        dist = float(dists[i]) if i < len(dists) else 0.0
        score = max(0.0, min(1.0, 1.0 - dist))
        out.append({
            "output_id": int(meta.get("output_id") or doc_id),
            "chat_id": meta.get("chat_id") or "",
            "date_iso": meta.get("date_iso") or "",
            "document": docs[i] if i < len(docs) else "",
            "score": score,
        })
    return out


def reset_collection(project_id: int) -> None:
    """Drop and recreate the collection — used when the project's
    embedding name changes (existing vectors are no longer dimensionally
    or semantically comparable to new ones, so the only honest answer
    is to rebuild)."""
    name = _collection_name(project_id)
    try:
        _get_client().delete_collection(name=name)
    except Exception:
        pass
    # `get_or_create` will rebuild on next access.


def delete_project(project_id: int) -> None:
    """Cascade-delete the project's memory index. Drops the collection
    on the active Chroma client (local or remote) and sweeps any stale
    per-project dir from a previous layout. Tolerates a missing
    collection so this is safe to call regardless of whether the
    project ever indexed anything."""
    name = _collection_name(project_id)
    try:
        _get_client().delete_collection(name=name)
    except Exception as e:
        # Collection-not-found is the common case here; log at debug
        # level so a project that never indexed doesn't pollute logs
        # on delete.
        logger.debug("memory_search: delete_collection(%s) failed: %s", name, e)
    # Local-mode legacy cleanup. Older versions stored per-project
    # subdirs under <root>/<project_id>/; if one exists, wipe it.
    # No-op for remote mode (the dir doesn't exist there).
    legacy = _legacy_project_dir(project_id)
    if os.path.isdir(legacy):
        try:
            shutil.rmtree(legacy, ignore_errors=True)
        except Exception as e:
            logger.warning("memory_search: legacy rmtree(%s) failed: %s", legacy, e)
