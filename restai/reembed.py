"""Re-embed a RAG project's knowledge base into a different embeddings model.

Changing `projects.embeddings` used to leave the vector store full of vectors
computed by the OLD model. When the dimension changed that surfaced as an
opaque 500; when it didn't, similarity scores were quietly meaningless and the
project answered as though its knowledge base were empty. Neither was
recoverable, because every ingest path deletes its source bytes.

It IS recoverable from the store itself: `StorageContext.from_defaults()` is
called without `persist_dir` everywhere, so no side docstore exists and the
vector store is authoritative for the chunk text. This module re-embeds that
text rather than re-ingesting from files nobody kept.

Four phases, in order, tracked on the job row so a crash is resumable:

1. ``snapshotting`` — page every chunk out to a JSONL file. Non-destructive;
   nothing is touched until this file is complete.
2. verify — cross-check the snapshot against ``info()``. **This is the check
   that makes the feature safe.** `WeaviateDB` and `PineconeDB` historically
   swallowed read errors and returned partial results, and Pinecone's
   `list()` is serverless-only, so "the store is empty" and "the read failed"
   look identical. Destroying a store on that evidence would lose everything.
3. ``resetting`` — rebind to the new embedding and drop/recreate the store,
   which is what lets a new dimension take effect.
4. ``rebuilding`` — stream the snapshot back in batches.

Chunk boundaries are preserved exactly. Re-splitting is not an option anyway:
the original documents are gone, so only the existing chunks exist to re-embed.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("restai.reembed")

# A job in either state owns the project's vector store; nothing else may read
# or write it. Used by the serving guards and by the enqueue 409.
OPEN_STATUSES = ("queued", "processing")

PHASE_SNAPSHOT = "snapshotting"
PHASE_RESET = "resetting"
PHASE_REBUILD = "rebuilding"

# How many chunks to pull per read page and to embed per insert batch. Chunks
# are small; the ceiling that matters is the embedding provider's per-request
# batch limit, which llama-index handles internally.
PAGE_SIZE = 500
BATCH_SIZE = 100

# Chunks sampled to estimate an average token length. The estimate feeds a
# confirmation dialog, so it must be fast — never scan the whole store for it.
ESTIMATE_SAMPLE = 200

# Keys llama-index writes into chunk metadata for its own bookkeeping. They
# describe the node we are about to replace, so they must not be carried onto
# the new one. `find_id` already filters `_`-prefixed keys on read for the
# same reason.
_INTERNAL_METADATA_KEYS = ("doc_id", "ref_doc_id", "document_id")


def _strip_internal_metadata(metadata: dict) -> dict:
    """User metadata only — `source`, `keywords`, loader-supplied keys.

    Everything llama-index adds is dropped: it is regenerated on insert, and
    keeping a stale `_node_content` would describe the old node rather than
    the new one.

    The alternative was `vector_stores.utils.metadata_dict_to_node`, which
    rebuilds the original node from `_node_content` and — verified against the
    pinned llama-index — does preserve `id_`. It is not used here: it would
    carry a serialized copy of every node through the snapshot to buy stable
    chunk ids, and nothing depends on those surviving a migration
    (`retrieval_events.chunk_id` is a historical log keyed on `source`, and
    `kg_entity_mentions` keys on `source` alone). User metadata round-trips
    identically either way, which is the part that affects retrieval."""
    return {
        k: v
        for k, v in (metadata or {}).items()
        if not k.startswith("_") and k not in _INTERNAL_METADATA_KEYS
    }


# --------------------------------------------------------------------------
# Job lookup — used by the routers, the serving guards and the sync cron
# --------------------------------------------------------------------------

def get_active_job(project_id: int, db):
    """The project's open re-embed job, if any."""
    from restai.models.databasemodels import ReembedJobDatabase

    try:
        return (
            db.db.query(ReembedJobDatabase)
            .filter(
                ReembedJobDatabase.project_id == int(project_id),
                ReembedJobDatabase.status.in_(OPEN_STATUSES),
            )
            .order_by(ReembedJobDatabase.created_at.asc())
            .first()
        )
    except Exception:
        # A missing table (pre-migration DB) must not take down chat.
        logger.debug("reembed: active-job lookup failed", exc_info=True)
        return None


def is_migrating(project_id: int, db) -> bool:
    return get_active_job(project_id, db) is not None


def migration_detail(job) -> str:
    """Message for the 503 raised by every knowledge path while a job is open."""
    return (
        f"Knowledge base is being re-embedded into '{job.to_embeddings}'. "
        "Retrieval and ingestion are unavailable until the migration completes."
    )


def raise_if_migrating(project_id: int, db) -> None:
    """503 while a migration owns this project's vector store.

    Blocking *reads* keeps callers from seeing a partially-rebuilt store.
    Blocking *writes* is a correctness requirement, not politeness: an ingest
    landing between the snapshot and the reset would be captured by neither
    and silently lost."""
    from fastapi import HTTPException

    job = get_active_job(project_id, db)
    if job is not None:
        raise HTTPException(status_code=503, detail=migration_detail(job))


# --------------------------------------------------------------------------
# Snapshot storage
# --------------------------------------------------------------------------

def snapshot_dir() -> str:
    """Directory holding in-flight snapshots.

    Under `UPLOAD_STAGING_PATH` rather than `$TMPDIR`, for a reason that
    differs from bulk ingest's. There, the API writes the file and the cron
    reads it, so the two containers must share a volume. Here the cron does
    both — but the path still has to survive BETWEEN cron invocations, which
    is what makes a crashed job resumable, and under Helm the cron is a
    CronJob pod whose local disk is gone on the next run."""
    from restai import config

    base = os.path.abspath(config.UPLOAD_STAGING_PATH or "./data")
    target = os.path.join(base, "reembed")
    os.makedirs(target, exist_ok=True)
    return target


def snapshot_path_for(job_id: int) -> str:
    return os.path.join(snapshot_dir(), f"job{int(job_id)}.jsonl")


def purge_orphan_snapshots(db) -> None:
    """Delete snapshots with no job row still referencing them — e.g. the
    project was deleted mid-migration and the row cascaded away.

    Keyed on `status != "done"`, deliberately NOT on `OPEN_STATUSES`. A job
    that failed after the reset has an `error` row whose snapshot is the only
    surviving copy of that knowledge base; purging it because the job is no
    longer "open" would destroy exactly what `finish_job` went out of its way
    to keep. Only a `done` job's snapshot is disposable — and `finish_job`
    has already unlinked that one."""
    from restai.models.databasemodels import ReembedJobDatabase

    try:
        directory = snapshot_dir()
    except Exception:
        return
    try:
        known = {
            row.snapshot_path
            for row in db.db.query(ReembedJobDatabase.snapshot_path).filter(
                ReembedJobDatabase.status != "done"
            )
            if row.snapshot_path
        }
    except Exception:
        return

    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if path in known or not os.path.isfile(path):
            continue
        try:
            os.unlink(path)
            logger.info("reembed: removed orphaned snapshot %s", path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------

def check_compatibility(vectorstore: Optional[str], from_dimension, to_dimension) -> dict:
    """Can this backend hold vectors of the target dimension for this project?

    Only Pinecone genuinely cannot: every RESTai project shares one index
    (`PINECONE_INDEX`) whose dimension is fixed when the index is created, and
    `delete(delete_all=True, namespace=...)` clears only the namespace inside
    it. Chroma, pgvector and Weaviate all drop and recreate their own store in
    `reset()`, which is exactly what a dimension change needs.
    """
    store = (vectorstore or "chroma").lower()
    changed = (
        from_dimension is not None
        and to_dimension is not None
        and int(from_dimension) != int(to_dimension)
    )

    if store == "pinecone" and changed:
        return {
            "compatible": False,
            "dimension_change": True,
            "reason": (
                f"Pinecone stores every project in one index with a fixed dimension "
                f"({from_dimension}). Moving to a {to_dimension}-dimension model needs a "
                f"new Pinecone index, which an administrator must create and point "
                f"RESTai at before this migration can run."
            ),
        }

    return {"compatible": True, "dimension_change": changed, "reason": None}


def estimate_reembed(project, to_embedding_props, db) -> dict:
    """Chunk count, token estimate and USD cost for migrating `project`.

    Samples rather than scanning: this is served synchronously to a
    confirmation dialog, and the billed figure comes from the real text as
    each batch is embedded anyway."""
    from restai.tools import tokens_from_string

    vector = getattr(project, "vector", None)
    chunks = int(vector.info() or 0) if vector else 0

    avg_tokens = 0.0
    if vector and chunks:
        try:
            sample = vector.list_all_nodes(limit=min(ESTIMATE_SAMPLE, chunks), offset=0)
        except Exception:
            sample = []
        if sample:
            total = 0
            for node in sample:
                text = node.get("text") or ""
                try:
                    total += tokens_from_string(text)
                except Exception:
                    total += len(text) // 4
            avg_tokens = total / len(sample)

    tokens = int(round(avg_tokens * chunks))
    rate = float(getattr(to_embedding_props, "input_cost", 0.0) or 0.0)

    compat = check_compatibility(
        getattr(project.props, "vectorstore", None),
        dimension_of(project.props.embeddings, db),
        getattr(to_embedding_props, "dimension", None),
    )

    return {
        "chunks": chunks,
        "tokens": tokens,
        "cost": tokens * rate / 1_000_000,
        "sampled": bool(avg_tokens),
        **compat,
    }


def dimension_of(embedding_name, db):
    if not embedding_name:
        return None
    try:
        row = db.get_embedding_by_name(embedding_name)
        return getattr(row, "dimension", None) if row else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# The phase machine
# --------------------------------------------------------------------------

class ReembedError(Exception):
    """Terminal failure — the job row is marked `error` with this message."""


# Phases from which the store may already have been emptied. A job resuming
# in one of these must NOT snapshot again: the reset has possibly run, so it
# would capture an empty or partial store and — because the snapshot is the
# only surviving copy of the knowledge base — overwrite the good one with it.
_POST_DESTRUCTIVE_PHASES = (PHASE_RESET, PHASE_REBUILD)


def _write_snapshot(vector, path: str) -> int:
    """Page the whole store out to JSONL. Returns the number of chunks written.

    Written to a temp file and renamed, so a crash mid-write can never leave a
    truncated snapshot that would later read as a complete (but short) one."""
    if os.path.exists(path):
        # Belt-and-braces: callers already gate on `phase`, but overwriting an
        # existing snapshot is unrecoverable, so refuse it outright rather
        # than trusting every future caller to get the gating right.
        raise ReembedError(
            f"Refusing to overwrite an existing snapshot at {path}. "
            "It is the only copy of this knowledge base outside the vector store."
        )
    tmp = path + ".partial"
    written = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        offset = 0
        while True:
            page = vector.list_all_nodes(limit=PAGE_SIZE, offset=offset)
            if not page:
                break
            for node in page:
                fh.write(json.dumps({
                    "id": node.get("id"),
                    "text": node.get("text") or "",
                    "metadata": _strip_internal_metadata(node.get("metadata")),
                }, ensure_ascii=False) + "\n")
                written += 1
            if len(page) < PAGE_SIZE:
                break
            offset += len(page)
    os.replace(tmp, path)
    return written


def _iter_snapshot(path: str, skip: int = 0):
    """Yield `{id, text, metadata}` from the snapshot, skipping the first
    `skip` lines so a resumed job re-embeds only what it has not already."""
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < skip:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                logger.warning("reembed: skipping malformed snapshot line %s in %s", i, path)


def run_job(job, brain, db) -> None:
    """Drive one job to completion. Raises `ReembedError` on terminal failure.

    Callers are responsible for the status/timestamp bookkeeping; this
    function owns `phase`, `chunks_total`, `chunks_done` and the vector store.
    """
    from restai.limits import accounting
    from restai.tools import tokens_from_string
    from restai.vectordb import tools as vector_tools
    from llama_index.core.schema import TextNode

    project = brain.find_project(job.project_id, db)
    if project is None:
        raise ReembedError("Project no longer exists.")
    if project.props.type != "rag":
        raise ReembedError("Only RAG projects have a knowledge base to re-embed.")

    snapshot = job.snapshot_path or snapshot_path_for(job.id)

    # ---- phases 1+2: snapshot and verify ---------------------------------
    # Skipped once the job has reached a phase from which the store may
    # already have been emptied. Re-running them there would read back the
    # reset (or half-rebuilt) store and overwrite the snapshot — the only
    # surviving copy of the knowledge base — with that. Note this covers
    # `resetting` as well as `rebuilding`: a crash in the window between
    # setting `resetting` and completing the reset leaves a job whose store
    # state is unknown, and "unknown" must be treated as already destroyed.
    if job.phase not in _POST_DESTRUCTIVE_PHASES:
        if project.vector is None:
            raise ReembedError(
                "Vector store is unavailable, so its contents cannot be read back. "
                "Check that the vector database is reachable and retry."
            )

        job.phase = PHASE_SNAPSHOT
        job.snapshot_path = snapshot
        db.db.commit()

        reported = int(project.vector.info() or 0)
        written = _write_snapshot(project.vector, snapshot)

        # The whole safety argument lives here. Anything less than an exact
        # match means we do not actually know what is in the store, and the
        # next step destroys it.
        if written != reported:
            raise ReembedError(
                f"Read back {written} chunks but the vector store reports {reported}. "
                "Refusing to migrate — the knowledge base has been left untouched. "
                "This usually means the vector database is unreachable or, on "
                "Pinecone, that the index is pod-based (id listing is "
                "serverless-only)."
            )
        if reported == 0:
            # `written == reported == 0` is the one ambiguous outcome. It is
            # still SAFE — nothing has been destroyed — but the message must
            # not assert "empty", because `WeaviateDB.info` and
            # `PineconeDB.info` both `return 0` from their except branch, so
            # an outage reads the same as an empty store.
            raise ReembedError(
                "Read back no chunks, so nothing was changed. Likely causes: the "
                "cron cannot see the same vector store as the API (on the local "
                "Chroma backend, EMBEDDINGS_PATH must be a volume shared by both, "
                "or use a remote Chroma server); the vector database is unreachable "
                "(Weaviate and Pinecone both report a count of 0 when the query "
                "fails); this is a pod-based Pinecone index, where id listing is "
                "unavailable; or the knowledge base is genuinely empty."
            )

        job.chunks_total = written
        job.chunks_done = 0
        db.db.commit()

    elif not os.path.exists(snapshot):
        # Resumed past the point of no return with the snapshot gone. The
        # store has been reset (and possibly partly rebuilt), so there is
        # nothing left to read and nothing to replay from. Fail loudly rather
        # than pretend — a silent "success" here would leave an empty or
        # partial knowledge base looking migrated.
        raise ReembedError(
            "Snapshot file is missing and the knowledge base has already been reset, "
            "so the migration cannot be resumed. Configure durable staging storage "
            "(Helm: uploadStaging.enabled=true) and re-ingest the affected sources."
        )

    # ---- phase 3: reset --------------------------------------------------
    # Rebind to the TARGET embedding before resetting, so the store is
    # recreated at the new dimension.
    target = brain.get_embedding(job.to_embeddings, db)
    if target is None:
        raise ReembedError(f"Embedding model '{job.to_embeddings}' not found.")

    project.props.embeddings = job.to_embeddings
    project.vector = vector_tools.find_vector_db(project)(brain, project, target)

    # Re-running the reset on a job resumed at `resetting` is safe and
    # deliberate: chunks are only written in the rebuild phase, and `phase`
    # flips to `rebuilding` before the first one lands, so a job still marked
    # `resetting` has `chunks_done == 0` and nothing to lose. Skipping it once
    # `rebuilding` is what protects the chunks already written.
    if job.phase != PHASE_REBUILD:
        job.phase = PHASE_RESET
        db.db.commit()
        project.vector.reset(brain)
        job.phase = PHASE_REBUILD
        db.db.commit()

    # ---- phase 4: rebuild ------------------------------------------------
    done = int(job.chunks_done or 0)
    batch: list = []
    batch_tokens = 0

    def _flush():
        nonlocal batch, batch_tokens, done
        if not batch:
            return
        project.vector.index.insert_nodes(batch)
        done += len(batch)
        job.chunks_done = done
        job.tokens_embedded = int(job.tokens_embedded or 0) + batch_tokens
        # Charged per batch, so a job that dies halfway bills only what it
        # actually spent and a resumed one does not double-charge.
        job.cost = float(job.cost or 0.0) + accounting.log_embedding_usage(
            db, project, target.props, batch_tokens,
            f"(reembed:{job.from_embeddings or 'none'}->{job.to_embeddings})",
            user_id=job.user_id,
        )
        db.db.commit()
        batch = []
        batch_tokens = 0

    for record in _iter_snapshot(snapshot, skip=done):
        text = record.get("text") or ""
        batch.append(TextNode(text=text, metadata=record.get("metadata") or {}))
        try:
            batch_tokens += tokens_from_string(text)
        except Exception:
            batch_tokens += len(text) // 4
        if len(batch) >= BATCH_SIZE:
            _flush()
    _flush()

    # Point the project at the model its vectors are now built with, and stamp
    # the provenance in the same write.
    #
    # The project-edit path already wrote `embeddings` before enqueueing, so
    # this is a no-op there. The standalone `POST /reembed` path did NOT —
    # without this, that route would leave the store full of new-model vectors
    # while the project kept querying with the old model, which is precisely
    # the failure this whole feature exists to remove, just inverted.
    row = db.get_project_by_id(project.props.id)
    if row is not None:
        row.embeddings = job.to_embeddings
        row.embeddings_indexed = job.to_embeddings
        db.db.commit()


def stamp_indexed_embedding(project, db) -> None:
    """Record which embedding model the project's stored vectors were built
    with. Called after every ingest and after a completed migration.

    Best-effort: failing to stamp costs a stale-looking banner, never data."""
    try:
        row = db.get_project_by_id(project.props.id)
        if row is not None and row.embeddings_indexed != project.props.embeddings:
            row.embeddings_indexed = project.props.embeddings
            db.db.commit()
    except Exception:
        logger.debug("reembed: embeddings_indexed stamp failed", exc_info=True)


def finish_job(job, db, error: Optional[str] = None) -> None:
    """Terminal bookkeeping. The snapshot is deleted only on success — on
    failure it is the surviving copy of the knowledge base."""
    job.completed_at = datetime.now(timezone.utc)
    if error:
        job.status = "error"
        job.error_message = error[:4000]
    else:
        job.status = "done"
        job.phase = None
        if job.snapshot_path:
            try:
                os.unlink(job.snapshot_path)
            except OSError:
                pass
    db.db.commit()
