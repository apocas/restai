#!/usr/bin/env python3
"""Browser container cleanup — removes agentic-browser containers idle
longer than `browser_timeout` seconds. Activity-aware (mirrors
`crons/docker_cleanup.py`): reads `last_activity` from the
`browser_chat_activity` table (UPSERTed on every `runtime.call()`),
falls back to container creation age only for orphans without a
heartbeat row.

Also skips eviction when Playwright is mid-request — even if the
heartbeat looks stale, an in-flight HTTP call to the micro-server
means the agent is actively using the container.

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
from restai.database import open_db_wrapper, engine as db_engine
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

        if not containers:
            cron.finish()
            return

        # DB-backed heartbeat: `runtime.call()` UPSERTs on every browser
        # tool call. Reading from here gives true idle time across all
        # RESTai instances. Orphans (created before this table existed,
        # or by some other RESTai version) fall back to container age.
        from datetime import datetime, timezone
        from restai.models.databasemodels import BrowserChatActivityDatabase

        db = open_db_wrapper()
        try:
            rows = db.db.query(BrowserChatActivityDatabase).all()
            activity_by_chat = {r.chat_id: r.last_activity for r in rows}
        finally:
            db.db.close()

        def _has_inflight_exec(container) -> bool:
            """True when Docker reports any exec session still running on
            the container. The browser tools talk over HTTP to the
            micro-server (not via exec), so this mostly catches the
            install-time pip exec — but we keep it for symmetry with
            docker_cleanup."""
            try:
                container.reload()
                exec_ids = container.attrs.get("ExecIDs") or []
            except Exception:
                return False
            for exec_id in exec_ids:
                try:
                    info = client.api.exec_inspect(exec_id)
                    if info.get("Running"):
                        return True
                except Exception:
                    continue
            return False

        from restai.instance import get_instance_id
        my_instance = get_instance_id()

        for c in containers:
            labels = c.labels or {}
            chat_id = labels.get("restai.browser_chat_id", "unknown")

            # Multi-install isolation — see docker_cleanup for rationale.
            cont_iid = labels.get("restai.instance_id")
            if cont_iid and cont_iid != my_instance:
                continue

            last_activity = activity_by_chat.get(chat_id)
            if last_activity is not None:
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                idle = now - last_activity.timestamp()
                source = "db"
            else:
                try:
                    created_at = int(labels.get("restai.created_at") or "0")
                except Exception:
                    created_at = 0
                idle = (now - created_at) if created_at else 0
                source = "label-fallback"

            if idle > idle_timeout:
                if _has_inflight_exec(c):
                    logger.info(
                        "Skipping browser container %s (chat_id=%s, idle=%ds, src=%s) — exec in flight",
                        c.short_id, chat_id, int(idle), source,
                    )
                    continue
                try:
                    c.stop(timeout=3)
                    removed += 1
                    logger.info(
                        "Removed idle browser container %s (chat_id=%s, idle=%ds, src=%s)",
                        c.short_id, chat_id, int(idle), source,
                    )
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
