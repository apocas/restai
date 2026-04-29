#!/usr/bin/env python3
"""App-Builder preview container cleanup.

Mirrors `crons/browser_cleanup.py`: enumerates `restai.app_managed=true`
containers and stops anything older than `app_docker_idle_timeout`.

Eviction is by container age (the `restai.created_at` label) rather than
last-activity. In-process `last_activity` would be more accurate but it
isn't visible across workers; container age is a safe upper bound — if a
container has been around for 30 minutes without anyone restarting it,
it's been idle long enough to recycle. Restarts don't count: the
`restart` endpoint creates a fresh container with a new `created_at`.

Usage:
    uv run python crons/app_cleanup.py
"""
import logging
import time
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.app_cleanup")

from restai import config  # noqa: F401 — env load side effect
from restai.settings import ensure_settings_table
from restai.database import engine as db_engine
from restai.cron_log import CronLogger


def main():
    ensure_settings_table(db_engine)

    cron = CronLogger("app_cleanup")
    removed = 0

    if not getattr(config, "APP_DOCKER_ENABLED", False):
        cron.info("App Builder runtime disabled; cleanup is a no-op.")
        cron.finish()
        return

    docker_url = (getattr(config, "DOCKER_URL", "") or "").strip()
    if not docker_url:
        cron.warning("DOCKER_URL not set; cannot enumerate app containers.")
        cron.finish()
        return

    if docker_url.startswith("tcp://"):
        cron.warning("App Builder requires a local Docker socket; remote daemon detected — skipping.")
        cron.finish()
        return

    idle_timeout = int(getattr(config, "APP_DOCKER_IDLE_TIMEOUT", 1800))

    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url=docker_url)
        now = time.time()

        containers = client.containers.list(
            filters={"label": ["restai.app_managed=true"]},
        )
        for c in containers:
            try:
                created_at = int(c.labels.get("restai.created_at") or "0")
            except Exception:
                created_at = 0
            age = now - created_at if created_at else 0
            if age > idle_timeout:
                project_id = c.labels.get("restai.app_project_id", "?")
                try:
                    c.stop(timeout=3)
                    removed += 1
                    logger.info("Removed idle app container %s (project=%s, age=%ds)", c.short_id, project_id, age)
                except Exception as e:
                    logger.warning("Failed to stop %s: %s", c.short_id, e)

        if removed:
            cron.info(f"Removed {removed} idle app container(s)")
        cron.finish(items_processed=removed)
    except Exception as e:
        cron.error(f"App cleanup crashed: {e}", details=traceback.format_exc())
        cron.finish()


if __name__ == "__main__":
    main()
