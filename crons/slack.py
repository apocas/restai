#!/usr/bin/env python3
"""Slack Poller — cron-friendly script.

Polls Slack for new messages on all projects with a slack_bot_token configured,
processes each message through the project's chat pipeline, sends responses, then exits.

Usage:
    uv run python crons/slack.py
"""

import asyncio
import inspect
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.slack")

from restai import config
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.models.databasemodels import ProjectDatabase
from restai.brain import Brain


def main():
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    from restai.cron_log import CronLogger
    cron = CronLogger("slack")
    processed = 0

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        logger.error("slack_sdk package not installed")
        cron.error("slack_sdk package not installed")
        cron.finish()
        return

    try:
        from restai.utils.crypto import decrypt_field

        projects = db.db.query(ProjectDatabase).all()

        for proj in projects:
            opts = json.loads(proj.options) if proj.options else {}
            # `slack_bot_token` is in PROJECT_SENSITIVE_KEYS — stored as
            # `$ENC$<ciphertext>` at rest. decrypt_field is a no-op for
            # legacy plaintext rows.
            bot_token = decrypt_field(opts.get("slack_bot_token") or "")
            if not bot_token:
                continue

            try:
                client = WebClient(token=bot_token)
                auth = client.auth_test()
                bot_user_id = auth["user_id"]
            except SlackApiError as e:
                logger.warning("Slack auth failed for project %s: %s", proj.name, e)
                cron.warning(f"Slack auth failed for {proj.name}: {e}")
                continue

            last_ts = opts.get("slack_last_ts", "0")

            # Get conversations the bot is a member of (DMs, channels, group DMs)
            try:
                convos = _get_bot_conversations(client)
            except SlackApiError as e:
                logger.warning("Failed to list conversations for project %s: %s", proj.name, e)
                cron.warning(f"Failed to list conversations for {proj.name}: {e}")
                continue

            newest_ts = last_ts

            for channel_id in convos:
                try:
                    result = client.conversations_history(
                        channel=channel_id,
                        oldest=last_ts,
                        limit=50,
                    )
                except SlackApiError as e:
                    logger.debug("Cannot read channel %s: %s", channel_id, e)
                    continue

                messages = result.get("messages", [])
                # Process oldest first
                for msg in reversed(messages):
                    # Skip bot's own messages, subtypes (joins, etc.), and bot messages
                    if msg.get("user") == bot_user_id:
                        continue
                    if msg.get("subtype") or msg.get("bot_id"):
                        continue

                    text = msg.get("text", "").strip()
                    if not text:
                        continue

                    msg_ts = msg.get("ts", "0")
                    if msg_ts > newest_ts:
                        newest_ts = msg_ts

                    try:
                        response = asyncio.run(
                            _process_message(brain, db, proj.id, text, channel_id)
                        )
                        if response:
                            client.chat_postMessage(
                                channel=channel_id,
                                text=response,
                                thread_ts=msg.get("ts") if msg.get("thread_ts") is None else msg.get("thread_ts"),
                            )
                        processed += 1
                    except Exception as e:
                        logger.error("Error processing Slack message for project %s: %s", proj.name, e)
                        cron.error(f"Error processing message for {proj.name}: {e}")

            # Update last_ts so we don't reprocess
            if newest_ts > last_ts:
                _update_slack_ts(db, proj.id, newest_ts)

        if processed:
            cron.info(f"Processed {processed} Slack message(s)")
        cron.finish(items_processed=processed)
    except Exception as e:
        cron.error(f"Slack poller crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()
    finally:
        db.db.close()


def _get_bot_conversations(client):
    """Get all conversation IDs the bot is a member of."""
    channel_ids = []
    cursor = None

    while True:
        kwargs = {"types": "im,mpim,public_channel,private_channel", "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor

        result = client.conversations_list(**kwargs)
        for ch in result.get("channels", []):
            if ch.get("is_member", False) or ch.get("is_im", False):
                channel_ids.append(ch["id"])

        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return channel_ids


def _update_slack_ts(db, project_id, ts):
    """Persist the latest processed message timestamp."""
    proj_db = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == project_id).first()
    if proj_db:
        opts = json.loads(proj_db.options) if proj_db.options else {}
        opts["slack_last_ts"] = ts
        proj_db.options = json.dumps(opts)
        db.db.commit()


async def _process_message(brain, db, project_id, text, channel_id):
    from restai.models.models import ChatModel, User
    from restai.helper import chat_main
    from fastapi import BackgroundTasks

    project = brain.find_project(project_id, db)
    if not project:
        return None

    chat_input = ChatModel(question=text, id=f"slack_{channel_id}")

    user_db = db.get_user_by_username("admin")
    if not user_db:
        return None
    user = User.model_validate(user_db)

    background_tasks = BackgroundTasks()

    class _FakeRequest:
        app = type("App", (), {"state": type("State", (), {"brain": brain})()})()

    result = await chat_main(
        _FakeRequest(), brain, project, chat_input, user, db, background_tasks,
    )

    for task in background_tasks.tasks:
        try:
            if inspect.iscoroutinefunction(task.func):
                await task.func(*task.args, **task.kwargs)
            else:
                task.func(*task.args, **task.kwargs)
        except Exception:
            pass

    if isinstance(result, dict):
        return result.get("answer", "")
    return None


if __name__ == "__main__":
    main()
