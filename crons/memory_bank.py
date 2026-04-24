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
import time
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.memory_bank_cron")

from restai import config  # noqa: F401  — side effect: env loaded
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.brain import Brain
from restai.cron_log import CronLogger
from restai import memory_bank


# Hard cap on how many conversations one cron tick will summarize. With
# the System LLM being remote (Ollama / OpenAI / etc.), each summary is
# ~1-5s best case and up to ~120s worst case (Ollama's request timeout).
# At 25 chats × worst case that's still under the runner's 600s job
# timeout — meaning the cron always reports back instead of getting
# silently killed and looking "stuck" to the admin. Backlog beyond this
# rolls over to subsequent ticks.
MAX_CHATS_PER_TICK = 25


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
        # Per-tick global budget. Once exhausted we still keep iterating
        # projects to run their compression step (cheap, no LLM calls
        # unless a project is over budget) — only the summarizer loop is
        # gated. Remaining chats roll into the next minute's run.
        budget_left = MAX_CHATS_PER_TICK
        deferred_total = 0

        import json
        for proj in memory_bank.list_enabled_projects(db):
            try:
                opts = json.loads(proj.options) if proj.options else {}
            except Exception:
                opts = {}
            max_tokens = int(opts.get("memory_bank_max_tokens") or 2000)

            chat_ids = memory_bank.chat_ids_needing_refresh(db, proj.id)
            if chat_ids:
                # Cap to whatever budget remains for this tick. Anything over
                # gets logged so the admin can see the backlog draining over
                # subsequent ticks instead of wondering why nothing changes.
                to_process = chat_ids[:budget_left]
                deferred = len(chat_ids) - len(to_process)
                if deferred > 0:
                    deferred_total += deferred
                    logger.info(
                        "memory_bank: project=%s — processing %d/%d chats this tick, %d deferred to next run",
                        proj.id, len(to_process), len(chat_ids), deferred,
                    )
                else:
                    logger.info(
                        "memory_bank: project=%s — processing %d chat(s) this tick",
                        proj.id, len(to_process),
                    )
                for idx, chat_id in enumerate(to_process, 1):
                    t0 = time.monotonic()
                    try:
                        written = memory_bank.summarize_conversation(brain, db, proj.id, chat_id)
                        if written is not None:
                            summarized += 1
                            elapsed = time.monotonic() - t0
                            logger.info(
                                "memory_bank: project=%s chat=%s summarized in %.1fs (%d/%d)",
                                proj.id, chat_id[:12], elapsed, idx, len(to_process),
                            )
                    except Exception as e:
                        logger.warning(
                            "memory_bank: summarize_conversation failed (project=%s chat=%s): %s",
                            proj.id, chat_id, e,
                        )
                        db.db.rollback()
                    budget_left -= 1
                    if budget_left <= 0:
                        deferred_total += len(chat_ids) - idx
                        break

            try:
                memory_bank.compress_entries(brain, db, proj.id, max_tokens)
                compressed_projects += 1
            except Exception as e:
                logger.warning(
                    "memory_bank: compress_entries failed (project=%s): %s", proj.id, e,
                )
                db.db.rollback()

            if budget_left <= 0:
                # Don't summarize more chats this tick, but we already
                # ran compression for this project. Keep iterating
                # remaining projects to record their deferred totals
                # and run their compression (which is cheap).
                continue

        msg = f"Summarized {summarized} conversation(s); compressed {compressed_projects} project(s)."
        if deferred_total > 0:
            msg += f" {deferred_total} chat(s) deferred to next tick."
        cron.info(msg)
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
