#!/usr/bin/env python3
"""Docker Container Cleanup — cron-friendly script.

Removes RESTai-managed Docker containers that have been idle longer than
the configured timeout (default 15 minutes).

Usage:
    uv run python crons/docker_cleanup.py
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.docker_cleanup")

from restai import config
from restai.settings import ensure_settings_table
from restai.database import open_db_wrapper, engine as db_engine


def main():
    ensure_settings_table(db_engine)

    from restai.cron_log import CronLogger
    cron = CronLogger("docker_cleanup")

    docker_url = getattr(config, "DOCKER_URL", "") or ""
    if not docker_url.strip():
        logger.debug("Docker not configured, nothing to clean up")
        cron.finish()
        return

    timeout = int(getattr(config, "DOCKER_TIMEOUT", 900))

    try:
        import docker
    except ImportError:
        logger.error("docker package not installed")
        cron.error("docker package not installed")
        cron.finish()
        return

    try:
        client = docker.DockerClient(base_url=docker_url)
        client.ping()
    except Exception as e:
        logger.error("Cannot connect to Docker at %s: %s", docker_url, e)
        cron.error(f"Cannot connect to Docker: {e}")
        cron.finish()
        return

    containers = client.containers.list(
        filters={"label": "restai.managed=true"},
    )

    if not containers:
        logger.debug("No managed containers found")
        cron.finish()
        return

    # DB-backed heartbeat: DockerManager.exec_command UPSERTs
    # `docker_chat_activity` on every terminal/run/upload call across
    # all RESTai instances sharing this DB. Using the row's
    # `last_activity` here gives us TRUE idle time. Containers without
    # a row (orphans, pre-migration) fall back to the old label-based
    # creation-age check so the rollout is gradual.
    from datetime import datetime, timezone
    from restai.models.databasemodels import DockerChatActivityDatabase

    db = open_db_wrapper()
    try:
        rows = db.db.query(DockerChatActivityDatabase).all()
        activity_by_chat = {r.chat_id: r.last_activity for r in rows}
    finally:
        db.db.close()

    now = time.time()
    removed = 0

    def _age_from_creation_label(container, labels) -> float:
        created_at = labels.get("restai.created_at")
        if created_at:
            try:
                return now - int(created_at)
            except Exception:
                pass
        try:
            container.reload()
            created_str = container.attrs.get("Created", "")
            if created_str:
                dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                return now - dt.timestamp()
        except Exception:
            pass
        return 0.0

    for container in containers:
        labels = container.labels or {}
        chat_id = labels.get("restai.chat_id", "unknown")

        last_activity = activity_by_chat.get(chat_id)
        if last_activity is not None:
            # Treat naive timestamps as UTC — UPSERTs use datetime.now(tz=utc)
            # but SQLite returns them naive on read.
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            idle = now - last_activity.timestamp()
            source = "db"
        else:
            idle = _age_from_creation_label(container, labels)
            source = "label-fallback"

        if idle > timeout:
            try:
                container.stop(timeout=5)
                logger.info(
                    "Removed idle container %s (chat_id=%s, idle=%ds, src=%s)",
                    container.short_id, chat_id, int(idle), source,
                )
                removed += 1
            except Exception as e:
                logger.warning("Failed to remove container %s: %s", container.short_id, e)
                cron.warning(f"Failed to remove container {container.short_id}: {e}")

    if removed:
        logger.info("Cleaned up %d idle container(s)", removed)
        cron.info(f"Cleaned up {removed} idle container(s)")

    cron.finish(items_processed=removed)


if __name__ == "__main__":
    main()
