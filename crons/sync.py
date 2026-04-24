#!/usr/bin/env python3
"""Knowledge Base Sync — cron-friendly script.

Checks all projects with sync enabled, syncs sources whose interval has elapsed, then exits.

Usage:
    uv run python crons/sync.py
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
    from restai.cron_log import CronLogger
    cron = CronLogger("sync")

    # Initialize settings from DB
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()
    synced_count = 0

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
                    from restai.utils.crypto import _decrypt_sync_source

                    # Source dict comes straight out of the project's JSON
                    # options, where SYNC_SOURCE_SENSITIVE_KEYS values are
                    # stored encrypted (`$ENC$...`). Decrypt before building
                    # the SyncSource or auth against S3 / Confluence /
                    # SharePoint / Google Drive will fail.
                    src = SyncSource(**_decrypt_sync_source(source))
                    logger.info(f"Syncing source '{src.name}' for project {proj.name} (ID {proj.id})")
                    _sync_source(project, src, db, brain)
                    _update_last_sync(db, proj.id, i)
                    synced_any = True
                    synced_count += 1
                    cron.info(f"Synced '{src.name}' for {proj.name}")
                    try:
                        from restai.webhooks import emit_event_for_project_id
                        emit_event_for_project_id(proj.id, "sync_completed", {
                            "source": src.name, "status": "ok",
                        })
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Failed to sync source '{source.get('name')}' for project {proj.id}: {e}")
                    cron.error(f"Failed '{source.get('name')}' for {proj.name}: {e}")
                    try:
                        from restai.webhooks import emit_event_for_project_id
                        emit_event_for_project_id(proj.id, "sync_completed", {
                            "source": source.get("name"), "status": "error", "error": str(e),
                        })
                    except Exception:
                        pass

        if not synced_any:
            logger.debug("No sources due for sync")

        cron.finish(items_processed=synced_count)
    except Exception as e:
        cron.error(f"Sync crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()
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
