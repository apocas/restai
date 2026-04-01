"""Knowledge Base Sync — background workers that periodically re-ingest external sources."""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone

from restai.database import get_db_wrapper

logger = logging.getLogger(__name__)

_workers: dict[int, "SyncWorker"] = {}
_workers_lock = threading.Lock()


class SyncWorker:
    """Background thread that periodically syncs external sources into a RAG project."""

    def __init__(self, project_id: int, app):
        self.project_id = project_id
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"sync-worker-{self.project_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Sync worker started for project {self.project_id}")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info(f"Sync worker stopped for project {self.project_id}")

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._sync_once()
            except Exception as e:
                logger.error(f"Sync error for project {self.project_id}: {e}")

            # Get current interval from DB (may have changed)
            interval = self._get_interval()
            if interval is None:
                break
            # Sleep in small increments so stop_event is responsive
            for _ in range(interval * 60):
                if self._stop_event.is_set():
                    return
                self._stop_event.wait(1)

    def _get_interval(self):
        try:
            db = get_db_wrapper()
            from restai.models.databasemodels import ProjectDatabase
            proj = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == self.project_id).first()
            if not proj:
                return None
            opts = json.loads(proj.options) if proj.options else {}
            db.db.close()
            return opts.get("sync_interval") or 60
        except Exception:
            return 60

    def _sync_once(self):
        db = get_db_wrapper()
        try:
            project = self.app.state.brain.find_project(self.project_id, db)
            if not project or project.props.type != "rag":
                return

            opts = project.props.options
            sources = opts.sync_sources if opts else None
            if not sources:
                return

            logger.info(f"Syncing project {self.project_id}: {len(sources)} sources")
            for source in sources:
                try:
                    _sync_source(project, source, db)
                except Exception as e:
                    logger.error(f"Failed to sync source '{source.name}' for project {self.project_id}: {e}")

            # Update last_sync timestamp
            from restai.models.databasemodels import ProjectDatabase
            proj_db = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == self.project_id).first()
            if proj_db:
                current_opts = json.loads(proj_db.options) if proj_db.options else {}
                current_opts["last_sync"] = datetime.now(timezone.utc).isoformat()
                proj_db.options = json.dumps(current_opts)
                db.db.commit()

            logger.info(f"Sync completed for project {self.project_id}")
        finally:
            db.db.close()


def _sync_source(project, source, db):
    """Sync a single SyncSource into the project's knowledge base."""
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata

    if source.type == "url":
        _sync_url(project, source, db)
    elif source.type == "s3":
        _sync_s3(project, source, db)
    else:
        logger.warning(f"Unknown sync source type: {source.type}")


def _sync_url(project, source, db):
    """Sync a web URL source."""
    from restai.loaders.url import SeleniumWebReader
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata

    logger.info(f"Syncing URL source '{source.name}': {source.url}")

    loader = SeleniumWebReader()
    documents = loader.load_data(urls=[source.url])
    documents = extract_keywords_for_metadata(documents)

    # Set source metadata
    for doc in documents:
        doc.metadata["source"] = source.name

    # Delete old and re-ingest
    if project.vector:
        try:
            deleted = project.vector.delete_source(source.name)
            logger.info(f"Deleted {len(deleted) if deleted else 0} old chunks for source '{source.name}'")
        except Exception as e:
            logger.warning(f"Failed to delete old chunks for source '{source.name}': {e}")
    n_chunks = index_documents_classic(project, documents, source.splitter, source.chunks)
    project.vector.save()
    logger.info(f"URL source '{source.name}' synced: {len(documents)} documents, {n_chunks} chunks")


def _sync_s3(project, source, db):
    """Sync files from an S3 bucket."""
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata
    from modules.loaders import find_file_loader

    try:
        import boto3
    except ImportError:
        raise RuntimeError("boto3 is required for S3 sync. Install with: pip install boto3")

    logger.info(f"Syncing S3 source '{source.name}': s3://{source.s3_bucket}/{source.s3_prefix or ''}")

    client_kwargs = {}
    if source.s3_region:
        client_kwargs["region_name"] = source.s3_region
    if source.s3_access_key and source.s3_secret_key:
        client_kwargs["aws_access_key_id"] = source.s3_access_key
        client_kwargs["aws_secret_access_key"] = source.s3_secret_key

    s3 = boto3.client("s3", **client_kwargs)

    # List objects
    list_kwargs = {"Bucket": source.s3_bucket}
    if source.s3_prefix:
        list_kwargs["Prefix"] = source.s3_prefix

    all_documents = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(**list_kwargs):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue  # skip directories

            ext = os.path.splitext(key)[1].lower()
            loader_cls = find_file_loader(ext)
            if loader_cls is None:
                logger.debug(f"Skipping unsupported file type: {key}")
                continue

            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                s3.download_fileobj(source.s3_bucket, key, tmp)
                tmp_path = tmp.name

            try:
                loader = loader_cls()
                docs = loader.load_data(file=tmp_path)
                doc_source = f"{source.name}/{os.path.basename(key)}"
                for doc in docs:
                    doc.metadata["source"] = doc_source
                docs = extract_keywords_for_metadata(docs)
                all_documents.extend(docs)
            finally:
                os.unlink(tmp_path)

    if not all_documents:
        logger.info(f"S3 source '{source.name}': no documents found")
        return

    # Delete old source docs and re-ingest
    if project.vector:
        try:
            # Delete all docs whose source starts with this sync source name
            existing_sources = project.vector.list()
            for src in existing_sources:
                if src == source.name or src.startswith(f"{source.name}/"):
                    project.vector.delete_source(src)
        except Exception:
            pass

    n_chunks = index_documents_classic(project, all_documents, source.splitter, source.chunks)
    project.vector.save()
    logger.info(f"S3 source '{source.name}' synced: {len(all_documents)} documents, {n_chunks} chunks")


# --- Global registry ---

def start_sync(project_id: int, app):
    with _workers_lock:
        if project_id in _workers:
            _workers[project_id].stop()
        worker = SyncWorker(project_id, app)
        _workers[project_id] = worker
        worker.start()


def stop_sync(project_id: int):
    with _workers_lock:
        worker = _workers.pop(project_id, None)
        if worker:
            worker.stop()


def stop_all_syncs():
    with _workers_lock:
        for worker in _workers.values():
            worker.stop()
        _workers.clear()


def is_sync_running(project_id: int) -> bool:
    with _workers_lock:
        return project_id in _workers


def run_sync_now(project_id: int, app):
    """Run a one-off sync in a background thread (for manual trigger)."""
    def _run():
        db = get_db_wrapper()
        try:
            project = app.state.brain.find_project(project_id, db)
            if not project or project.props.type != "rag":
                return
            opts = project.props.options
            sources = opts.sync_sources if opts else None
            if not sources:
                return
            for source in sources:
                try:
                    _sync_source(project, source, db)
                except Exception as e:
                    logger.error(f"Manual sync failed for source '{source.name}': {e}")

            # Update last_sync
            from restai.models.databasemodels import ProjectDatabase
            proj_db = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == project_id).first()
            if proj_db:
                current_opts = json.loads(proj_db.options) if proj_db.options else {}
                current_opts["last_sync"] = datetime.now(timezone.utc).isoformat()
                proj_db.options = json.dumps(current_opts)
                db.db.commit()
        finally:
            db.db.close()

    threading.Thread(target=_run, name=f"sync-manual-{project_id}", daemon=True).start()
