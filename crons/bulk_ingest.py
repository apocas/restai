#!/usr/bin/env python3
"""Bulk ingest runner. Drains queued bulk_ingest_jobs.

Per-row claim (queued → processing in one txn) so concurrent runners
can't pick up the same job — flock cron usually prevents overlap, but
manual invocation alongside the cron can race.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.bulk_ingest")



# A job claimed by a runner that was then killed (OOM, deploy, the runner's
# own per-job timeout) stays `processing` forever: the terminal status is only
# written after the work finishes. Nothing ever reclaimed those rows, so the
# UI showed "processing" indefinitely and the staged file leaked. Anything
# older than this is considered abandoned and reset to `queued` for one retry.
STALE_PROCESSING_SECONDS = 4 * 3600


def _reclaim_stalled_jobs(db, BulkIngestJobDatabase, cron) -> None:
    """Requeue jobs abandoned mid-flight, and delete their orphaned files."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSING_SECONDS)
    try:
        stalled = (
            db.db.query(BulkIngestJobDatabase)
            .filter(
                BulkIngestJobDatabase.status == "processing",
                BulkIngestJobDatabase.started_at.isnot(None),
                BulkIngestJobDatabase.started_at < cutoff,
            )
            .all()
        )
        for job in stalled:
            # Only worth retrying while the staged file still exists.
            if job.file_path and os.path.exists(job.file_path):
                job.status = "queued"
                job.started_at = None
                logger.warning("Requeued stalled bulk-ingest job %s", job.id)
            else:
                job.status = "error"
                job.error_message = "Abandoned mid-processing; staged file is gone."
                job.completed_at = datetime.now(timezone.utc)
                logger.warning("Failed stalled bulk-ingest job %s (file missing)", job.id)
        if stalled:
            db.db.commit()
            cron.warning(f"Reclaimed {len(stalled)} stalled job(s)")
    except Exception as e:
        logger.warning("Stalled-job reclaim failed: %s", e)

    _purge_orphan_staged_files(db, BulkIngestJobDatabase)


def _purge_orphan_staged_files(db, BulkIngestJobDatabase) -> None:
    """Delete staged files with no live job row (leaked by crashes/kills)."""
    from restai import config as _config

    queue_dir = os.path.abspath(_config.UPLOAD_STAGING_PATH or "")
    if not queue_dir or not os.path.isdir(queue_dir):
        return
    try:
        known = {
            row.file_path
            for row in db.db.query(BulkIngestJobDatabase.file_path).filter(
                BulkIngestJobDatabase.status.in_(("queued", "processing"))
            )
            if row.file_path
        }
    except Exception:
        return

    cutoff = time.time() - STALE_PROCESSING_SECONDS
    for name in os.listdir(queue_dir):
        path = os.path.join(queue_dir, name)
        if path in known:
            continue
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.unlink(path)
                logger.info("Removed orphaned staged upload %s", path)
        except OSError:
            pass


_MANAGER = None
_MANAGER_TRIED = False


def _get_manager():
    """Lazily start the docling worker's multiprocessing manager.

    Both docling paths need one: `load_documents` calls `manager.dict()`
    outright, and `auto_ingest` silently skips docling when handed None. The
    queue used to pass None to both, so `method=docling` raised AttributeError
    on every job and `method=auto` never tried docling at all — the queue
    quietly ingested at a lower fidelity than the synchronous endpoint.

    Started lazily so a runner tick that has no docling work (or no queued jobs
    at all) doesn't pay for a spawned Manager process every minute.
    """
    global _MANAGER, _MANAGER_TRIED
    if _MANAGER is None and not _MANAGER_TRIED:
        _MANAGER_TRIED = True
        try:
            from restai.multiprocessing import get_manager

            _MANAGER = get_manager()
        except Exception as e:
            logger.warning("Could not start multiprocessing manager: %s", e)
            _MANAGER = None
    return _MANAGER


def main():
    from restai.settings import ensure_settings_table
    from restai.database import engine as db_engine, open_db_wrapper
    from restai.models.databasemodels import BulkIngestJobDatabase
    from restai.brain import Brain
    from restai.observability.cron_log import CronLogger

    ensure_settings_table(db_engine)

    # Auto-create on pre-migration DBs (mirrors lifespan pattern in main.py).
    try:
        BulkIngestJobDatabase.__table__.create(db_engine, checkfirst=True)
    except Exception:
        pass

    brain = Brain(lightweight=True)
    cron = CronLogger("bulk_ingest")
    processed = 0
    reclaimed = False


    try:
        while True:
            db = open_db_wrapper()
            try:
                if not reclaimed:
                    # Piggy-backs on this iteration's session rather than
                    # opening its own.
                    _reclaim_stalled_jobs(db, BulkIngestJobDatabase, cron)
                    reclaimed = True
                # Claim one job atomically (SELECT + UPDATE in one txn); loop drains queue.
                job = (
                    db.db.query(BulkIngestJobDatabase)
                    .filter(BulkIngestJobDatabase.status == "queued")
                    .order_by(BulkIngestJobDatabase.created_at.asc())
                    .first()
                )
                if job is None:
                    db.db.close()
                    break
                job.status = "processing"
                job.started_at = datetime.now(timezone.utc)
                db.db.commit()
                job_id = job.id
                project_id = job.project_id
                file_path = job.file_path
                filename = job.filename
                method = job.method or "auto"
                splitter = job.splitter or "sentence"
                chunks = int(job.chunks or 256)
            except Exception as e:
                logger.exception("Failed to claim next job: %s", e)
                # Both `break` paths close the session explicitly — the drain
                # loop only reaches its own `db.db.close()` on the success
                # path, so bailing out here used to leak a pooled connection
                # per tick.
                try:
                    db.db.close()
                except Exception:
                    pass
                break

            logger.info(f"Processing job {job_id}: {filename} (project={project_id}, method={method})")
            ok = False
            err_msg = None
            docs_count = 0
            chunks_count = 0

            try:
                if not os.path.isfile(file_path):
                    raise RuntimeError(f"staged file missing: {file_path}")

                project = brain.find_project(project_id, db)
                if project is None:
                    raise RuntimeError(f"project {project_id} not found")
                if project.props.type != "rag":
                    raise RuntimeError("project is not RAG type")

                from pathlib import Path
                from restai.vectordb.tools import (
                    index_documents_classic,
                    index_documents_docling,
                    extract_keywords_for_metadata,
                )
                from restai.vectordb.tools import find_file_loader
                from restai import reembed
                from unidecode import unidecode

                ext = os.path.splitext(filename)[1].lower()
                source_name = unidecode(filename)
                used_method = method

                if method == "auto":
                    from restai.loaders.auto_ingest import auto_ingest
                    documents, used_method = auto_ingest(
                        file_path, source_name, manager=_get_manager(), opts={}
                    )
                elif method == "markitdown":
                    from restai.loaders.auto_ingest import load_with_markitdown
                    documents = load_with_markitdown(file_path, source=source_name)
                elif method == "docling":
                    from restai.document.runner import load_documents
                    manager = _get_manager()
                    if manager is None:
                        raise RuntimeError(
                            "docling requires a multiprocessing manager, which this "
                            "runner could not start; retry with method=auto"
                        )
                    documents = load_documents(manager, file_path)
                else:
                    used_method = "classic"
                    loader = find_file_loader(ext, {})
                    try:
                        documents = loader.load_data(file=Path(file_path))
                    except TypeError:
                        documents = loader.load_data(input_file=Path(file_path))

                if not documents:
                    raise RuntimeError("No content could be extracted from the file")

                documents = extract_keywords_for_metadata(documents)
                for document in documents:
                    if "filename" in document.metadata:
                        del document.metadata["filename"]
                    document.metadata["source"] = source_name

                if used_method in ("markitdown", "docling"):
                    chunks_count = index_documents_docling(project, documents)
                else:
                    chunks_count = index_documents_classic(project, documents, splitter, chunks)

                docs_count = len(documents)
                project.vector.save()
                reembed.stamp_indexed_embedding(project, db)
                ok = True
            except Exception as e:
                logger.exception("Job %d failed: %s", job_id, e)
                err_msg = str(e)[:1000]

            # Fresh session for finalization — avoids stale state after long ingest.
            db2 = open_db_wrapper()
            try:
                j = db2.db.query(BulkIngestJobDatabase).filter(BulkIngestJobDatabase.id == job_id).first()
                if j is not None:
                    j.status = "done" if ok else "error"
                    j.completed_at = datetime.now(timezone.utc)
                    if ok:
                        j.documents_count = docs_count
                        j.chunks_count = chunks_count
                    else:
                        j.error_message = err_msg
                    db2.db.commit()
            except Exception as e:
                logger.exception("Failed to finalize job %d: %s", job_id, e)
            finally:
                db2.db.close()

            try:
                os.unlink(file_path)
            except OSError:
                pass

            processed += 1
            try:
                db.db.close()
            except Exception:
                pass
            cron.info(f"Job {job_id} finished: {'ok' if ok else 'error'}")

        cron.finish(items_processed=processed)
    except Exception as e:
        cron.error(f"Bulk ingest runner crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()


if __name__ == "__main__":
    main()
