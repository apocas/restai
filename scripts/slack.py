#!/usr/bin/env python3
"""Slack Bot Daemon — long-running process.

Maintains Socket Mode connections for all projects with Slack tokens configured.
Run as a separate process (systemd, supervisor, or screen/tmux), NOT as a cron job.

Usage:
    uv run python scripts/slack.py

Systemd example:
    [Service]
    WorkingDirectory=/path/to/restai
    ExecStart=/path/to/restai/.venv/bin/python scripts/slack.py
    Restart=always
"""

import asyncio
import json
import logging
import signal
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.slack")

from restai import config
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.models.databasemodels import ProjectDatabase
from restai.brain import Brain


_stop = threading.Event()


def main():
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    projects = db.db.query(ProjectDatabase).all()
    bots = []

    for proj in projects:
        opts = json.loads(proj.options) if proj.options else {}
        bot_token = opts.get("slack_bot_token")
        app_token = opts.get("slack_app_token")
        if not bot_token or not app_token:
            continue

        try:
            from restai.slack_bot import SlackBot
            bot = SlackBot(proj.id, bot_token, app_token, brain)
            bot.start()
            bots.append(bot)
            logger.info(f"Slack bot started for project {proj.name} (ID {proj.id})")
        except Exception as e:
            logger.error(f"Failed to start Slack bot for project {proj.id}: {e}")

    db.db.close()

    if not bots:
        logger.info("No Slack bots configured. Exiting.")
        return

    logger.info(f"Running {len(bots)} Slack bot(s). Press Ctrl+C to stop.")

    # Handle graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        _stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    _stop.wait()

    for bot in bots:
        bot.stop()

    logger.info("All Slack bots stopped.")


if __name__ == "__main__":
    main()
