#!/usr/bin/env python3
"""Telegram Poller — cron-friendly script.

Polls Telegram for pending updates on all projects with a telegram_token configured,
processes each message through the project's chat pipeline, sends responses, then exits.

Usage:
    uv run python crons/telegram.py
"""

import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.telegram")

from restai import config
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.models.databasemodels import ProjectDatabase
from restai.brain import Brain
from restai.telegram import get_updates, send_message


def main():
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    from restai.cron_log import CronLogger
    cron = CronLogger("telegram")
    processed = 0

    try:
        projects = db.db.query(ProjectDatabase).all()

        for proj in projects:
            opts = json.loads(proj.options) if proj.options else {}
            token = opts.get("telegram_token")
            if not token:
                continue

            # Poll with short timeout (1s) — get pending updates only
            updates = get_updates(token, offset=0, timeout=1)
            if updates is None:
                logger.warning(f"Telegram API error for project {proj.id}")
                cron.warning(f"Telegram API error for project {proj.name}")
                continue
            if not updates:
                continue

            logger.info(f"Processing {len(updates)} Telegram updates for project {proj.name}")

            for update in updates:
                message = update.get("message")
                if not message:
                    continue

                text = message.get("text")
                chat_id = message.get("chat", {}).get("id")
                if not text or not chat_id:
                    continue

                try:
                    send_typing(token, chat_id)
                    response = asyncio.run(_process_message(brain, db, proj.id, text, chat_id))
                    if response:
                        send_message(token, chat_id, response)
                    processed += 1
                except Exception as e:
                    logger.error(f"Error processing Telegram message for project {proj.id}: {e}")
                    cron.error(f"Error processing message for {proj.name}: {e}")

            # Acknowledge processed updates
            if updates:
                last_offset = updates[-1]["update_id"] + 1
                get_updates(token, offset=last_offset, timeout=1)

        if processed:
            cron.info(f"Processed {processed} Telegram message(s)")
        cron.finish(items_processed=processed)
    except Exception as e:
        cron.error(f"Telegram poller crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()
    finally:
        db.db.close()


async def _process_message(brain, db, project_id, text, chat_id):
    from restai.models.models import ChatModel, User
    from restai.helper import chat_main
    from fastapi import BackgroundTasks

    project = brain.find_project(project_id, db)
    if not project:
        return None

    chat_input = ChatModel(question=text, id=f"telegram_{chat_id}")

    # Create a minimal user for the chat
    user_db = db.get_user_by_username("admin")
    if not user_db:
        return None
    user = User.model_validate(user_db)

    background_tasks = BackgroundTasks()
    result = await chat_main(project, chat_input, user, db, brain, background_tasks)
    await background_tasks()

    if isinstance(result, dict):
        return result.get("answer", "")
    return None


def send_typing(token, chat_id):
    """Send typing indicator to Telegram chat."""
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
