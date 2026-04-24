#!/usr/bin/env python3
"""Project Routines Runner — cron-friendly script.

Checks all enabled routines, fires those whose schedule interval has elapsed, then exits.

Usage:
    uv run python crons/routines.py
"""

import asyncio
import inspect
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.routines")

from restai import config
from restai.settings import load_settings, ensure_settings_table
from restai.database import get_db_wrapper, engine as db_engine
from restai.brain import Brain


async def _fire_routine(brain, db, routine, project):
    """Execute a routine's message through the project's question pipeline."""
    from fastapi import BackgroundTasks
    from restai.helper import question_main
    from restai.models.models import QuestionModel, User

    # Use project creator as the user
    creator = db.get_user_by_id(project.props.creator) if project.props.creator else None
    if creator is None:
        # Fallback to admin
        creator = db.get_user_by_username("admin")
    if creator is None:
        logger.error("No user found to run routine %d", routine.id)
        return None

    user = User.model_validate(creator)

    q = QuestionModel(question=routine.message)
    background_tasks = BackgroundTasks()

    # Create a minimal request-like object
    class _FakeRequest:
        app = type("App", (), {"state": type("State", (), {"brain": brain})()})()

    result = await question_main(
        _FakeRequest(), brain, project, q, user, db, background_tasks,
    )

    # Execute queued background tasks (inference logging)
    for task in background_tasks.tasks:
        try:
            if inspect.iscoroutinefunction(task.func):
                await task.func(*task.args, **task.kwargs)
            else:
                task.func(*task.args, **task.kwargs)
        except Exception:
            pass

    return result


async def _run():
    ensure_settings_table(db_engine)
    settings_db = get_db_wrapper()
    load_settings(settings_db)
    settings_db.db.close()

    brain = Brain(lightweight=True)
    db = get_db_wrapper()

    from restai.cron_log import CronLogger
    cron = CronLogger("routines")

    try:
        routines = db.get_all_enabled_routines()
        if not routines:
            logger.debug("No enabled routines found")
            cron.finish()
            return

        now = datetime.now(timezone.utc)
        fired = 0

        for routine in routines:
            if routine.last_run:
                last = routine.last_run
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed_minutes = (now - last).total_seconds() / 60
                if elapsed_minutes < routine.schedule_minutes:
                    continue

            project = brain.find_project(routine.project_id, db)
            if not project:
                logger.warning("Routine %d: project %d not found, skipping", routine.id, routine.project_id)
                cron.warning(f"Routine '{routine.name}': project {routine.project_id} not found")
                continue

            logger.info("Firing routine '%s' (id=%d) for project '%s'", routine.name, routine.id, project.props.name)

            import time as _time
            start = _time.monotonic()
            try:
                result = await asyncio.wait_for(
                    _fire_routine(brain, db, routine, project), timeout=300,
                )
                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                duration_ms = int((_time.monotonic() - start) * 1000)

                routine.last_run = datetime.now(timezone.utc)
                routine.last_result = answer[:2000] if answer else None
                routine.updated_at = datetime.now(timezone.utc)
                db.db.commit()

                # Append a success row to the execution log.
                try:
                    from restai.models.databasemodels import RoutineExecutionLogDatabase
                    db.db.add(RoutineExecutionLogDatabase(
                        routine_id=routine.id, project_id=routine.project_id,
                        status="ok", result=(answer[:2000] if answer else None),
                        duration_ms=duration_ms, manual=False,
                        created_at=datetime.now(timezone.utc),
                    ))
                    db.db.commit()
                except Exception:
                    logger.exception("Failed to write routine execution log row")

                fired += 1
                cron.info(f"Fired '{routine.name}' for {project.props.name}")
            except Exception as e:
                duration_ms = int((_time.monotonic() - start) * 1000)
                logger.error("Routine '%s' failed: %s", routine.name, e)
                cron.error(f"Routine '{routine.name}' failed: {e}")
                try:
                    db.db.rollback()
                    routine.last_run = datetime.now(timezone.utc)
                    routine.last_result = f"ERROR: {e}"
                    routine.updated_at = datetime.now(timezone.utc)
                    db.db.commit()
                except Exception:
                    logger.warning("Failed to update routine '%s' after error", routine.name)
                # Error row (best-effort, always runs).
                try:
                    from restai.models.databasemodels import RoutineExecutionLogDatabase
                    db.db.add(RoutineExecutionLogDatabase(
                        routine_id=routine.id, project_id=routine.project_id,
                        status="error", result=str(e)[:2000],
                        duration_ms=duration_ms, manual=False,
                        created_at=datetime.now(timezone.utc),
                    ))
                    db.db.commit()
                except Exception:
                    logger.exception("Failed to write routine execution log row after error")
                try:
                    from restai.webhooks import emit_event_for_project_id
                    emit_event_for_project_id(project.props.id, "routine_failed", {
                        "routine_id": routine.id,
                        "routine_name": routine.name,
                        "error": str(e)[:500],
                    })
                except Exception:
                    pass

        cron.finish(items_processed=fired)
    except Exception as e:
        cron.error(f"Routines runner crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()
    finally:
        db.db.close()


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
