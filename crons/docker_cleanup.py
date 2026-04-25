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
from restai.database import get_db_wrapper, engine as db_engine


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

    # Find all RESTai-managed containers
    containers = client.containers.list(
        filters={"label": "restai.managed=true"},
    )

    if not containers:
        logger.debug("No managed containers found")
        cron.finish()
        return

    now = time.time()
    removed = 0

    for container in containers:
        labels = container.labels or {}
        created_at = labels.get("restai.created_at")
        chat_id = labels.get("restai.chat_id", "unknown")

        if not created_at:
            # No timestamp label — use container creation time
            try:
                container.reload()
                # Docker API returns created time as ISO string
                from datetime import datetime, timezone
                created_str = container.attrs.get("Created", "")
                if created_str:
                    dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age = now - dt.timestamp()
                else:
                    age = 0
            except Exception:
                age = 0
        else:
            age = now - int(created_at)

        if age > timeout:
            try:
                container.stop(timeout=5)
                logger.info(
                    "Removed idle container %s (chat_id=%s, idle=%ds)",
                    container.short_id, chat_id, int(age),
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
