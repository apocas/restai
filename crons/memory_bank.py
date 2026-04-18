#!/usr/bin/env python3
"""Project Memory Bank Runner — cron-friendly script.

For every agent project with `memory_bank_enabled=True`, summarizes any
conversations that have new activity since the last summarization and are
now idle, then runs the compression ladder so the bank stays within each
project's `memory_bank_max_tokens` budget.

Usage:
    uv run python crons/memory_bank.py
"""

import logging
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.memory_bank_cron")

from restai import config  # noqa: F401  — side effect: env loaded
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.brain import Brain
from restai.cron_log import CronLogger
from restai import memory_bank


def _run():
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()
    cron = CronLogger("memory_bank")

    if brain.get_system_llm(db) is None:
        # No System LLM configured — nothing this cron can do. Log a single
        # warning so the admin sees why the bank stays empty, then exit.
        cron.warning("No System LLM configured; memory bank cron is a no-op until one is set.")
        cron.finish()
        db.db.close()
        return

    try:
        summarized = 0
        compressed_projects = 0

        import json
        for proj in memory_bank.list_enabled_projects(db):
            try:
                opts = json.loads(proj.options) if proj.options else {}
            except Exception:
                opts = {}
            max_tokens = int(opts.get("memory_bank_max_tokens") or 2000)

            chat_ids = memory_bank.chat_ids_needing_refresh(db, proj.id)
            for chat_id in chat_ids:
                try:
                    written = memory_bank.summarize_conversation(brain, db, proj.id, chat_id)
                    if written is not None:
                        summarized += 1
                except Exception as e:
                    logger.warning(
                        "memory_bank: summarize_conversation failed (project=%s chat=%s): %s",
                        proj.id, chat_id, e,
                    )
                    db.db.rollback()

            try:
                memory_bank.compress_entries(brain, db, proj.id, max_tokens)
                compressed_projects += 1
            except Exception as e:
                logger.warning(
                    "memory_bank: compress_entries failed (project=%s): %s", proj.id, e,
                )
                db.db.rollback()

        cron.info(
            f"Summarized {summarized} conversation(s); compressed {compressed_projects} project(s)."
        )
        cron.finish(items_processed=summarized)
    except Exception as e:
        cron.error(f"Memory bank runner crashed: {e}", details=traceback.format_exc())
        cron.finish()
    finally:
        db.db.close()


def main():
    _run()


if __name__ == "__main__":
    main()
