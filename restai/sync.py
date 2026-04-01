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
    elif source.type == "confluence":
        _sync_confluence(project, source, db)
    elif source.type == "sharepoint":
        _sync_sharepoint(project, source, db)
    elif source.type == "gdrive":
        _sync_gdrive(project, source, db)
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


def _sync_confluence(project, source, db):
    """Sync pages from a Confluence Cloud space."""
    import requests
    from llama_index.core.schema import Document
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata

    base_url = (source.confluence_base_url or "").rstrip("/")
    space_key = source.confluence_space_key
    email = source.confluence_email
    api_token = source.confluence_api_token

    if not base_url or not space_key or not email or not api_token:
        raise ValueError("Confluence source requires base_url, space_key, email, and api_token")

    logger.info(f"Syncing Confluence source '{source.name}': {base_url}/wiki/spaces/{space_key}")

    auth = (email, api_token)
    headers = {"Accept": "application/json"}

    # Fetch all pages in the space using v2 API with pagination
    all_documents = []
    url = f"{base_url}/wiki/api/v2/spaces/{space_key}/pages"
    params = {"limit": 50, "body-format": "storage"}

    while url:
        resp = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for page in data.get("results", []):
            title = page.get("title", "Untitled")
            body_html = page.get("body", {}).get("storage", {}).get("value", "")

            if not body_html:
                continue

            # Strip HTML tags for plain text
            from html.parser import HTMLParser
            from io import StringIO

            class _HTMLStripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._text = StringIO()
                def handle_data(self, d):
                    self._text.write(d)
                def get_text(self):
                    return self._text.getvalue()

            stripper = _HTMLStripper()
            stripper.feed(body_html)
            text = stripper.get_text().strip()

            if not text:
                continue

            doc_source = f"{source.name}/{title}"
            all_documents.append(Document(
                text=text,
                metadata={"source": doc_source, "title": title, "url": f"{base_url}/wiki/spaces/{space_key}/pages/{page.get('id', '')}"},
            ))

        # Handle pagination
        next_link = data.get("_links", {}).get("next")
        if next_link:
            url = f"{base_url}{next_link}" if next_link.startswith("/") else next_link
            params = None  # params are embedded in the next URL
        else:
            url = None

    if not all_documents:
        logger.info(f"Confluence source '{source.name}': no pages found")
        return

    all_documents = extract_keywords_for_metadata(all_documents)

    # Delete old and re-ingest
    if project.vector:
        try:
            existing_sources = project.vector.list()
            for src in existing_sources:
                if src == source.name or src.startswith(f"{source.name}/"):
                    project.vector.delete_source(src)
        except Exception as e:
            logger.warning(f"Failed to delete old Confluence chunks for '{source.name}': {e}")

    n_chunks = index_documents_classic(project, all_documents, source.splitter, source.chunks)
    project.vector.save()
    logger.info(f"Confluence source '{source.name}' synced: {len(all_documents)} pages, {n_chunks} chunks")


def _sync_sharepoint(project, source, db):
    """Sync files from a SharePoint Online document library via Microsoft Graph API."""
    import requests as req
    from llama_index.core.schema import Document
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata
    from modules.loaders import find_file_loader

    tenant_id = source.sharepoint_tenant_id
    client_id = source.sharepoint_client_id
    client_secret = source.sharepoint_client_secret
    site_name = source.sharepoint_site_name
    folder_path = source.sharepoint_folder

    if not tenant_id or not client_id or not client_secret or not site_name:
        raise ValueError("SharePoint source requires tenant_id, client_id, client_secret, and site_name")

    logger.info(f"Syncing SharePoint source '{source.name}': site={site_name}")

    # Acquire OAuth2 token via client credentials flow
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_resp = req.post(token_url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }, timeout=15)
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    graph = "https://graph.microsoft.com/v1.0"

    # Resolve site ID from site name
    site_resp = req.get(f"{graph}/sites?search={site_name}", headers=headers, timeout=15)
    site_resp.raise_for_status()
    sites = site_resp.json().get("value", [])
    if not sites:
        raise ValueError(f"SharePoint site '{site_name}' not found")
    site_id = sites[0]["id"]

    # Get the default drive (document library)
    drive_resp = req.get(f"{graph}/sites/{site_id}/drive", headers=headers, timeout=15)
    drive_resp.raise_for_status()
    drive_id = drive_resp.json()["id"]

    # List files — optionally filtered to a folder
    if folder_path:
        folder_path = folder_path.strip("/")
        list_url = f"{graph}/drives/{drive_id}/root:/{folder_path}:/children"
    else:
        list_url = f"{graph}/drives/{drive_id}/root/children"

    all_documents = []
    url = list_url

    while url:
        resp = req.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("value", []):
            # Skip folders
            if "folder" in item:
                continue

            name = item.get("name", "")
            ext = os.path.splitext(name)[1].lower()
            loader_cls = find_file_loader(ext)
            if loader_cls is None:
                logger.debug(f"Skipping unsupported file type: {name}")
                continue

            # Download file content
            download_url = item.get("@microsoft.graph.downloadUrl")
            if not download_url:
                continue

            file_resp = req.get(download_url, timeout=60)
            file_resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_resp.content)
                tmp_path = tmp.name

            try:
                loader = loader_cls()
                docs = loader.load_data(file=tmp_path)
                doc_source = f"{source.name}/{name}"
                for doc in docs:
                    doc.metadata["source"] = doc_source
                docs = extract_keywords_for_metadata(docs)
                all_documents.extend(docs)
            finally:
                os.unlink(tmp_path)

        # Pagination
        url = data.get("@odata.nextLink")

    if not all_documents:
        logger.info(f"SharePoint source '{source.name}': no documents found")
        return

    # Delete old and re-ingest
    if project.vector:
        try:
            existing_sources = project.vector.list()
            for src in existing_sources:
                if src == source.name or src.startswith(f"{source.name}/"):
                    project.vector.delete_source(src)
        except Exception as e:
            logger.warning(f"Failed to delete old SharePoint chunks for '{source.name}': {e}")

    n_chunks = index_documents_classic(project, all_documents, source.splitter, source.chunks)
    project.vector.save()
    logger.info(f"SharePoint source '{source.name}' synced: {len(all_documents)} files, {n_chunks} chunks")


def _sync_gdrive(project, source, db):
    """Sync files from a Google Drive folder via service account."""
    import requests as req
    from llama_index.core.schema import Document
    from restai.vectordb.tools import index_documents_classic, extract_keywords_for_metadata
    from modules.loaders import find_file_loader

    sa_json = source.gdrive_service_account_json
    folder_id = source.gdrive_folder_id

    if not sa_json or not folder_id:
        raise ValueError("Google Drive source requires service_account_json and folder_id")

    logger.info(f"Syncing Google Drive source '{source.name}': folder={folder_id}")

    # Parse service account JSON and get access token via JWT
    import json as _json
    import time as _time
    import jwt as _jwt
    import hashlib

    sa = _json.loads(sa_json)
    now = int(_time.time())
    payload = {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/drive.readonly",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    signed_jwt = _jwt.encode(payload, sa["private_key"], algorithm="RS256")

    token_resp = req.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": signed_jwt,
    }, timeout=15)
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}

    # List files in folder (non-trashed, not folders)
    all_documents = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"

    while True:
        params = {
            "q": query,
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 100,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = req.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("files", []):
            name = item["name"]
            mime = item["mimeType"]
            file_id = item["id"]

            # Handle Google Docs/Sheets/Slides by exporting
            export_mime = None
            export_ext = None
            if mime == "application/vnd.google-apps.document":
                export_mime = "text/plain"
                export_ext = ".txt"
            elif mime == "application/vnd.google-apps.spreadsheet":
                export_mime = "text/csv"
                export_ext = ".csv"
            elif mime == "application/vnd.google-apps.presentation":
                export_mime = "text/plain"
                export_ext = ".txt"
            else:
                ext = os.path.splitext(name)[1].lower()
                if not find_file_loader(ext):
                    logger.debug(f"Skipping unsupported file: {name}")
                    continue
                export_ext = ext

            # Download or export
            if export_mime:
                dl_resp = req.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    headers=headers, params={"mimeType": export_mime}, timeout=60,
                )
            else:
                dl_resp = req.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                    headers=headers, timeout=60,
                )
            dl_resp.raise_for_status()

            # For exported text, create Document directly
            if export_mime and export_mime.startswith("text/"):
                text = dl_resp.text.strip()
                if text:
                    doc_source = f"{source.name}/{name}"
                    all_documents.append(Document(
                        text=text,
                        metadata={"source": doc_source, "title": name},
                    ))
                continue

            # For binary files, use file loaders
            loader_cls = find_file_loader(export_ext)
            if not loader_cls:
                continue

            with tempfile.NamedTemporaryFile(suffix=export_ext, delete=False) as tmp:
                tmp.write(dl_resp.content)
                tmp_path = tmp.name

            try:
                loader = loader_cls()
                docs = loader.load_data(file=tmp_path)
                doc_source = f"{source.name}/{name}"
                for doc in docs:
                    doc.metadata["source"] = doc_source
                all_documents.extend(docs)
            finally:
                os.unlink(tmp_path)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if not all_documents:
        logger.info(f"Google Drive source '{source.name}': no documents found")
        return

    all_documents = extract_keywords_for_metadata(all_documents)

    # Delete old and re-ingest
    if project.vector:
        try:
            existing_sources = project.vector.list()
            for src in existing_sources:
                if src == source.name or src.startswith(f"{source.name}/"):
                    project.vector.delete_source(src)
        except Exception as e:
            logger.warning(f"Failed to delete old Google Drive chunks for '{source.name}': {e}")

    n_chunks = index_documents_classic(project, all_documents, source.splitter, source.chunks)
    project.vector.save()
    logger.info(f"Google Drive source '{source.name}' synced: {len(all_documents)} files, {n_chunks} chunks")


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
