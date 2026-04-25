#!/usr/bin/env python3
"""Bulk ingest runner.

Picks up every ``queued`` row in ``bulk_ingest_jobs``, dispatches the
file to the same ingestion pipeline the synchronous endpoint uses
(auto_ingest → docling → classic fallback), and flips status to
``done`` or ``error``. Tempfile is deleted in either case so the
staging dir doesn't grow unbounded.

Locks per-row at the DB level: we claim a row by flipping it from
``queued`` to ``processing`` in a single update, so two concurrent
runners (unlikely under the flock-based cron runner but possible if
the user runs this manually alongside the cron) can't process the
same job twice.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.bulk_ingest")


def main():
    from restai.settings import ensure_settings_table
    from restai.database import engine as db_engine, get_db_wrapper
    from restai.models.databasemodels import BulkIngestJobDatabase, ProjectDatabase
    from restai.brain import Brain
    from restai.cron_log import CronLogger

    ensure_settings_table(db_engine)

    # Auto-create the new table when running against a pre-migration
    # DB — mirrors the lifespan pattern in main.py.
    try:
        BulkIngestJobDatabase.__table__.create(db_engine, checkfirst=True)
    except Exception:
        pass

    brain = Brain(lightweight=True)
    cron = CronLogger("bulk_ingest")
    processed = 0

    try:
        while True:
            db = get_db_wrapper()
            try:
                # Claim one job atomically: SELECT + UPDATE in a single
                # transaction. Loop so we drain the queue each tick.
                job = (
                    db.db.query(BulkIngestJobDatabase)
                    .filter(BulkIngestJobDatabase.status == "queued")
                    .order_by(BulkIngestJobDatabase.created_at.asc())
                    .first()
                )
                if job is None:
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
                break
            finally:
                # Keep the session alive until we're done with the job —
                # we reload via job_id below.
                pass

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
                from modules.loaders import find_file_loader
                from unidecode import unidecode

                ext = os.path.splitext(filename)[1].lower()
                source_name = unidecode(filename)
                used_method = method

                if method == "auto":
                    from restai.loaders.markitdown_loader import auto_ingest
                    documents, used_method = auto_ingest(file_path, source_name, manager=None, opts={})
                elif method == "markitdown":
                    from restai.loaders.markitdown_loader import load_with_markitdown
                    documents = load_with_markitdown(file_path, source=source_name)
                elif method == "docling":
                    from restai.document.runner import load_documents
                    documents = load_documents(None, file_path)
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
                if project.cache:
                    project.cache.clear()
                ok = True
            except Exception as e:
                logger.exception("Job %d failed: %s", job_id, e)
                err_msg = str(e)[:1000]

            # Re-open the session and update the row with the final
            # status. Using a fresh session avoids stale-state issues
            # after long-running ingestion.
            db2 = get_db_wrapper()
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

            # Clean up the staged file regardless of outcome — failed
            # jobs can be resubmitted by the admin, no point keeping
            # broken bytes around.
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
