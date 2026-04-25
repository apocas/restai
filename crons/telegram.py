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
from restai.settings import ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.models.databasemodels import ProjectDatabase
from restai.brain import Brain
from restai.telegram import get_updates, send_message


def main():
    ensure_settings_table(db_engine)

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    from restai.cron_log import CronLogger
    cron = CronLogger("telegram")
    processed = 0

    try:
        from restai.utils.crypto import decrypt_field

        projects = db.db.query(ProjectDatabase).all()
        logger.info(f"Scanning {len(projects)} project(s) for Telegram tokens")

        enabled_count = 0

        for proj in projects:
            opts = json.loads(proj.options) if proj.options else {}
            token = decrypt_field(opts.get("telegram_token") or "")
            if not token:
                continue

            # Parse the per-project allowlist. Empty/missing = open to all
            # (legacy behavior). Tolerant of whitespace, trailing commas,
            # and stray non-numeric junk so an admin's typo doesn't lock
            # everyone out silently.
            allowed_raw = (opts.get("telegram_allowed_chat_ids") or "").strip()
            allowed_ids: set[int] = set()
            if allowed_raw:
                for piece in allowed_raw.replace(";", ",").split(","):
                    piece = piece.strip()
                    if not piece:
                        continue
                    try:
                        allowed_ids.add(int(piece))
                    except ValueError:
                        logger.warning(f"  ⚠ ignoring non-numeric chat id in allowlist: {piece!r}")

            enabled_count += 1
            logger.info(
                f"Polling project '{proj.name}' (id={proj.id})"
                + (f" — allowlist: {sorted(allowed_ids)}" if allowed_ids else " — allowlist: open")
            )

            updates, err = get_updates(token, offset=0, timeout=1)
            if err is not None:
                logger.warning(f"Telegram API error for project {proj.name} (id={proj.id}): {err}")
                continue
            if not updates:
                logger.info(f"No new Telegram updates for project '{proj.name}'")
                continue

            logger.info(f"Got {len(updates)} update(s) for project '{proj.name}'")

            for update in updates:
                message = update.get("message")
                if not message:
                    logger.info(f"Skipping non-message update: {list(update.keys())}")
                    continue

                text = message.get("text")
                chat_id = message.get("chat", {}).get("id")
                if not text or not chat_id:
                    logger.info(f"Skipping message with no text/chat_id (text={bool(text)}, chat_id={chat_id})")
                    continue

                from_user = message.get("from", {}).get("username") or message.get("from", {}).get("id")
                logger.info(f"  ← message from {from_user} (chat={chat_id}): {text[:200]!r}")

                # Built-in shortcut: replies with the chat_id so admins (or
                # would-be users) can grab their id without going through
                # the agent. Always allowed — it's the primary way an
                # unauthorized user finds out what id they need to ask the
                # admin to add to the allowlist.
                if text.strip().lower() in ("/chatid", "/myid"):
                    logger.info(f"  → replying with chat id {chat_id}")
                    try:
                        send_message(token, chat_id, f"Chat ID: {chat_id}")
                    except Exception as e:
                        logger.warning(f"Failed to reply to /chatid: {e}")
                    processed += 1
                    continue

                # Allowlist gate. Skip silently when the user isn't on the
                # list — well, almost silently: we send a one-line "not
                # authorized" reply so the user sees the bot is alive and
                # knows to ask the admin.
                if allowed_ids and chat_id not in allowed_ids:
                    logger.info(f"  ✗ chat {chat_id} not in allowlist for project '{proj.name}', rejecting")
                    try:
                        send_message(
                            token, chat_id,
                            "You are not authorized to use this bot. "
                            f"If you should be, ask the admin to add chat id {chat_id} to the project's allowlist.",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send unauthorized reply: {e}")
                    processed += 1
                    continue

                try:
                    send_typing(token, chat_id)
                    logger.info(f"  → invoking project '{proj.name}' agent for chat {chat_id}")
                    response = asyncio.run(_process_message(brain, db, proj.id, text, chat_id))
                    if response:
                        logger.info(f"  → sending response ({len(response)} chars): {response[:200]!r}")
                        send_message(token, chat_id, response)
                    else:
                        logger.warning(f"  ✗ project '{proj.name}' returned no response for chat {chat_id}")
                    processed += 1
                except Exception as e:
                    logger.exception(f"Error processing Telegram message for project {proj.name} (id={proj.id}): {e}")

            # Acknowledge processed updates so Telegram doesn't redeliver.
            if updates:
                last_offset = updates[-1]["update_id"] + 1
                logger.info(f"Acking {len(updates)} update(s) up to offset {last_offset}")
                _, ack_err = get_updates(token, offset=last_offset, timeout=1)
                if ack_err is not None:
                    logger.warning(f"Failed to ack updates for project {proj.name}: {ack_err}")

        logger.info(f"Tick complete: {enabled_count} project(s) with Telegram, {processed} message(s) processed")
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
        logger.warning(f"_process_message: project {project_id} not found")
        return None

    # `chat_id=f"telegram_{chat_id}"` keeps each Telegram chat as its own
    # conversation in the agent's memory store across cron ticks.
    chat_input = ChatModel(question=text, id=f"telegram_{chat_id}")

    user_db = db.get_user_by_username("admin")
    if not user_db:
        logger.warning("_process_message: no 'admin' user — cannot run agent")
        return None
    user = User.model_validate(user_db)

    background_tasks = BackgroundTasks()
    # chat_main signature: (request, brain, project, chat_input, user, db, background_tasks).
    # The Request slot is `_` (unused) inside chat_main, so None is fine.
    result = await chat_main(None, brain, project, chat_input, user, db, background_tasks)
    await background_tasks()

    if isinstance(result, dict):
        return result.get("answer", "")
    if result is None:
        logger.warning(f"_process_message: chat_main returned None for project {project_id}")
        return None
    logger.warning(f"_process_message: chat_main returned unexpected type {type(result).__name__}")
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
