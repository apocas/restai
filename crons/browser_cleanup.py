#!/usr/bin/env python3
"""Browser container cleanup — removes agentic-browser containers idle
longer than `browser_timeout` seconds. Mirrors `crons/docker_cleanup.py`
for the shell-terminal sandbox.

Usage:
    uv run python crons/browser_cleanup.py
"""
import logging
import time
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.browser_cleanup")

from restai import config  # noqa: F401 — env load side effect
from restai.settings import ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.cron_log import CronLogger


def main():
    ensure_settings_table(db_engine)

    cron = CronLogger("browser_cleanup")
    removed = 0

    if not getattr(config, "BROWSER_ENABLED", False):
        cron.info("Agentic Browser disabled; cleanup is a no-op.")
        cron.finish()
        return

    docker_url = (getattr(config, "DOCKER_URL", "") or "").strip()
    if not docker_url:
        cron.warning("DOCKER_URL not set; cannot enumerate browser containers.")
        cron.finish()
        return

    idle_timeout = int(getattr(config, "BROWSER_TIMEOUT", 900))

    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url=docker_url)
        now = time.time()

        containers = client.containers.list(
            filters={"label": ["restai.browser_managed=true"]},
        )
        for c in containers:
            try:
                created_at = int(c.labels.get("restai.created_at") or "0")
            except Exception:
                created_at = 0
            age = now - created_at if created_at else 0
            if age > idle_timeout:
                try:
                    c.stop(timeout=3)
                    removed += 1
                    logger.info("Removed idle browser container %s (age=%ds)", c.short_id, age)
                except Exception as e:
                    logger.warning("Failed to stop %s: %s", c.short_id, e)

        if removed:
            cron.info(f"Removed {removed} idle browser container(s)")
        cron.finish(items_processed=removed)
    except Exception as e:
        cron.error(f"Browser cleanup crashed: {e}", details=traceback.format_exc())
        cron.finish()


if __name__ == "__main__":
    main()
