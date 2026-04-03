#!/usr/bin/env python3
"""Knowledge Base Sync — cron-friendly script.

Checks all projects with sync enabled, syncs sources whose interval has elapsed, then exits.

Usage:
    uv run python scripts/sync.py

Cron example (every 5 minutes):
    */5 * * * * cd /path/to/restai && uv run python scripts/sync.py >> /var/log/restai-sync.log 2>&1
"""

import json
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.sync")

# Load config (reads .env)
from restai import config
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.models.databasemodels import ProjectDatabase
from restai.brain import Brain


def main():
    # Initialize settings from DB
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    try:
        projects = db.db.query(ProjectDatabase).all()
        synced_any = False

        for proj in projects:
            opts = json.loads(proj.options) if proj.options else {}
            if not opts.get("sync_enabled") or not opts.get("sync_sources"):
                continue

            sources = opts["sync_sources"]
            now = datetime.now(timezone.utc)

            for i, source in enumerate(sources):
                interval_minutes = source.get("sync_interval") or 60
                last_sync = source.get("last_sync")

                if last_sync:
                    try:
                        last = datetime.fromisoformat(last_sync)
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        elapsed = (now - last).total_seconds() / 60
                        if elapsed < interval_minutes:
                            continue
                    except (ValueError, TypeError):
                        pass

                # Load project with vector store
                project = brain.find_project(proj.id, db)
                if not project or project.props.type != "rag":
                    break

                # Mark as syncing before starting
                _update_last_sync(db, proj.id, i)

                try:
                    from restai.sync import _sync_source
                    from restai.models.models import SyncSource

                    src = SyncSource(**source)
                    logger.info(f"Syncing source '{src.name}' for project {proj.name} (ID {proj.id})")
                    _sync_source(project, src, db)
                    _update_last_sync(db, proj.id, i)
                    synced_any = True
                except Exception as e:
                    logger.error(f"Failed to sync source '{source.get('name')}' for project {proj.id}: {e}")

        if not synced_any:
            logger.debug("No sources due for sync")

    finally:
        db.db.close()


def _update_last_sync(db, project_id, source_index):
    proj_db = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == project_id).first()
    if proj_db:
        current_opts = json.loads(proj_db.options) if proj_db.options else {}
        src_list = current_opts.get("sync_sources", [])
        if source_index < len(src_list):
            src_list[source_index]["last_sync"] = datetime.now(timezone.utc).isoformat()
            current_opts["sync_sources"] = src_list
            proj_db.options = json.dumps(current_opts)
            db.db.commit()


if __name__ == "__main__":
    main()
